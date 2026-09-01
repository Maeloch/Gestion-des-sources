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
