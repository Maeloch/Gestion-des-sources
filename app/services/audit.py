"""Service pour la gestion des logs d'audit."""
from sqlalchemy.orm import Session
from app.models.audit import AuditLogDB, AuditLogCreate
from app.repositories.audit import AuditRepository

class AuditService:
    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    def log_action(self, audit_log: AuditLogCreate) -> AuditLogDB:
        """Enregistre une action dans les logs d'audit."""
        return self.audit_repo.create(audit_log)
