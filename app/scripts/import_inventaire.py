"""Script en ligne de commande pour importer le fichier d'inventaire Excel.

    python -m app.scripts.import_inventaire mon_fichier.xlsx

Fait la même chose que la page "Import" du site — utile si tu préfères la
ligne de commande, ou pour un fichier trop volumineux pour un upload web.
"""
import argparse
from pathlib import Path

from app.database import SessionLocal
from app.services.inventory_import import importer_fichier


def main():
    parser = argparse.ArgumentParser(description="Importer l'inventaire Excel historique.")
    parser.add_argument("file_path", type=str, help="Chemin vers le fichier .xlsx")
    args = parser.parse_args()

    if not Path(args.file_path).exists():
        print(f"Erreur : le fichier {args.file_path} n'existe pas.")
        return

    db = SessionLocal()
    try:
        rapport = importer_fichier(args.file_path, db=db, utilisateur="ligne de commande")
    finally:
        db.close()

    print(f"Feuilles traitées : {', '.join(rapport['feuilles_traitees'])}")
    print(f"Sources créées : {len(rapport['sources_creees'])}")
    print(f"Sources déjà présentes (ignorées) : {len(rapport['sources_ignorees_deja_presentes'])}")
    for feuille, ligne, sid in rapport["sources_ignorees_deja_presentes"]:
        print(f"   - {feuille} ligne {ligne} : {sid}")
    print(f"Sources en erreur (ignorées) : {len(rapport['sources_ignorees_erreur'])}")
    for feuille, ligne, sid, err in rapport["sources_ignorees_erreur"]:
        print(f"   - {feuille} ligne {ligne} ({sid}) : {err}")
    print(f"Radionucléides créés : {rapport['radionuclides_crees']}")
    print(f"Lieux créés : {rapport['lieux_crees']}")
    if rapport["avertissements"]:
        print(f"\nAvertissements ({len(rapport['avertissements'])}) :")
        for a in rapport["avertissements"]:
            print(f"   - {a}")


if __name__ == "__main__":
    main()
