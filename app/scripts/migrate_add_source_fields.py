"""Migration : ajoute à la table `sources` les champs manquants par rapport
au cahier des charges (fournisseur, commentaire, quantite_initiale,
volume_recipient_litres).

Sûre à exécuter plusieurs fois (ne fait rien si les colonnes existent déjà).
Appelée automatiquement au démarrage de l'application (voir `app/main.py`).

Note sur `quantite_initiale` : pour les sources déjà existantes, on ne peut
pas savoir avec certitude quelle était leur quantité de départ (cette
information n'était pas suivie avant). Par défaut, cette migration recopie
la quantité *actuelle* comme quantité initiale pour les sources existantes —
c'est une approximation, pas une vraie donnée historique. Si tu connais les
vraies quantités de départ de tes sources existantes, corrige-les
manuellement depuis la pop-up de modification d'une source une fois
l'application lancée.
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
        cur.execute("PRAGMA table_info(sources)")
        columns = [row[1] for row in cur.fetchall()]

        changed = False

        if "fournisseur" not in columns:
            print("[migration] Ajout de la colonne 'fournisseur' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN fournisseur VARCHAR(150)")
            changed = True

        if "commentaire" not in columns:
            print("[migration] Ajout de la colonne 'commentaire' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN commentaire VARCHAR(1000)")
            changed = True

        if "quantite_initiale" not in columns:
            print("[migration] Ajout de la colonne 'quantite_initiale' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN quantite_initiale FLOAT")
            # Approximation pour les sources déjà existantes : voir docstring ci-dessus.
            cur.execute("UPDATE sources SET quantite_initiale = quantite WHERE quantite IS NOT NULL")
            changed = True

        if "volume_recipient_litres" not in columns:
            print("[migration] Ajout de la colonne 'volume_recipient_litres' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN volume_recipient_litres FLOAT")
            changed = True

        if changed:
            conn.commit()
            print("[migration] Terminé (nouveaux champs CDC sur 'sources').")
    finally:
        conn.close()


def migrate_consumptions(db_path: str = None) -> None:
    """Ajoute la colonne 'utilisateur' à la table consumptions si absente."""
    if db_path is None:
        db_path = str(Path("data") / "database.sqlite")

    if not Path(db_path).exists():
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(consumptions)")
        columns = [row[1] for row in cur.fetchall()]

        if "utilisateur" not in columns:
            print("[migration] Ajout de la colonne 'utilisateur' à la table 'consumptions'...")
            cur.execute("ALTER TABLE consumptions ADD COLUMN utilisateur VARCHAR(50)")
            conn.commit()
            print("[migration] Terminé (colonne 'utilisateur' sur 'consumptions').")

        if "masse_avant" not in columns:
            print("[migration] Ajout des colonnes 'masse_avant'/'masse_apres' à la table 'consumptions'...")
            cur.execute("ALTER TABLE consumptions ADD COLUMN masse_avant FLOAT")
            cur.execute("ALTER TABLE consumptions ADD COLUMN masse_apres FLOAT")
            conn.commit()
            print("[migration] Terminé (pesée double sur 'consumptions').")
    finally:
        conn.close()


def migrate_volume_recipient(db_path: str = None) -> None:
    """Ajoute les colonnes 'volume_recipient'/'unite_volume' (couple
    valeur+unité) à la table sources, en reportant les valeurs de
    l'ancienne colonne 'volume_recipient_litres' (toujours en litres, par
    construction de son nom) -- 12/07/2026."""
    if db_path is None:
        db_path = str(Path("data") / "database.sqlite")

    if not Path(db_path).exists():
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(sources)")
        columns = [row[1] for row in cur.fetchall()]

        if "volume_recipient" not in columns:
            print("[migration] Ajout des colonnes 'volume_recipient'/'unite_volume' à la table 'sources'...")
            cur.execute("ALTER TABLE sources ADD COLUMN volume_recipient FLOAT")
            cur.execute("ALTER TABLE sources ADD COLUMN unite_volume VARCHAR(20)")
            if "volume_recipient_litres" in columns:
                cur.execute(
                    "UPDATE sources SET volume_recipient = volume_recipient_litres, "
                    "unite_volume = 'L' WHERE volume_recipient_litres IS NOT NULL"
                )
            conn.commit()
            print("[migration] Terminé (volume_recipient/unite_volume sur 'sources', anciennes valeurs reportées en L).")
    finally:
        conn.close()


def migrate_radionuclides(db_path: str = None) -> None:
    """Ajoute la colonne 'activite_est_specifique' à la table radionuclides si absente."""
    if db_path is None:
        db_path = str(Path("data") / "database.sqlite")

    if not Path(db_path).exists():
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(radionuclides)")
        columns = [row[1] for row in cur.fetchall()]

        if "activite_est_specifique" not in columns:
            print("[migration] Ajout de la colonne 'activite_est_specifique' à la table 'radionuclides'...")
            # Par défaut à 0 (False) pour tous les radionucléides déjà
            # existants : on ne change pas l'interprétation de leurs
            # activités déjà saisies (comportement historique préservé).
            cur.execute("ALTER TABLE radionuclides ADD COLUMN activite_est_specifique BOOLEAN DEFAULT 0")
            conn.commit()
            print("[migration] Terminé (colonne 'activite_est_specifique' sur 'radionuclides').")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    migrate_consumptions()
    migrate_radionuclides()
