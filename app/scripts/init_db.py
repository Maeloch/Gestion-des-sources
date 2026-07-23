"""Script pour initialiser la base de données."""
from app.database import engine, Base
from app.models.source import SourceDB
from app.models.radionuclide import RadionuclideDB
from app.models.audit import AuditLogDB
from app.models.user import UserDB
from app.models.location import LocationDB
from app.models.consumption import ConsumptionDB
from app.models.movement import MovementDB
from app.models.lara_cache import LaraCacheDB
from app.models.role_request import RoleRequestDB

def init_db():
    """Initialise la base de données en créant toutes les tables."""
    print("Initialisation de la base de données...")
    Base.metadata.create_all(bind=engine)
    print("Base de données initialisée avec succès !")

if __name__ == "__main__":
    init_db()
