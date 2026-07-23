"""Repository pour les consommations."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.consumption import ConsumptionDB, ConsumptionCreate

class ConsumptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, consumption_id: int) -> Optional[ConsumptionDB]:
        return self.db.query(ConsumptionDB).filter(ConsumptionDB.id == consumption_id).first()

    def get_all(self) -> List[ConsumptionDB]:
        return self.db.query(ConsumptionDB).all()

    def get_by_source(self, source_id: str) -> List[ConsumptionDB]:
        return self.db.query(ConsumptionDB).filter(ConsumptionDB.source_id == source_id).all()

    def create(self, consumption: ConsumptionCreate) -> ConsumptionDB:
        db_consumption = ConsumptionDB(**consumption.model_dump())
        self.db.add(db_consumption)
        try:
            self.db.commit()
            self.db.refresh(db_consumption)
            return db_consumption
        except Exception:
            self.db.rollback()
            raise

    def update(self, consumption_id: int, updates: dict) -> Optional[ConsumptionDB]:
        db_consumption = self.get_by_id(consumption_id)
        if not db_consumption:
            return None
        for champ, valeur in updates.items():
            if valeur is not None:
                setattr(db_consumption, champ, valeur)
        self.db.commit()
        self.db.refresh(db_consumption)
        return db_consumption
