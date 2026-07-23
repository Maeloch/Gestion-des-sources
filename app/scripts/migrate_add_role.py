"""Migration : fait passer la table `users` de l'ancien système
(colonne booléenne `is_admin`) au nouveau système à 4 rôles (colonne `role`).

Cette migration est sûre à exécuter plusieurs fois : si la colonne `role`
existe déjà, elle ne fait rien. Elle est appelée automatiquement au
démarrage de l'application (voir `app/main.py`), donc tu n'as normalement
rien à faire manuellement. Elle reste disponible en ligne de commande pour
information ou en cas de souci :

    python -m app.scripts.migrate_add_role
"""
import sqlite3
from pathlib import Path


def migrate(db_path: str = None) -> None:
    if db_path is None:
        db_path = str(Path("data") / "database.sqlite")

    if not Path(db_path).exists():
        # Pas encore de base de données : elle sera créée directement avec
        # le nouveau schéma (colonne `role`), rien à migrer.
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cur.fetchall()]

        if "role" in columns:
            return  # déjà migré, rien à faire

        print("[migration] Ajout de la colonne 'role' à la table 'users'...")
        cur.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20)")

        if "is_admin" in columns:
            # Les anciens admins restent admins ; les anciens non-admins
            # passent en 'utilisateur_mn' (accès complet hors administration)
            # pour ne pas leur retirer silencieusement des droits qu'ils
            # avaient déjà avec l'ancien système, qui ne connaissait pas
            # encore la distinction Matière Nucléaire / lecture seule.
            cur.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1")
            cur.execute(
                "UPDATE users SET role = 'utilisateur_mn' WHERE is_admin = 0 OR is_admin IS NULL"
            )
        # Filet de sécurité si jamais une ligne n'a toujours pas de rôle
        cur.execute("UPDATE users SET role = 'utilisateur_mn' WHERE role IS NULL")

        conn.commit()
        print("[migration] Terminé : rôles attribués à partir de l'ancien statut admin.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
