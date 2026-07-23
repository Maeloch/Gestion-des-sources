"""Tests des améliorations d'ergonomie demandées le 14/07/2026 : recherche
libre et filtre par radionucléide sur la page Sources, bouton "Consommer"
avec présélection automatique, et champ de sélection de source à
consommer converti en texte avec suggestions (au lieu d'un menu déroulant
pénible avec beaucoup de sources)."""


def test_page_sources_liste_les_radionuclides_distincts_pour_le_filtre(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-FILTRE-1", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-FILTRE-1", "nom": "Am-241", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    page = admin_client.get("/sources")
    assert page.status_code == 200
    assert 'id="filterRadionuclide"' in page.text
    assert '<option value="Am-241">Am-241</option>' in page.text
    assert 'id="searchId"' in page.text


def test_page_sources_ligne_porte_les_radionuclides_pour_le_filtre_js(admin_client, default_location):
    """Le filtre JS s'appuie sur data-sort-radionuclides (déjà utilisé
    pour le tri) plutôt qu'un attribut dédié -- vérifie qu'il est bien
    présent sur chaque ligne."""
    admin_client.post("/sources/", json={
        "id": "SRC-FILTRE-2", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-FILTRE-2", "nom": "Ra-226", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    page = admin_client.get("/sources")
    assert 'data-sort-radionuclides="Ra-226"' in page.text


def test_bouton_consommer_present_sur_source_consommable_active(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-CONSOMMER-BTN", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 5, "unite_quantite": "g",
    })
    page = admin_client.get("/sources")
    assert 'href="/consumptions?source=SRC-CONSOMMER-BTN"' in page.text


def test_bouton_consommer_absent_sur_source_scellee(admin_client, default_location):
    """Le bouton "Consommer" n'a de sens que pour une source gaz/liquide
    (consommable) -- absent pour une source scellée."""
    admin_client.post("/sources/", json={
        "id": "SRC-SCELLEE-PAS-CONSO", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    page = admin_client.get("/sources")
    assert 'href="/consumptions?source=SRC-SCELLEE-PAS-CONSO"' not in page.text


def test_page_consumptions_presequence_la_source_depuis_l_url(admin_client, default_location):
    """?source=XXX (venant du bouton "Consommer" de la page Sources) doit
    être lu côté client pour ouvrir la pop-up directement sur la bonne
    source -- vérifié ici au niveau du HTML/JS rendu (le comportement
    dynamique lui-même est vérifié séparément avec un moteur DOM)."""
    admin_client.post("/sources/", json={
        "id": "SRC-PRESELECT", "type": "non-scellée", "etat_physique": "gaz",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "L",
    })
    page = admin_client.get("/consumptions?source=SRC-PRESELECT")
    assert page.status_code == 200
    assert "preselectionDepuisUrl" in page.text
    assert "params.get('source')" in page.text


def test_champ_source_consumptions_est_un_texte_avec_datalist_pas_un_menu_deroulant(admin_client, default_location):
    """14/07/2026 : remplacé un <select> (pénible avec beaucoup de
    sources) par un champ texte avec suggestions natives (datalist),
    tapable au clavier plutôt que seulement cliquable."""
    admin_client.post("/sources/", json={
        "id": "SRC-DATALIST", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 5, "unite_quantite": "g",
    })
    page = admin_client.get("/consumptions")
    assert page.status_code == 200
    assert '<select id="source_id"' not in page.text
    assert 'list="sourcesDatalist"' in page.text
    assert '<datalist id="sourcesDatalist">' in page.text
    assert '<option value="SRC-DATALIST">' in page.text


def test_soumission_consumptions_rejette_saisie_ne_correspondant_a_aucune_source(admin_client, default_location):
    """Le champ texte accepte n'importe quelle saisie, contrairement à un
    menu déroulant -- la validation JS au moment de la soumission (pas
    testable directement ici, teste plutôt la présence du contrôle) doit
    exister dans le script rendu."""
    admin_client.post("/sources/", json={
        "id": "SRC-VALIDATION-TEST", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 5, "unite_quantite": "g",
    })
    page = admin_client.get("/consumptions")
    assert "ne correspond à aucune source gaz/liquide connue" in page.text
    assert "stocksSources[sourceId]" in page.text
