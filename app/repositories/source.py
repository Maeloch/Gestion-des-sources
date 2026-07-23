"""Repository pour les sources radioactives."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.source import SourceDB, SourceCreate, SourceUpdate, ETATS_ARCHIVES

class SourceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, source_id: str) -> Optional[SourceDB]:
        return self.db.query(SourceDB).filter(SourceDB.id == source_id).first()

    def get_all(self, archivees: bool = None) -> List[SourceDB]:
        """Sans argument (par défaut) : toutes les sources, sans filtre —
        comportement inchangé pour ne pas casser les usages existants
        (ex. calcul du cloisonnement Matière Nucléaire, qui doit connaître
        TOUTES les sources, y compris archivées).
        archivees=False : uniquement les sources actives (pas remisée / en
        déchet / transférée / détruite).
        archivees=True : uniquement les sources archivées."""
        query = self.db.query(SourceDB)
        if archivees is True:
            query = query.filter(SourceDB.etat_utilisation.in_(ETATS_ARCHIVES))
        elif archivees is False:
            query = query.filter(~SourceDB.etat_utilisation.in_(ETATS_ARCHIVES))
        return query.all()

    def create(self, source: SourceCreate) -> SourceDB:
        data = source.model_dump()
        if not data.get("lieu_stockage"):
            data["lieu_stockage"] = ""  # champ historique NOT NULL en base ; plus rempli depuis le formulaire
        db_source = SourceDB(**data)
        self.db.add(db_source)
        try:
            self.db.commit()
            self.db.refresh(db_source)
            return db_source
        except Exception:
            self.db.rollback()
            raise

    def update(self, source_id: str, source_update: SourceUpdate) -> Optional[SourceDB]:
        db_source = self.get_by_id(source_id)
        if not db_source:
            return None
        for key, value in source_update.model_dump(exclude_unset=True).items():
            setattr(db_source, key, value)
        try:
            self.db.commit()
            self.db.refresh(db_source)
            return db_source
        except Exception:
            self.db.rollback()
            raise

    def delete(self, source_id: str) -> bool:
        db_source = self.get_by_id(source_id)
        if not db_source:
            return False
        self.db.delete(db_source)
        try:
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

