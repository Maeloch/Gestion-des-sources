"""Modèle pour les radionucléides."""
from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date
from app.database import Base

# Modèle SQLAlchemy
class RadionuclideDB(Base):
    __tablename__ = "radionuclides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(50), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    nom = Column(String(50), nullable=False, index=True)
    activite = Column(Float, nullable=False)
    unite_activite = Column(String(10), nullable=False)
    date_reference = Column(Date, nullable=False)
    periode = Column(Float, nullable=True)
    lien_laraweb = Column(String(255), nullable=True)
    # Ajouté pour le CDC : par défaut (False), `activite` est déjà la valeur
    # totale de la source (comportement historique, inchangé). Si True,
    # `activite` est une activité SPÉCIFIQUE (par unité de quantité, ex.
    # Bq/g) et l'activité totale de la source se calcule alors en la
    # multipliant par la quantité restante sur la source (uniquement
    # pertinent pour les sources liquides/gazeuses avec une quantité suivie).
    activite_est_specifique = Column(Boolean, default=False, nullable=False)

    # Relations
    source = relationship("SourceDB", back_populates="radionuclides")

# Modèles Pydantic
class RadionuclideBase(BaseModel):
    nom: str
    activite: float
    unite_activite: str
    date_reference: date
    periode: Optional[float] = None
    lien_laraweb: Optional[str] = None
    activite_est_specifique: bool = False

class RadionuclideCreate(RadionuclideBase):
    source_id: str

class RadionuclideUpdate(BaseModel):
    nom: Optional[str] = None
    activite: Optional[float] = None
    unite_activite: Optional[str] = None
    date_reference: Optional[date] = None
    periode: Optional[float] = None
    lien_laraweb: Optional[str] = None
    source_id: Optional[str] = None
    activite_est_specifique: Optional[bool] = None

class Radionuclide(RadionuclideBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: str
