"""Modèle pour les consommations de sources."""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional
from datetime import datetime
from app.database import Base

# Modèle SQLAlchemy
class ConsumptionDB(Base):
    __tablename__ = "consumptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(50), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    quantite_utilisee = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    commentaire = Column(String(255), nullable=True)
    # Ajouté pour correspondre au cahier des charges : qui a fait cette
    # consommation (auparavant, seul le journal d'audit le savait, pas la
    # consommation elle-même). Nullable pour ne pas casser les
    # consommations déjà enregistrées avant l'ajout de ce champ.
    utilisateur = Column(String(50), nullable=True)
    # Pesée double (12/07/2026) : masse totale (récipient + contenu) avant
    # et après prélèvement, plutôt qu'une quantité consommée estimée à la
    # main. quantite_utilisee reste la valeur de référence (calculée comme
    # masse_avant - masse_apres quand les deux sont fournies), pour rester
    # compatible avec tout ce qui l'utilise déjà. Facultatifs : le mode
    # "quantité directe" (sans pesée double) reste possible, notamment
    # pour les sources gaz où peser n'a pas de sens.
    masse_avant = Column(Float, nullable=True)
    masse_apres = Column(Float, nullable=True)

    # Relations
    source = relationship("SourceDB", back_populates="consumptions")

# Modèles Pydantic
class ConsumptionBase(BaseModel):
    source_id: str
    commentaire: Optional[str] = None

class ConsumptionCreate(ConsumptionBase):
    # L'un ou l'autre : soit quantite_utilisee directement (mode simple,
    # notamment pour le gaz), soit masse_avant + masse_apres (pesée
    # double, notamment pour le liquide) -- validé dans le service, pas
    # ici, pour un message d'erreur plus clair côté métier.
    quantite_utilisee: Optional[float] = None
    masse_avant: Optional[float] = None
    masse_apres: Optional[float] = None

class ConsumptionUpdate(BaseModel):
    """Correction d'une consommation/pesée déjà enregistrée -- ajouté le
    13/07/2026 : "j'aimerais avoir le droit de modifier cette pesée, je
    suis jamais à l'abri de mal renseigner des valeurs". Chaque champ
    fourni remplace l'ancienne valeur ; le reste est inchangé. Toute
    modification est tracée dans l'audit (voir la route), pour concilier
    le droit à l'erreur avec un minimum de traçabilité.

    `timestamp` (date seule, JJ/MM/AAAA côté formulaire) ajoutée le
    31/07/2026 : la date pouvait déjà être fausse dès la première saisie
    (import d'une fiche mal transcrite, notamment), sans possibilité de
    la corriger après coup -- seule la valeur l'était."""
    quantite_utilisee: Optional[float] = None
    masse_avant: Optional[float] = None
    masse_apres: Optional[float] = None
    commentaire: Optional[str] = None
    timestamp: Optional[datetime] = None

class Consumption(ConsumptionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    quantite_utilisee: float
    timestamp: datetime
    utilisateur: Optional[str] = None
    masse_avant: Optional[float] = None
    masse_apres: Optional[float] = None
