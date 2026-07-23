"""Modèle pour les lieux (stockage ou utilisation) des sources."""
from sqlalchemy import Column, Integer, String
from pydantic import BaseModel, ConfigDict
from typing import Optional
from app.database import Base

# Modèle SQLAlchemy
class LocationDB(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nom = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)
    # Champs ajoutés pour structurer un lieu (ex: "Armoire des sources",
    # site "IRMA", bâtiment "389", pièce "72"). Tous facultatifs : un lieu
    # peut être juste un nom simple (ex: "EPICEA") si la précision
    # bâtiment/pièce n'a pas de sens pour lui.
    site = Column(String(100), nullable=True)
    batiment = Column(String(50), nullable=True)
    piece = Column(String(50), nullable=True)

# Modèles Pydantic
class LocationBase(BaseModel):
    nom: str
    description: Optional[str] = None
    site: Optional[str] = None
    batiment: Optional[str] = None
    piece: Optional[str] = None

class LocationCreate(LocationBase):
    pass

class LocationUpdate(BaseModel):
    nom: Optional[str] = None
    description: Optional[str] = None
    site: Optional[str] = None
    batiment: Optional[str] = None
    piece: Optional[str] = None
    # Si le nouveau nom correspond à un lieu existant différent, la
    # modification est refusée (409) tant que ce champ n'est pas mis à
    # vrai explicitement -- évite qu'une simple faute de frappe déclenche
    # une fusion silencieuse. Voir la route update_location. Ajouté le
    # 13/07/2026, suite à une suggestion directe : renommer un lieu vers
    # un nom déjà pris propose maintenant de fusionner, plutôt que
    # d'échouer avec une erreur de contrainte SQL.
    confirmer_fusion: bool = False

class LocationFusion(BaseModel):
    cible_id: int

class Location(LocationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
