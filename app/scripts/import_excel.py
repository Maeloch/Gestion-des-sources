"""Script pour importer des données depuis un fichier Excel."""
import argparse
from pathlib import Path
import openpyxl
from app.database import SessionLocal
from app.models.source import SourceCreate
from app.repositories.source import SourceRepository

def import_sources_from_excel(file_path: str):
    """Importe des sources depuis un fichier Excel."""
    db = SessionLocal()
    try:
        repo = SourceRepository(db)
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active

        headers = [cell.value for cell in sheet[1]]
        required_columns = ["id", "type", "etat_physique", "etat_utilisation", "date_arrivee", "lieu_stockage"]
        if not all(col in headers for col in required_columns):
            raise ValueError("Le fichier Excel ne contient pas les colonnes requises.")

        col_indices = {header: idx for idx, header in enumerate(headers)}

        for row in sheet.iter_rows(min_row=2, values_only=True):
            source_data = {
                "id": row[col_indices["id"]],
                "type": row[col_indices["type"]],
                "etat_physique": row[col_indices["etat_physique"]],
                "etat_utilisation": row[col_indices["etat_utilisation"]],
                "date_arrivee": row[col_indices["date_arrivee"]],
                "lieu_stockage": row[col_indices["lieu_stockage"]],
            }
            if "num_certificat_etalonnage" in col_indices:
                source_data["num_certificat_etalonnage"] = row[col_indices["num_certificat_etalonnage"]]
            if "num_source_fabricant" in col_indices:
                source_data["num_source_fabricant"] = row[col_indices["num_source_fabricant"]]
            if "matiere_nucleaire" in col_indices:
                source_data["matiere_nucleaire"] = bool(row[col_indices["matiere_nucleaire"]])
            if "quantite" in col_indices:
                source_data["quantite"] = float(row[col_indices["quantite"]]) if row[col_indices["quantite"]] else None
            if "unite_quantite" in col_indices:
                source_data["unite_quantite"] = row[col_indices["unite_quantite"]]

            source = SourceCreate(**source_data)
            repo.create(source)
            print(f"Source {source.id} importée.")

        db.commit()
        print("Import terminé avec succès !")
    except Exception as e:
        db.rollback()
        print(f"Erreur lors de l'import : {e}")
    finally:
        db.close()

def main():
    """Point d'entrée pour le script."""
    parser = argparse.ArgumentParser(description="Importer des sources depuis un fichier Excel.")
    parser.add_argument("file_path", type=str, help="Chemin vers le fichier Excel.")
    args = parser.parse_args()

    if not Path(args.file_path).exists():
        print(f"Erreur : Le fichier {args.file_path} n'existe pas.")
        return

    import_sources_from_excel(args.file_path)

if __name__ == "__main__":
    main()
