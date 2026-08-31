"""Tests du script d'application d'une version fraîchement décompressée
sur un dossier stable existant (app/scripts/appliquer_version.py) --
ajouté le 22/07/2026."""
import subprocess
import sys
import pytest


import shutil as _shutil
from pathlib import Path as _Path

_VRAI_SCRIPT = _Path(__file__).resolve().parent.parent / "app" / "scripts" / "appliquer_version.py"


def _preparer_source(tmp_path, version="0.1.99"):
    """Simule 'ce dossier' (une nouvelle version fraîchement décompressée).
    Le script appliquer_version.py doit être une copie du VRAI fichier
    (pas un texte factice) : c'est lui qu'on exécute via `python -m`, et
    son calcul de SOURCE (Path(__file__).parent.parent.parent) doit
    correctement désigner CE dossier simulé une fois copié ici."""
    source = tmp_path / "nouvelle_version"
    (source / "app" / "scripts").mkdir(parents=True)
    (source / "app" / "main.py").write_text("# nouveau contenu")
    (source / "app" / "version.py").write_text(f'APP_VERSION = "{version}"\n')
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


def _charger_module_depuis(source):
    """Charge le script appliquer_version.py copié dans `source` comme un
    module Python -- son calcul de SOURCE (Path(__file__).parent.parent.parent)
    désigne alors correctement ce dossier simulé, nécessaire pour que
    verifier_version_en_ligne() lise la bonne version attendue."""
    import importlib.util
    chemin_script = source / "app" / "scripts" / "appliquer_version.py"
    spec = importlib.util.spec_from_file_location("appliquer_version_test_verif", chemin_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verifie_version_en_ligne_correspond(tmp_path, capsys):
    """31/07/2026 : ajouté après qu'un avertissement textuel seul se soit
    montré insuffisant en pratique (V0.1.34 restée active plusieurs
    versions après son remplacement sur disque, sans que ça se voie
    autrement)."""
    source = _preparer_source(tmp_path, version="0.1.99")
    module = _charger_module_depuis(source)

    import unittest.mock
    reponse_simulee = unittest.mock.Mock()
    reponse_simulee.json.return_value = {"version": "0.1.99"}
    with unittest.mock.patch("requests.get", return_value=reponse_simulee):
        with unittest.mock.patch("time.sleep"):  # pas la peine d'attendre pendant les tests
            module.verifier_version_en_ligne()

    sortie = capsys.readouterr().out
    assert "Vérifié en ligne" in sortie
    assert "0.1.99" in sortie

def test_verifie_version_en_ligne_ne_correspond_pas(tmp_path, capsys):
    """Le cas réel rencontré : le serveur déjà lancé répond encore avec
    l'ancienne version -- doit être signalé de façon impossible à rater,
    pas seulement dans un avertissement textuel qu'on peut manquer."""
    source = _preparer_source(tmp_path, version="0.1.99")
    module = _charger_module_depuis(source)

    import unittest.mock
    reponse_simulee = unittest.mock.Mock()
    reponse_simulee.json.return_value = {"version": "0.1.34"}
    with unittest.mock.patch("requests.get", return_value=reponse_simulee):
        with unittest.mock.patch("time.sleep"):
            module.verifier_version_en_ligne()

    sortie = capsys.readouterr().out
    assert "ATTENTION" in sortie
    assert "0.1.34" in sortie
    assert "0.1.99" in sortie
    assert "relance" in sortie.lower()


def test_verifie_version_en_ligne_serveur_injoignable_ne_bloque_pas(tmp_path, capsys):
    """Si le serveur n'est pas joignable (pas encore lancé, port
    différent...), la vérification doit se signaler sans jamais lever
    d'exception -- ce n'est qu'une vérification de confort."""
    source = _preparer_source(tmp_path, version="0.1.99")
    module = _charger_module_depuis(source)

    import unittest.mock
    with unittest.mock.patch("requests.get", side_effect=ConnectionError("refused")):
        with unittest.mock.patch("time.sleep"):
            module.verifier_version_en_ligne()  # ne doit lever aucune exception

    assert "non concluante" in capsys.readouterr().out


def test_endpoint_version_renvoie_la_version_courante(admin_client):
    """L'endpoint /version lui-même, côté application -- utilisé par
    verifier_version_en_ligne() ci-dessus, doit renvoyer un JSON simple
    avec la version en cours, sans authentification nécessaire."""
    from app.version import APP_VERSION
    reponse = admin_client.get("/version")
    assert reponse.status_code == 200
    assert reponse.json() == {"version": APP_VERSION}


def test_nettoyer_cache_bytecode_supprime_tous_les_pycache(tmp_path):
    module = _charger_module_depuis(_preparer_source(tmp_path))
    cible = tmp_path / "cible_avec_cache"
    (cible / "app" / "sous_dossier").mkdir(parents=True)
    (cible / "app" / "__pycache__").mkdir()
    (cible / "app" / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"factice")
    (cible / "app" / "sous_dossier" / "__pycache__").mkdir()
    (cible / "app" / "sous_dossier" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"factice")

    module.nettoyer_cache_bytecode(cible)

    assert not (cible / "app" / "__pycache__").exists()
    assert not (cible / "app" / "sous_dossier" / "__pycache__").exists()


def test_nettoyer_cache_bytecode_ne_plante_pas_si_aucun_cache(tmp_path):
    module = _charger_module_depuis(_preparer_source(tmp_path))
    cible = tmp_path / "cible_sans_cache"
    (cible / "app").mkdir(parents=True)
    module.nettoyer_cache_bytecode(cible)  # ne doit lever aucune exception


def test_reproduction_complete_du_bug_et_de_son_correctif(tmp_path):
    """Reproduction de bout en bout du cas réel signalé : un fichier .py
    remplacé se retrouve avec exactement le même (date de modification,
    taille en octets) que l'ancien -- suffisant pour tromper la
    vérification par défaut de Python et faire tourner silencieusement
    le bytecode compilé de l'ANCIENNE version. Vérifié dans les DEUX
    sens : sans nettoyer_cache_bytecode(), le bug se produit bien (pour
    prouver que le correctif est réellement nécessaire, pas superflu) ;
    avec, il ne se produit plus."""
    import subprocess as sp
    import os

    def version_vue_par_un_processus_frais(dossier_app_parent):
        resultat = sp.run(
            [sys.executable, "-c", "from app.version import APP_VERSION; print(APP_VERSION)"],
            cwd=str(dossier_app_parent), capture_output=True, text=True,
        )
        return resultat.stdout.strip()

    cible = tmp_path / "cible"
    (cible / "app").mkdir(parents=True)
    (cible / "app" / "__init__.py").write_text("")
    (cible / "app" / "version.py").write_text('APP_VERSION = "0.1.34"')
    mtime_original = 1785492000.0  # horodatage fixe, reproductible
    os.utime(cible / "app" / "version.py", (mtime_original, mtime_original))
    assert version_vue_par_un_processus_frais(cible) == "0.1.34"  # __pycache__ créé au passage

    # Remplacement par la nouvelle version, avec EXACTEMENT le même mtime
    # et la même taille en octets (le cas de collision reproduit) :
    # même nombre de caractères que "0.1.34".
    (cible / "app" / "version.py").write_text('APP_VERSION = "0.1.99"')
    os.utime(cible / "app" / "version.py", (mtime_original, mtime_original))
    assert (cible / "app" / "version.py").stat().st_size == len('APP_VERSION = "0.1.34"')

    # Sans le correctif : le bug se produit (preuve qu'il est nécessaire).
    assert version_vue_par_un_processus_frais(cible) == "0.1.34"

    # Avec le correctif : le cache est nettoyé, un processus frais lit
    # bien la nouvelle version, quel que soit le mtime.
    module = _charger_module_depuis(_preparer_source(tmp_path))
    module.nettoyer_cache_bytecode(cible)
    assert version_vue_par_un_processus_frais(cible) == "0.1.99"


def test_resoudre_dubious_ownership_extrait_le_chemin_avec_espaces(tmp_path):
    """31/08/2026, cas réel signalé : git refuse d'opérer sur un dépôt
    dont il ne peut pas vérifier proprement le propriétaire -- fréquent
    sur un lecteur réseau mappé (M:\\... vers un partage SMB), même sans
    rien de réellement compromis (CVE-2022-24765). git indique lui-même
    la commande exacte pour lever ce blocage -- reprise telle quelle
    plutôt que reconstruite, le format exact (préfixe %(prefix)/// pour
    les chemins réseau) dépendant de la version de git installée."""
    from app.scripts.appliquer_version import _resoudre_dubious_ownership_si_applicable
    import unittest.mock

    erreur_reelle_rapportee = (
        "fatal: detected dubious ownership in repository at "
        "'//stockagefont/Metiers/SCA-SUIVI PHYSIQUE/Inventaires/Gestion des sources/current'\n"
        "'//stockagefont/Metiers/SCA-SUIVI PHYSIQUE/Inventaires/Gestion des sources/current' "
        "may refer to a non-local directory\n"
        "To add an exception for this directory, call:\n\n"
        "\tgit config --global --add safe.directory "
        "'%(prefix)///stockagefont/Metiers/SCA-SUIVI PHYSIQUE/Inventaires/Gestion des sources/current'\n"
    )

    with unittest.mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = unittest.mock.Mock(returncode=0)
        resultat = _resoudre_dubious_ownership_si_applicable(erreur_reelle_rapportee, tmp_path)

    assert resultat is True
    chemin_utilise = mock_run.call_args[0][0][-1]  # dernier argument de la commande git appelée
    assert chemin_utilise == "%(prefix)///stockagefont/Metiers/SCA-SUIVI PHYSIQUE/Inventaires/Gestion des sources/current"


def test_resoudre_dubious_ownership_ignore_les_autres_erreurs(tmp_path):
    """Une erreur git différente (pas de dubious ownership) ne doit
    jamais déclencher de tentative de correctif -- ce serait un
    correctif sans rapport avec le problème réel."""
    from app.scripts.appliquer_version import _resoudre_dubious_ownership_si_applicable
    resultat = _resoudre_dubious_ownership_si_applicable("fatal: not a git repository", tmp_path)
    assert resultat is False


def test_reproduction_reelle_dubious_ownership_et_correctif(tmp_path):
    """Reproduction de bout en bout avec un vrai dépôt git, pas
    seulement un message d'erreur simulé : un dossier dont le
    propriétaire diffère de l'utilisateur courant déclenche réellement
    le blocage de git, et le correctif le résout réellement (le commit,
    qui aurait échoué sinon, aboutit). Ignoré si l'environnement de test
    ne permet pas de changer le propriétaire d'un fichier (nécessite les
    privilèges root sur la plupart des systèmes)."""
    import os
    import pwd
    if os.geteuid() != 0:
        pytest.skip("nécessite les privilèges root pour changer le propriétaire d'un fichier")
    try:
        autre_utilisateur = pwd.getpwnam("nobody")
    except KeyError:
        pytest.skip("utilisateur 'nobody' introuvable sur ce système")

    depot = tmp_path / "depot avec espaces"
    (depot / "app").mkdir(parents=True)
    (depot / "app" / "version.py").write_text('APP_VERSION = "0.1.40"')
    (depot / "app" / "main.py").write_text("# initial")

    subprocess.run(["git", "init", "-q"], cwd=depot, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.fr"], cwd=depot, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=depot, check=True)
    subprocess.run(["git", "add", "-A"], cwd=depot, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "premier commit"], cwd=depot, check=True)

    (depot / "app" / "main.py").write_text("# modifie par la mise a jour")
    for chemin in [depot] + list(depot.rglob("*")):
        os.chown(chemin, autre_utilisateur.pw_uid, autre_utilisateur.pw_gid)

    module = _charger_module_depuis(_preparer_source(tmp_path))
    from app.version import APP_VERSION  # celle du vrai projet, utilisée par commit_git_si_applicable
    try:
        module.commit_git_si_applicable(depot)
        # Vérifié PENDANT que le dossier est encore déclaré sûr (sinon
        # cette commande échouerait elle-même pour la même raison).
        log = subprocess.run(["git", "log", "--oneline"], cwd=depot, capture_output=True, text=True)
        assert f"Mise à jour vers V{APP_VERSION}" in log.stdout
    finally:
        # Nettoyage : sinon la config globale reste modifiée pour de bon
        # sur la machine qui exécute les tests.
        subprocess.run(["git", "config", "--global", "--unset-all", "safe.directory"], capture_output=True)
