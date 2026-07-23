"""Modèle pour les demandes de changement de rôle : un utilisateur peut
demander un rôle différent, un administrateur approuve ou rejette."""
from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from enum import Enum as PyEnum
from app.database import Base
from app.models.user import UserRole


class StatutDemande(str, PyEnum):
    en_attente = "en_attente"
    approuvee = "approuvee"
    rejetee = "rejetee"


# Modèle SQLAlchemy
class RoleRequestDB(Base):
    __tablename__ = "role_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False)
    role_demande = Column(SAEnum(UserRole), nullable=False)
    statut = Column(SAEnum(StatutDemande), default=StatutDemande.en_attente, nullable=False)
    commentaire = Column(String(500), nullable=True)
    date_demande = Column(DateTime, default=datetime.utcnow, nullable=False)
    traite_par = Column(String(50), nullable=True)
    date_traitement = Column(DateTime, nullable=True)


# Modèles Pydantic
class RoleRequestCreate(BaseModel):
    role_demande: UserRole
    commentaire: Optional[str] = None


class RoleRequestTraitement(BaseModel):
    action: str  # "approuver" ou "rejeter"


class RoleRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role_demande: UserRole
    statut: StatutDemande
    commentaire: Optional[str] = None
    date_demande: datetime
    traite_par: Optional[str] = None
    date_traitement: Optional[datetime] = None
