"""Routes pour les radionucléides."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from app.models.radionuclide import Radionuclide, RadionuclideCreate, RadionuclideUpdate, RadionuclideDB
from app.models.audit import AuditLogCreate
from app.repositories.radionuclide import RadionuclideRepository
from app.repositories.source import SourceRepository
from app.repositories.audit import AuditRepository
from app.models.source import is_archived
from app.security.permissions import (
    get_current_user,
    require_write_access,
    user_can_access_mn,
    check_source_mn_access,
)
from app.database import get_db

router = APIRouter(prefix="/radionuclides", tags=["radionuclides"])

@router.get("/", response_model=List[Radionuclide])
async def list_radionuclides(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = RadionuclideRepository(db)
    radionuclides = repo.get_all()
    if user_can_access_mn(current_user):
        return radionuclides
    # On masque les radionucléides rattachés à une source Matière Nucléaire.
    mn_source_ids = {s.id for s in SourceRepository(db).get_all() if s.matiere_nucleaire}
    return [r for r in radionuclides if r.source_id not in mn_source_ids]

@router.get("/{radionuclide_id}", response_model=Radionuclide)
async def get_radionuclide(
    radionuclide_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = RadionuclideRepository(db)
    radionuclide = repo.get_by_id(radionuclide_id)
    if not radionuclide:
        raise HTTPException(status_code=404, detail="Radionucléide non trouvé")
    source = SourceRepository(db).get_by_id(radionuclide.source_id)
    check_source_mn_access(source, current_user)
    return radionuclide

@router.post("/", response_model=Radionuclide)
async def create_radionuclide(
    radionuclide: RadionuclideCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    source = SourceRepository(db).get_by_id(radionuclide.source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucune source avec l'identifiant '{radionuclide.source_id}' : crée d'abord la source.",
        )
    check_source_mn_access(source, current_user)
    if is_archived(source):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"La source '{source.id}' est archivée (statut : {source.etat_utilisation.value}) : "
                "impossible d'y ajouter un nouveau radionucléide."
            ),
        )

    from app.services.matieres_nucleaires import normaliser_nom_radionuclide, est_matiere_nucleaire
    radionuclide.nom = normaliser_nom_radionuclide(radionuclide.nom)

    repo = RadionuclideRepository(db)
    audit_repo = AuditRepository(db)

    # Classement automatique en Matière Nucléaire (12/07/2026) : H-3, Li-6,
    # et tout isotope de thorium/uranium/plutonium classent leur source par
    # défaut, sans attendre que quelqu'un coche la case à la main. Volontai-
    # rement inconditionnel (même si l'utilisateur courant n'a pas
    # lui-même accès aux sources MN) : c'est justement le mécanisme de
    # protection qui doit se déclencher dans ce cas, pas être contourné.
    if est_matiere_nucleaire(radionuclide.nom) and not source.matiere_nucleaire:
        source.matiere_nucleaire = True
        db.commit()
        audit_repo.create(AuditLogCreate(
            utilisateur=current_user.username,
            action="UPDATE",
            table_modifiee="sources",
            id_source=source.id,
            champ_modifie="matiere_nucleaire",
            valeur_avant="False",
            valeur_apres="True (classement automatique, radionucléide " + radionuclide.nom + ")",
        ))
    db_radionuclide = repo.create(radionuclide)
    audit_repo.create(AuditLogCreate(
        utilisateur=current_user.username,
        action="CREATE",
        table_modifiee="radionuclides",
        id_source=radionuclide.source_id,
        valeur_apres=str(radionuclide.model_dump()),
    ))
    return db_radionuclide

@router.put("/{radionuclide_id}", response_model=Radionuclide)
async def update_radionuclide(
    radionuclide_id: int,
    radionuclide_update: RadionuclideUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = RadionuclideRepository(db)
    existing = repo.get_by_id(radionuclide_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Radionucléide non trouvé")

    source_repo = SourceRepository(db)
    current_source = source_repo.get_by_id(existing.source_id)
    check_source_mn_access(current_source, current_user)

    if radionuclide_update.source_id and radionuclide_update.source_id != existing.source_id:
        new_source = source_repo.get_by_id(radionuclide_update.source_id)
        if not new_source:
            raise HTTPException(status_code=404, detail=f"Aucune source avec l'identifiant '{radionuclide_update.source_id}'.")
        check_source_mn_access(new_source, current_user)

    if radionuclide_update.nom:
        from app.services.matieres_nucleaires import normaliser_nom_radionuclide
        radionuclide_update.nom = normaliser_nom_radionuclide(radionuclide_update.nom)

    db_radionuclide = repo.update(radionuclide_id, radionuclide_update)

    audit_repo = AuditRepository(db)

    from app.services.matieres_nucleaires import est_matiere_nucleaire
    source_finale = source_repo.get_by_id(db_radionuclide.source_id)
    if source_finale and est_matiere_nucleaire(db_radionuclide.nom) and not source_finale.matiere_nucleaire:
        source_finale.matiere_nucleaire = True
        db.commit()
        audit_repo.create(AuditLogCreate(
            utilisateur=current_user.username,
            action="UPDATE",
            table_modifiee="sources",
            id_source=source_finale.id,
            champ_modifie="matiere_nucleaire",
            valeur_avant="False",
            valeur_apres="True (classement automatique, radionucléide " + db_radionuclide.nom + ")",
        ))
    audit_repo.create(AuditLogCreate(
        utilisateur=current_user.username,
        action="UPDATE",
        table_modifiee="radionuclides",
        id_source=db_radionuclide.source_id,
        valeur_apres=str(radionuclide_update.model_dump(exclude_unset=True)),
    ))
    return db_radionuclide

@router.delete("/{radionuclide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_radionuclide(
    radionuclide_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = RadionuclideRepository(db)
    existing = repo.get_by_id(radionuclide_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Radionucléide non trouvé")

    source = SourceRepository(db).get_by_id(existing.source_id)
    check_source_mn_access(source, current_user)

    source_id = existing.source_id
    repo.delete(radionuclide_id)

    audit_repo = AuditRepository(db)
    audit_repo.create(AuditLogCreate(
        utilisateur=current_user.username,
        action="DELETE",
        table_modifiee="radionuclides",
        id_source=source_id,
    ))
    return
