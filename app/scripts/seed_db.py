"""Script pour peupler la base de données avec des données de test."""
from app.database import SessionLocal
from app.models.source import SourceDB, SourceType, EtatPhysique, EtatUtilisation, UniteQuantite
from app.models.radionuclide import RadionuclideDB
from app.models.user import UserDB, UserRole
from app.security.auth import get_password_hash
from datetime import date

def seed_db():
    db = SessionLocal()
    try:
        # Ajoute un utilisateur admin (uniquement s'il n'existe pas déjà)
        if not db.query(UserDB).filter(UserDB.username == "admin").first():
            hashed_password = get_password_hash("admin123")
            admin = UserDB(
                username="admin",
                email="admin@example.com",
                hashed_password=hashed_password,
                full_name="Admin User",
                role=UserRole.admin,
            )
            db.add(admin)

        # Ajoute une source de test (uniquement si elle n'existe pas déjà)
        if not db.query(SourceDB).filter(SourceDB.id == "SRC-001").first():
            source = SourceDB(
                id="SRC-001",
                type=SourceType.scellee,
                etat_physique=EtatPhysique.solide,
                etat_utilisation=EtatUtilisation.en_utilisation,
                date_arrivee=date(2023, 1, 1),
                lieu_stockage="Salle A",
                matiere_nucleaire=True,
                quantite=100.0,
                unite_quantite=UniteQuantite.g,
            )
            db.add(source)
            db.flush()  # pour que la FK ci-dessous trouve bien la source

            # Ajoute un radionucléide de test, rattaché à cette source
            radionuclide = RadionuclideDB(
                source_id="SRC-001",
                nom="Cs-137",
                activite=1000.0,
                unite_activite="Bq",
                date_reference=date(2023, 1, 1),
                periode=30.0,  # 30 ans
                lien_laraweb="http://www.lnhb.fr/Laraweb/Results/Cs-137.lara.txt",
            )
            db.add(radionuclide)

        db.commit()
        print("Base de données peuplée avec succès !")
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
