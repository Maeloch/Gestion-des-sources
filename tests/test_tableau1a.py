"""Tests du Tableau 1a : catégorisation de l'uranium et agrégation par
matière et par lieu."""
import openpyxl
from app.services.matieres_nucleaires import categoriser_uranium


def test_categorisation_uranium_naturel_exact():
    assert categoriser_uranium(0.7202) == "naturel"


def test_categorisation_uranium_appauvri():
    assert categoriser_uranium(0.2) == "appauvri"


def test_categorisation_uranium_enrichi_bandes():
    assert categoriser_uranium(5) == "enrichi_moins_10"
    assert categoriser_uranium(12) == "enrichi_10_20"
    assert categoriser_uranium(50) == "enrichi_20_plus"


def test_tableau1a_agrege_par_lieu(admin_client, tmp_path):
    # Deux lieux
    epicea = admin_client.post("/locations/", json={"nom": "Labo EPICEA", "site": "EPICEA"}).json()
    irma = admin_client.post("/locations/", json={"nom": "Armoire IRMA", "site": "IRMA"}).json()

    # Source 1 : Plutonium à EPICEA
    admin_client.post("/sources/", json={
        "id": "MN-1", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": epicea["id"],
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "MN-1", "nom": "239-Pu", "activite": 1e9,
        "unite_activite": "Bq", "date_reference": "2020-01-01", "periode": 24110,
    })

    # Source 2 : Uranium naturel (mélange U-238/U-235 dans les bonnes proportions) à IRMA
    admin_client.post("/sources/", json={
        "id": "MN-2", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": irma["id"],
    })
    # 1kg de U-238 et une quantité de U-235 donnant le ratio naturel (0.7202% en masse)
    # m235 / (m235 + m238) = 0.007202  =>  m235 = m238 * 0.007202 / (1-0.007202)
    m238_g = 1000.0
    m235_g = m238_g * 0.007202 / (1 - 0.007202)
    # Convertir ces masses cibles en activités via la formule inverse (réutilise la même physique)
    from app.services.matieres_nucleaires import MASSES_MOLAIRES_G_PAR_MOL, NOMBRE_AVOGADRO
    import math
    def activite_pour_masse(masse_g, periode_annees, masse_molaire):
        periode_s = periode_annees * 365.25 * 24 * 3600
        return masse_g * math.log(2) * NOMBRE_AVOGADRO / (periode_s * masse_molaire)

    a238 = activite_pour_masse(m238_g, 4.468e9, MASSES_MOLAIRES_G_PAR_MOL[("U", 238)])
    a235 = activite_pour_masse(m235_g, 7.04e8, MASSES_MOLAIRES_G_PAR_MOL[("U", 235)])

    admin_client.post("/radionuclides/", json={
        "source_id": "MN-2", "nom": "238-U", "activite": a238,
        "unite_activite": "Bq", "date_reference": "2020-01-01", "periode": 4.468e9,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "MN-2", "nom": "235-U", "activite": a235,
        "unite_activite": "Bq", "date_reference": "2020-01-01", "periode": 7.04e8,
    })

    output = tmp_path / "tableau1a.xlsx"
    resp = admin_client.get("/export/tableau1a.xlsx")
    assert resp.status_code == 200
    output.write_bytes(resp.content)

    wb = openpyxl.load_workbook(output)
    ws = wb.active
    # Plutonium (ligne 7) : colonne C = EPICEA
    assert ws["C7"].value is not None and ws["C7"].value > 0
    assert ws["E7"].value is None  # rien à IRMA pour le Pu
    # Uranium naturel (ligne 12, en kg) : colonne E = IRMA
    assert ws["E12"].value is not None and ws["E12"].value > 0
    assert ws["C12"].value is None  # rien à EPICEA pour l'U naturel
