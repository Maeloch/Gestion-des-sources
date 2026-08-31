"""Tests de la fiche détaillée par source (/sources/{id}/fiche) --
demandé le 28/07/2026, réalisé le 30/07/2026."""


def test_fiche_source_regroupe_toutes_les_informations(admin_client, default_location):
    autre_lieu = admin_client.post("/locations/", json={"nom": "Lieu Test Fiche"}).json()
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-COMPLETE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "fournisseur": "CERCA", "commentaire": "Commentaire de test",
        "emplacement_habituel_id": default_location, "quantite_initiale": 200, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-FICHE-COMPLETE", "nom": "Cs-137", "activite": 1000000,
        "unite_activite": "Bq", "date_reference": "2020-01-01", "periode": 30.17,
    })
    admin_client.post("/movements/", json={
        "source_id": "SRC-FICHE-COMPLETE", "to_location_id": autre_lieu["id"], "commentaire": "mouvement test",
    })
    admin_client.post("/consumptions/", json={
        "source_id": "SRC-FICHE-COMPLETE", "masse_avant": 200, "masse_apres": 190, "commentaire": "conso test",
    })

    page = admin_client.get("/sources/SRC-FICHE-COMPLETE/fiche")
    assert page.status_code == 200
    assert "CERCA" in page.text
    assert "Commentaire de test" in page.text
    assert "Cs-137" in page.text
    assert "mouvement test" in page.text
    assert "conso test" in page.text
    assert "190.0" in page.text  # quantité restante correctement calculée


def test_fiche_source_distingue_emplacement_habituel_et_actuel(admin_client, default_location):
    autre_lieu = admin_client.post("/locations/", json={"nom": "Lieu Emprunt Fiche"}).json()
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-EMPLACEMENTS", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/movements/", json={"source_id": "SRC-FICHE-EMPLACEMENTS", "to_location_id": autre_lieu["id"]})

    page = admin_client.get("/sources/SRC-FICHE-EMPLACEMENTS/fiche")
    assert "en cours" in page.text  # le mouvement n'a pas de retour


def test_fiche_source_bouton_emprunter_absent_si_deja_emprunte(admin_client, default_location):
    autre_lieu = admin_client.post("/locations/", json={"nom": "Lieu Deja Emprunte"}).json()
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-DEJA-EMPRUNTE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/movements/", json={"source_id": "SRC-FICHE-DEJA-EMPRUNTE", "to_location_id": autre_lieu["id"]})

    page = admin_client.get("/sources/SRC-FICHE-DEJA-EMPRUNTE/fiche")
    assert 'href="/movements?source=SRC-FICHE-DEJA-EMPRUNTE"' not in page.text


def test_fiche_source_bouton_emprunter_present_si_disponible(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-DISPONIBLE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources/SRC-FICHE-DISPONIBLE/fiche")
    assert 'href="/movements?source=SRC-FICHE-DISPONIBLE"' in page.text


def test_fiche_source_masses_consommees_avec_unite(admin_client, default_location):
    """31/07/2026, signalé directement : les masses avant/après d'une
    consommation n'affichaient aucune unité sur cette page, contrairement
    à la page Consommations elle-même."""
    admin_client.post("/sources/", json={
        "id": "SRC-MASSE-UNITE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 200, "unite_quantite": "g",
    })
    admin_client.post("/consumptions/", json={
        "source_id": "SRC-MASSE-UNITE", "masse_avant": 200, "masse_apres": 190,
    })
    page = admin_client.get("/sources/SRC-MASSE-UNITE/fiche")
    assert "200.0 g" in page.text
    assert "190.0 g" in page.text


def test_fiche_source_bouton_modifier_ouvre_directement_le_formulaire(admin_client, default_location):
    """31/07/2026 : "Modifier" renvoyait vers la liste filtrée, mais
    fallait recliquer "Modifier" une seconde fois pour arriver au
    formulaire -- signalé comme confus. Toujours pas de duplication du
    formulaire complexe sur cette page (choix maintenu), mais le lien
    ouvre maintenant directement le formulaire via ?modifier=XXX, même
    principe que ?source=XXX sur Consommations/Mouvements."""
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-MODIFIER", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources/SRC-FICHE-MODIFIER/fiche")
    assert 'href="/sources?recherche=SRC-FICHE-MODIFIER&modifier=SRC-FICHE-MODIFIER"' in page.text
    assert "openEditModal" not in page.text


def test_fiche_source_404_si_source_inexistante(admin_client):
    resp = admin_client.get("/sources/SRC-N-EXISTE-PAS/fiche")
    assert resp.status_code == 404


def test_fiche_source_sans_donnees_associees_ne_plante_pas(admin_client, default_location):
    """Une source toute neuve, sans radionucléide/mouvement/consommation,
    doit quand même afficher une fiche propre (messages "aucun ... pour
    cette source" plutôt qu'une erreur)."""
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-VIDE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources/SRC-FICHE-VIDE/fiche")
    assert page.status_code == 200
    assert "Aucun radionucléide" in page.text
    assert "Aucun mouvement" in page.text
    assert "Aucune consommation" in page.text


def test_identifiant_source_cliquable_vers_sa_propre_fiche(admin_client, default_location):
    """L'identifiant, sur la page Sources elle-même, était en texte brut
    -- devient cliquable vers sa propre fiche, comme partout ailleurs."""
    admin_client.post("/sources/", json={
        "id": "SRC-AUTO-LIEN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources")
    assert 'href="/sources/SRC-AUTO-LIEN/fiche"' in page.text


def test_fiche_source_mn_inaccessible_sans_droit_mn(client, admin_client, default_location):
    """Une source MN ne doit pas être consultable par un compte sans
    accès MN -- 404 plutôt que 403, pour ne pas même confirmer
    l'existence de la source (même logique que l'API JSON existante)."""
    from tests.conftest import register_and_login
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-MN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "matiere_nucleaire": True,
    })
    lecteur = register_and_login(client, "lecteur_sans_mn", role="lecteur", admin_client=admin_client)
    resp = lecteur.get("/sources/SRC-FICHE-MN/fiche")
    assert resp.status_code == 404
