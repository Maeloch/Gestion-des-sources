"""Routes pour les consommations (sources gaz et liquide uniquement)."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from app.models.consumption import Consumption, ConsumptionCreate, ConsumptionUpdate, ConsumptionDB
from app.models.audit import AuditLogCreate
from app.repositories.consumption import ConsumptionRepository
from app.repositories.source import SourceRepository
from app.repositories.audit import AuditRepository
from app.services.consumption import ConsumptionService
from app.security.permissions import (
    get_current_user,
    require_write_access,
    user_can_access_mn,
    check_source_mn_access,
)
from app.database import get_db

router = APIRouter(prefix="/consumptions", tags=["consumptions"])

@router.get("/", response_model=List[Consumption])
async def list_consumptions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = ConsumptionRepository(db)
    consumptions = repo.get_all()
    if user_can_access_mn(current_user):
        return consumptions
    mn_source_ids = {s.id for s in SourceRepository(db).get_all() if s.matiere_nucleaire}
    return [c for c in consumptions if c.source_id not in mn_source_ids]

@router.post("/", response_model=Consumption)
async def create_consumption(
    consumption: ConsumptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    source = SourceRepository(db).get_by_id(consumption.source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Aucune source avec l'identifiant '{consumption.source_id}'.")
    check_source_mn_access(source, current_user)

    service = ConsumptionService(
        source_repo=SourceRepository(db),
        consumption_repo=ConsumptionRepository(db),
        audit_repo=AuditRepository(db),
    )
    try:
        db_consumption = service.use_source(
            source_id=consumption.source_id,
            quantite_utilisee=consumption.quantite_utilisee,
            masse_avant=consumption.masse_avant,
            masse_apres=consumption.masse_apres,
            utilisateur=current_user.username,
            commentaire=consumption.commentaire,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return db_consumption


@router.patch("/{consumption_id}", response_model=Consumption)
async def update_consumption(
    consumption_id: int,
    updates: ConsumptionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    """Corrige une consommation/pesée déjà enregistrée -- demandé le
    13/07/2026 : une erreur de saisie ne doit pas rester bloquée pour
    toujours. Chaque champ modifié est tracé dans l'audit (avant/après),
    pour concilier ce droit à l'erreur avec un minimum de traçabilité
    (pas idéal du point de vue assurance qualité, mais nécessaire en
    pratique -- l'audit reste la garde-fou)."""
    repo = ConsumptionRepository(db)
    existante = repo.get_by_id(consumption_id)
    if not existante:
        raise HTTPException(status_code=404, detail="Consommation non trouvée")

    source = SourceRepository(db).get_by_id(existante.source_id)
    if source:
        check_source_mn_access(source, current_user)

    valeurs_avant = {
        "quantite_utilisee": existante.quantite_utilisee,
        "masse_avant": existante.masse_avant,
        "masse_apres": existante.masse_apres,
        "commentaire": existante.commentaire,
        "timestamp": existante.timestamp,
    }

    donnees = updates.model_dump(exclude_unset=True)
    # Si l'une des deux pesées change sans que l'autre soit fournie, la
    # quantité consommée doit être recalculée à partir des VALEURS
    # FINALES (nouvelle ou ancienne, selon ce qui a été fourni) pour ne
    # jamais laisser quantite_utilisee incohérente avec la pesée corrigée.
    nouveau_masse_avant = donnees.get("masse_avant", existante.masse_avant)
    nouveau_masse_apres = donnees.get("masse_apres", existante.masse_apres)
    if (
        ("masse_avant" in donnees or "masse_apres" in donnees)
        and nouveau_masse_avant is not None
        and nouveau_masse_apres is not None
    ):
        if nouveau_masse_avant < nouveau_masse_apres:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La masse après ({nouveau_masse_apres}) ne peut pas dépasser la masse avant ({nouveau_masse_avant}).",
            )
        donnees["quantite_utilisee"] = nouveau_masse_avant - nouveau_masse_apres

    db_consumption = repo.update(consumption_id, donnees)

    audit_repo = AuditRepository(db)
    for champ, valeur_avant in valeurs_avant.items():
        valeur_apres = getattr(db_consumption, champ)
        if valeur_avant == valeur_apres:
            continue
        audit_repo.create(AuditLogCreate(
            utilisateur=current_user.username,
            action="UPDATE",
            table_modifiee="consumptions",
            id_source=db_consumption.source_id,
            champ_modifie=f"consommation#{consumption_id}.{champ}",
            valeur_avant=str(valeur_avant) if valeur_avant is not None else None,
            valeur_apres=str(valeur_apres) if valeur_apres is not None else None,
        ))

    return db_consumption

@router.delete("/{consumption_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consumption(
    consumption_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    """Supprime une consommation/pesée -- demandé le 31/07/2026, pour
    corriger un doublon (ex: le même document importé deux fois par
    erreur). Contrairement aux sources (jamais supprimables, voir
    ailleurs dans le code -- une source reste un objet physique qui doit
    toujours rester traçable, même détruite), une consommation en
    doublon ne correspond à AUCUN événement réel : rien à archiver, la
    supprimer ne perd aucune trace d'un fait qui ne s'est jamais produit.
    La suppression elle-même reste tracée dans l'audit, qui survit à la
    consommation supprimée."""
    repo = ConsumptionRepository(db)
    existante = repo.get_by_id(consumption_id)
    if not existante:
        raise HTTPException(status_code=404, detail="Consommation non trouvée")

    source = SourceRepository(db).get_by_id(existante.source_id)
    if source:
        check_source_mn_access(source, current_user)

    resume_avant_suppression = (
        f"date={existante.timestamp}, quantite_utilisee={existante.quantite_utilisee}, "
        f"masse_avant={existante.masse_avant}, masse_apres={existante.masse_apres}"
    )

    repo.delete(consumption_id)

    AuditRepository(db).create(AuditLogCreate(
        utilisateur=current_user.username,
        action="DELETE",
        table_modifiee="consumptions",
        id_source=existante.source_id,
        champ_modifie=f"consommation#{consumption_id}",
        valeur_avant=resume_avant_suppression,
        valeur_apres=None,
    ))
    return
