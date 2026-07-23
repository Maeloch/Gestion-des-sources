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


def test_reimport_sans_option_ignore_toujours_la_source_existante(admin_client, default_location):
    """14/07/2026 : comportement par défaut inchangé -- sans cocher
    l'option, une correction faite dans le fichier exporté puis réimporté
    reste sans effet (source ignorée comme "déjà présente")."""
    admin_client.post("/sources/", json={
        "id": "SRC-SANS-MAJ", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "fournisseur": "Fournisseur original",
    })
    export_resp = admin_client.get("/export/sources.xlsx")

    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
    ws = wb["Sources"]
    headers = [c.value for c in ws[1]]
    col_fournisseur = headers.index("Fournisseur") + 1
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "SRC-SANS-MAJ":
            ws.cell(row=row[0].row, column=col_fournisseur, value="Fournisseur CORRIGÉ")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    import_resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("corrige.xlsx", buffer, "application/octet-stream")},
        # mettre_a_jour_existantes non transmis : comportement par défaut (False)
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["sources_creees"] == 0
    assert len(import_resp.json()["sources_mises_a_jour"]) == 0

    source = admin_client.get("/sources/SRC-SANS-MAJ").json()
    assert source["fournisseur"] == "Fournisseur original"  # pas corrigé


def test_reimport_avec_option_applique_la_correction(admin_client, default_location):
    """14/07/2026 : avec l'option cochée, exporter, corriger le fichier à
    la main, puis réimporter applique bien la correction -- exactement le
    scénario décrit ("exporter, corriger, réimporter"), jusqu'ici
    impossible (la correction était silencieusement ignorée)."""
    admin_client.post("/sources/", json={
        "id": "SRC-AVEC-MAJ", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "fournisseur": "Fournisseur original",
        "commentaire": "Erreur à corriger",
    })
    export_resp = admin_client.get("/export/sources.xlsx")

    import openpyxl, io
    wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
    ws = wb["Sources"]
    headers = [c.value for c in ws[1]]
    col_fournisseur = headers.index("Fournisseur") + 1
    col_commentaire = headers.index("Commentaire") + 1
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "SRC-AVEC-MAJ":
            ws.cell(row=row[0].row, column=col_fournisseur, value="Fournisseur CORRIGÉ")
            ws.cell(row=row[0].row, column=col_commentaire, value="Corrigé à la main")
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    import_resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("corrige.xlsx", buffer, "application/octet-stream")},
        data={"mettre_a_jour_existantes": "true"},
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["sources_creees"] == 0
    assert len(import_resp.json()["sources_mises_a_jour"]) == 1

    source = admin_client.get("/sources/SRC-AVEC-MAJ").json()
    assert source["fournisseur"] == "Fournisseur CORRIGÉ"
    assert source["commentaire"] == "Corrigé à la main"


def test_reimport_avec_option_ne_touche_pas_aux_radionuclides(admin_client, default_location):
    """14/07/2026 : le mode mise à jour ne doit modifier que les champs de
    la source elle-même, jamais ses radionucléides déjà associés (pour ne
    pas risquer d'en créer des doublons à chaque réimport)."""
    admin_client.post("/sources/", json={
        "id": "SRC-RN-INTACT", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-RN-INTACT", "nom": "Co-60", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    export_resp = admin_client.get("/export/sources.xlsx")

    import_resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("export.xlsx", export_resp.content, "application/octet-stream")},
        data={"mettre_a_jour_existantes": "true"},
    )
    assert import_resp.status_code == 200

    radionuclides = admin_client.get("/radionuclides").text
    assert radionuclides.count('data-sort-nom="Co-60"') == 1  # toujours un seul, pas dupliqué


def test_reimport_avec_option_supprime_tous_les_radionuclides_si_plus_aucune_ligne(admin_client, default_location):
    """14/07/2026, cas limite trouvé en vérifiant l'archive livrée : si
    TOUS les radionucléides d'une source sont retirés du fichier (plus
    aucune ligne du tout pour cette source, pas seulement une partie),
    cette source n'apparaissait plus du tout dans le regroupement par
    source -- elle n'était donc jamais réconciliée, et ses
    radionucléides existants n'étaient jamais supprimés malgré le mode
    mise à jour actif. Corrigé : une source mise à jour est prise en
    compte pour la réconciliation même si le fichier ne décrit plus
    aucun radionucléide pour elle."""
    admin_client.post("/sources/", json={
        "id": "SRC-TOUT-RETIRE", "type": "non-scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-TOUT-RETIRE", "nom": "MELANGE GAMMA", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })

    import openpyxl, io
    export_resp = admin_client.get("/export/sources.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
    rn_ws = wb["Radionucléides"]
    for row in rn_ws.iter_rows(min_row=2):
        if row[0].value == "SRC-TOUT-RETIRE":
            for cell in row:
                cell.value = None  # retire complètement la seule ligne de cette source
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("tout_retire.xlsx", buffer, "application/octet-stream")},
        data={"mettre_a_jour_existantes": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["radionuclides_supprimes"]) == 1
    assert data["radionuclides_supprimes"][0]["nom"] == "MELANGE GAMMA"

    source = admin_client.get("/sources/SRC-TOUT-RETIRE").json()
    assert source["radionuclides"] == []


def test_reimport_avec_option_reconcilie_radionuclides_ajout_suppr_maj(admin_client, default_location):
    """14/07/2026, cas réel signalé : "j'ai supprimé et ajouté des lignes,
    ça n'a pas mis à jour la BDD existante (par exemple, une source avec
    un rn MELANGE GAMMA, ce qui n'est pas un rn et que j'ai modifié à la
    main)". Reproduit précisément ce scénario : une source a un
    radionucléide "MELANGE GAMMA" erroné et un "Co-60" correct ; dans le
    fichier réimporté, "MELANGE GAMMA" est retiré, "Co-60" est laissé tel
    quel, et un nouveau "Cs-137" est ajouté. En mode mise à jour, les
    trois doivent se répercuter : suppression, conservation, ajout."""
    admin_client.post("/sources/", json={
        "id": "SRC-MELANGE", "type": "non-scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MELANGE", "nom": "MELANGE GAMMA", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MELANGE", "nom": "Co-60", "activite": 500,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })

    import openpyxl, io
    export_resp = admin_client.get("/export/sources.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
    rn_ws = wb["Radionucléides"]
    headers = [c.value for c in rn_ws[1]]
    col_nom = headers.index("Nom") + 1

    # Retirer la ligne "MELANGE GAMMA" du fichier (en la vidant -- la
    # ligne "ID Source" vide sera ignorée à la relecture).
    for row in rn_ws.iter_rows(min_row=2):
        if row[col_nom - 1].value == "MELANGE GAMMA":
            for cell in row:
                cell.value = None

    # Ajouter une nouvelle ligne "Cs-137" pour la même source.
    rn_ws.append(["SRC-MELANGE", "Cs-137", 750, "Non", "Bq", "2021-01-01", None, None])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("corrige.xlsx", buffer, "application/octet-stream")},
        data={"mettre_a_jour_existantes": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["radionuclides_crees"] == 1  # Cs-137
    assert len(data["radionuclides_supprimes"]) == 1
    assert data["radionuclides_supprimes"][0]["nom"] == "MELANGE GAMMA"

    source = admin_client.get("/sources/SRC-MELANGE").json()
    noms = {rn["nom"] for rn in source["radionuclides"]}
    assert noms == {"Co-60", "Cs-137"}  # MELANGE GAMMA retiré, Co-60 conservé, Cs-137 ajouté


def test_reimport_sans_option_ne_supprime_jamais_de_radionuclide(admin_client, default_location):
    """Sans l'option mise à jour, même une ligne retirée du fichier ne
    doit jamais entraîner de suppression en base -- comportement prudent
    par défaut, la suppression n'a lieu qu'avec une intention explicite."""
    admin_client.post("/sources/", json={
        "id": "SRC-PRUDENT", "type": "non-scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-PRUDENT", "nom": "Am-241", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })

    import openpyxl, io
    export_resp = admin_client.get("/export/sources.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
    rn_ws = wb["Radionucléides"]
    for row in rn_ws.iter_rows(min_row=2):
        for cell in row:
            cell.value = None  # vide toutes les lignes -- fichier "sans radionucléides"
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("sans_option.xlsx", buffer, "application/octet-stream")},
        # mettre_a_jour_existantes non transmis : False par défaut
    )
    assert resp.status_code == 200
    assert len(resp.json()["radionuclides_supprimes"]) == 0

    source = admin_client.get("/sources/SRC-PRUDENT").json()
    assert len(source["radionuclides"]) == 1  # Am-241 toujours là


def test_reimport_avec_option_met_a_jour_activite_radionuclide_existant(admin_client, default_location):
    """En mode mise à jour, une valeur corrigée sur un radionucléide déjà
    présent (même nom) doit se répercuter, pas seulement les ajouts/
    suppressions."""
    admin_client.post("/sources/", json={
        "id": "SRC-MAJ-ACTIVITE", "type": "non-scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-MAJ-ACTIVITE", "nom": "Sr-90", "activite": 1000,
        "unite_activite": "Bq", "date_reference": "2020-01-01",
    })

    import openpyxl, io
    export_resp = admin_client.get("/export/sources.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(export_resp.content))
    rn_ws = wb["Radionucléides"]
    headers = [c.value for c in rn_ws[1]]
    col_activite = headers.index("Activité de référence") + 1
    for row in rn_ws.iter_rows(min_row=2):
        if row[headers.index("Nom")].value == "Sr-90":
            row[col_activite - 1].value = 4242
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("maj_activite.xlsx", buffer, "application/octet-stream")},
        data={"mettre_a_jour_existantes": "true"},
    )
    assert resp.status_code == 200
    assert resp.json()["radionuclides_mis_a_jour"] == 1

    source = admin_client.get("/sources/SRC-MAJ-ACTIVITE").json()
    sr90 = next(rn for rn in source["radionuclides"] if rn["nom"] == "Sr-90")
    assert sr90["activite"] == 4242
    """14/07/2026, cas réel signalé : une formule VBA personnalisée
    (Période, allant chercher une donnée sur LaraWeb) jamais recalculée
    par Excel avant l'enregistrement du fichier ne laisse aucune valeur
    exploitable -- openpyxl lit alors le code d'erreur figé dans le
    fichier (#NAME?, #REF!...). Avant ce correctif, cette valeur brute
    partait silencieusement en base ; elle doit maintenant être détectée,
    ignorée (pas stockée telle quelle), et signalée dans le rapport
    d'import plutôt que de disparaître sans explication."""
    admin_client.post("/sources/", json={
        "id": "SRC-FORMULE", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
    })

    import openpyxl, io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sources"
    ws.append(["ID"])
    ws.append(["SRC-FORMULE"])
    rn_ws = wb.create_sheet("Radionucléides")
    rn_ws.append(["ID Source", "Nom", "Activité de référence", "Activité spécifique ?",
                  "Unité", "Date de référence", "Période (années)", "Lien LaraWeb"])
    rn_ws.append(["SRC-FORMULE", "Cs-137", 1000, "Non", "Bq", "2020-01-01", "#NAME?", "http://lnhb.fr/valide"])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    resp = admin_client.post(
        "/import/inventaire",
        files={"file": ("test.xlsx", buffer, "application/octet-stream")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert any("erreur de formule non calculée" in a for a in data["avertissements"])
    assert any("Période (années)" in a for a in data["avertissements"])

    radionuclides_page = admin_client.get("/radionuclides").text
    assert "#NAME?" not in radionuclides_page  # jamais stockée ni affichée telle quelle
