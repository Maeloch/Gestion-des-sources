"""Fixtures partagées pour les tests. La base de données de test est
entièrement isolée (SQLite en mémoire) : les tests ne touchent jamais à
data/database.sqlite.

Note : importer `app.main` déclenche les migrations automatiques sur le
fichier data/database.sqlite réel (voir app/main.py). C'est un effet de
bord inoffensif (les migrations ne font rien si déjà appliquées) mais pas
totalement propre — à améliorer un jour en rendant les migrations
paresseuses plutôt qu'exécutées à l'import. Les tests eux-mêmes n'utilisent
que la base en mémoire ci-dessous, jamais ce fichier réel.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def db_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(db_engine):
    """Session directe sur le même moteur que admin_client -- ajoutée le
    28/07/2026 pour tester un script autonome (import de consommations
    historiques) qui travaille directement avec une session de base de
    données, hors du chemin HTTP habituel de ce projet. Utilisée
    conjointement avec admin_client dans un même test (les deux
    partagent le même db_engine) : sources créées via l'API comme
    d'habitude, script testé directement sur cette même base."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def register_and_login(client: TestClient, username: str, role: str = None, admin_client: TestClient = None) -> TestClient:
    """Crée un utilisateur, le promeut au rôle demandé si besoin (nécessite
    un client déjà connecté en admin), puis renvoie un TestClient connecté
    avec ce compte (cookie de session posé)."""
    resp = client.post("/auth/register", json={
        "username": username,
        "email": f"{username}@example.com",
        "password": "testpass123",
        "full_name": username,
    })
    assert resp.status_code == 200, resp.text

    if role and role != "lecteur":
        assert admin_client is not None, "un client admin est nécessaire pour changer un rôle"
        users = admin_client.get("/users/").json()
        user_id = next(u["id"] for u in users if u["username"] == username)
        resp = admin_client.patch(f"/users/{user_id}/role", json={"role": role})
        assert resp.status_code == 200, resp.text

    resp = client.post("/auth/token", data={"username": username, "password": "testpass123"})
    assert resp.status_code in (200, 303), resp.text
    return client


@pytest.fixture()
def default_location(admin_client):
    """Un lieu prêt à l'emploi, nécessaire depuis que emplacement_habituel_id
    est obligatoire à la création d'une source (10/07/2026)."""
    resp = admin_client.post("/locations/", json={"nom": "Lieu de test par défaut"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest.fixture()
def admin_client(client):
    """Un client connecté avec un compte admin fraîchement créé."""
    # Le tout premier compte n'est pas admin automatiquement : on le crée
    # normalement puis on le promeut directement en base pour amorcer
    # (aucune autre façon de créer le tout premier admin, cohérent avec le
    # fonctionnement réel de l'application - voir seed_db.py).
    resp = client.post("/auth/register", json={
        "username": "admintest",
        "email": "admintest@example.com",
        "password": "testpass123",
        "full_name": "Admin Test",
    })
    assert resp.status_code == 200, resp.text

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    from app.models.user import UserDB, UserRole
    user = db.query(UserDB).filter(UserDB.username == "admintest").first()
    user.role = UserRole.admin
    db.commit()
    db.close()

    resp = client.post("/auth/token", data={"username": "admintest", "password": "testpass123"})
    assert resp.status_code in (200, 303), resp.text
    return client
