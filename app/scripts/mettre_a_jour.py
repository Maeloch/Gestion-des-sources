"""Met à jour l'application vers la dernière version disponible sur le
dépôt git, aussi simplement que possible pour l'utilisateur -- demandé
le 21/07/2026.

Usage : python -m app.scripts.mettre_a_jour

Ce que fait ce script, dans l'ordre :

1. Sauvegarde la base de données actuelle (data/database.sqlite) dans
   data/backups/, horodatée -- un filet de sécurité avant toute mise à
   jour, même si le code d'une nouvelle version ne devrait normalement
   jamais y toucher directement (ce fichier n'est pas suivi par git,
   voir .gitignore -- un `git pull` ne le touche jamais).
2. `git pull` (récupère la nouvelle version).
3. "Touche" app/main.py (change sa date de modification sans changer
   son contenu) pour déclencher de façon certaine le rechargement
   automatique d'un serveur déjà lancé avec `uvicorn ... --reload` --
   plus fiable que de compter uniquement sur la détection automatique
   de TOUS les fichiers modifiés par le git pull, qui peut avoir des
   cas limites selon la configuration du greffon de surveillance.

Suppose un serveur DÉJÀ EN COURS D'EXÉCUTION avec l'option --reload
(voir le README, section "Mises à jour automatiques"). Sans --reload,
ce script prépare la mise à jour mais ne redémarre rien tout seul : il
faut alors relancer le serveur manuellement après l'avoir exécuté.

Les migrations de schéma (voir app/scripts/migrate_*.py) s'exécutent
automatiquement à l'import de app.main, donc au prochain démarrage
(rechargement inclus) -- rien de spécial à faire ici pour elles.
"""
import subprocess
import shutil
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent


def sauvegarder_bdd() -> None:
    bdd = RACINE / "data" / "database.sqlite"
    if not bdd.exists():
        print("Pas de base de données existante à sauvegarder (première installation ?).")
        return
    dossier_backups = RACINE / "data" / "backups"
    dossier_backups.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = dossier_backups / f"database-avant-maj-{horodatage}.sqlite"
    shutil.copy2(bdd, destination)
    print(f"Base de données sauvegardée : {destination}")


def git_pull() -> None:
    resultat = subprocess.run(["git", "pull"], cwd=RACINE, capture_output=True, text=True)
    if resultat.stdout.strip():
        print(resultat.stdout.strip())
    if resultat.returncode != 0:
        print("ÉCHEC du git pull :", file=sys.stderr)
        print(resultat.stderr.strip(), file=sys.stderr)
        print(
            "\nMise à jour interrompue avant tout changement de code "
            "(conflit, réseau, dépôt non initialisé...) -- corrige le "
            "problème puis relance ce script. La base de données n'a pas "
            "été touchée, elle reste utilisable telle quelle.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("Code mis à jour avec succès.")


def forcer_rechargement() -> None:
    principal = RACINE / "app" / "main.py"
    if principal.exists():
        principal.touch()
        print("Rechargement du serveur déclenché (si lancé avec --reload).")


def main() -> None:
    print("=== Mise à jour de l'application ===\n")
    sauvegarder_bdd()
    git_pull()
    forcer_rechargement()
    print("\nTerminé. Si le serveur ne tournait pas avec --reload, relance-le manuellement.")


if __name__ == "__main__":
    main()
