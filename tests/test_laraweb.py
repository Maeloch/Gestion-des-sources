"""Tests du service LaraWeb : parseur (contre de vraies données capturées
depuis le site le 10/07/2026) et pipeline complet fetch -> cache -> API
(réseau simulé, cf. note ci-dessous)."""
from unittest.mock import patch, MagicMock
from app.services.laraweb import parser_fichier_lara, LaraWebError, get_or_fetch
from app.models.lara_cache import LaraCacheDB
from tests.conftest import register_and_login

# Échantillons réels, récupérés directement depuis http://www.lnhb.fr/nuclides/
# le 10/07/2026 (Sr-90 et Pu-239 : cas "normal" avec Half-life en années et
# en secondes ; Po-212 : cas limite, demi-vie si courte qu'elle n'est
# exprimée qu'en secondes).
SR_90 = """Nuclide ; Sr-90 
Element ; Strontium
Z ; 38
Daughter(s) ; (B-) ; Y-90 ; 100
Half-life (a) ; 28.80 ; 0.07
Half-life (s) ; 908.8E6 ; 2.2E6
Decay constant (1/s) ; 762.7E-12 ; 1.9E-12
Specific activity (Bq/g) ; 5.103E12 ; 0.012E12
Reference ; CEA/LNE-LNHB - 2005
No emissions for the selected type
==========================================================================================================
"""

PU_239 = """Nuclide ; Pu-239
Element ; Plutonium
Z ; 94
Half-life (a) ; 24.100E3 ; 0.011E3
Half-life (s) ; 760.52E9 ; 0.35E9
Specific activity (Bq/g) ; 2.2965E9 ; 0.0010E9
Reference ; KRI - 2007
==========================================================================================================
"""

PO_212 = """Nuclide ; Po-212
Element ; Polonium
Z ; 84
Half-life (s) ; 300E-9 ; 2E-9
Specific activity (Bq/g) ; 6.563E27 ; 0.044E27
Reference ; Surrey Univ. - 2010
==========================================================================================================
"""


def test_parser_sr90():
    r = parser_fichier_lara(SR_90)
    assert r["nuclide"] == "Sr-90"
    assert r["element"] == "Strontium"
    assert r["z"] == 38
    assert abs(r["half_life_years"] - 28.798) < 0.01
    assert r["specific_activity_bq_g"] == 5.103e12
    assert r["reference"] == "CEA/LNE-LNHB - 2005"


def test_parser_pu239_coherent_avec_reference_connue():
    """L'activité massique du Pu-239 est une valeur de référence bien
    connue (~2,3 GBq/g)."""
    r = parser_fichier_lara(PU_239)
    assert 2.2e9 < r["specific_activity_bq_g"] < 2.4e9
    assert abs(r["half_life_years"] - 24100) < 50


def test_parser_po212_demi_vie_tres_courte():
    """Cas limite : pas de ligne 'Half-life (a)', seulement en secondes."""
    r = parser_fichier_lara(PO_212)
    assert r["half_life_seconds"] == 3e-7
    assert r["half_life_years"] < 1e-13  # converti correctement malgré l'absence de ligne (a)


def test_parser_reponse_invalide_leve_erreur():
    try:
        parser_fichier_lara("<html>404 Not Found</html>")
        assert False, "aurait dû lever LaraWebError"
    except LaraWebError:
        pass


def test_pipeline_complet_fetch_cache_api(client, admin_client):
    """Vérifie tout le circuit : appel API -> service -> (réseau simulé,
    voir note) -> mise en cache -> réponse. Le réseau réel vers lnhb.fr
    n'est pas accessible depuis mon bac à sable de développement (liste
    blanche réseau restreinte) : la requête HTTP elle-même est simulée
    ici avec de vraies données capturées manuellement sur le site, mais le
    code qui l'effectue (`requests.get`) est le même que celui qui
    tournera réellement chez toi. À vérifier une fois en conditions
    réelles après livraison."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = PU_239

    with patch("app.services.laraweb.requests.get", return_value=mock_response) as mock_get:
        response = admin_client.get("/laraweb/Pu-239")
        assert response.status_code == 200
        data = response.json()
        assert data["nuclide"] == "Pu-239"
        assert data["element"] == "Plutonium"
        mock_get.assert_called_once()
        url_appelee = mock_get.call_args[0][0]
        assert url_appelee == "http://www.lnhb.fr/nuclides/Pu-239.lara.txt"

    # Deuxième appel : doit venir du cache, sans réappeler le réseau
    with patch("app.services.laraweb.requests.get", return_value=mock_response) as mock_get2:
        response2 = admin_client.get("/laraweb/Pu-239")
        assert response2.status_code == 200
        mock_get2.assert_not_called()


def test_lecteur_ne_peut_pas_interroger_laraweb(client, admin_client):
    lecteur = register_and_login(client, "lara_lecteur", role="lecteur", admin_client=admin_client)
    response = lecteur.get("/laraweb/Co-60")
    assert response.status_code == 403


def test_export_accessible_admin_et_mn_mais_pas_lecteur(client, admin_client):
    """Changement du 10/07/2026 : l'export (pas l'import) est désormais
    accessible aux utilisateurs MN, en plus des admins."""
    mn_user = register_and_login(client, "export_mn", role="utilisateur_mn", admin_client=admin_client)
    assert mn_user.get("/export/sources.xlsx").status_code == 200

    lecteur = register_and_login(client, "export_lecteur", role="lecteur", admin_client=admin_client)
    assert lecteur.get("/export/sources.xlsx").status_code == 403

    # L'import, lui, reste réservé aux admins même pour un utilisateur MN
    resp = mn_user.post("/import/inventaire", files={"file": ("test.xlsx", b"fake", "application/octet-stream")})
    assert resp.status_code == 403
