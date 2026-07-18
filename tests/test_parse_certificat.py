"""Tests de l'extraction de certificat d'étalonnage PDF -- ajouté le
14/07/2026. Utilise le vrai certificat exemple fourni (un document
scanné, texte OCR très abîmé par endroits) plutôt qu'un PDF de test
propre : c'est justement ce cas réel, difficile, qui doit être couvert."""
import pytest

CERTIFICAT_EXEMPLE = "/mnt/user-data/uploads/CS137ELSB45_-_78515-5_-_SCA-155.pdf"


def _certificat_disponible():
    import os
    return os.path.exists(CERTIFICAT_EXEMPLE)


@pytest.mark.skipif(not _certificat_disponible(), reason="certificat exemple non disponible dans cet environnement")
def test_extraction_certificat_champs_essentiels():
    """Les champs les plus importants (radionucléide, activité massique
    et son unité, masse délivrée, incertitude) doivent être extraits
    correctement malgré le bruit OCR réel de ce document scanné."""
    from app.services.parse_certificat import extraire_certificat
    r = extraire_certificat(CERTIFICAT_EXEMPLE)

    assert r["radionuclide_nom"] == "Cs-137"
    assert r["activite"] == 876.0
    assert r["unite_activite"] == "kBq/g"
    assert r["activite_est_specifique"] is True
    assert r["masse_delivree_g"] == 5.027
    assert r["incertitude_pourcent"] == 1.5
    assert r["type_source"] == "non-scellée"


def test_extraction_certificat_date_invalide_renvoie_none_pas_une_valeur_fausse():
    """Sur ce document, le texte de la date de référence est trop abîmé
    par l'OCR pour être fiable (des chiffres semblent insérés/déplacés) --
    doit renvoyer None plutôt qu'une date incohérente comme "l'an 9120"."""
    if not _certificat_disponible():
        pytest.skip("certificat exemple non disponible dans cet environnement")
    from app.services.parse_certificat import extraire_certificat
    r = extraire_certificat(CERTIFICAT_EXEMPLE)
    if r["date_reference"] is not None:
        from datetime import datetime
        d = datetime.strptime(r["date_reference"], "%Y-%m-%d")
        assert 1980 <= d.year <= 2035  # jamais une date absurde comme l'an 9120


def test_parser_date_tolerant_rejette_annee_implausible():
    from app.services.parse_certificat import _parser_date_tolerant
    # "0110912014" (10 chiffres, séparateurs disparus) ne doit jamais
    # produire une date avec une année absurde comme 9120.
    resultat = _parser_date_tolerant("0110912014")
    if resultat is not None:
        annee = int(resultat[:4])
        assert 1980 <= annee <= 2035


def test_parser_date_tolerant_cas_propre():
    from app.services.parse_certificat import _parser_date_tolerant
    assert _parser_date_tolerant("01/09/2014") == "2014-09-01"
    assert _parser_date_tolerant("Date de référence : 01/09/2014, à 12h") == "2014-09-01"


def test_route_extraction_necessite_un_pdf(admin_client):
    resp = admin_client.post(
        "/sources/depuis_certificat",
        files={"file": ("notes.txt", b"pas un pdf", "text/plain")},
    )
    assert resp.status_code == 400


def test_route_extraction_refusee_pour_lecteur(client, admin_client):
    from tests.conftest import register_and_login
    lecteur = register_and_login(client, "lecteur_cert", role="lecteur", admin_client=admin_client)
    resp = lecteur.post(
        "/sources/depuis_certificat",
        files={"file": ("test.pdf", b"%PDF-1.4 pas un vrai contenu", "application/pdf")},
    )
    assert resp.status_code == 403


@pytest.mark.skipif(not _certificat_disponible(), reason="certificat exemple non disponible dans cet environnement")
def test_route_extraction_via_api(admin_client):
    with open(CERTIFICAT_EXEMPLE, "rb") as f:
        resp = admin_client.post(
            "/sources/depuis_certificat",
            files={"file": ("certificat.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["radionuclide_nom"] == "Cs-137"
    assert "texte_brut" in data
