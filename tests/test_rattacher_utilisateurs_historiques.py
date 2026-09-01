"""Tests du script rattachant les données déjà en base (consommations,
mouvements, audit) à un véritable utilisateur -- ajouté le 31/08/2026,
en réponse au cas réel "Liatimi" (une personne qui a réalisé une action
tracée par le passé, mais qui n'a pas de compte et n'en aura jamais)."""
from datetime import datetime, date

from app.models.consumption import ConsumptionDB
from app.models.movement import MovementDB
from app.models.audit import AuditLogDB, AuditAction
from app.models.user import UserDB
from app.scripts.rattacher_utilisateurs_historiques import rattacher


def test_rattache_a_un_compte_existant_par_nom_exact(admin_client, db_session, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-RATTACHE-1", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    compte = db_session.query(UserDB).filter(UserDB.username == "admintest").first()

    # Simule une consommation déjà en base, texte seul (comme avant
    # l'ajout d'utilisateur_id), sans passer par l'API qui le renseigne
    # déjà automatiquement -- c'est justement ce cas "déjà en base" que
    # ce script doit couvrir.
    db_session.add(ConsumptionDB(source_id="SRC-RATTACHE-1", quantite_utilisee=1, timestamp=datetime(2020, 1, 1), utilisateur="admintest"))
    db_session.commit()

    rapport = rattacher(db_session)

    assert rapport["consumptions"]["lignes_traitees"] == 1
    assert rapport["consumptions"]["rattachees_a_un_compte_existant"] == 1
    assert rapport["consumptions"]["utilisateurs_historiques_crees"] == []

    conso = db_session.query(ConsumptionDB).filter(ConsumptionDB.source_id == "SRC-RATTACHE-1").first()
    assert conso.utilisateur_id == compte.id


def test_cree_un_enregistrement_historique_si_aucune_correspondance(admin_client, db_session, default_location):
    """Le cas réel signalé : "Liatimi" n'a pas de compte (parti il y a
    15 ans) mais a réalisé une action tracée -- ne doit jamais rester
    sans utilisateur rattaché."""
    admin_client.post("/sources/", json={
        "id": "SRC-RATTACHE-2", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    db_session.add(ConsumptionDB(source_id="SRC-RATTACHE-2", quantite_utilisee=1, timestamp=datetime(2019, 1, 1), utilisateur="Liatimi"))
    db_session.commit()

    rapport = rattacher(db_session)

    assert rapport["consumptions"]["utilisateurs_historiques_crees"] == ["Liatimi"]
    liatimi = db_session.query(UserDB).filter(UserDB.username == "Liatimi").first()
    assert liatimi is not None
    assert liatimi.is_active is False
    assert liatimi.email is None

    conso = db_session.query(ConsumptionDB).filter(ConsumptionDB.source_id == "SRC-RATTACHE-2").first()
    assert conso.utilisateur_id == liatimi.id


def test_meme_nom_sur_plusieurs_tables_ne_cree_qu_un_seul_enregistrement(admin_client, db_session, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-RATTACHE-3", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    db_session.add(ConsumptionDB(source_id="SRC-RATTACHE-3", quantite_utilisee=1, timestamp=datetime(2019, 1, 1), utilisateur="Liatimi"))
    db_session.add(ConsumptionDB(source_id="SRC-RATTACHE-3", quantite_utilisee=1, timestamp=datetime(2019, 2, 1), utilisateur="Liatimi"))
    db_session.add(AuditLogDB(utilisateur="Liatimi", action=AuditAction.UTILISATION, table_modifiee="consumptions", id_source="SRC-RATTACHE-3"))
    db_session.commit()

    rattacher(db_session)

    tous_les_liatimi = db_session.query(UserDB).filter(UserDB.username == "Liatimi").all()
    assert len(tous_les_liatimi) == 1

    ids_utilises = {
        c.utilisateur_id for c in db_session.query(ConsumptionDB).filter(ConsumptionDB.source_id == "SRC-RATTACHE-3").all()
    }
    ids_utilises |= {a.utilisateur_id for a in db_session.query(AuditLogDB).filter(AuditLogDB.utilisateur == "Liatimi").all()}
    assert ids_utilises == {tous_les_liatimi[0].id}


def test_deuxieme_passage_ne_fait_rien_sur_ce_qui_est_deja_rattache(admin_client, db_session, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-RATTACHE-4", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    db_session.add(ConsumptionDB(source_id="SRC-RATTACHE-4", quantite_utilisee=1, timestamp=datetime(2019, 1, 1), utilisateur="Liatimi"))
    db_session.commit()

    rattacher(db_session)
    rapport_second_passage = rattacher(db_session)

    assert rapport_second_passage["consumptions"]["lignes_traitees"] == 0
    # Toujours un seul enregistrement, pas de doublon créé au second passage.
    assert db_session.query(UserDB).filter(UserDB.username == "Liatimi").count() == 1


def test_correspondance_insensible_a_la_casse(admin_client, db_session, default_location):
    """31/08/2026, signalé directement : GDO, BDL et CMO sont de vrais
    comptes connectés (Grégoire, Bernadette, Céline). Si le compte réel
    est enregistré autrement que la casse exacte utilisée sur la fiche
    papier transcrite, il ne doit surtout pas se retrouver dupliqué en
    un enregistrement historique distinct."""
    from app.repositories.user import UserRepository
    from app.models.user import UserCreate, UserRole
    repo = UserRepository(db_session)
    bernadette = repo.create(UserCreate(username="Bdl", email="bdl@test.fr", password="motdepasse123", role=UserRole.utilisateur))

    admin_client.post("/sources/", json={
        "id": "SRC-CASSE-1", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 100, "unite_quantite": "g",
    })
    # La fiche papier transcrite porte "BDL" (majuscules), le compte reel est "Bdl".
    db_session.add(ConsumptionDB(source_id="SRC-CASSE-1", quantite_utilisee=1, timestamp=datetime(2020, 1, 1), utilisateur="BDL"))
    db_session.commit()

    rapport = rattacher(db_session)

    assert rapport["consumptions"]["rattachees_a_un_compte_existant"] == 1
    assert rapport["consumptions"]["utilisateurs_historiques_crees"] == []
    assert db_session.query(UserDB).filter(UserDB.username.ilike("bdl")).count() == 1  # pas de doublon

    conso = db_session.query(ConsumptionDB).filter(ConsumptionDB.source_id == "SRC-CASSE-1").first()
    assert conso.utilisateur_id == bernadette.id
