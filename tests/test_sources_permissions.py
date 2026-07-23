"""Tests sur les sources : permissions par rôle, cloisonnement Matière
Nucléaire, et archivage."""
from tests.conftest import register_and_login

SOURCE_NORMALE = {
    "id": "SRC-TEST-01", "type": "scellée", "etat_physique": "solide",
    "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
    "matiere_nucleaire": False,
}
SOURCE_MN = {
    "id": "SRC-TEST-MN", "type": "non-scellée", "etat_physique": "liquide",
    "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
    "matiere_nucleaire": True, "quantite": 100, "unite_quantite": "g",
}


def _lecteur(client, admin_client):
    return register_and_login(client, "lecteur1", role="lecteur", admin_client=admin_client)


def _utilisateur(client, admin_client):
    return register_and_login(client, "utilisateur1", role="utilisateur", admin_client=admin_client)


def _utilisateur_mn(client, admin_client):
    return register_and_login(client, "mn1", role="utilisateur_mn", admin_client=admin_client)


def test_admin_peut_creer_une_source(admin_client, default_location):
    resp = admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == "SRC-TEST-01"


def test_creation_sans_lieu_refusee(admin_client):
    """10/07/2026 : un lieu habituel est désormais obligatoire à la création."""
    resp = admin_client.post("/sources/", json=SOURCE_NORMALE)  # pas de emplacement_habituel_id
    assert resp.status_code == 422  # erreur de validation Pydantic (champ requis manquant)


def test_creation_avec_lieu_inexistant_refusee(admin_client):
    resp = admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": 99999})
    assert resp.status_code == 400
    assert "Aucun lieu" in resp.json()["detail"]


def test_identifiant_duplique_refuse_proprement(admin_client, default_location):
    payload = {**SOURCE_NORMALE, "emplacement_habituel_id": default_location}
    admin_client.post("/sources/", json=payload)
    resp = admin_client.post("/sources/", json=payload)
    assert resp.status_code == 400
    assert "existe déjà" in resp.json()["detail"]


def test_lecteur_ne_peut_pas_creer_de_source(client, admin_client, default_location):
    lecteur = _lecteur(client, admin_client)
    resp = lecteur.post("/sources/", json={**SOURCE_NORMALE, "id": "SRC-LECTEUR", "emplacement_habituel_id": default_location})
    assert resp.status_code == 403


def test_utilisateur_peut_creer_une_source_non_mn(client, admin_client, default_location):
    user = _utilisateur(client, admin_client)
    resp = user.post("/sources/", json={**SOURCE_NORMALE, "id": "SRC-USER-OK", "emplacement_habituel_id": default_location})
    assert resp.status_code == 200


def test_utilisateur_ne_peut_pas_creer_une_source_mn(client, admin_client, default_location):
    user = _utilisateur(client, admin_client)
    resp = user.post("/sources/", json={**SOURCE_MN, "id": "SRC-USER-MN-REFUS", "emplacement_habituel_id": default_location})
    assert resp.status_code == 403


def test_source_mn_invisible_pour_utilisateur_sans_acces_mn(client, admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_MN, "emplacement_habituel_id": default_location})
    user = _utilisateur(client, admin_client)

    liste = user.get("/sources/").json()
    assert SOURCE_MN["id"] not in [s["id"] for s in liste]

    resp = user.get(f"/sources/{SOURCE_MN['id']}")
    assert resp.status_code == 404


def test_source_mn_visible_pour_utilisateur_mn(client, admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_MN, "emplacement_habituel_id": default_location})
    mn_user = _utilisateur_mn(client, admin_client)
    liste = mn_user.get("/sources/").json()
    assert SOURCE_MN["id"] in [s["id"] for s in liste]


def test_classement_automatique_matiere_nucleaire_a_l_ajout_de_radionuclide(admin_client, default_location):
    """12/07/2026 : ajouter un radionucléide comme Pu-239 à une source qui
    n'est pas marquée MN doit la classer automatiquement, sans attendre
    que quelqu'un coche la case à la main."""
    admin_client.post("/sources/", json={
        "id": "SRC-AUTO-MN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location, "matiere_nucleaire": False,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-AUTO-MN", "nom": "Pu-239", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2026-01-01",
    })
    source = admin_client.get("/sources/SRC-AUTO-MN").json()
    assert source["matiere_nucleaire"] is True

    # Un radionucléide ordinaire (Co-60), lui, ne doit rien changer.
    admin_client.post("/sources/", json={
        "id": "SRC-PAS-MN", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location, "matiere_nucleaire": False,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-PAS-MN", "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2026-01-01",
    })
    source2 = admin_client.get("/sources/SRC-PAS-MN").json()
    assert source2["matiere_nucleaire"] is False


def test_archivage_sort_la_source_de_la_liste_active(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={"etat_utilisation": "en déchet"})

    actives = admin_client.get("/sources/").json()
    assert SOURCE_NORMALE["id"] not in [s["id"] for s in actives]

    archivees = admin_client.get("/sources/?archivees=true").json()
    assert SOURCE_NORMALE["id"] in [s["id"] for s in archivees]


def test_source_archivee_non_modifiable_par_non_admin(client, admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={"etat_utilisation": "en déchet"})

    mn_user = _utilisateur_mn(client, admin_client)
    resp = mn_user.put(f"/sources/{SOURCE_NORMALE['id']}", json={"commentaire": "test"})
    assert resp.status_code == 403


def test_source_archivee_modifiable_par_admin(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={"etat_utilisation": "en déchet"})

    resp = admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={"etat_utilisation": "en utilisation"})
    assert resp.status_code == 200

    actives = admin_client.get("/sources/").json()
    assert SOURCE_NORMALE["id"] in [s["id"] for s in actives]


def test_impossible_ajouter_radionuclide_sur_source_archivee(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={"etat_utilisation": "remisée"})

    resp = admin_client.post("/radionuclides/", json={
        "source_id": SOURCE_NORMALE["id"], "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2026-01-01",
    })
    assert resp.status_code == 400
    assert "archivée" in resp.json()["detail"]


def test_suppression_bloquee_si_historique(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_MN, "id": "SRC-HIST", "emplacement_habituel_id": default_location})
    admin_client.post("/consumptions/", json={"source_id": "SRC-HIST", "quantite_utilisee": 10})

    resp = admin_client.delete("/sources/SRC-HIST")
    assert resp.status_code == 400
    assert "historique" in resp.json()["detail"] or "consommations" in resp.json()["detail"]


def test_suppression_ok_sans_historique(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    resp = admin_client.delete(f"/sources/{SOURCE_NORMALE['id']}")
    assert resp.status_code == 204


def test_audit_precis_par_champ_modifie(admin_client, default_location):
    """10/07/2026 : l'audit doit montrer précisément quel champ a changé
    (et son avant/après), pas un unique événement générique "toutes"."""
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={
        "etat_utilisation": "en déchet",
        "commentaire": "test granularité",
    })

    logs = admin_client.get("/audit/").json()
    logs_source = [l for l in logs if l["id_source"] == SOURCE_NORMALE["id"] and l["action"] == "UPDATE"]

    champ_etat = next((l for l in logs_source if l["champ_modifie"] == "etat_utilisation"), None)
    assert champ_etat is not None, "aucune entrée précise pour etat_utilisation"
    assert champ_etat["valeur_avant"] == "en utilisation"
    assert champ_etat["valeur_apres"] == "en déchet"

    champ_commentaire = next((l for l in logs_source if l["champ_modifie"] == "commentaire"), None)
    assert champ_commentaire is not None, "aucune entrée précise pour commentaire"

    assert not any(l["champ_modifie"] == "toutes" for l in logs_source)


def test_audit_ignore_les_champs_fournis_mais_inchanges(admin_client, default_location):
    """Si le formulaire renvoie un champ avec la même valeur qu'avant, ça
    ne doit pas produire une entrée d'audit trompeuse (rien n'a changé)."""
    admin_client.post("/sources/", json={**SOURCE_NORMALE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_NORMALE['id']}", json={
        "etat_utilisation": SOURCE_NORMALE["etat_utilisation"],
    })
    logs = admin_client.get("/audit/").json()
    logs_source = [l for l in logs if l["id_source"] == SOURCE_NORMALE["id"] and l["champ_modifie"] == "etat_utilisation"]
    assert logs_source == []
