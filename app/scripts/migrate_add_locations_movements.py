"""Migration : ajoute les colonnes nécessaires au système de lieux et
d'emprunts (cycle sortie / retour d'une source).

- table `locations` : site, batiment, piece
- table `sources` : emplacement_actuel_id (où se trouve la source maintenant)
- table `movements` : date_retour_prevue, date_retour_reelle, utilisateur

Sûre à exécuter plusieurs fois. Appelée automatiquement au démarrage de
l'application (voir `app/main.py`).
"""
import sqlite3
from pathlib import Path


def migrate(db_path: str = None) -> None:
    if db_path is None:
        db_path = str(Path("data") / "database.sqlite")

    if not Path(db_path).exists():
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # --- locations ---
        cur.execute("PRAGMA table_info(locations)")
        loc_columns = [row[1] for row in cur.fetchall()]
        for col in ("site", "batiment", "piece"):
            if col not in loc_columns:
                print(f"[migration] Ajout de la colonne '{col}' à la table 'locations'...")
                cur.execute(f"ALTER TABLE locations ADD COLUMN {col} VARCHAR(100)")

        # --- sources ---
        cur.execute("PRAGMA table_info(sources)")
        source_columns = [row[1] for row in cur.fetchall()]
        if "emplacement_actuel_id" not in source_columns:
            print("[migration] Ajout de la colonne 'emplacement_actuel_id' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN emplacement_actuel_id INTEGER REFERENCES locations(id)")
        if "emplacement_habituel_id" not in source_columns:
            print("[migration] Ajout de la colonne 'emplacement_habituel_id' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN emplacement_habituel_id INTEGER REFERENCES locations(id)")
        if "reference_catalogue" not in source_columns:
            print("[migration] Ajout de la colonne 'reference_catalogue' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN reference_catalogue VARCHAR(100)")

        # --- lara_cache (nouvelle table) ---
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lara_cache'")
        if not cur.fetchone():
            print("[migration] Création de la table 'lara_cache'...")
            cur.execute("""
                CREATE TABLE lara_cache (
                    nuclide VARCHAR(20) PRIMARY KEY,
                    element VARCHAR(50),
                    z INTEGER,
                    half_life_years FLOAT,
                    half_life_seconds FLOAT,
                    specific_activity_bq_g FLOAT,
                    reference VARCHAR(255),
                    fetched_at DATETIME NOT NULL
                )
            """)

        # --- role_requests (nouvelle table) ---
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='role_requests'")
        if not cur.fetchone():
            print("[migration] Création de la table 'role_requests'...")
            cur.execute("""
                CREATE TABLE role_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(50) NOT NULL,
                    role_demande VARCHAR(20) NOT NULL,
                    statut VARCHAR(20) NOT NULL DEFAULT 'en_attente',
                    commentaire VARCHAR(500),
                    date_demande DATETIME NOT NULL,
                    traite_par VARCHAR(50),
                    date_traitement DATETIME
                )
            """)

        # --- movements ---
        cur.execute("PRAGMA table_info(movements)")
        movement_columns = [row[1] for row in cur.fetchall()]
        needs_backfill = "date_retour_reelle" not in movement_columns
        if "date_retour_prevue" not in movement_columns:
            print("[migration] Ajout de la colonne 'date_retour_prevue' à la table 'movements'...")
            cur.execute("ALTER TABLE movements ADD COLUMN date_retour_prevue DATE")
        if "date_retour_reelle" not in movement_columns:
            print("[migration] Ajout de la colonne 'date_retour_reelle' à la table 'movements'...")
            cur.execute("ALTER TABLE movements ADD COLUMN date_retour_reelle DATE")
        if "utilisateur" not in movement_columns:
            print("[migration] Ajout de la colonne 'utilisateur' à la table 'movements'...")
            cur.execute("ALTER TABLE movements ADD COLUMN utilisateur VARCHAR(50)")

        if needs_backfill:
            # Les mouvements déjà enregistrés avant l'existence du cycle
            # emprunt/retour n'avaient pas cette notion : on les considère
            # comme déjà clôturés (retournés le jour même) plutôt que de les
            # faire apparaître comme "en cours" dans la nouvelle interface.
            cur.execute(
                "UPDATE movements SET date_retour_reelle = date(timestamp) WHERE date_retour_reelle IS NULL"
            )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
