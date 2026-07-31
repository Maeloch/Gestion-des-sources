"""Calcul du "spectre-type" des sources consommées sur une plage de
temps -- demandé le 30/07/2026, pour estimer la composition isotopique
des déchets (supposée proportionnelle à l'activité des sources mères
consommées).

Principe : pour chaque consommation dans la plage, l'activité qu'elle
représente est calculée à la date de CETTE consommation, POUR CHAQUE
RADIONUCLÉIDE DE LA SOURCE (réutilise activites_par_radionuclide_bq,
généralisation de la fonction historique qui ne considérait que le
premier radionucléide -- voir sa docstring pour le raisonnement complet
sur pourquoi cette généralisation ne pose pas de difficulté
mathématique particulière). Chaque activité est ensuite amenée par
décroissance jusqu'à une date de référence choisie (par défaut,
aujourd'hui) -- ce qui donne l'activité que ce radionucléide représente
ENCORE aujourd'hui dans les déchets, pas seulement au moment où il a été
consommé. Les activités sont ensuite regroupées par radionucléide et
converties en pourcentages du total.

Hypothèse assumée, pas cachée (héritée de activites_par_radionuclide_bq) :
une source à plusieurs radionucléides est supposée homogène -- consommer
X% de sa masse/volume consomme X% de CHAQUE radionucléide qu'elle
contient, pas plus l'un que l'autre. Vraie pour un mélange de calibration
homogène (le cas typique), à garder en tête sinon.
"""
from datetime import date, datetime
from typing import Optional

from app.models.consumption import ConsumptionDB
from app.services.decay import DecayService
from app.services.units import activites_par_radionuclide_bq


def calculer_spectre_consommation(db, date_debut: date, date_fin: date, date_reference: Optional[date] = None) -> dict:
    """Calcule le spectre-type des radionucléides consommés entre
    date_debut et date_fin (bornes incluses), l'activité de chaque
    radionucléide étant amenée par décroissance jusqu'à date_reference
    (aujourd'hui par défaut).

    Lève une ValueError si date_reference est antérieure à date_fin : la
    décroissance n'a de sens que vers l'avant dans le temps -- calculer
    "à une date antérieure aux consommations examinées" ferait
    remonter l'activité au lieu de la faire décroître, un résultat sans
    signification physique plutôt qu'une simple imprécision.
    """
    if date_reference is None:
        date_reference = date.today()
    if date_reference < date_fin:
        raise ValueError(
            "La date de référence (à laquelle le spectre est calculé) doit être "
            "égale ou postérieure à la fin de la plage de consommations examinée."
        )

    consommations = (
        db.query(ConsumptionDB)
        .filter(ConsumptionDB.timestamp >= datetime.combine(date_debut, datetime.min.time()))
        .filter(ConsumptionDB.timestamp <= datetime.combine(date_fin, datetime.max.time()))
        .all()
    )

    activites_par_rn: dict = {}
    consommations_incluses = []
    radionuclides_sans_periode = set()
    consommations_ignorees = []

    for c in consommations:
        source = c.source
        if not source or not source.radionuclides:
            consommations_ignorees.append({"id": c.id, "source_id": c.source_id, "raison": "source sans radionucléide connu"})
            continue

        date_conso = c.timestamp.date() if c.timestamp else date_reference
        activites_de_cette_conso = activites_par_radionuclide_bq(db, source, c)

        # Un radionucléide sans période connue n'apparaît pas dans
        # activites_par_radionuclide_bq (aucune décroissance calculable) --
        # détecté ici séparément, pour le signaler plutôt que de laisser
        # sa contribution disparaître silencieusement du spectre.
        for rn in source.radionuclides:
            if not rn.periode and rn.nom not in activites_de_cette_conso:
                radionuclides_sans_periode.add(rn.nom)

        if not activites_de_cette_conso:
            consommations_ignorees.append({"id": c.id, "source_id": c.source_id, "raison": "aucune activité calculable pour cette source (période radioactive ou concentration manquante)"})
            continue

        for nom_rn, activite_a_la_conso in activites_de_cette_conso.items():
            rn = next(r for r in source.radionuclides if r.nom == nom_rn)
            activite_decayed = DecayService.calculate_activity(
                initial_activity=activite_a_la_conso,
                half_life_years=rn.periode,
                initial_date=date_conso,
                current_date=date_reference,
            )
            activites_par_rn[nom_rn] = activites_par_rn.get(nom_rn, 0.0) + activite_decayed
            consommations_incluses.append({
                "id": c.id, "source_id": source.id, "radionuclide": nom_rn,
                "date": date_conso, "activite_a_la_consommation_bq": activite_a_la_conso,
            })

    total_bq = sum(activites_par_rn.values())
    spectre = [
        {
            "nom": nom,
            "activite_bq": activite,
            "pourcentage": (activite / total_bq * 100) if total_bq > 0 else 0.0,
        }
        for nom, activite in sorted(activites_par_rn.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "date_debut": date_debut,
        "date_fin": date_fin,
        "date_reference": date_reference,
        "spectre": spectre,
        "total_bq": total_bq,
        "consommations": sorted(consommations_incluses, key=lambda x: x["date"]),
        "consommations_ignorees": consommations_ignorees,
        "radionuclides_sans_periode": sorted(radionuclides_sans_periode),
    }


def exporter_spectre_excel(resultat: dict, output_path: str) -> None:
    """Exporte un spectre déjà calculé (voir calculer_spectre_consommation)
    vers un fichier Excel à deux feuilles -- demandé le 31/07/2026.
    Prend le résultat déjà calculé plutôt que de recalculer, pour que
    l'export reflète exactement ce qui a été affiché à l'écran."""
    import openpyxl

    wb = openpyxl.Workbook()

    sheet_spectre = wb.active
    sheet_spectre.title = "Spectre"
    sheet_spectre.append([
        f"Spectre-type du {resultat['date_debut'].strftime('%d/%m/%Y')} "
        f"au {resultat['date_fin'].strftime('%d/%m/%Y')}, "
        f"à la date du {resultat['date_reference'].strftime('%d/%m/%Y')}"
    ])
    sheet_spectre.append([])
    sheet_spectre.append(["Radionucléide", "Activité (Bq)", "Part du total (%)"])
    for entree in resultat["spectre"]:
        sheet_spectre.append([entree["nom"], entree["activite_bq"], round(entree["pourcentage"], 2)])
    sheet_spectre.append([])
    sheet_spectre.append(["Total", resultat["total_bq"], 100.0 if resultat["spectre"] else 0.0])
    for col_lettre, largeur in zip("ABC", (18, 16, 16)):
        sheet_spectre.column_dimensions[col_lettre].width = largeur

    sheet_conso = wb.create_sheet("Consommations incluses")
    sheet_conso.append(["Date", "Source", "Radionucléide", "Activité à la consommation (Bq)"])
    for c in resultat["consommations"]:
        sheet_conso.append([
            c["date"].strftime("%d/%m/%Y"), c["source_id"], c["radionuclide"],
            c["activite_a_la_consommation_bq"],
        ])
    for col_lettre, largeur in zip("ABCD", (14, 16, 16, 26)):
        sheet_conso.column_dimensions[col_lettre].width = largeur

    wb.save(output_path)
