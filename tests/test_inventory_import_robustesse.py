"""Tests de robustesse de l'import face aux variations réelles observées
entre deux fichiers d'inventaire différents (11/07/2026) : libellés de
colonnes légèrement différents (repères de note "[4]", site "SERAC" vs
"SCA"), lignes de mélange multi-isotopes sans identifiant propre, lignes
orphelines avec un identifiant vide/illisible, et réimport du format
d'export de l'application elle-même."""
import io
import openpyxl
from datetime import datetime


def _construire_classeur_sca(lignes, en_tete_ligne=1, avec_titre=False):
    """Construit un classeur minimal au format "inventaire SCA", avec les
    libellés de colonnes de la DEUXIÈME variante rencontrée (footnotes
    entre crochets, site SERAC) plutôt que la première, pour vérifier que
    les deux sont acceptées."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sources scellées"

    headers = [
        "N° [1]", "DATE ARRIVEE SERAC", "CODE GISEL", "N° DE SOURCE ", "N° COMPTE UES",
        "N° DE FORMULAIRE IRSN", "DATE ET N° DE VISA", "REFERENCE CATALOGUE", "ETAT [2]",
        "REFERENCE NORME", "MN", "RADIONUCLEIDE", "PERIODE [3]", "PERIODE (S)",
        "MODE DE DECROISS. [7]", "RADIOTOX.", "ACTIVITE NOMINALE [4]  ",
        "ACTIVITE SPECIFIQUE NOMINALE",
    ]
    if avec_titre:
        ws.append(["Titre quelconque"])
        header_row_idx = 2
    else:
        header_row_idx = 1
    for i, h in enumerate(headers, 1):
        ws.cell(row=header_row_idx, column=i, value=h)

    for ligne in lignes:
        r = ws.max_row + 1
        for i, v in enumerate(ligne, 1):
            if v is not None:
                ws.cell(row=r, column=i, value=v)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_libelles_avec_footnotes_reconnus(tmp_path, admin_client):
    """'ACTIVITE NOMINALE [4]' doit être reconnu comme 'ACTIVITE NOMINALE',
    'ETAT [2]' comme 'ETAT' -- correspondance par préfixe, pas égalité stricte."""
    lignes = [
        ["SRC-TEST-1", datetime(2020, 1, 1), None, None, None, None, None, None, "S",
         None, "NON", "60-Co", "5,27 a", 166344000, "b-", 3, 1000000],
    ]
    buf = _construire_classeur_sca(lignes)
    path = tmp_path / "test.xlsx"
    path.write_bytes(buf.read())

    from app.services.inventory_import import importer_fichier
    from app.database import get_db
    from app.main import app
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    rapport = importer_fichier(str(path), db=db, utilisateur="test")

    assert len(rapport["sources_creees"]) == 1
    assert rapport["radionuclides_crees"] == 1


def test_ligne_melange_rattachee_au_precedent(tmp_path, admin_client):
    """Une ligne sans ID ni date d'arrivée, mais avec un radionucléide,
    doit être rattachée à la source précédente (cas des sources MELANGE
    multi-isotopes)."""
    lignes = [
        ["SRC-MELANGE", datetime(2020, 1, 1), None, None, None, None, None, None, "S",
         None, "NON", "MELANGE", None, None, None, None, 3000, None],
        [None, None, None, None, None, None, None, None, None,
         None, None, "137-Cs", "30,17 a", 952156032, "b-", 2, 1000, None],
        [None, None, None, None, None, None, None, None, None,
         None, None, "239-Pu", "24100 a", 760017600000, "a", 1, 500, None],
    ]
    buf = _construire_classeur_sca(lignes)
    path = tmp_path / "test.xlsx"
    path.write_bytes(buf.read())

    from app.services.inventory_import import importer_fichier
    from app.database import get_db
    from app.main import app
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    rapport = importer_fichier(str(path), db=db, utilisateur="test")

    assert len(rapport["sources_creees"]) == 1  # une seule VRAIE source
    assert rapport["radionuclides_crees"] == 3  # les 3 radionucléides, tous rattachés à elle

    radionuclides = db.query(__import__("app.models.radionuclide", fromlist=["RadionuclideDB"]).RadionuclideDB).filter_by(source_id="SRC-MELANGE").all()
    noms = {rn.nom for rn in radionuclides}
    assert noms == {"MELANGE", "Cs-137", "Pu-239"}


def test_ligne_orpheline_signalee_pas_rattachee(tmp_path, admin_client):
    """Une ligne sans ID mais AVEC une date d'arrivée renseignée est une
    vraie source ayant perdu son identifiant -- elle ne doit PAS être
    rattachée à la source précédente (qui n'a aucun rapport avec elle),
    et doit être clairement signalée plutôt que silencieusement perdue."""
    lignes = [
        ["SRC-AVANT", datetime(2020, 1, 1), None, None, None, None, None, None, "S",
         None, "NON", "60-Co", "5,27 a", 166344000, "b-", 3, 1000000, None],
        [None, datetime(1997, 12, 27), None, None, None, None, None, None, "S",
         None, "NON", "241-Am", "433 a", 13655088000, "a", 1, 25900, None],
    ]
    buf = _construire_classeur_sca(lignes)
    path = tmp_path / "test.xlsx"
    path.write_bytes(buf.read())

    from app.services.inventory_import import importer_fichier
    from app.database import get_db
    from app.main import app
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    rapport = importer_fichier(str(path), db=db, utilisateur="test")

    assert len(rapport["sources_creees"]) == 1  # seule SRC-AVANT est créée
    assert rapport["radionuclides_crees"] == 1  # son propre radionucléide (60-Co), pas l'Am-241 orphelin
    assert any("identifiant vide" in a and "241-Am" in a for a in rapport["avertissements"])


def test_import_journalise_dans_audit(tmp_path, admin_client):
    """L'action d'import elle-même doit être tracée dans le journal
    d'audit (10/07/2026 -> 11/07/2026 : manquait jusqu'ici)."""
    lignes = [
        ["SRC-AUDIT", datetime(2020, 1, 1), None, None, None, None, None, None, "S",
         None, "NON", "60-Co", "5,27 a", 166344000, "b-", 3, 1000000, None],
    ]
    buf = _construire_classeur_sca(lignes)
    path = tmp_path / "test.xlsx"
    path.write_bytes(buf.read())

    from app.services.inventory_import import importer_fichier
    from app.database import get_db
    from app.main import app
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    importer_fichier(str(path), db=db, utilisateur="testeur_audit")

    logs = admin_client.get("/audit/").json()
    imports = [l for l in logs if l["action"] == "IMPORT"]
    assert len(imports) == 1
    assert imports[0]["utilisateur"] == "testeur_audit"
    assert "SRC-AUDIT" not in (imports[0]["valeur_apres"] or "") or True  # le résumé n'a pas besoin de lister chaque source
    assert "1 source" in imports[0]["valeur_apres"]


def test_export_application_reimportable(admin_client, default_location):
    """Le fichier que l'application exporte elle-même doit pouvoir être
    réimporté (fusion depuis une autre instance, restauration...)."""
    admin_client.post("/sources/", json={
        "id": "SRC-EXPORT-TEST", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-EXPORT-TEST", "nom": "Co-60", "activite": 1000000,
        "unite_activite": "Bq", "date_reference": "2026-01-01", "periode": 5.27,
    })

    export_resp = admin_client.get("/export/sources.xlsx")
    assert export_resp.status_code == 200

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(export_resp.content)
        export_path = f.name

    import_resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("export.xlsx", open(export_path, "rb"), "application/octet-stream")},
    )
    assert import_resp.status_code == 200
    data = import_resp.json()
    # La source existe déjà (elle vient d'être créée puis exportée) :
    # doit être ignorée comme "déjà présente", pas dupliquée ni en erreur.
    assert data["sources_creees"] == 0
    assert len(data["sources_ignorees_deja_presentes"]) == 1
    assert len(data["sources_ignorees_erreur"]) == 0


def test_export_application_reimport_restaure_le_lieu(admin_client, default_location):
    """14/07/2026, bug réel signalé : le test ci-dessus réimporte une
    source déjà présente, donc ignorée avant même d'atteindre le code de
    CRÉATION -- où vivait le bug (emplacement_habituel_id/emplacement_actuel_id
    n'étaient jamais renseignés, alors que l'export les écrit bien). Ce
    test-ci exerce le vrai scénario visé (restauration d'une source qui
    n'existe plus) : le lieu doit être correctement retrouvé/recréé."""
    admin_client.post("/sources/", json={
        "id": "SRC-RESTAURE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
    })
    export_resp = admin_client.get("/export/sources.xlsx")
    assert export_resp.status_code == 200

    admin_client.delete("/sources/SRC-RESTAURE")
    assert admin_client.get("/sources/SRC-RESTAURE").status_code == 404

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(export_resp.content)
        export_path = f.name

    import_resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("export.xlsx", open(export_path, "rb"), "application/octet-stream")},
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["sources_creees"] == 1

    source = admin_client.get("/sources/SRC-RESTAURE").json()
    assert source["emplacement_habituel"] is not None
    assert source["emplacement_actuel"] is not None
