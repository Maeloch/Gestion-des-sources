"""Repository pour les lieux de stockage."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.location import LocationDB, LocationCreate, LocationUpdate

class LocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, location_id: int) -> Optional[LocationDB]:
        return self.db.query(LocationDB).filter(LocationDB.id == location_id).first()

    def get_all(self) -> List[LocationDB]:
        return self.db.query(LocationDB).all()

    def create(self, location: LocationCreate) -> LocationDB:
        db_location = LocationDB(**location.model_dump())
        self.db.add(db_location)
        try:
            self.db.commit()
            self.db.refresh(db_location)
            return db_location
        except Exception:
            self.db.rollback()
            raise

    def update(self, location_id: int, location_update: LocationUpdate) -> Optional[LocationDB]:
        db_location = self.get_by_id(location_id)
        if not db_location:
            return None
        for key, value in location_update.model_dump(exclude_unset=True).items():
            setattr(db_location, key, value)
        try:
            self.db.commit()
            self.db.refresh(db_location)
            return db_location
        except Exception:
            self.db.rollback()
            raise

    def delete(self, location_id: int) -> bool:
        db_location = self.get_by_id(location_id)
        if not db_location:
            return False
        self.db.delete(db_location)
        try:
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise
