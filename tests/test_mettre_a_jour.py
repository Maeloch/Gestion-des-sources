"""Tests du script de mise à jour (app/scripts/mettre_a_jour.py) --
ajouté le 21/07/2026. Le vrai `git pull` a été vérifié manuellement avec
un dépôt distant réel (voir le rapport de diagnostic) plutôt qu'ici : le
simuler proprement en test automatisé demanderait de construire un dépôt
git complet à chaque exécution, pour un bénéfice marginal par rapport à
cette vérification déjà faite. Les tests ci-dessous couvrent les parties
qui ne dépendent pas d'un dépôt distant : la sauvegarde de la base et le
déclenchement du rechargement."""
import importlib


def test_sauvegarder_bdd_cree_une_copie_horodatee(tmp_path, monkeypatch):
    from app.scripts import mettre_a_jour
    monkeypatch.setattr(mettre_a_jour, "RACINE", tmp_path)

    (tmp_path / "data").mkdir()
    bdd = tmp_path / "data" / "database.sqlite"
    bdd.write_text("contenu de test")

    mettre_a_jour.sauvegarder_bdd()

    sauvegardes = list((tmp_path / "data" / "backups").glob("database-avant-maj-*.sqlite"))
    assert len(sauvegardes) == 1
    assert sauvegardes[0].read_text() == "contenu de test"


def test_sauvegarder_bdd_sans_base_existante_ne_plante_pas(tmp_path, monkeypatch, capsys):
    from app.scripts import mettre_a_jour
    monkeypatch.setattr(mettre_a_jour, "RACINE", tmp_path)

    mettre_a_jour.sauvegarder_bdd()  # pas de data/database.sqlite du tout

    assert not (tmp_path / "data" / "backups").exists()
    assert "première installation" in capsys.readouterr().out.lower()


def test_forcer_rechargement_change_la_date_de_modification(tmp_path, monkeypatch):
    from app.scripts import mettre_a_jour
    monkeypatch.setattr(mettre_a_jour, "RACINE", tmp_path)

    (tmp_path / "app").mkdir()
    principal = tmp_path / "app" / "main.py"
    principal.write_text("# contenu")
    mtime_avant = principal.stat().st_mtime

    import time
    time.sleep(0.05)
    mettre_a_jour.forcer_rechargement()

    assert principal.stat().st_mtime > mtime_avant
    assert principal.read_text() == "# contenu"  # le contenu, lui, ne change jamais
