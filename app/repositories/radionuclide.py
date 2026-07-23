"""Repository pour les radionucléides."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.radionuclide import RadionuclideDB, RadionuclideCreate, RadionuclideUpdate

class RadionuclideRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, radionuclide_id: int) -> Optional[RadionuclideDB]:
        return self.db.query(RadionuclideDB).filter(RadionuclideDB.id == radionuclide_id).first()

    def get_all(self) -> List[RadionuclideDB]:
        return self.db.query(RadionuclideDB).all()

    def get_by_source(self, source_id: str) -> List[RadionuclideDB]:
        return self.db.query(RadionuclideDB).filter(RadionuclideDB.source_id == source_id).all()

    def create(self, radionuclide: RadionuclideCreate) -> RadionuclideDB:
        db_radionuclide = RadionuclideDB(**radionuclide.model_dump())
        self.db.add(db_radionuclide)
        try:
            self.db.commit()
            self.db.refresh(db_radionuclide)
            return db_radionuclide
        except Exception:
            self.db.rollback()
            raise

    def update(self, radionuclide_id: int, radionuclide_update: RadionuclideUpdate) -> Optional[RadionuclideDB]:
        db_radionuclide = self.get_by_id(radionuclide_id)
        if not db_radionuclide:
            return None
        for key, value in radionuclide_update.model_dump(exclude_unset=True).items():
            setattr(db_radionuclide, key, value)
        try:
            self.db.commit()
            self.db.refresh(db_radionuclide)
            return db_radionuclide
        except Exception:
            self.db.rollback()
            raise

    def delete(self, radionuclide_id: int) -> bool:
        db_radionuclide = self.get_by_id(radionuclide_id)
        if not db_radionuclide:
            return False
        self.db.delete(db_radionuclide)
        try:
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise
