"""Tests pour le changement de mot de passe et les demandes de
changement de rôle (11/07/2026)."""
from tests.conftest import register_and_login


def test_changement_mot_de_passe(client, admin_client):
    utilisateur = register_and_login(client, "user_mdp", role=None, admin_client=admin_client)

    resp = utilisateur.patch("/users/me/password", json={
        "mot_de_passe_actuel": "testpass123",
        "nouveau_mot_de_passe": "nouveaumotdepasse456",
    })
    assert resp.status_code == 204

    # L'ancien mot de passe ne doit plus fonctionner
    resp = client.post("/auth/token", data={"username": "user_mdp", "password": "testpass123"})
    assert resp.status_code == 401

    # Le nouveau doit fonctionner
    resp = client.post("/auth/token", data={"username": "user_mdp", "password": "nouveaumotdepasse456"})
    assert resp.status_code in (200, 303)


def test_changement_mot_de_passe_refuse_si_actuel_incorrect(client, admin_client):
    utilisateur = register_and_login(client, "user_mdp2", role=None, admin_client=admin_client)
    resp = utilisateur.patch("/users/me/password", json={
        "mot_de_passe_actuel": "mauvais_mot_de_passe",
        "nouveau_mot_de_passe": "nouveaumotdepasse456",
    })
    assert resp.status_code == 400


def test_badge_notification_demandes_en_attente(client, admin_client):
    """13/07/2026 : jusqu'ici, rien ne signalait à un administrateur
    qu'une demande de changement de rôle existait -- il devait penser à
    aller voir la page Utilisateurs de lui-même. Un badge doit maintenant
    apparaître dans le bandeau dès qu'une demande est en attente."""
    # Avant toute demande : pas de badge.
    page_avant = admin_client.get("/sources")
    assert "notif-dot" not in page_avant.text

    utilisateur = register_and_login(client, "user_badge", role=None, admin_client=admin_client)
    utilisateur.post("/users/me/demande-role", json={"role_demande": "utilisateur_mn"})

    # Le même compte admin, reconnecté (la session partagée a changé de
    # côté à cause de register_and_login), doit maintenant voir le badge.
    admin_client.post("/auth/token", data={"username": "admintest", "password": "testpass123"})
    page_apres = admin_client.get("/sources")
    assert "notif-dot" in page_apres.text
    assert "(1 en attente)" in page_apres.text


def test_demande_de_role_puis_approbation(client, admin_client):
    utilisateur = register_and_login(client, "user_demande", role=None, admin_client=admin_client)

    resp = utilisateur.post("/users/me/demande-role", json={
        "role_demande": "utilisateur_mn", "commentaire": "j'en ai besoin pour mon travail",
    })
    assert resp.status_code == 200
    demande_id = resp.json()["id"]
    assert resp.json()["statut"] == "en_attente"

    # register_and_login a changé la session du client partagé : on
    # se reconnecte en admin pour la suite (même client, autre cookie).
    admin_client.post("/auth/token", data={"username": "admintest", "password": "testpass123"})

    # Visible par l'admin
    demandes = admin_client.get("/users/demandes-role").json()
    assert any(d["id"] == demande_id for d in demandes)

    # L'admin approuve
    resp = admin_client.patch(f"/users/demandes-role/{demande_id}", json={"action": "approuver"})
    assert resp.status_code == 200
    assert resp.json()["statut"] == "approuvee"

    # Le rôle doit être réellement appliqué
    users = admin_client.get("/users/").json()
    user_demande = next(u for u in users if u["username"] == "user_demande")
    assert user_demande["role"] == "utilisateur_mn"


def test_demande_de_role_rejetee_ne_change_pas_le_role(client, admin_client):
    utilisateur = register_and_login(client, "user_reject", role=None, admin_client=admin_client)
    resp = utilisateur.post("/users/me/demande-role", json={"role_demande": "admin"})
    demande_id = resp.json()["id"]

    admin_client.post("/auth/token", data={"username": "admintest", "password": "testpass123"})

    resp = admin_client.patch(f"/users/demandes-role/{demande_id}", json={"action": "rejeter"})
    assert resp.status_code == 200
    assert resp.json()["statut"] == "rejetee"

    users = admin_client.get("/users/").json()
    user_reject = next(u for u in users if u["username"] == "user_reject")
    assert user_reject["role"] == "lecteur"


def test_impossible_deux_demandes_en_attente(client, admin_client):
    utilisateur = register_and_login(client, "user_double", role=None, admin_client=admin_client)
    resp1 = utilisateur.post("/users/me/demande-role", json={"role_demande": "utilisateur"})
    assert resp1.status_code == 200

    resp2 = utilisateur.post("/users/me/demande-role", json={"role_demande": "utilisateur_mn"})
    assert resp2.status_code == 400


def test_utilisateur_non_admin_ne_peut_pas_lister_les_demandes(client, admin_client):
    utilisateur = register_and_login(client, "user_pasadmin", role=None, admin_client=admin_client)
    resp = utilisateur.get("/users/demandes-role")
    assert resp.status_code == 403
