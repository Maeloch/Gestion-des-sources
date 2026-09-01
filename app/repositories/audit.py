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
        # Fait correspondre automatiquement utilisateur_id au nom déjà
        # renseigné (31/08/2026) : centralisé ici plutôt que sur chacun
        # des nombreux points d'appel (sources, radionucléides,
        # utilisateurs...), qui n'ont pas besoin d'être modifiés -- le nom
        # correspond toujours à un compte réel pour une action en direct
        # (current_user.username), donc cette correspondance réussit
        # systématiquement dans ce cas. Ne s'applique qu'aux nouvelles
        # actions ; les données déjà en base sont traitées par la
        # migration dédiée (voir services/utilisateurs_historiques.py).
        if db_audit_log.utilisateur:
            from app.repositories.user import UserRepository
            correspondant = UserRepository(self.db).get_by_username(db_audit_log.utilisateur)
            if correspondant:
                db_audit_log.utilisateur_id = correspondant.id
        self.db.add(db_audit_log)
        self.db.commit()
        self.db.refresh(db_audit_log)
        return db_audit_log
