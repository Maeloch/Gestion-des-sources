"""Test de fumée ("smoke test") : aucune page HTML ne doit jamais planter
en erreur serveur (500), quel que soit l'état de connexion.

C'est directement le test qui aurait détecté le bug du 10/07/2026 (le menu
plantait pour tout visiteur non connecté, y compris sur la page de
connexion elle-même). Une page peut légitimement répondre 200 (affichée),
303 (redirigée vers la connexion) ou 403 (réservée à un rôle supérieur) —
jamais 500.
"""
import pytest
from tests.conftest import register_and_login

# Toutes les pages HTML de l'application (voir les @app.get(...) dans app/main.py).
PAGES_PUBLIQUES = ["/", "/auth/login", "/auth/register"]
PAGES_PROTEGEES = [
    "/sources", "/sources/archive", "/radionuclides", "/consumptions",
    "/movements", "/locations",
]
PAGES_ADMIN_OU_MN = ["/audit"]
PAGES_ADMIN_SEUL = ["/import-export", "/users"]

TOUTES_LES_PAGES = PAGES_PUBLIQUES + PAGES_PROTEGEES + PAGES_ADMIN_OU_MN + PAGES_ADMIN_SEUL


@pytest.mark.parametrize("page", TOUTES_LES_PAGES)
def test_aucune_page_ne_plante_pour_visiteur_anonyme(client, page):
    """LE test qui aurait détecté le bug du 10/07 : peu importe si la page
    s'affiche, redirige ou refuse l'accès — elle ne doit jamais planter."""
    response = client.get(page, follow_redirects=False)
    assert response.status_code != 500, f"{page} plante (500) pour un visiteur non connecté"
    assert response.status_code in (200, 303, 401, 403), (
        f"{page} renvoie un code inattendu ({response.status_code}) pour un visiteur non connecté"
    )


@pytest.mark.parametrize("page", TOUTES_LES_PAGES)
def test_aucune_page_ne_plante_pour_role_lecteur(client, admin_client, page):
    lecteur = register_and_login(client, "smoketest_lecteur", role="lecteur", admin_client=admin_client)
    response = lecteur.get(page, follow_redirects=False)
    assert response.status_code != 500, f"{page} plante (500) pour un lecteur"
    assert response.status_code in (200, 303, 401, 403)


@pytest.mark.parametrize("page", TOUTES_LES_PAGES)
def test_aucune_page_ne_plante_pour_role_utilisateur_mn(client, admin_client, page):
    mn_user = register_and_login(client, "smoketest_mn", role="utilisateur_mn", admin_client=admin_client)
    response = mn_user.get(page, follow_redirects=False)
    assert response.status_code != 500, f"{page} plante (500) pour un utilisateur MN"
    assert response.status_code in (200, 303, 401, 403)


def test_page_accueil_anonyme_redirige_vers_connexion(client):
    """"/" redirige désormais directement vers la connexion pour un
    visiteur anonyme (plus de page d'accueil séparée)."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"

    page = client.get("/auth/login")
    assert page.status_code == 200
    assert "Se connecter" in page.text
    assert "S'inscrire" in page.text


def test_page_accueil_apres_connexion_redirige_vers_sources(client, admin_client):
    """"/" redirige vers Sources pour un utilisateur connecté, et le menu
    affiche bien son nom (pas les liens de connexion)."""
    mn_user = register_and_login(client, "smoketest_login", role="utilisateur_mn", admin_client=admin_client)
    response = mn_user.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/sources"

    page = mn_user.get("/sources")
    assert page.status_code == 200
    assert "smoketest_login" in page.text
    assert "<a href=\"/auth/login\">Connexion</a>" not in page.text
