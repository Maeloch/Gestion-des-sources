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
5. "Touche" app/main.py du dossier cible, pour déclencher de façon
   certaine le rechargement d'un serveur déjà lancé avec --reload.

Si un serveur tourne déjà (avec --reload) depuis le dossier cible, la
mise à jour est donc appliquée à chaud : rien à redémarrer à la main.
"""
import platform
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


def commit_git_si_applicable(cible: Path) -> None:
    if not (cible / ".git").exists():
        print("Le dossier cible n'est pas un dépôt git : étapes commit/push ignorées.")
        return
    try:
        from app.version import APP_VERSION
    except Exception:
        APP_VERSION = "inconnue"
    subprocess.run(["git", "add", "-A"], cwd=cible, capture_output=True, text=True)
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


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage : python -m app.scripts.appliquer_version /chemin/vers/mon/dossier/stable", file=sys.stderr)
        sys.exit(1)
    cible = Path(sys.argv[1]).expanduser().resolve()

    print(f"=== Application de la mise à jour sur {cible} ===\n")
    verifier_cible(cible)
    sauvegarder_bdd(cible)
    copier_vers(cible)
    commit_git_si_applicable(cible)
    forcer_rechargement(cible)
    print("\nTerminé.")


if __name__ == "__main__":
    main()
