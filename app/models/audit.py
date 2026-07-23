"""Modèle pour les logs d'audit."""
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLAlchemyEnum  # ← Utilise SQLAlchemyEnum
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from enum import Enum as PyEnum  # ← Enum Python pour Pydantic
from app.database import Base

# Énumération pour les actions d'audit (Python Enum pour Pydantic)
class AuditAction(str, PyEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UTILISATION = "UTILISATION"
    PESEE = "PESEE"
    EMPRUNT = "EMPRUNT"
    RETOUR = "RETOUR"
    IMPORT = "IMPORT"

# Modèle SQLAlchemy
class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    utilisateur = Column(String(50), nullable=False)
    action = Column(SQLAlchemyEnum(AuditAction), nullable=False)  # ← Utilise SQLAlchemyEnum
    table_modifiee = Column(String(50), nullable=False)
    id_source = Column(String(50), nullable=True)
    champ_modifie = Column(String(50), nullable=True)
    valeur_avant = Column(String(255), nullable=True)
    valeur_apres = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

# Modèles Pydantic
class AuditLogBase(BaseModel):
    utilisateur: str
    action: AuditAction  # ← Utilise l'Enum Python ici
    table_modifiee: str
    id_source: Optional[str] = None
    champ_modifie: Optional[str] = None
    valeur_avant: Optional[str] = None
    valeur_apres: Optional[str] = None

class AuditLogCreate(AuditLogBase):
    pass

class AuditLog(AuditLogBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime
