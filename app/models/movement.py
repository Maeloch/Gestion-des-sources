"""Modèle pour les mouvements de sources (cycle emprunt / retour).

Un mouvement représente la sortie d'une source d'un lieu vers un autre
(par exemple : de l'armoire de stockage IRMA vers le labo EPICEA). Tant que
`date_retour_reelle` n'est pas renseignée, la source est considérée
"sortie" (empruntée). La renseigner ("marquer comme retournée") ramène la
source à son lieu de départ.
"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime, date
from app.database import Base

# Modèle SQLAlchemy
class MovementDB(Base):
    __tablename__ = "movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(50), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    commentaire = Column(String(255), nullable=True)
    # --- Champs du cycle emprunt / retour ---
    date_retour_prevue = Column(Date, nullable=True)
    date_retour_reelle = Column(Date, nullable=True)  # NULL = toujours "sorti"
    utilisateur = Column(String(50), nullable=True)

    # Relations
    source = relationship("SourceDB", back_populates="movements")
    from_location = relationship("LocationDB", foreign_keys=[from_location_id])
    to_location = relationship("LocationDB", foreign_keys=[to_location_id])

# Modèles Pydantic
class MovementBase(BaseModel):
    source_id: str
    commentaire: Optional[str] = None

class MovementCreate(MovementBase):
    # from_location_id n'est PAS demandé ici : il est déduit automatiquement
    # du lieu actuel de la source au moment de la création (voir la route).
    to_location_id: int
    date_retour_prevue: Optional[date] = None

class MovementRetour(BaseModel):
    """Utilisé pour clôturer un emprunt (marquer une source comme revenue)."""
    date_retour_reelle: Optional[date] = None  # si absent : aujourd'hui
    commentaire: Optional[str] = None

class Movement(MovementBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    timestamp: datetime
    date_retour_prevue: Optional[date] = None
    date_retour_reelle: Optional[date] = None
    utilisateur: Optional[str] = None
