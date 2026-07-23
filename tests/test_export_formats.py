"""Tests des exports ODS et PDF (en plus de XLSX) -- ajoutés le
13/07/2026, en anticipation d'une réduction de la dépendance à Microsoft.
Un test par export suffit pour couvrir le mécanisme de conversion partagé
(_repondre_export) sans multiplier les appels à LibreOffice (lents)."""


def test_export_sources_reflete_emplacement_actuel_pas_lieu_stockage_fige(admin_client, default_location):
    """14/07/2026, signalé directement : après avoir corrigé les lieux
    d'une source (fusion, renommage...), l'export continuait d'afficher
    l'ancien "lieu de stockage" -- un champ texte figé au moment de
    l'import, jamais mis à jour depuis, redondant avec les colonnes
    "Emplacement habituel/actuel" (elles, toujours à jour). La colonne
    "Lieu de stockage" est retirée de l'export : Emplacement habituel/
    actuel devient la seule source de vérité affichée."""
    admin_client.post("/sources/", json={
        "id": "SRC-LIEU-FIGE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    autre_lieu = admin_client.post("/locations/", json={"nom": "Nouveau lieu corrigé"}).json()
    admin_client.put("/sources/SRC-LIEU-FIGE", json={"emplacement_habituel_id": autre_lieu["id"]})

    resp = admin_client.get("/export/sources.xlsx")
    assert resp.status_code == 200

    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws = wb["Sources"]
    headers = [c.value for c in ws[1]]
    assert "Lieu de stockage" not in headers  # colonne retirée, plus de champ figé à afficher
    col_emplacement = headers.index("Emplacement habituel")
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "SRC-LIEU-FIGE":
            assert row[col_emplacement].value == "Nouveau lieu corrigé"


def test_export_sources_xlsx_toujours_fonctionnel_apres_refonte(admin_client, default_location):
    """Le format historique doit continuer à fonctionner à l'identique
    après la réécriture des routes pour accepter plusieurs formats."""
    admin_client.post("/sources/", json={
        "id": "SRC-EXPORT-FMT", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/sources.xlsx")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert resp.content[:2] == b"PK"  # signature d'un fichier zip (xlsx)


def test_export_sources_ods(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-EXPORT-ODS", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/sources.ods")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.oasis.opendocument.spreadsheet"
    assert resp.content[:2] == b"PK"  # ODS est aussi un zip


def test_export_annexe1_pdf(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-MN-PDF", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/annexe1.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_export_annexe1_pdf_est_bien_forme_paysage_a4(admin_client, default_location):
    """14/07/2026, bug réel signalé : converti sans réglage de mise en
    page, le PDF sortait en A4 portrait avec du texte tronqué/superposé
    (tableau trop large). Doit maintenant sortir en A4 paysage."""
    admin_client.post("/sources/", json={
        "id": "SRC-MN-LAYOUT", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/annexe1.pdf")
    assert resp.status_code == 200

    import pdfplumber, io
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        page = pdf.pages[0]
        assert page.width > page.height  # paysage, pas portrait


def test_export_annexe1_contient_la_date_du_jour(admin_client, default_location):
    """14/07/2026 : la date d'inventaire (cellule I4) était absente."""
    from datetime import date
    admin_client.post("/sources/", json={
        "id": "SRC-MN-DATE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/annexe1.xlsx")
    assert resp.status_code == 200

    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    valeur_i4 = wb.active["I4"].value
    assert valeur_i4 == date.today().strftime("%d/%m/%Y")


def test_export_tableau1a_contient_la_date_du_jour(admin_client, default_location):
    """14/07/2026 : la date d'inventaire (cellule H3) était absente."""
    from datetime import date
    resp = admin_client.get("/export/tableau1a.xlsx")
    assert resp.status_code == 200

    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    valeur_h3 = wb.active["H3"].value
    assert valeur_h3 == date.today().strftime("%d/%m/%Y")


def test_export_tableau1a_ods_conserve_len_tete_avertissements(admin_client, default_location):
    """Le refactor doit conserver l'en-tête X-Avertissements-Count,
    quel que soit le format demandé -- pas seulement xlsx."""
    admin_client.post("/sources/", json={
        "id": "SRC-TAB-ODS", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "matiere_nucleaire": True, "emplacement_habituel_id": default_location,
    })
    resp = admin_client.get("/export/tableau1a.ods")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.oasis.opendocument.spreadsheet"


def test_export_format_non_reconnu_404(admin_client):
    resp = admin_client.get("/export/sources.docx")
    assert resp.status_code == 404
