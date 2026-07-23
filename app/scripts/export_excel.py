"""Script pour exporter des données vers un fichier Excel."""
import argparse
import openpyxl
from app.database import SessionLocal
from app.repositories.source import SourceRepository
from app.repositories.radionuclide import RadionuclideRepository

def export_sources_to_excel(file_path: str, db=None):
    """Exporte la liste complète des sources (actives + archivées) et leurs
    radionucléides vers un fichier Excel à deux feuilles, pour les besoins
    d'inventaire.

    `db`, si fourni, est utilisée telle quelle (cohérent avec
    generer_annexe1/generer_tableau1a, et nécessaire pour que la route web
    utilise bien la même session que le reste de la requête) ; sinon, une
    session est créée puis fermée localement (usage en ligne de commande)."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        repo = SourceRepository(db)
        sources = repo.get_all()  # toutes, actives et archivées

        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = "Sources"

        headers = [
            "ID", "Type", "État physique", "État d'utilisation", "Archivée",
            "Date d'arrivée", "Fournisseur",
            "Matière nucléaire", "Quantité restante", "Quantité initiale",
            "Unité de quantité", "Volume récipient (L)",
            "Emplacement habituel", "Emplacement actuel",
            "Numéro certificat", "Numéro fabricant", "Lien dossier",
            "Commentaire",
        ]
        sheet.append(headers)

        from app.models.source import is_archived

        for source in sources:
            row = [
                source.id,
                source.type.value if source.type else None,
                source.etat_physique.value if source.etat_physique else None,
                source.etat_utilisation.value if source.etat_utilisation else None,
                "Oui" if is_archived(source) else "Non",
                source.date_arrivee,
                source.fournisseur,
                "Oui" if source.matiere_nucleaire else "Non",
                source.quantite,
                source.quantite_initiale,
                source.unite_quantite.value if source.unite_quantite else None,
                source.volume_recipient_litres,
                source.emplacement_habituel.nom if source.emplacement_habituel else None,
                source.emplacement_actuel.nom if source.emplacement_actuel else None,
                source.num_certificat_etalonnage,
                source.num_source_fabricant,
                source.lien_dossier_admin,
                source.commentaire,
            ]
            sheet.append(row)
        for col_cells in sheet.columns:
            sheet.column_dimensions[col_cells[0].column_letter].width = 18

        rn_sheet = wb.create_sheet("Radionucléides")
        rn_headers = ["ID Source", "Nom", "Activité de référence", "Activité spécifique ?",
                      "Unité", "Date de référence", "Période (années)", "Lien LaraWeb"]
        rn_sheet.append(rn_headers)
        radionuclides = RadionuclideRepository(db).get_all()
        for rn in radionuclides:
            rn_sheet.append([
                rn.source_id, rn.nom, rn.activite,
                "Oui" if rn.activite_est_specifique else "Non",
                rn.unite_activite, rn.date_reference, rn.periode, rn.lien_laraweb,
            ])
        for col_cells in rn_sheet.columns:
            rn_sheet.column_dimensions[col_cells[0].column_letter].width = 18

        wb.save(file_path)
        print(f"Export terminé : {file_path}")
    finally:
        if close_db:
            db.close()

def main():
    parser = argparse.ArgumentParser(description="Exporter les sources vers un fichier Excel.")
    parser.add_argument("file_path", type=str, help="Chemin vers le fichier Excel de sortie.")
    args = parser.parse_args()
    export_sources_to_excel(args.file_path)

if __name__ == "__main__":
    main()
