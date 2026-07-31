"""Tests de l'harmonisation des pop-ups de modification (Annuler /
Enregistrer / Supprimer) -- demandé le 31/07/2026, en suite de l'ajout
de Supprimer sur les consommations. Sources gardent volontairement
Annuler/Enregistrer SANS Supprimer (choix déjà établi : une source doit
toujours rester traçable, jamais purement supprimable)."""


def test_radionuclides_supprimer_deplace_dans_la_popup(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-HARMONIE-RN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-HARMONIE-RN", "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    page = admin_client.get("/radionuclides")
    assert 'id="rnDeleteBtn"' in page.text
    # Plus de bouton Supprimer directement sur la ligne du tableau.
    corps_tableau = page.text.split("<tbody>")[1].split("</tbody>")[0]
    assert "deleteRadionuclide(" not in corps_tableau


def test_locations_supprimer_deplace_dans_la_popup(admin_client):
    admin_client.post("/locations/", json={"nom": "Lieu Harmonie Test"})
    page = admin_client.get("/locations")
    assert 'id="locationDeleteBtn"' in page.text
    corps_tableau = page.text.split("<tbody>")[1].split("</tbody>")[0]
    assert "deleteLocation(" not in corps_tableau


def test_radionuclides_bouton_annuler_present(admin_client):
    page = admin_client.get("/radionuclides")
    assert ">Annuler<" in page.text


def test_locations_bouton_annuler_present(admin_client):
    page = admin_client.get("/locations")
    assert ">Annuler<" in page.text


def test_sources_bouton_annuler_present_mais_pas_supprimer(admin_client, default_location):
    """Sources : Annuler ajouté pour l'harmonisation, mais surtout PAS de
    bouton Supprimer -- une source doit toujours rester traçable, choix
    déjà établi (voir DELETE /sources/{id}, retirée en V0.1.27)."""
    page = admin_client.get("/sources")
    assert ">Annuler<" in page.text
    assert "deleteSource" not in page.text
