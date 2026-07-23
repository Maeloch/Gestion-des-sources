"""Modèle pour les sources radioactives."""
from sqlalchemy import Column, String, Boolean, Float, Date, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import date
from enum import Enum as PyEnum
from app.database import Base
from app.models.radionuclide import Radionuclide
from app.models.location import Location

# Énumérations
class SourceType(str, PyEnum):
    scellee = "scellée"
    non_scellee = "non-scellée"

class EtatPhysique(str, PyEnum):
    solide = "solide"
    liquide = "liquide"
    gaz = "gaz"

class EtatUtilisation(str, PyEnum):
    en_utilisation = "en utilisation"
    remisee = "remisée"
    en_dechet = "en déchet"
    en_attente = "en attente"
    # Ajoutés pour correspondre au cahier des charges (04/07/2026) : les 4
    # valeurs ci-dessus existaient déjà et sont conservées (aucune source
    # existante n'est affectée) ; celles-ci s'y ajoutent.
    transferee = "transférée"
    detruite = "détruite"

class UniteQuantite(str, PyEnum):
    sans_objet = "sans objet"
    # Masse
    microgramme = "µg"
    mg = "mg"
    g = "g"
    kg = "kg"
    # Volume (liquides)
    mL = "mL"
    L = "L"
    # Pression (gaz)
    Pa = "Pa"
    kPa = "kPa"
    bar = "bar"

# États d'utilisation considérés comme "archivés" : la source n'est plus en
# circulation active. Elle sort de l'inventaire empruntable/consommable
# normal et ne reste consultable que dans la liste d'archives. Modifier une
# source déjà dans un de ces états est réservé aux administrateurs (pour
# corriger une erreur), et on ne peut plus lui ajouter de radionucléide, de
# consommation, ni démarrer un emprunt.
ETATS_ARCHIVES = (EtatUtilisation.remisee, EtatUtilisation.en_dechet, EtatUtilisation.transferee, EtatUtilisation.detruite)

def is_archived(source) -> bool:
    return source is not None and source.etat_utilisation in ETATS_ARCHIVES

# Modèle SQLAlchemy
class SourceDB(Base):
    __tablename__ = "sources"

    id = Column(String(50), primary_key=True, index=True)
    type = Column(Enum(SourceType), nullable=False)
    etat_physique = Column(Enum(EtatPhysique), nullable=False)
    etat_utilisation = Column(Enum(EtatUtilisation), nullable=False)
    date_arrivee = Column(Date, nullable=False)
    num_certificat_etalonnage = Column(String(100), nullable=True)
    num_source_fabricant = Column(String(100), nullable=True)
    lien_dossier_admin = Column(String(255), nullable=True)
    # "REFERENCE CATALOGUE" dans l'inventaire historique : référence du
    # modèle/catalogue fournisseur (ex: "EU152EGSB500KBQ"). Utilisée comme
    # colonne "Identification" dans l'export Annexe 1.
    reference_catalogue = Column(String(100), nullable=True)
    lieu_stockage = Column(String(100), nullable=False)
    matiere_nucleaire = Column(Boolean, default=False)
    quantite = Column(Float, nullable=True)
    unite_quantite = Column(Enum(UniteQuantite), nullable=True)
    # --- Champs ajoutés pour correspondre au cahier des charges ---
    fournisseur = Column(String(150), nullable=True)
    commentaire = Column(String(1000), nullable=True)
    # Quantité de départ, conservée séparément de `quantite` (qui diminue à
    # chaque consommation) pour pouvoir afficher "il reste X% du stock initial".
    quantite_initiale = Column(Float, nullable=True)
    # Uniquement pertinent pour les sources gazeuses (volume du récipient, en litres).
    volume_recipient_litres = Column(Float, nullable=True)  # historique ; conservé pour compatibilité, plus utilisé par le formulaire
    volume_recipient = Column(Float, nullable=True)
    unite_volume = Column(Enum(UniteQuantite), nullable=True)
    # Où se trouve la source EN CE MOMENT (mis à jour automatiquement par
    # les mouvements/emprunts).
    emplacement_actuel_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    # Où la source vit HABITUELLEMENT (son lieu de rangement par défaut,
    # directement modifiable depuis la fiche de la source — ce n'est PAS un
    # emprunt). Un emprunt part toujours de ce lieu et y revient au retour.
    emplacement_habituel_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # Relations
    radionuclides = relationship("RadionuclideDB", back_populates="source", cascade="all, delete-orphan")
    consumptions = relationship("ConsumptionDB", back_populates="source")
    movements = relationship("MovementDB", back_populates="source")
    emplacement_actuel = relationship("LocationDB", foreign_keys=[emplacement_actuel_id])
    emplacement_habituel = relationship("LocationDB", foreign_keys=[emplacement_habituel_id])

# Modèles Pydantic
class SourceBase(BaseModel):
    id: str
    type: SourceType
    etat_physique: EtatPhysique
    etat_utilisation: EtatUtilisation
    date_arrivee: date
    # Champ historique (texte libre) : conservé pour ne pas perdre les
    # données déjà importées, mais retiré du formulaire — remplacé par
    # emplacement_habituel_id (lieu structuré), jugé redondant à l'usage
    # (retour du 10/07/2026).
    lieu_stockage: Optional[str] = None
    matiere_nucleaire: bool = False
    quantite: Optional[float] = None
    unite_quantite: Optional[UniteQuantite] = None
    fournisseur: Optional[str] = None
    commentaire: Optional[str] = None
    quantite_initiale: Optional[float] = None
    volume_recipient_litres: Optional[float] = None  # historique ; conservé pour compatibilité
    volume_recipient: Optional[float] = None
    unite_volume: Optional[UniteQuantite] = None
    emplacement_habituel_id: Optional[int] = None

class SourceCreate(SourceBase):
    # Obligatoire à la création (contrairement à SourceBase) : plus de
    # source sans lieu structuré, décidé le 10/07/2026. Un lieu doit donc
    # exister avant la toute première source — d'où le bouton "+ Lieu"
    # ajouté directement sur la page Sources.
    emplacement_habituel_id: int
    num_certificat_etalonnage: Optional[str] = None
    num_source_fabricant: Optional[str] = None
    lien_dossier_admin: Optional[str] = None
    reference_catalogue: Optional[str] = None

class SourceUpdate(BaseModel):
    type: Optional[SourceType] = None
    etat_physique: Optional[EtatPhysique] = None
    etat_utilisation: Optional[EtatUtilisation] = None
    date_arrivee: Optional[date] = None
    num_certificat_etalonnage: Optional[str] = None
    num_source_fabricant: Optional[str] = None
    lien_dossier_admin: Optional[str] = None
    reference_catalogue: Optional[str] = None
    lieu_stockage: Optional[str] = None
    matiere_nucleaire: Optional[bool] = None
    quantite: Optional[float] = None
    unite_quantite: Optional[UniteQuantite] = None
    fournisseur: Optional[str] = None
    commentaire: Optional[str] = None
    quantite_initiale: Optional[float] = None
    volume_recipient_litres: Optional[float] = None  # historique ; conservé pour compatibilité
    volume_recipient: Optional[float] = None
    unite_volume: Optional[UniteQuantite] = None
    emplacement_habituel_id: Optional[int] = None

class Source(SourceBase):
    model_config = ConfigDict(from_attributes=True)
    num_certificat_etalonnage: Optional[str] = None
    num_source_fabricant: Optional[str] = None
    lien_dossier_admin: Optional[str] = None
    reference_catalogue: Optional[str] = None
    radionuclides: List[Radionuclide] = []
    emplacement_actuel: Optional[Location] = None
    emplacement_habituel: Optional[Location] = None
    # Calculée (décroissance moins consommations), pas stockée en base —
    # voir app/services/units.py:quantite_restante_calculee. None si le
    # calcul n'est pas possible (pas de radionucléide/période exploitable) ;
    # se rabattre alors sur le champ `quantite` (historique).
    quantite_calculee: Optional[float] = None
