"""Repository pour les mouvements de sources."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.movement import MovementDB, MovementCreate

class MovementRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, movement_id: int) -> Optional[MovementDB]:
        return self.db.query(MovementDB).filter(MovementDB.id == movement_id).first()

    def get_all(self) -> List[MovementDB]:
        return self.db.query(MovementDB).order_by(MovementDB.timestamp.desc()).all()

    def get_by_source(self, source_id: str) -> List[MovementDB]:
        return self.db.query(MovementDB).filter(MovementDB.source_id == source_id).all()

    def get_open_movement_for_source(self, source_id: str) -> Optional[MovementDB]:
        """L'emprunt en cours (non encore retourné) pour cette source, s'il y en a un."""
        return (
            self.db.query(MovementDB)
            .filter(MovementDB.source_id == source_id, MovementDB.date_retour_reelle.is_(None))
            .first()
        )

    def create(self, db_movement: MovementDB) -> MovementDB:
        """Contrairement aux autres repositories, create() reçoit ici
        directement un objet MovementDB déjà construit (pas un schéma
        MovementCreate) : la route/service a besoin de renseigner
        from_location_id et utilisateur, qui ne viennent pas du formulaire
        envoyé par le navigateur."""
        self.db.add(db_movement)
        try:
            self.db.commit()
            self.db.refresh(db_movement)
            return db_movement
        except Exception:
            self.db.rollback()
            raise
