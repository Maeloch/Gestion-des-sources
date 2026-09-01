"""Migration : ajoute la colonne `utilisateur_id` (clé étrangère vers
`users.id`) sur `consumptions`, `movements` et `audit_logs` -- demandé le
31/08/2026, pour relier le texte `utilisateur` déjà présent à un
véritable enregistrement utilisateur plutôt qu'un simple nom libre.

Cette migration est sûre à exécuter plusieurs fois : si la colonne
existe déjà sur une table, elle ne fait rien pour celle-ci. Elle est
appelée automatiquement au démarrage de l'application (voir
`app/main.py`), donc rien à faire manuellement. Elle ne fait QUE créer
la colonne (structure) -- le rattachement effectif des lignes déjà en
base à un utilisateur existant ou nouvellement créé est une étape
séparée et volontairement distincte (voir
`app/scripts/rattacher_utilisateurs_historiques.py`), pour ne jamais
mélanger "faire évoluer le schéma" et "modifier des données".
"""
import sqlite3
from pathlib import Path


TABLES = ["consumptions", "movements", "audit_logs"]


def migrate(db_path: str = None) -> None:
    if db_path is None:
        db_path = str(Path("data") / "database.sqlite")

    if not Path(db_path).exists():
        # Pas encore de base de données : elle sera créée directement avec
        # le nouveau schéma (colonne déjà présente), rien à migrer.
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for table in TABLES:
            cur.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cur.fetchall()]
            if not columns:
                continue  # table pas encore créée (base très ancienne/partielle) : rien à migrer ici
            if "utilisateur_id" in columns:
                continue  # déjà migré, rien à faire pour cette table

            print(f"[migration] Ajout de la colonne 'utilisateur_id' à la table '{table}'...")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN utilisateur_id INTEGER REFERENCES users(id)")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
