"""Routes pour les sources radioactives."""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List
from sqlalchemy.orm import Session
from app.models.source import Source, SourceCreate, SourceUpdate, SourceDB, is_archived
from app.models.audit import AuditLogCreate
from app.repositories.source import SourceRepository
from app.repositories.audit import AuditRepository
from app.repositories.movement import MovementRepository
from app.security.permissions import (
    get_current_user,
    get_current_admin,
    require_write_access,
    user_can_access_mn,
    check_source_mn_access,
    require_mn_access_for,
)
from app.database import get_db

router = APIRouter(prefix="/sources", tags=["sources"])

@router.get("/", response_model=List[Source])
async def list_sources(
    archivees: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Par défaut, ne renvoie que les sources actives (en circulation).
    Passer ?archivees=true pour obtenir la liste d'archives (remisée, en
    déchet, transférée, détruite) à la place."""
    from app.services.units import quantite_restante_calculee
    repo = SourceRepository(db)
    sources = repo.get_all(archivees=archivees)
    if not user_can_access_mn(current_user):
        # Rôles 'utilisateur' et 'lecteur' : les sources Matière Nucléaire
        # n'apparaissent même pas dans la liste.
        sources = [s for s in sources if not s.matiere_nucleaire]
    for s in sources:
        s.quantite_calculee = quantite_restante_calculee(db, s)
    return sources

@router.get("/{source_id}", response_model=Source)
async def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.units import quantite_restante_calculee
    repo = SourceRepository(db)
    source = repo.get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source non trouvée")
    check_source_mn_access(source, current_user)
    source.quantite_calculee = quantite_restante_calculee(db, source)
    return source

@router.post("/depuis_certificat")
async def extraire_depuis_certificat(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write_access),
):
    """Extrait les champs utiles d'un certificat d'étalonnage PDF (format
    CERCA/LEA-Orano notamment), pour pré-remplir la création d'une
    source -- demandé le 14/07/2026. NE CRÉE RIEN : renvoie une
    proposition de champs à vérifier avant de les valider dans le
    formulaire habituel. Les certificats scannés donnent un texte
    parfois très abîmé par l'OCR ; un champ non trouvé avec une
    confiance raisonnable est laissé vide plutôt que deviné."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF.")

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    from app.services.parse_certificat import extraire_certificat
    try:
        resultat = extraire_certificat(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de lire ce PDF : {e}")

    # Le texte brut complet n'est utile que pour un contrôle visuel côté
    # client (comparer avec l'original) ; pas la peine de le renvoyer sur
    # des dizaines de pages.
    resultat["texte_brut"] = resultat["texte_brut"][:3000]
    return resultat


@router.post("/", response_model=Source)
async def create_source(
    source: SourceCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    require_mn_access_for(source.matiere_nucleaire, current_user)

    repo = SourceRepository(db)
    audit_repo = AuditRepository(db)

    if repo.get_by_id(source.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Une source avec l'identifiant '{source.id}' existe déjà.",
        )

    from app.repositories.location import LocationRepository
    if not LocationRepository(db).get_by_id(source.emplacement_habituel_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aucun lieu avec l'identifiant {source.emplacement_habituel_id}. Crée-le d'abord.",
        )

    db_source = repo.create(source)
    if db_source.emplacement_habituel_id and not db_source.emplacement_actuel_id:
        # Une source qui vient d'être créée avec un lieu habituel est
        # considérée comme s'y trouvant déjà (pas besoin d'enregistrer un
        # mouvement fictif pour ça).
        db_source.emplacement_actuel_id = db_source.emplacement_habituel_id
        db.commit()
        db.refresh(db_source)

    audit_repo.create(AuditLogCreate(
        utilisateur=current_user.username,
        action="CREATE",
        table_modifiee="sources",
        id_source=db_source.id,
        champ_modifie="toutes",
        valeur_apres=str(source.model_dump()),
    ))
    from app.services.units import quantite_restante_calculee
    db_source.quantite_calculee = quantite_restante_calculee(db, db_source)
    return db_source

@router.put("/{source_id}", response_model=Source)
async def update_source(
    source_id: str,
    source_update: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = SourceRepository(db)
    audit_repo = AuditRepository(db)
    movement_repo = MovementRepository(db)

    existing = repo.get_by_id(source_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Source non trouvée")
    # On ne peut pas modifier une source MN sans y avoir accès (elle est
    # d'ailleurs invisible : 404 plutôt que 403, comme pour la lecture).
    check_source_mn_access(existing, current_user)

    if is_archived(existing) and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Cette source est archivée (statut : {existing.etat_utilisation.value}). "
                "Seul un administrateur peut la modifier (pour corriger une erreur)."
            ),
        )

    # On ne peut pas non plus rendre MN une source qui ne l'était pas, sans
    # avoir soi-même accès aux sources MN.
    if source_update.matiere_nucleaire is not None:
        require_mn_access_for(source_update.matiere_nucleaire, current_user)

    # Capture des valeurs AVANT modification, pour un journal d'audit
    # précis (un événement par champ réellement changé, avec sa valeur
    # avant/après) plutôt qu'un unique événement générique "toutes les
    # valeurs" — demandé le 10/07/2026, l'ancien comportement ne montrant
    # pas ce qui avait concrètement changé.
    valeurs_avant = {
        champ: getattr(existing, champ)
        for champ in source_update.model_dump(exclude_unset=True).keys()
    }

    db_source = repo.update(source_id, source_update)

    if source_update.emplacement_habituel_id is not None:
        # Si la source n'est pas actuellement sortie (aucun emprunt ouvert),
        # changer son lieu habituel met aussi à jour son lieu actuel.
        if not movement_repo.get_open_movement_for_source(source_id):
            db_source.emplacement_actuel_id = source_update.emplacement_habituel_id
            db.commit()
            db.refresh(db_source)

    for champ, valeur_avant in valeurs_avant.items():
        valeur_apres = getattr(db_source, champ)
        # Les enums (type, etat_physique, etat_utilisation, unite_quantite)
        # doivent être comparés/affichés par leur .value, pas l'objet Python.
        va = valeur_avant.value if hasattr(valeur_avant, "value") else valeur_avant
        vp = valeur_apres.value if hasattr(valeur_apres, "value") else valeur_apres
        if va == vp:
            continue  # valeur fournie mais identique à l'existante : pas un vrai changement
        audit_repo.create(AuditLogCreate(
            utilisateur=current_user.username,
            action="UPDATE",
            table_modifiee="sources",
            id_source=source_id,
            champ_modifie=champ,
            valeur_avant=str(va) if va is not None else None,
            valeur_apres=str(vp) if vp is not None else None,
        ))
    from app.services.units import quantite_restante_calculee
    db_source.quantite_calculee = quantite_restante_calculee(db, db_source)
    return db_source

# La suppression définitive d'une source a été retirée le 22/07/2026,
# sur retour direct : dans un contexte de traçabilité réglementaire
# (matières nucléaires), aucune source ne devrait jamais disparaître
# complètement de la base -- son statut d'utilisation ("détruite", "en
# déchet", "transférée"...) suffit à la faire sortir de la liste active,
# tout en gardant une trace permanente (page Archives). L'ancienne route
# avait déjà un garde-fou contre la perte d'historique (refusait de
# supprimer une source avec des consommations ou mouvements rattachés),
# mais ce garde-fou avait un trou : les radionucléides n'étaient pas
# protégés de la même façon (suppression en cascade), une source qui en
# portait mais n'avait ni consommation ni mouvement pouvait donc être
# supprimée avec ses données de radionucléide, sans avertissement. Plutôt
# que de combler ce trou au cas par cas, la suppression elle-même est
# retirée : voir la page Archives et le bouton "Corriger" pour modifier
# une source déjà archivée si besoin (ex: fusionner un doublon en
# changeant son statut et en documentant la correction dans son
# commentaire, plutôt qu'en la faisant disparaître).
