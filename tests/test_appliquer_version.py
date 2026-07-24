"""Tests du script d'application d'une version fraîchement décompressée
sur un dossier stable existant (app/scripts/appliquer_version.py) --
ajouté le 22/07/2026."""
import subprocess
import pytest


import shutil as _shutil
from pathlib import Path as _Path

_VRAI_SCRIPT = _Path(__file__).resolve().parent.parent / "app" / "scripts" / "appliquer_version.py"


def _preparer_source(tmp_path):
    """Simule 'ce dossier' (une nouvelle version fraîchement décompressée).
    Le script appliquer_version.py doit être une copie du VRAI fichier
    (pas un texte factice) : c'est lui qu'on exécute via `python -m`, et
    son calcul de SOURCE (Path(__file__).parent.parent.parent) doit
    correctement désigner CE dossier simulé une fois copié ici."""
    source = tmp_path / "nouvelle_version"
    (source / "app" / "scripts").mkdir(parents=True)
    (source / "app" / "main.py").write_text("# nouveau contenu")
    _shutil.copy2(_VRAI_SCRIPT, source / "app" / "scripts" / "appliquer_version.py")
    (source / "data").mkdir()
    (source / "data" / "database.sqlite").write_text("base neuve et vide livree avec le zip")
    (source / ".env").write_text("SECRET_KEY=secret_livre_avec_le_zip")
    return source


def _preparer_cible(tmp_path, avec_git=True, avec_vieux_fichier=True):
    cible = tmp_path / "installation_stable"
    (cible / "app").mkdir(parents=True)
    (cible / "data").mkdir()
    (cible / "app" / "main.py").write_text("# ancien contenu")
    (cible / "data" / "database.sqlite").write_text("VRAIE BASE - NE JAMAIS ECRASER")
    (cible / ".env").write_text("SECRET_KEY=vrai_secret_de_l_utilisateur")
    if avec_vieux_fichier:
        (cible / "app" / "fichier_disparu_dans_la_nouvelle_version.py").write_text("vieux code")
    if avec_git:
        subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=cible, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.fr"], cwd=cible, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=cible, check=True)
        subprocess.run(["git", "add", "-A"], cwd=cible, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "etat initial"], cwd=cible, check=True)
    return cible


def _lancer_script(source, cible):
    import sys
    return subprocess.run(
        [sys.executable, "-m", "app.scripts.appliquer_version", str(cible)],
        cwd=source, capture_output=True, text=True,
    )


def test_ne_touche_jamais_la_vraie_base_ni_le_vrai_env(tmp_path):
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path)

    resultat = _lancer_script(source, cible)
    assert resultat.returncode == 0, resultat.stderr

    assert (cible / "data" / "database.sqlite").read_text() == "VRAIE BASE - NE JAMAIS ECRASER"
    assert (cible / ".env").read_text() == "SECRET_KEY=vrai_secret_de_l_utilisateur"


def test_copie_bien_les_nouveaux_fichiers(tmp_path):
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path)

    _lancer_script(source, cible)

    assert (cible / "app" / "main.py").read_text() == "# nouveau contenu"
    assert (cible / "app" / "scripts" / "appliquer_version.py").exists()


def test_ne_supprime_pas_un_fichier_absent_de_la_nouvelle_version(tmp_path):
    """Une copie n'efface jamais ce qu'elle ne remplace pas -- limite
    connue, à mentionner à l'utilisateur plutôt qu'un vrai defaut, mais
    qui doit rester vraie (pas de suppression surprise)."""
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_vieux_fichier=True)

    _lancer_script(source, cible)

    assert (cible / "app" / "fichier_disparu_dans_la_nouvelle_version.py").exists()


def test_cree_un_commit_git_si_le_depot_existe(tmp_path):
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_git=True)

    _lancer_script(source, cible)

    log = subprocess.run(["git", "log", "--oneline"], cwd=cible, capture_output=True, text=True)
    assert log.stdout.count("\n") == 2  # le commit initial + le nouveau


def test_ignore_gracieusement_l_absence_de_git(tmp_path):
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_git=False)

    resultat = _lancer_script(source, cible)

    assert resultat.returncode == 0
    assert "n'est pas un dépôt git" in resultat.stdout
    assert not (cible / ".git").exists()


def test_refuse_un_dossier_cible_inexistant(tmp_path):
    source = _preparer_source(tmp_path)
    resultat = _lancer_script(source, tmp_path / "nexiste_pas")
    assert resultat.returncode == 1


def test_refuse_un_dossier_cible_qui_ne_ressemble_pas_a_l_appli(tmp_path):
    source = _preparer_source(tmp_path)
    cible_invalide = tmp_path / "dossier_quelconque"
    cible_invalide.mkdir()
    (cible_invalide / "fichier.txt").write_text("surprise")

    resultat = _lancer_script(source, cible_invalide)

    assert resultat.returncode == 1
    # Rien ne doit avoir été copié dans un dossier qui n'a pas l'air d'être une installation.
    assert list(cible_invalide.iterdir()) == [cible_invalide / "fichier.txt"]


def test_sauvegarde_la_base_du_dossier_cible_avant_la_copie(tmp_path):
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path)

    _lancer_script(source, cible)

    sauvegardes = list((cible / "data" / "backups").glob("database-avant-maj-*.sqlite"))
    assert len(sauvegardes) == 1
    assert sauvegardes[0].read_text() == "VRAIE BASE - NE JAMAIS ECRASER"


def _preparer_remote_bare(tmp_path):
    """Un vrai dépôt bare local, servant de dépôt distant simulé (comme
    GitHub) -- permet de tester le push automatique pour de vrai, pas
    seulement en théorie."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "--initial-branch=main", str(remote)], check=True)
    return remote


def test_pousse_automatiquement_si_un_remote_est_configure(tmp_path):
    """23/07/2026, demandé directement ("pourquoi ce n'est pas
    automatique ?") : un commit doit être suivi d'un push automatique
    vers le dépôt distant, s'il y en a un de configuré."""
    remote = _preparer_remote_bare(tmp_path)
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_git=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=cible, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=cible, check=True)

    resultat = _lancer_script(source, cible)

    assert resultat.returncode == 0
    assert "Poussé vers le dépôt distant avec succès" in resultat.stdout
    log_distant = subprocess.run(
        ["git", "log", "--oneline", "main"], cwd=remote, capture_output=True, text=True,
    )
    assert log_distant.stdout.count("\n") == 2  # le commit initial + celui de la mise à jour


def test_ignore_gracieusement_l_absence_de_remote(tmp_path):
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_git=True)  # dépôt git local, mais AUCUN remote configuré

    resultat = _lancer_script(source, cible)

    assert resultat.returncode == 0
    assert "Aucun dépôt distant configuré" in resultat.stdout


def test_echec_du_push_ne_fait_pas_echouer_le_script(tmp_path):
    """Un push refusé (dépôt distant qui a avancé ailleurs, ex: mise à
    jour faite depuis un autre poste entre-temps) ne doit jamais faire
    échouer toute la mise à jour : le commit local, lui, a déjà réussi et
    doit être conservé."""
    remote = _preparer_remote_bare(tmp_path)
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_git=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=cible, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=cible, check=True)

    # Simule un autre poste qui pousse une modification concurrente,
    # faisant avancer le distant sans que "cible" ne le sache.
    autre_poste = tmp_path / "autre_poste"
    subprocess.run(["git", "clone", "-q", str(remote), str(autre_poste)], check=True)
    subprocess.run(["git", "config", "user.email", "t@t.fr"], cwd=autre_poste, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=autre_poste, check=True)
    (autre_poste / "app" / "main.py").write_text("# modif concurrente")
    subprocess.run(["git", "add", "-A"], cwd=autre_poste, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "modif concurrente"], cwd=autre_poste, check=True)
    subprocess.run(["git", "push", "-q"], cwd=autre_poste, check=True)

    resultat = _lancer_script(source, cible)

    assert resultat.returncode == 0  # ne plante jamais
    assert "ATTENTION : échec du push" in resultat.stderr
    # Le commit local a bien eu lieu malgré l'échec du push.
    log_local = subprocess.run(["git", "log", "--oneline"], cwd=cible, capture_output=True, text=True)
    assert "Mise à jour vers" in log_local.stdout


def test_avertit_sur_windows_du_risque_de_cascade_de_rechargement(tmp_path):
    """24/07/2026, cas réel rencontré : sur Windows, avec --reload actif
    et beaucoup de fichiers modifiés d'un coup (le cas normal pour ce
    script), plusieurs tentatives de rechargement peuvent se marcher
    dessus (confirmé par un vrai journal de serveur fourni par
    l'utilisateur -- neuf tentatives interrompues d'affilée avant qu'une
    ne finisse par aboutir). Un avertissement explicite doit apparaître
    UNIQUEMENT sur Windows, invitant à vérifier la version affichée et à
    redémarrer manuellement en cas de doute."""
    source = _preparer_source(tmp_path)
    cible = _preparer_cible(tmp_path, avec_git=False)

    import unittest.mock
    with unittest.mock.patch("platform.system", return_value="Windows"):
        # Le sous-processus, lui, tourne dans un VRAI interprète Python
        # séparé (subprocess.run) : ce monkeypatch ne l'atteint pas.
        # Ce test vérifie donc directement la fonction plutôt que le
        # sous-processus complet, contrairement aux autres tests de ce
        # fichier -- nécessaire ici puisque le comportement dépend de la
        # plateforme d'exécution, qu'on ne peut pas simuler à travers un
        # sous-processus indépendant.
        import importlib.util
        spec = importlib.util.spec_from_file_location("appliquer_version_test", _VRAI_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        import io
        import contextlib
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            module.forcer_rechargement(cible)

    assert "ATTENTION (Windows)" in sortie.getvalue()
    assert "lecteur réseau" in sortie.getvalue()


def test_pas_d_avertissement_windows_hors_windows(tmp_path):
    cible = _preparer_cible(tmp_path, avec_git=False)

    import unittest.mock
    with unittest.mock.patch("platform.system", return_value="Linux"):
        import importlib.util
        spec = importlib.util.spec_from_file_location("appliquer_version_test2", _VRAI_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        import io
        import contextlib
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            module.forcer_rechargement(cible)

    assert "ATTENTION (Windows)" not in sortie.getvalue()
