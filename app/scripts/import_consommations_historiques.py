"""Point d'entrée en ligne de commande pour l'import des consommations
historiques -- voir app/services/import_consommations_historiques.py
pour le format attendu et le raisonnement complet.

Usage :
    python -m app.scripts.import_consommations_historiques mon_fichier.xlsx
    python -m app.scripts.import_consommations_historiques --modele modele_vide.xlsx
"""
import sys

from app.database import SessionLocal
from app.services.import_consommations_historiques import (
    importer_consommations_historiques,
    generer_modele_vide,
)


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "--modele":
        if len(sys.argv) != 2:
            print(
                "Usage :\n"
                "  python -m app.scripts.import_consommations_historiques mon_fichier.xlsx\n"
                "  python -m app.scripts.import_consommations_historiques --modele modele_vide.xlsx",
                file=sys.stderr,
            )
            sys.exit(1)

    if sys.argv[1] == "--modele":
        generer_modele_vide(sys.argv[2])
        print(f"Modèle vide généré : {sys.argv[2]}")
        return

    fichier = sys.argv[1]
    db = SessionLocal()
    try:
        rapport = importer_consommations_historiques(fichier, db)
    finally:
        db.close()

    print(f"\n{rapport['consommations_creees']} consommation(s) créée(s).")
    if rapport["lignes_ignorees"]:
        print(f"\n{len(rapport['lignes_ignorees'])} ligne(s) ignorée(s) :")
        for l in rapport["lignes_ignorees"]:
            print(f"  Ligne {l['ligne']} (source '{l['source_id']}') : {l['raison']}")


if __name__ == "__main__":
    main()
