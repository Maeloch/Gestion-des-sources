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


def test_toutes_les_popup_ont_autant_de_annuler_que_de_submit(admin_client, default_location):
    """31/07/2026, passe complète : chaque bouton submit (à l'intérieur
    d'une pop-up) doit avoir son pendant Annuler -- vérifié une bonne
    fois pour toutes plutôt que page par page, en comptant les deux sur
    chaque page qui affiche au moins une pop-up. Une source est créée
    pour que sources.html affiche bien son formulaire de modification
    (masqué sans locations, voir ailleurs)."""
    admin_client.post("/sources/", json={
        "id": "SRC-COMPTAGE-BOUTONS", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    for url in ("/sources", "/radionuclides", "/locations", "/movements", "/consumptions"):
        page = admin_client.get(url)
        nb_submit = page.text.count('type="submit"')
        nb_annuler = page.text.count(">Annuler<")
        assert nb_submit == nb_annuler, f"{url} : {nb_submit} submit mais {nb_annuler} Annuler"
        assert nb_submit > 0, f"{url} : aucun bouton submit trouvé, le test ne vérifie rien"


def test_mouvements_les_trois_formulaires_ont_annuler(admin_client, default_location):
    """31/07/2026 : les trois formulaires de cette page (démarrer un
    emprunt, marquer un retour, ajouter un lieu) n'avaient chacun qu'un
    seul bouton, sans Annuler -- signalé comme manquant d'homogénéité."""
    admin_client.post("/sources/", json={
        "id": "SRC-MVT-BOUTONS", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/movements")
    assert 'onclick="closeModal()">Annuler' in page.text
    assert 'onclick="closeRetourModal()">Annuler' in page.text
    assert 'onclick="closeAddLocationModal()">Annuler' in page.text


def test_sources_ajouts_rapides_ont_annuler(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-AJOUTS-RAPIDES", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources")
    assert 'onclick="closeAddRnModal()">Annuler' in page.text
    assert 'onclick="closeAddLocationModal()">Annuler' in page.text


def test_sources_archive_bouton_correction_stylise_et_a_annuler(admin_client, default_location):
    """31/07/2026 : le bouton de cette pop-up n'était même pas stylisé en
    primary (contrairement à toutes les autres), et n'avait pas Annuler."""
    page = admin_client.get("/sources/archive")
    assert '<button type="submit" class="primary">Enregistrer la correction</button>' in page.text
    assert ">Annuler<" in page.text


def test_consumptions_formulaire_creation_a_annuler(admin_client, default_location):
    """31/07/2026 : seul le formulaire de correction (pas celui de
    création) avait Annuler jusqu'ici sur cette page."""
    admin_client.post("/sources/", json={
        "id": "SRC-CONSO-BOUTONS", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "g",
    })
    page = admin_client.get("/consumptions")
    # closeModal() est spécifique au formulaire de création sur cette
    # page (le formulaire de correction utilise closeEditModal()).
    assert 'onclick="closeModal()">Annuler' in page.text


def test_base_popups_globales_ont_annuler(admin_client):
    """31/07/2026 : les deux pop-up de base.html (changer son mot de
    passe, demander un changement de rôle), présentes sur chaque page,
    n'avaient pas Annuler."""
    page = admin_client.get("/locations")  # n'importe quelle page suffit, base.html est partagé
    assert 'onclick="fermerModalMotDePasse()">Annuler' in page.text
    assert 'onclick="fermerModalDemandeRole()">Annuler' in page.text
