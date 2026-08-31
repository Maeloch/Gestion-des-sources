"""Applique le contenu d'une nouvelle version (CE dossier, fraîchement
décompressé depuis l'archive reçue) sur un dossier stable existant --
demandé le 22/07/2026, pensé spécifiquement pour l'organisation actuelle
(un nouveau dossier V0.1.XX à chaque nouvelle version reçue), sans
obliger à tout réorganiser autour de git dès maintenant.

Usage : depuis CE dossier (la nouvelle version fraîchement décompressée,
PAS le dossier stable) :

    python -m app.scripts.appliquer_version /chemin/vers/mon/dossier/stable

Ce que fait ce script, dans l'ordre :

1. Vérifie que le dossier cible existe et ressemble à une installation
   valide (présence de app/main.py) -- sécurité, pour ne jamais copier
   par erreur vers un dossier qui n'a rien à voir avec l'application.
2. Sauvegarde data/database.sqlite du dossier CIBLE (pas celui-ci : ce
   dossier-ci, fraîchement décompressé, ne contient qu'une base neuve et
   vide, pas la vraie) dans data/backups/ du dossier cible, horodatée.
3. Copie tout le contenu de ce dossier vers le dossier cible, SAUF :
   data/ (la vraie base du dossier cible n'est jamais touchée), .env
   (les vrais réglages/secrets du dossier cible non plus), .git/
   (l'historique git du dossier cible, s'il existe), et les dossiers
   techniques (venv, __pycache__, .pytest_cache, *.egg-info) qui n'ont
   rien à faire dans une copie de mise à jour.
4. Si le dossier cible est un dépôt git (présence d'un .git/), enregistre
   la mise à jour comme un commit, puis le pousse automatiquement vers le
   dépôt distant s'il y en a un de configuré -- sinon, ces deux étapes
   sont simplement ignorées : git n'est pas obligatoire pour utiliser ce
   script. Un échec du push (pas de réseau, dépôt distant qui a avancé
   ailleurs...) n'interrompt jamais la mise à jour : le commit local, lui,
   a déjà réussi.
4bis. Supprime tous les dossiers __pycache__ de la cible -- ajouté le
   31/07/2026. Jamais copiés depuis la nouvelle version (voir l'étape 3),
   donc jamais remplacés par la copie elle-même : sans cette étape, un
   fichier .py fraîchement copié pourrait, dans de rares cas, se
   retrouver avec exactement le même (date de modification, taille) que
   l'ancien -- plus probable sur un lecteur réseau qu'en local -- ce qui
   suffit à tromper Python et à lui faire exécuter le bytecode compilé
   de l'ANCIENNE version, silencieusement, malgré un fichier source à
   jour sur disque (vérifié et reproduit empiriquement, pas supposé).
5. "Touche" app/main.py du dossier cible, pour déclencher de façon
   certaine le rechargement d'un serveur déjà lancé avec --reload.

Si un serveur tourne déjà (avec --reload) depuis le dossier cible, la
mise à jour est donc appliquée à chaud : rien à redémarrer à la main.
"""
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent.parent

# Noms ignorés PARTOUT dans l'arborescence copiée (comparaison par nom,
# pas par chemin complet -- voir shutil.ignore_patterns).
IGNORES = shutil.ignore_patterns(
    "data", ".env", ".git", "venv", "venv_test", ".venv",
    "__pycache__", ".pytest_cache", "*.egg-info",
)


def verifier_cible(cible: Path) -> None:
    if not cible.exists():
        print(f"Erreur : le dossier cible n'existe pas : {cible}", file=sys.stderr)
        sys.exit(1)
    if not (cible / "app" / "main.py").exists():
        print(
            f"Erreur : {cible} ne ressemble pas à une installation de l'application "
            "(app/main.py introuvable). Arrêt par sécurité, rien n'a été copié.",
            file=sys.stderr,
        )
        sys.exit(1)
    if cible.resolve() == SOURCE.resolve():
        print("Erreur : le dossier cible est le même que celui-ci. Rien à faire.", file=sys.stderr)
        sys.exit(1)


def sauvegarder_bdd(cible: Path) -> None:
    bdd = cible / "data" / "database.sqlite"
    if not bdd.exists():
        print("Pas de base de données existante à sauvegarder dans le dossier cible.")
        return
    dossier_backups = cible / "data" / "backups"
    dossier_backups.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = dossier_backups / f"database-avant-maj-{horodatage}.sqlite"
    shutil.copy2(bdd, destination)
    print(f"Base de données (du dossier cible) sauvegardée : {destination}")


def copier_vers(cible: Path) -> None:
    shutil.copytree(SOURCE, cible, ignore=IGNORES, dirs_exist_ok=True)
    print(f"Fichiers copiés vers {cible} (data/, .env et .git non touchés).")


def nettoyer_cache_bytecode(cible: Path) -> None:
    """Supprime tous les dossiers __pycache__ de la cible -- ajouté le
    31/07/2026, après un cas réel où un fichier Python fraîchement copié
    s'est retrouvé avec exactement le même (date de modification, taille
    en octets) que l'ancien qu'il remplaçait -- une coïncidence bien
    plus probable sur un lecteur réseau (granularité d'horodatage plus
    grossière qu'un disque local) qu'en local, mais qui suffit à elle
    seule à tromper la vérification par défaut de Python : le bytecode
    compilé de l'ANCIENNE version reste alors utilisé silencieusement,
    même après une copie et un redémarrage complets, le fichier source
    sur disque étant pourtant correctement à jour (vérifié et reproduit
    empiriquement avant d'écrire ce correctif -- pas une simple
    supposition).

    __pycache__ n'est jamais copié depuis la nouvelle version (voir
    IGNORES) : les anciens dossiers, sur la cible, ne sont donc jamais
    remplacés par la copie elle-même, seulement par cette étape dédiée.
    Toujours sûr à supprimer : Python les régénère automatiquement,
    depuis le code source actuel, dès le prochain import."""
    supprimes = 0
    for dossier in cible.rglob("__pycache__"):
        if dossier.is_dir():
            shutil.rmtree(dossier, ignore_errors=True)
            supprimes += 1
    if supprimes:
        print(f"Cache bytecode Python nettoyé ({supprimes} dossier(s) __pycache__ supprimé(s)) -- "
              "élimine le risque qu'un fichier reste exécuté dans son ancienne version malgré la copie.")


def commit_git_si_applicable(cible: Path) -> None:
    if not (cible / ".git").exists():
        print("Le dossier cible n'est pas un dépôt git : étapes commit/push ignorées.")
        return
    try:
        from app.version import APP_VERSION
    except Exception:
        APP_VERSION = "inconnue"

    ajout = subprocess.run(["git", "add", "-A"], cwd=cible, capture_output=True, text=True)
    if ajout.returncode != 0 and _resoudre_dubious_ownership_si_applicable(ajout.stderr, cible):
        # Le dossier cible vient d'être déclaré sûr : "git add" (jamais
        # vérifié jusqu'ici -- corrigé le 31/08/2026, un cas réel l'a
        # montré silencieusement en échec) doit être rejoué avant de
        # poursuivre, sinon rien ne serait effectivement indexé.
        ajout = subprocess.run(["git", "add", "-A"], cwd=cible, capture_output=True, text=True)

    resultat = subprocess.run(
        ["git", "commit", "-m", f"Mise à jour vers V{APP_VERSION}"],
        cwd=cible, capture_output=True, text=True,
    )
    if resultat.returncode != 0 and _resoudre_dubious_ownership_si_applicable(resultat.stderr, cible):
        resultat = subprocess.run(
            ["git", "commit", "-m", f"Mise à jour vers V{APP_VERSION}"],
            cwd=cible, capture_output=True, text=True,
        )

    if resultat.returncode == 0:
        print(f"Commit git créé : \"Mise à jour vers V{APP_VERSION}\".")
    else:
        # Rien à commiter (fichiers identiques) n'est pas une erreur.
        print("Rien de nouveau à commiter (fichiers identiques au dernier commit) ou dépôt non configuré :")
        print(resultat.stdout.strip() or resultat.stderr.strip())
        return  # rien de nouveau : rien à pousser non plus

    pousser_si_applicable(cible)


def _resoudre_dubious_ownership_si_applicable(sortie_erreur: str, cible: Path) -> bool:
    """Ajouté le 31/08/2026, suite à un cas réel : sur un dossier
    partagé en réseau (lecteur mappé, ex. M:\\... vers un partage SMB),
    git refuse par défaut d'opérer -- "fatal: detected dubious
    ownership" -- une mesure de sécurité (depuis la CVE-2022-24765) qui
    se déclenche sur ce type de chemin même quand rien n'est réellement
    compromis. git indique lui-même, dans son propre message d'erreur,
    la commande exacte pour lever ce blocage (`git config --global
    --add safe.directory ...`) -- on la reprend telle quelle, plutôt
    que de reconstruire nous-mêmes le chemin (le format exact attendu,
    avec le préfixe %(prefix)/// pour les chemins réseau, dépend de la
    version de git et ne vaut pas la peine d'être deviné).

    Renvoie True si le blocage a été levé (l'appelant doit alors rejouer
    la commande git qui avait échoué), False sinon (erreur différente,
    ou blocage non résolu -- l'appelant garde son comportement actuel)."""
    if "detected dubious ownership" not in sortie_erreur:
        return False
    correspondance = re.search(r"git config --global --add safe\.directory ('[^']*'|\S+)", sortie_erreur)
    if not correspondance:
        return False
    chemin_sur = correspondance.group(1).strip("'")
    resultat = subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", chemin_sur],
        capture_output=True, text=True,
    )
    if resultat.returncode == 0:
        print(
            f"Dossier déclaré sûr auprès de git ({chemin_sur}) -- mesure de sécurité de git "
            "(pas propre à ce dossier) qui bloque par défaut les dépôts sur certains chemins "
            "réseau ; réglé une bonne fois, ne devrait plus se reproduire sur cette machine."
        )
        return True
    print(f"Tentative de résoudre le blocage \"dubious ownership\" infructueuse : {resultat.stderr.strip()}")
    return False


def pousser_si_applicable(cible: Path) -> None:
    """Pousse le commit vers le dépôt distant, si un est configuré --
    demandé le 23/07/2026 ("pourquoi ce n'est pas automatique ?"). Un
    échec (pas de remote, réseau, rejet parce que le distant a avancé
    ailleurs) n'interrompt jamais la mise à jour : le commit LOCAL, lui,
    a déjà réussi et reste la garantie principale -- l'historique existe
    sur cette machine même si le push rate. Message clair dans ce cas,
    avec la commande à relancer à la main une fois le problème réglé."""
    remotes = subprocess.run(["git", "remote"], cwd=cible, capture_output=True, text=True)
    if not remotes.stdout.strip():
        print("Aucun dépôt distant configuré (git remote) : étape push ignorée.")
        return
    resultat = subprocess.run(["git", "push"], cwd=cible, capture_output=True, text=True)
    if resultat.returncode == 0:
        print("Poussé vers le dépôt distant avec succès.")
    else:
        print("\nATTENTION : échec du push (le commit local, lui, a bien été fait) :", file=sys.stderr)
        print((resultat.stderr or resultat.stdout).strip(), file=sys.stderr)
        print("Corrige le problème (ex: 'git pull' si le distant a avancé ailleurs), "
              "puis relance 'git push' à la main depuis ce dossier.", file=sys.stderr)


def forcer_rechargement(cible: Path) -> None:
    principal = cible / "app" / "main.py"
    if principal.exists():
        principal.touch()
        print("Rechargement du serveur déclenché (si lancé avec --reload depuis ce dossier).")

    if platform.system() == "Windows":
        print(
            "\nATTENTION (Windows) : cette mise à jour vient de modifier beaucoup de "
            "fichiers d'un coup. Sur Windows, --reload peut mal réagir dans ce cas "
            "précis (plusieurs tentatives de rechargement se marchent dessus les unes "
            "les autres, avec des erreurs affichées dans le terminal du serveur) --\n"
            "encore plus probable si ce dossier est sur un lecteur réseau. Vérifie que "
            "la page web affiche bien la nouvelle version en bas à droite : si non, "
            "arrête le serveur (Ctrl+C dans son terminal, au besoin plusieurs fois) et "
            "relance-le proprement plutôt que de faire confiance au rechargement "
            "automatique pour cette fois-ci."
        )

    verifier_version_en_ligne()


def verifier_version_en_ligne() -> None:
    """Vérifie qu'un serveur déjà lancé reflète bien la nouvelle version
    -- ajouté le 31/07/2026, après que l'avertissement textuel ci-dessus,
    seul, se soit montré insuffisant en pratique (la V0.1.34 est restée
    active plusieurs versions après son remplacement sur disque, sans
    que ça se voie autrement qu'en relisant la page soi-même -- ce
    qu'il est facile d'oublier de faire).

    N'échoue et ne bloque jamais : si le serveur n'est pas joignable
    (pas encore lancé, port différent du défaut...), le signale
    simplement sans lever d'exception -- ce n'est qu'une vérification de
    confort, pas une étape strictement nécessaire au reste du script."""
    import time
    try:
        import requests
    except ImportError:
        return  # requests non installé dans cet environnement : vérification sautée, pas bloquant

    import re
    fichier_version = SOURCE / "app" / "version.py"
    if not fichier_version.exists():
        return
    correspondance = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', fichier_version.read_text(encoding="utf-8"))
    if not correspondance:
        return
    version_attendue = correspondance.group(1)

    time.sleep(2)  # laisser --reload, s'il se déclenche, le temps de le faire
    try:
        reponse = requests.get("http://127.0.0.1:8000/version", timeout=3)
        version_en_cours = reponse.json().get("version")
    except Exception:
        print(
            "\n(Vérification en ligne non concluante : aucun serveur ne répond sur "
            "http://127.0.0.1:8000 -- normal s'il n'est pas encore lancé, ou tourne sur "
            "un autre port. Vérifie manuellement la version affichée en bas de la page "
            "une fois lancé.)"
        )
        return

    if version_en_cours == version_attendue:
        print(f"\n✓ Vérifié en ligne : le serveur déjà lancé tourne bien sur la V{version_attendue}.")
    else:
        print(
            f"\n⚠ ATTENTION : le serveur déjà lancé répond encore en V{version_en_cours}, "
            f"pas V{version_attendue} -- la mise à jour sur disque a bien eu lieu (vérifiable "
            "avec 'git log' dans ce dossier), mais ce serveur-là ne l'a pas prise en "
            "compte (--reload a probablement mal réagi, voir l'avertissement ci-dessus). "
            "Arrête ce serveur (Ctrl+C dans son terminal, au besoin plusieurs fois) et "
            "relance-le proprement -- ne continue pas à utiliser cette instance en l'état."
        )


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage : python -m app.scripts.appliquer_version /chemin/vers/mon/dossier/stable", file=sys.stderr)
        sys.exit(1)
    cible = Path(sys.argv[1]).expanduser().resolve()

    print(f"=== Application de la mise à jour sur {cible} ===\n")
    verifier_cible(cible)
    sauvegarder_bdd(cible)
    copier_vers(cible)
    nettoyer_cache_bytecode(cible)
    commit_git_si_applicable(cible)
    forcer_rechargement(cible)
    print("\nTerminé.")


if __name__ == "__main__":
    main()
