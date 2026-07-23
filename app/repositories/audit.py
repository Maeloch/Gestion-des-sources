"""Repository pour les logs d'audit."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.audit import AuditLogDB, AuditLogCreate

class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, limit: int = 100) -> List[AuditLogDB]:
        return self.db.query(AuditLogDB).order_by(AuditLogDB.timestamp.desc()).limit(limit).all()

    def get_by_source(self, source_id: str, limit: int = 100) -> List[AuditLogDB]:
        return self.db.query(AuditLogDB).filter(AuditLogDB.id_source == source_id).order_by(AuditLogDB.timestamp.desc()).limit(limit).all()

    def create(self, audit_log: AuditLogCreate) -> AuditLogDB:
        db_audit_log = AuditLogDB(**audit_log.model_dump())
        self.db.add(db_audit_log)
        self.db.commit()
        self.db.refresh(db_audit_log)
        return db_audit_log
