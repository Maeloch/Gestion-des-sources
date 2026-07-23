"""Routes pour l'import de l'inventaire Excel et les exports."""
import tempfile
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.security.permissions import get_current_admin, require_admin_or_mn
from app.database import get_db

router = APIRouter(tags=["import_export"])


_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "pdf": "application/pdf",
}


def _repondre_export(generer_fn, nom_base: str, format_demande: str):
    """Génère un export (toujours en XLSX d'abord, via `generer_fn`), puis
    le convertit vers `format_demande` si ce n'est pas déjà "xlsx" --
    demandé le 13/07/2026 (ODS et PDF, en plus de XLSX, en anticipation
    d'une réduction de la dépendance à Microsoft). `generer_fn` reçoit le
    chemin de sortie XLSX et fait le travail habituel (inchangé) ; sa
    valeur de retour éventuelle (ex: le rapport d'avertissements du
    Tableau 1a) est renvoyée telle quelle à l'appelant, en plus de la
    réponse HTTP, pour ne rien perdre du comportement existant."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp_path = tmp.name
    resultat_generation = generer_fn(tmp_path)

    if format_demande == "xlsx":
        chemin_final = tmp_path
    else:
        from app.services.convert_export import convertir_xlsx
        try:
            chemin_final = convertir_xlsx(tmp_path, format_demande)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

    reponse = FileResponse(
        chemin_final,
        media_type=_MEDIA_TYPES[format_demande],
        filename=f"{nom_base}.{format_demande}",
    )
    return reponse, resultat_generation


@router.post("/import/inventaire")
async def upload_inventaire(
    file: UploadFile = File(...),
    mettre_a_jour_existantes: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    """Importe les sources depuis le fichier d'inventaire Excel historique.
    Réservé aux administrateurs (opération de masse).

    `mettre_a_jour_existantes` (case à cocher côté formulaire, décochée
    par défaut) : permet de corriger un fichier déjà exporté par
    l'application puis de le réimporter pour appliquer les corrections
    -- sans cette option, une source déjà présente est ignorée (jamais
    écrasée), donc les corrections seraient silencieusement perdues."""
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Le fichier doit être au format .xlsx")

    from app.services.inventory_import import importer_fichier

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        rapport = importer_fichier(
            tmp_path, db=db, utilisateur=current_user.username,
            nom_fichier_original=file.filename, mettre_a_jour_existantes=mettre_a_jour_existantes,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Échec de l'import : {e}")
    finally:
        os.unlink(tmp_path)

    return {
        "feuilles_traitees": rapport["feuilles_traitees"],
        "sources_creees": len(rapport["sources_creees"]),
        "sources_mises_a_jour": [
            {"feuille": f, "ligne": l, "id": sid} for f, l, sid in rapport["sources_mises_a_jour"]
        ],
        "sources_ignorees_deja_presentes": [
            {"feuille": f, "ligne": l, "id": sid} for f, l, sid in rapport["sources_ignorees_deja_presentes"]
        ],
        "sources_ignorees_erreur": [
            {"feuille": f, "ligne": l, "id": sid, "erreur": err} for f, l, sid, err in rapport["sources_ignorees_erreur"]
        ],
        "radionuclides_crees": rapport["radionuclides_crees"],
        "radionuclides_mis_a_jour": rapport["radionuclides_mis_a_jour"],
        "radionuclides_supprimes": [
            {"source_id": sid, "nom": nom} for sid, nom in rapport["radionuclides_supprimes"]
        ],
        "lieux_crees": rapport["lieux_crees"],
        "avertissements": rapport["avertissements"],
    }


@router.get("/export/sources.{format}")
async def export_sources(
    format: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin_or_mn),
):
    """Exporte la liste complète des sources (actives et archivées).
    Formats : xlsx, ods (LibreOffice Calc), pdf."""
    if format not in ("xlsx", "ods", "pdf"):
        raise HTTPException(status_code=404, detail="Format non reconnu (xlsx, ods ou pdf attendu)")
    from app.scripts.export_excel import export_sources_to_excel

    reponse, _ = _repondre_export(lambda p: export_sources_to_excel(p, db=db), "sources_export", format)
    return reponse


@router.get("/export/annexe1.{format}")
async def export_annexe1(
    format: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin_or_mn),
):
    """Exporte un pré-remplissage de l'Annexe 1 (inventaire physique des
    matières nucléaires), à compléter pendant l'inventaire physique.
    Formats : xlsx, ods (LibreOffice Calc), pdf."""
    if format not in ("xlsx", "ods", "pdf"):
        raise HTTPException(status_code=404, detail="Format non reconnu (xlsx, ods ou pdf attendu)")
    from app.services.export_annexe1 import generer_annexe1

    reponse, _ = _repondre_export(lambda p: generer_annexe1(db, p), "annexe1_prefill", format)
    return reponse


@router.get("/export/tableau1a.{format}")
async def export_tableau1a(
    format: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin_or_mn),
):
    """Exporte le Tableau 1a (récapitulatif par matière et par lieu),
    calculé à partir des mêmes masses que l'Annexe 1.
    Formats : xlsx, ods (LibreOffice Calc), pdf."""
    if format not in ("xlsx", "ods", "pdf"):
        raise HTTPException(status_code=404, detail="Format non reconnu (xlsx, ods ou pdf attendu)")
    from app.services.export_tableau1a import generer_tableau1a

    rapport_boite = {}

    def _generer(p):
        rapport_boite["valeur"] = generer_tableau1a(db, p)

    reponse, _ = _repondre_export(_generer, "tableau1a", format)
    rapport = rapport_boite["valeur"]
    if rapport["avertissements"]:
        # En-tête custom pour remonter les avertissements sans bloquer le téléchargement
        reponse.headers["X-Avertissements-Count"] = str(len(rapport["avertissements"]))
    return reponse


@router.get("/export/inventaire_mn.pdf")
async def export_inventaire_mn(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin_or_mn),
):
    """Exporte un document imprimable pour l'inventaire physique (à la
    main) des sources Matière Nucléaire actives : une ligne par source
    avec son identifiant, son (ou ses) radionucléide(s), son emplacement,
    une case à cocher pour confirmer la présence physique, et deux
    emplacements de signature. Demandé le 13/07/2026 : à imprimer,
    compléter en vérifiant chaque source, signer, et conserver."""
    from app.services.export_inventaire_mn import generer_inventaire_mn

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = tmp.name
    generer_inventaire_mn(db, tmp_path)

    return FileResponse(
        tmp_path,
        media_type="application/pdf",
        filename="inventaire_mn.pdf",
    )
