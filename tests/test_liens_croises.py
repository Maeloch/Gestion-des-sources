"""Tests de la revue de cohérence des liens croisés demandée le
28/07/2026 : partout où un identifiant de source, un nom de
radionucléide ou un lieu était affiché en texte brut sur une page autre
que la sienne, il devient cliquable vers la page correspondante,
pré-filtrée via ?recherche=."""


def test_radionuclides_source_id_cliquable_vers_fiche_source(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-LIEN-RN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-LIEN-RN", "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    page = admin_client.get("/radionuclides")
    assert 'href="/sources/SRC-LIEN-RN/fiche"' in page.text


def test_movements_source_id_vers_fiche_et_lieux_vers_liste_filtree(admin_client, default_location):
    autre_lieu = admin_client.post("/locations/", json={"nom": "Lieu Destination"}).json()
    admin_client.post("/sources/", json={
        "id": "SRC-LIEN-MVT", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/movements/", json={"source_id": "SRC-LIEN-MVT", "to_location_id": autre_lieu["id"]})

    page = admin_client.get("/movements")
    assert 'href="/sources/SRC-LIEN-MVT/fiche"' in page.text
    assert 'href="/locations?recherche=Lieu+Destination"' in page.text or 'href="/locations?recherche=Lieu%20Destination"' in page.text


def test_consumptions_source_id_vers_fiche_source(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-LIEN-CONSO", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "g",
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-LIEN-CONSO", "quantite_utilisee": 1})

    page = admin_client.get("/consumptions")
    assert 'href="/sources/SRC-LIEN-CONSO/fiche"' in page.text


def test_audit_source_id_vers_fiche_source_quand_present(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-LIEN-AUDIT", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/audit")
    assert 'href="/sources/SRC-LIEN-AUDIT/fiche"' in page.text


def test_sources_noms_radionuclides_et_lieu_cliquables(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-LIEN-SOURCES", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-LIEN-SOURCES", "nom": "Ir-192", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    page = admin_client.get("/sources")
    assert 'href="/radionuclides?recherche=Ir-192"' in page.text
    assert '/locations?recherche=' in page.text  # le lieu par défaut, encodé selon son nom


def test_recherche_prefillie_depuis_url_sur_sources(admin_client, default_location):
    """Vérifie que le paramètre est bien lu et injecté dans le HTML rendu
    (le comportement dynamique -- préremplissage ET filtrage effectif --
    est vérifié séparément avec un moteur DOM, voir le rapport)."""
    page = admin_client.get("/sources?recherche=Co-60")
    assert page.status_code == 200
    assert "rechercheDepuisUrl" in page.text
    assert ".get('recherche')" in page.text


def test_recherche_prefillie_depuis_url_generique(admin_client, default_location):
    page = admin_client.get("/locations?recherche=EPICEA")
    assert page.status_code == 200
    # La logique de préremplissage vit dans filtrable.js, partagé --
    # vérifie juste que la page l'utilise bien (rendreFiltrable appelé).
    assert "rendreFiltrable(" in page.text
