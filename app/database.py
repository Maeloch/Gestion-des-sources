"""Configuration de la base de données SQLAlchemy."""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# Crée le dossier data/ s'il n'existe pas
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)

# Chemin vers le fichier SQLite
sqlite_path = data_dir / "database.sqlite"

# URL de connexion SQLite
SQLALCHEMY_DATABASE_URL = f"sqlite:///{sqlite_path}"

# Créer le moteur SQLAlchemy
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# Base pour les modèles
Base = declarative_base()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Générateur de session de base de données."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
