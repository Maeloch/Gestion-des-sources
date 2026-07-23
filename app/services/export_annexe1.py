"""Génère un pré-remplissage de l'Annexe 1 ("Inventaire Physique Des
Matières Nucléaires") à partir des sources marquées Matière Nucléaire.

Mapping des colonnes précisé le 10/07/2026 :
- Code matière EUR/National : déduit du radionucléide (voir matieres_nucleaires.py)
- Produit / code : le radionucléide (ex: "233-U")
- Produit / désignation : l'identifiant de la source (ex: "SCA-001")
- Produit / nombre : toujours 1 (une source = un objet physique)
- Identification (conteneur) : la référence catalogue de la source
- Mesure / Date : la date de référence du radionucléide
- Mesure / Masse de source (g) : la quantité de la source (masse ou pression, selon le cas)
- Mesure / Masse en radioélément (g) : calculée à partir de l'activité ACTUELLE
  (pas la référence/initiale) — voir matieres_nucleaires.masse_radioelement_g

Une source ayant plusieurs radionucléides donne plusieurs lignes (une par
radionucléide), avec la même désignation/nombre/identification.

Colonnes "Teneur en éléments %" et "Total par matière" volontairement
laissées vides : la première n'est pas déductible des données actuellement
suivies, la seconde est un total agrégé (pas une valeur par ligne) — à
préciser.
"""
from pathlib import Path
import openpyxl

from app.services.matieres_nucleaires import code_matiere, masse_radionuclide_g
from app.services.units import activite_actuelle_bq

TEMPLATE_PATH = Path(__file__).parent.parent / "resources" / "annexe1_template.xlsx"


def generer_annexe1(db, output_path: str) -> int:
    """Renvoie le nombre de lignes générées (une par radionucléide d'une
    source Matière Nucléaire, pas une par source)."""
    from app.repositories.source import SourceRepository
    from datetime import date

    sources = [s for s in SourceRepository(db).get_all() if s.matiere_nucleaire]

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    ws = wb.active

    # Date de l'inventaire (celle de la génération du document, en face du
    # libellé "Date" en H4) -- demandé le 14/07/2026, absente jusqu'ici.
    ws.cell(row=4, column=9, value=date.today().strftime("%d/%m/%Y"))

    row = 9  # la première ligne de données, juste après l'en-tête (lignes 1-8)
    lignes_generees = 0

    for source in sources:
        radionuclides = source.radionuclides or []
        if not radionuclides:
            # Une source MN sans radionucléide renseigné : une ligne quand
            # même, pour qu'elle n'échappe pas à l'inventaire, sans les
            # colonnes qui dépendent d'un radionucléide.
            ws.cell(row=row, column=4, value=source.id)
            ws.cell(row=row, column=5, value=1)
            ws.cell(row=row, column=6, value=source.reference_catalogue)
            if source.quantite is not None:
                ws.cell(row=row, column=8, value=source.quantite)
            row += 1
            lignes_generees += 1
            continue

        for rn in radionuclides:
            code_eur, code_national = code_matiere(rn.nom)
            if code_eur:
                ws.cell(row=row, column=1, value=code_eur)
            if code_national:
                ws.cell(row=row, column=2, value=code_national)

            ws.cell(row=row, column=3, value=rn.nom)          # code produit
            ws.cell(row=row, column=4, value=source.id)        # désignation
            ws.cell(row=row, column=5, value=1)                 # nombre
            if source.reference_catalogue:
                ws.cell(row=row, column=6, value=source.reference_catalogue)  # identification
            ws.cell(row=row, column=7, value=rn.date_reference)  # date

            if source.quantite is not None:
                ws.cell(row=row, column=8, value=source.quantite)  # masse de source / pression

            if rn.periode:
                activite_actuelle = activite_actuelle_bq(rn)
                masse_re = masse_radionuclide_g(db, rn, activite_actuelle)
                if masse_re is not None:
                    ws.cell(row=row, column=9, value=round(masse_re, 3))  # masse en radioélément

            row += 1
            lignes_generees += 1

    wb.save(output_path)
    return lignes_generees
