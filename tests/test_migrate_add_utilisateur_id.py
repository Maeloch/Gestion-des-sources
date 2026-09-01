"""Tests de la migration ajoutant utilisateur_id sur consumptions,
movements et audit_logs -- ajouté le 31/08/2026."""
import sqlite3

from app.scripts.migrate_add_utilisateur_id import migrate


def _creer_base_ancien_schema(chemin: str) -> None:
    """Construit une base minimale avec l'ANCIEN schéma (sans
    utilisateur_id), pour vérifier que la migration l'ajoute bien --
    plutôt que de supposer que create_all() suffit (il ne modifie
    jamais une table déjà existante, justement le problème réel
    rencontré en développant cette migration)."""
    conn = sqlite3.connect(chemin)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute("CREATE TABLE consumptions (id INTEGER PRIMARY KEY, utilisateur TEXT)")
    conn.execute("CREATE TABLE movements (id INTEGER PRIMARY KEY, utilisateur TEXT)")
    conn.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, utilisateur TEXT)")
    conn.commit()
    conn.close()


def test_migration_ajoute_la_colonne_sur_les_trois_tables(tmp_path):
    chemin = str(tmp_path / "test.sqlite")
    _creer_base_ancien_schema(chemin)

    migrate(chemin)

    conn = sqlite3.connect(chemin)
    for table in ("consumptions", "movements", "audit_logs"):
        colonnes = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        assert "utilisateur_id" in colonnes, f"utilisateur_id manquante sur {table}"
    conn.close()


def test_migration_sure_a_relancer_plusieurs_fois(tmp_path):
    chemin = str(tmp_path / "test.sqlite")
    _creer_base_ancien_schema(chemin)

    migrate(chemin)
    migrate(chemin)  # ne doit lever aucune exception (ex: colonne déjà là)

    conn = sqlite3.connect(chemin)
    colonnes = [r[1] for r in conn.execute("PRAGMA table_info(consumptions)").fetchall()]
    assert colonnes.count("utilisateur_id") == 1  # une seule fois, pas dupliquée
    conn.close()


def test_migration_ne_plante_pas_si_base_inexistante(tmp_path):
    chemin = str(tmp_path / "n_existe_pas.sqlite")
    migrate(chemin)  # ne doit lever aucune exception : la base sera créée directement à jour
