"""Tests de la généralisation à tous les radionucléides d'une source
(activites_par_radionuclide_bq, 30/07/2026, en remettant en question la
simplification historique "premier radionucléide seulement" plutôt qu'en
la reproduisant sans y réfléchir) et du spectre-type de consommation qui
s'appuie dessus."""
from datetime import date, timedelta

from app.repositories.source import SourceRepository
from app.services.units import activites_par_radionuclide_bq
from app.services.spectre_consommation import calculer_spectre_consommation


def _creer_source_mono_rn(admin_client, default_location, source_id="SRC-MONO", activite_bq_g=10, quantite_utilisee=4):
    admin_client.post("/sources/", json={
        "id": source_id, "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": source_id, "nom": "Co-60", "activite": activite_bq_g,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": source_id, "quantite_utilisee": quantite_utilisee})


def test_activites_par_radionuclide_source_mono_rn(admin_client, db_session, default_location):
    """Cas de base (le seul rencontré en pratique actuellement) : le
    résultat doit être identique à ce que donnait déjà l'ancienne
    fonction pour ce même cas -- aucune régression sur le cas courant."""
    _creer_source_mono_rn(admin_client, default_location, activite_bq_g=10, quantite_utilisee=4)
    source = SourceRepository(db_session).get_by_id("SRC-MONO")
    conso = source.consumptions[0]

    resultat = activites_par_radionuclide_bq(db_session, source, conso)

    assert list(resultat.keys()) == ["Co-60"]
    assert resultat["Co-60"] == 40.0  # 10 Bq/g x 4g, decroissance nulle (meme jour que la reference)


def test_activites_par_radionuclide_source_multi_rn_mode_specifique(admin_client, db_session, default_location):
    """Le point central de la question posée : une source à DEUX
    radionucléides, chacun avec sa propre concentration, doit donner
    deux contributions correctes -- pas seulement la première."""
    admin_client.post("/sources/", json={
        "id": "SRC-MULTI", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MULTI", "nom": "Co-60", "activite": 5,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MULTI", "nom": "Cs-137", "activite": 15,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 30.17,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-MULTI", "quantite_utilisee": 4})

    source = SourceRepository(db_session).get_by_id("SRC-MULTI")
    conso = source.consumptions[0]
    resultat = activites_par_radionuclide_bq(db_session, source, conso)

    assert set(resultat.keys()) == {"Co-60", "Cs-137"}
    assert resultat["Co-60"] == 20.0   # 5 Bq/g x 4g
    assert resultat["Cs-137"] == 60.0  # 15 Bq/g x 4g


def test_activites_par_radionuclide_multi_rn_mode_total_meme_fraction_pour_chacun(admin_client, db_session, default_location):
    """Mode activité totale (pas spécifique) : la même fraction consommée
    (quantité utilisée / quantité juste avant) doit s'appliquer à chaque
    radionucléide -- l'hypothèse d'homogénéité assumée explicitement."""
    admin_client.post("/sources/", json={
        "id": "SRC-MULTI-TOTAL", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MULTI-TOTAL", "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": False,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MULTI-TOTAL", "nom": "Cs-137", "activite": 3000,
        "unite_activite": "Bq", "date_reference": str(date.today()), "periode": 30.17,
        "activite_est_specifique": False,
    })
    # 10g consommés sur 100g initiaux -- 10% de fraction, attendue identique pour les deux.
    admin_client.post("/consumptions/", json={"source_id": "SRC-MULTI-TOTAL", "quantite_utilisee": 10})

    source = SourceRepository(db_session).get_by_id("SRC-MULTI-TOTAL")
    conso = source.consumptions[0]
    resultat = activites_par_radionuclide_bq(db_session, source, conso)

    assert resultat["Co-60"] == 100.0    # 10% de 1000
    assert resultat["Cs-137"] == 300.0   # 10% de 3000, meme fraction


def test_activites_par_radionuclide_ignore_gracieusement_un_rn_sans_periode(admin_client, db_session, default_location):
    """Un radionucléide en défaut (période inconnue) ne doit jamais faire
    échouer le calcul des AUTRES radionucléides de la même source."""
    admin_client.post("/sources/", json={
        "id": "SRC-PERIODE-PARTIELLE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-PERIODE-PARTIELLE", "nom": "Co-60", "activite": 5,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-PERIODE-PARTIELLE", "nom": "RN-Inconnu", "activite": 15,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": None,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-PERIODE-PARTIELLE", "quantite_utilisee": 4})

    source = SourceRepository(db_session).get_by_id("SRC-PERIODE-PARTIELLE")
    conso = source.consumptions[0]
    resultat = activites_par_radionuclide_bq(db_session, source, conso)

    assert resultat == {"Co-60": 20.0}  # RN-Inconnu absent, mais Co-60 present et correct


def test_spectre_source_multi_radionuclides_les_deux_apparaissent(admin_client, db_session, default_location):
    """Bout en bout : une source à deux radionucléides consommée une
    seule fois doit produire DEUX entrées dans le spectre, pas une."""
    admin_client.post("/sources/", json={
        "id": "SRC-SPECTRE-MULTI", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-SPECTRE-MULTI", "nom": "Co-60", "activite": 5,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-SPECTRE-MULTI", "nom": "Cs-137", "activite": 15,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 30.17,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-SPECTRE-MULTI", "quantite_utilisee": 4})

    resultat = calculer_spectre_consommation(db_session, date.today() - timedelta(days=1), date.today(), date.today())

    noms = {entree["nom"] for entree in resultat["spectre"]}
    assert noms == {"Co-60", "Cs-137"}
    co60 = next(e for e in resultat["spectre"] if e["nom"] == "Co-60")
    cs137 = next(e for e in resultat["spectre"] if e["nom"] == "Cs-137")
    assert abs(co60["pourcentage"] - 25.0) < 0.1   # 20 Bq sur 80 Bq
    assert abs(cs137["pourcentage"] - 75.0) < 0.1  # 60 Bq sur 80 Bq


def test_spectre_leve_erreur_si_reference_avant_fin_de_plage(db_session):
    import pytest
    with pytest.raises(ValueError, match="postérieure"):
        calculer_spectre_consommation(db_session, date(2026, 7, 1), date(2026, 7, 31), date(2026, 7, 15))


def test_spectre_accepte_reference_egale_a_la_fin_de_plage(admin_client, db_session, default_location):
    _creer_source_mono_rn(admin_client, default_location, source_id="SRC-REF-EGALE")
    resultat = calculer_spectre_consommation(db_session, date.today() - timedelta(days=1), date.today(), date.today())
    assert resultat["spectre"]  # ne lève pas d'exception, produit un résultat


def test_page_spectre_affiche_les_deux_radionuclides_d_une_source_multi(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-PAGE-MULTI", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-PAGE-MULTI", "nom": "Co-60", "activite": 5,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-PAGE-MULTI", "nom": "Cs-137", "activite": 15,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 30.17,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-PAGE-MULTI", "quantite_utilisee": 4})

    debut = (date.today() - timedelta(days=1)).isoformat()
    fin = date.today().isoformat()
    page = admin_client.get(f"/consumptions/spectre?date_debut={debut}&date_fin={fin}&date_reference={fin}")

    assert page.status_code == 200
    assert page.text.count('href="/sources/SRC-PAGE-MULTI/fiche"') == 2  # une fois par radionucléide, dans le tableau de détail
    assert "sources_multi_radionuclides" not in page.text  # l'avertissement devenu obsolète a bien disparu


def test_page_spectre_affiche_erreur_si_date_reference_invalide(admin_client, default_location):
    page = admin_client.get("/consumptions/spectre?date_debut=2026-07-01&date_fin=2026-07-31&date_reference=2026-07-15")
    assert page.status_code == 200
    assert "postérieure" in page.text
    assert "31/07/2026" in page.text  # la date est bien affichée en français, pas en ISO


def test_page_spectre_lien_present_depuis_consumptions(admin_client):
    page = admin_client.get("/consumptions")
    assert 'href="/consumptions/spectre"' in page.text


def test_export_spectre_xlsx_contenu_correct(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-EXPORT-SPECTRE-TEST", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-EXPORT-SPECTRE-TEST", "nom": "Co-60", "activite": 10,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-EXPORT-SPECTRE-TEST", "quantite_utilisee": 4})

    debut = (date.today() - timedelta(days=1)).isoformat()
    fin = date.today().isoformat()
    resp = admin_client.get(f"/consumptions/spectre/export.xlsx?date_debut={debut}&date_fin={fin}&date_reference={fin}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Spectre", "Consommations incluses"]
    lignes_spectre = list(wb["Spectre"].iter_rows(values_only=True))
    assert lignes_spectre[2] == ("Radionucléide", "Activité (Bq)", "Part du total (%)")
    assert lignes_spectre[3][0] == "Co-60"
    lignes_conso = list(wb["Consommations incluses"].iter_rows(values_only=True))
    assert lignes_conso[1][1] == "SRC-EXPORT-SPECTRE-TEST"


def test_export_spectre_refuse_si_date_reference_invalide(admin_client):
    resp = admin_client.get("/consumptions/spectre/export.xlsx?date_debut=2026-07-01&date_fin=2026-07-31&date_reference=2026-07-15")
    assert resp.status_code == 400


def test_bouton_export_present_sur_la_page(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-BOUTON-EXPORT", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-BOUTON-EXPORT", "nom": "Co-60", "activite": 10,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": 5.27,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-BOUTON-EXPORT", "quantite_utilisee": 4})

    debut = (date.today() - timedelta(days=1)).isoformat()
    fin = date.today().isoformat()
    page = admin_client.get(f"/consumptions/spectre?date_debut={debut}&date_fin={fin}&date_reference={fin}")
    assert "/consumptions/spectre/export.xlsx?" in page.text


def test_message_ignore_ne_reference_plus_de_fonction_python(admin_client, default_location):
    """31/07/2026, signalé directement : le message affiché à l'utilisateur
    ne doit jamais nommer une fonction Python interne."""
    admin_client.post("/sources/", json={
        "id": "SRC-SANS-PERIODE-MSG", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-SANS-PERIODE-MSG", "nom": "RN-Test", "activite": 10,
        "unite_activite": "Bq/g", "date_reference": str(date.today()), "periode": None,
        "activite_est_specifique": True,
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-SANS-PERIODE-MSG", "quantite_utilisee": 4})

    debut = (date.today() - timedelta(days=1)).isoformat()
    fin = date.today().isoformat()
    page = admin_client.get(f"/consumptions/spectre?date_debut={debut}&date_fin={fin}&date_reference={fin}")

    assert "activites_par_radionuclide_bq" not in page.text
    assert "aucune activité calculable" in page.text
