"""Tests de l'export du document d'inventaire physique (imprimable) des
sources Matière Nucléaire -- ajouté le 13/07/2026."""
import pytest


def test_export_inventaire_mn_contient_les_sources_mn_actives(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "MN-INV-1", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "MN-INV-1", "nom": "U-235", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })

    resp = admin_client.get("/export/inventaire_mn.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"

    # Le contenu texte du PDF doit citer la source et son radionucléide.
    import pdfplumber
    import io
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        texte = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "MN-INV-1" in texte
    assert "U-235" in texte


def test_export_inventaire_mn_exclut_sources_non_mn(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "NON-MN-1", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": False, "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/inventaire_mn.pdf")
    assert resp.status_code == 200
    import pdfplumber, io
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        texte = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "NON-MN-1" not in texte


def test_export_inventaire_mn_exclut_sources_archivees(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "MN-ARCHIVEE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "détruite", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/inventaire_mn.pdf")
    assert resp.status_code == 200
    import pdfplumber, io
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        texte = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "MN-ARCHIVEE" not in texte


def test_export_inventaire_mn_refuse_sans_acces_mn(client, admin_client):
    from tests.conftest import register_and_login
    lecteur = register_and_login(client, "lecteur_inv", role="lecteur", admin_client=admin_client)
    resp = lecteur.get("/export/inventaire_mn.pdf")
    assert resp.status_code == 403
