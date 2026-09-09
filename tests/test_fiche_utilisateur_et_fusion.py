"""Tests de la fiche utilisateur, de la fusion et de la protection contre
la suppression d'un compte qui porte de l'historique -- ajouté le
31/08/2026, en réponse à la demande de contrôle total sur les
utilisateurs et au principe "jamais sans attache"."""
from datetime import datetime

from app.models.consumption import ConsumptionDB
from app.models.user import UserDB, UserCreateHistorique
from app.repositories.user import UserRepository


def _id_de(admin_client, username):
    for u in admin_client.get("/users/").json():
        if u["username"] == username:
            return u["id"]
    raise AssertionError(f"utilisateur '{username}' introuvable")


def test_fiche_utilisateur_regroupe_son_activite(admin_client, db_session, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-FICHE-U1", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    admin_client.post("/consumptions/", json={"source_id": "SRC-FICHE-U1", "quantite_utilisee": 4})

    admin_id = _id_de(admin_client, "admintest")
    page = admin_client.get(f"/users/{admin_id}/fiche")

    assert page.status_code == 200
    assert "SRC-FICHE-U1" in page.text
    assert "compte actif" in page.text


def test_fiche_utilisateur_historique_affiche_le_bon_statut(admin_client, db_session):
    liatimi = UserRepository(db_session).create_historique(UserCreateHistorique(username="Liatimi"))
    page = admin_client.get(f"/users/{liatimi.id}/fiche")
    assert page.status_code == 200
    assert "historique" in page.text
    assert "jamais connecté" in page.text


def test_fiche_utilisateur_reservee_aux_admins(client, admin_client):
    from tests.conftest import register_and_login
    admin_id = _id_de(admin_client, "admintest")
    lecteur = register_and_login(client, "lecteur_fiche_user", role="lecteur", admin_client=admin_client)

    resp = lecteur.get(f"/users/{admin_id}/fiche")
    assert resp.status_code in (401, 403)


def test_suppression_bloquee_si_historique_rattache(admin_client, db_session, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-PROTECTION-1", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    liatimi = UserRepository(db_session).create_historique(UserCreateHistorique(username="Liatimi"))
    db_session.add(ConsumptionDB(source_id="SRC-PROTECTION-1", quantite_utilisee=1, timestamp=datetime(2019, 1, 1), utilisateur="Liatimi", utilisateur_id=liatimi.id))
    db_session.commit()

    resp = admin_client.delete(f"/users/{liatimi.id}")
    assert resp.status_code == 400
    assert "impossible de le supprimer" in resp.json()["detail"].lower()
    assert db_session.query(UserDB).filter(UserDB.id == liatimi.id).first() is not None


def test_suppression_possible_sans_historique_rattache(admin_client, db_session):
    """Un enregistrement historique créé par erreur (ex: faute de frappe
    corrigée avant tout rattachement réel) doit rester supprimable
    normalement -- la protection ne s'applique qu'à ce qui porte
    effectivement de l'historique."""
    fantome = UserRepository(db_session).create_historique(UserCreateHistorique(username="FauteDeFrappe"))
    resp = admin_client.delete(f"/users/{fantome.id}")
    assert resp.status_code == 204


def test_fusion_reattache_tout_puis_supprime_la_source(admin_client, db_session, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-FUSION-1", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    liatimi = UserRepository(db_session).create_historique(UserCreateHistorique(username="Liatimi"))
    db_session.add(ConsumptionDB(source_id="SRC-FUSION-1", quantite_utilisee=1, timestamp=datetime(2019, 1, 1), utilisateur="Liatimi", utilisateur_id=liatimi.id))
    db_session.commit()
    admin_id = _id_de(admin_client, "admintest")

    resp = admin_client.post(f"/users/{liatimi.id}/fusionner", json={"cible_id": admin_id})
    assert resp.status_code == 204

    assert db_session.query(UserDB).filter(UserDB.id == liatimi.id).first() is None
    conso = db_session.query(ConsumptionDB).filter(ConsumptionDB.source_id == "SRC-FUSION-1").first()
    assert conso.utilisateur_id == admin_id
    assert conso.utilisateur == "admintest"


def test_fusion_elle_meme_tracee_dans_audit(admin_client, db_session):
    liatimi = UserRepository(db_session).create_historique(UserCreateHistorique(username="Liatimi"))
    admin_id = _id_de(admin_client, "admintest")

    admin_client.post(f"/users/{liatimi.id}/fusionner", json={"cible_id": admin_id})

    audit = admin_client.get("/audit").text
    assert "Liatimi" in audit
    assert "fusion" in audit.lower()


def test_fusion_avec_soi_meme_refusee(admin_client):
    admin_id = _id_de(admin_client, "admintest")
    resp = admin_client.post(f"/users/{admin_id}/fusionner", json={"cible_id": admin_id})
    assert resp.status_code == 400


def test_fusion_utilisateur_inexistant_404(admin_client):
    admin_id = _id_de(admin_client, "admintest")
    resp = admin_client.post("/users/999999/fusionner", json={"cible_id": admin_id})
    assert resp.status_code == 404


def test_admin_definit_le_mot_de_passe_dun_autre_utilisateur(admin_client, db_session):
    """01/09/2026, demandé directement : gestion admin renforcée des
    comptes, sur le modèle de Yunohost. Différent de /me/password
    (self-service, exige l'ancien) : ici l'admin agit directement, sans
    connaître le mot de passe actuel."""
    from app.repositories.user import UserRepository
    from app.models.user import UserCreate, UserRole
    bernadette = UserRepository(db_session).create(UserCreate(
        username="bdl_pwd", email="bdl_pwd@test.fr", password="ancienmotdepasse1", role=UserRole.utilisateur,
    ))

    resp = admin_client.patch(f"/users/{bernadette.id}/password", json={"nouveau_mot_de_passe": "nouveaumotdepasse999"})
    assert resp.status_code == 204

    # Le nouveau mot de passe fonctionne vraiment pour se connecter.
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client_frais:
        connexion = client_frais.post("/auth/token", data={"username": "bdl_pwd", "password": "nouveaumotdepasse999"})
        assert connexion.status_code in (200, 303)


def test_admin_ne_peut_pas_definir_mot_de_passe_sur_historique(admin_client, db_session):
    from app.repositories.user import UserRepository
    from app.models.user import UserCreateHistorique
    liatimi = UserRepository(db_session).create_historique(UserCreateHistorique(username="Liatimi_pwd"))
    resp = admin_client.patch(f"/users/{liatimi.id}/password", json={"nouveau_mot_de_passe": "nouveaumotdepasse999"})
    assert resp.status_code == 400


def test_admin_definit_mot_de_passe_trop_court_refuse(admin_client, db_session):
    from app.repositories.user import UserRepository
    from app.models.user import UserCreate, UserRole
    u = UserRepository(db_session).create(UserCreate(
        username="court_pwd", email="court_pwd@test.fr", password="motdepasse123", role=UserRole.utilisateur,
    ))
    resp = admin_client.patch(f"/users/{u.id}/password", json={"nouveau_mot_de_passe": "abc"})
    assert resp.status_code == 400


def test_non_admin_ne_peut_pas_definir_mot_de_passe_dautrui(client, admin_client):
    from tests.conftest import register_and_login
    admin_id = _id_de(admin_client, "admintest")
    lecteur = register_and_login(client, "lecteur_pwd_test", role="lecteur", admin_client=admin_client)
    resp = lecteur.patch(f"/users/{admin_id}/password", json={"nouveau_mot_de_passe": "nouveaumotdepasse999"})
    assert resp.status_code in (401, 403)


def test_revoquer_acces_empeche_la_connexion(admin_client, db_session):
    """01/09/2026 : révoquer l'accès (plutôt que supprimer) doit
    réellement empêcher la connexion, pas seulement changer un champ
    sans effet."""
    from app.repositories.user import UserRepository
    from app.models.user import UserCreate, UserRole
    u = UserRepository(db_session).create(UserCreate(
        username="revoque_test", email="revoque_test@test.fr", password="motdepasse123", role=UserRole.utilisateur,
    ))

    resp = admin_client.patch(f"/users/{u.id}/acces", json={"actif": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client_frais:
        connexion = client_frais.post("/auth/token", data={"username": "revoque_test", "password": "motdepasse123"})
        assert connexion.status_code == 401


def test_reactiver_acces_permet_de_nouveau_la_connexion(admin_client, db_session):
    from app.repositories.user import UserRepository
    from app.models.user import UserCreate, UserRole
    u = UserRepository(db_session).create(UserCreate(
        username="reactive_test", email="reactive_test@test.fr", password="motdepasse123", role=UserRole.utilisateur,
    ))
    admin_client.patch(f"/users/{u.id}/acces", json={"actif": False})

    resp = admin_client.patch(f"/users/{u.id}/acces", json={"actif": True})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client_frais:
        connexion = client_frais.post("/auth/token", data={"username": "reactive_test", "password": "motdepasse123"})
        assert connexion.status_code in (200, 303)


def test_admin_ne_peut_pas_revoquer_son_propre_acces(admin_client):
    admin_id = _id_de(admin_client, "admintest")
    resp = admin_client.patch(f"/users/{admin_id}/acces", json={"actif": False})
    assert resp.status_code == 400


def test_revocation_tracee_dans_audit(admin_client, db_session):
    from app.repositories.user import UserRepository
    from app.models.user import UserCreate, UserRole
    u = UserRepository(db_session).create(UserCreate(
        username="audit_revoque", email="audit_revoque@test.fr", password="motdepasse123", role=UserRole.utilisateur,
    ))
    admin_client.patch(f"/users/{u.id}/acces", json={"actif": False})

    audit = admin_client.get("/audit").text
    assert "audit_revoque" in audit or "is_active" in audit.lower()


def test_connexion_sur_historique_ne_plante_pas(db_session):
    """01/09/2026, vrai bug trouvé en construisant la révocation : un
    enregistrement historique n'a pas de mot de passe du tout
    (hashed_password=None) -- verify_password() planterait dessus si
    is_active n'était pas vérifié avant. Doit échouer proprement (401),
    jamais planter (500)."""
    from app.repositories.user import UserRepository
    from app.models.user import UserCreateHistorique
    UserRepository(db_session).create_historique(UserCreateHistorique(username="Liatimi_connexion"))

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client_frais:
        connexion = client_frais.post("/auth/token", data={"username": "Liatimi_connexion", "password": "peu importe"})
        assert connexion.status_code == 401
