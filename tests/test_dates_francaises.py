"""Tests de l'affichage des dates au format français (JJ/MM/AAAA) --
demandé le 30/07/2026 ("par pur chauvinisme")."""
from datetime import date, datetime

from app.services.units import date_fr


def test_date_fr_formate_une_date():
    assert date_fr(date(2026, 7, 30)) == "30/07/2026"


def test_date_fr_formate_un_datetime_sans_heure_par_defaut():
    assert date_fr(datetime(2026, 7, 30, 14, 35)) == "30/07/2026"


def test_date_fr_avec_heure():
    assert date_fr(datetime(2026, 7, 30, 14, 35), avec_heure=True) == "30/07/2026 14:35"


def test_date_fr_valeur_nulle():
    assert date_fr(None) == "—"


def test_page_sources_affiche_la_date_en_francais(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-DATE-FR-TEST", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-03-15",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources")
    assert "15/03/2020" in page.text
    # Toujours présente en ISO dans l'attribut de tri (nécessaire pour un
    # tri chronologique correct -- ne doit pas devenir français là).
    assert 'data-sort-datearrivee="2020-03-15"' in page.text


def test_page_radionuclides_affiche_la_date_en_francais(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-DATE-FR-RN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-DATE-FR-RN", "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-03-15",
    })
    page = admin_client.get("/radionuclides")
    assert "15/03/2020" in page.text


def test_page_movements_affiche_les_dates_en_francais(admin_client, default_location):
    autre_lieu = admin_client.post("/locations/", json={"nom": "Lieu Date Fr"}).json()
    admin_client.post("/sources/", json={
        "id": "SRC-DATE-FR-MVT", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/movements/", json={
        "source_id": "SRC-DATE-FR-MVT", "to_location_id": autre_lieu["id"],
        "date_retour_prevue": "2026-08-15",
    })
    page = admin_client.get("/movements")
    assert "15/08/2026" in page.text


def test_page_consumptions_affiche_la_date_en_francais(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-DATE-FR-CONSO", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "g",
    })
    resp = admin_client.post("/consumptions/", json={"source_id": "SRC-DATE-FR-CONSO", "quantite_utilisee": 1})
    page = admin_client.get("/consumptions")
    # Le format attendu JJ/MM/AAAA doit être présent quelque part.
    import re
    assert re.search(r"\d{2}/\d{2}/\d{4}", page.text)


def test_fiche_source_affiche_toutes_ses_dates_en_francais(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-DATE-FR-FICHE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-03-15",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-DATE-FR-FICHE", "nom": "Ir-192", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-03-15",
    })
    page = admin_client.get("/sources/SRC-DATE-FR-FICHE/fiche")
    assert page.text.count("15/03/2020") == 2  # date d'arrivée + date de référence


def test_page_users_affiche_la_date_de_demande_en_francais(client, admin_client):
    from tests.conftest import register_and_login
    utilisateur = register_and_login(client, "demandeur_date_fr", role=None, admin_client=admin_client)
    utilisateur.post("/users/me/demande-role", json={"role_demande": "utilisateur"})

    # register_and_login a changé la session du client partagé (même
    # patron que test_users_roles.py) : on se reconnecte en admin.
    admin_client.post("/auth/token", data={"username": "admintest", "password": "testpass123"})

    page = admin_client.get("/users")
    import re
    assert re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", page.text)
