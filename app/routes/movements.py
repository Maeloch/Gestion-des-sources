"""Routes pour les mouvements (emprunts) de sources."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from app.models.movement import Movement, MovementCreate, MovementRetour
from app.repositories.movement import MovementRepository
from app.repositories.source import SourceRepository
from app.repositories.location import LocationRepository
from app.repositories.audit import AuditRepository
from app.services.movement import MovementService
from app.security.permissions import (
    get_current_user,
    require_write_access,
    user_can_access_mn,
    check_source_mn_access,
)
from app.database import get_db

router = APIRouter(prefix="/movements", tags=["movements"])

@router.get("/", response_model=List[Movement])
async def list_movements(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = MovementRepository(db)
    movements = repo.get_all()
    if user_can_access_mn(current_user):
        return movements
    mn_source_ids = {s.id for s in SourceRepository(db).get_all() if s.matiere_nucleaire}
    return [m for m in movements if m.source_id not in mn_source_ids]

@router.post("/", response_model=Movement)
async def create_movement(
    movement: MovementCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    source = SourceRepository(db).get_by_id(movement.source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Aucune source avec l'identifiant '{movement.source_id}'.")
    check_source_mn_access(source, current_user)

    service = MovementService(
        source_repo=SourceRepository(db),
        location_repo=LocationRepository(db),
        movement_repo=MovementRepository(db),
        audit_repo=AuditRepository(db),
    )
    try:
        db_movement = service.demarrer_emprunt(
            source_id=movement.source_id,
            to_location_id=movement.to_location_id,
            utilisateur=current_user.username,
            date_retour_prevue=movement.date_retour_prevue,
            commentaire=movement.commentaire,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return db_movement

@router.patch("/{movement_id}/retour", response_model=Movement)
async def retourner_movement(
    movement_id: int,
    retour: MovementRetour,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    movement_repo = MovementRepository(db)
    existing = movement_repo.get_by_id(movement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Mouvement non trouvé")

    source = SourceRepository(db).get_by_id(existing.source_id)
    check_source_mn_access(source, current_user)

    service = MovementService(
        source_repo=SourceRepository(db),
        location_repo=LocationRepository(db),
        movement_repo=movement_repo,
        audit_repo=AuditRepository(db),
    )
    try:
        db_movement = service.retourner_emprunt(
            movement_id=movement_id,
            utilisateur=current_user.username,
            date_retour_reelle=retour.date_retour_reelle,
            commentaire=retour.commentaire,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return db_movement
