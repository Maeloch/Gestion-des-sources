"""Routes pour les logs d'audit."""
from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session
from app.models.audit import AuditLog, AuditLogDB
from app.repositories.audit import AuditRepository
from app.security.permissions import require_audit_access
from app.database import get_db

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/", response_model=List[AuditLog])
async def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_audit_access),
):
    repo = AuditRepository(db)
    return repo.get_all(limit=limit)
