"""Conversion d'un fichier XLSX déjà généré vers ODS (LibreOffice Calc) ou
PDF, via LibreOffice en ligne de commande (headless) -- demandé le
13/07/2026, en anticipation d'une réduction de la dépendance à Microsoft
à l'institut.

Choix technique : convertir le XLSX DÉJÀ généré (par openpyxl, tel
qu'aujourd'hui pour l'export des sources, l'Annexe 1 et le Tableau 1a)
plutôt que réécrire chaque export dans une bibliothèque Python différente
(ex: odfpy). Deux raisons : (1) LibreOffice fait une conversion fidèle
(couleurs, largeurs de colonnes, cellules fusionnées) -- important en
particulier pour l'Annexe 1, dont la mise en forme officielle du modèle
est justement conservée depuis le 10/07/2026 ; réécrire cette mise en
forme dans une autre bibliothèque aurait dupliqué ce travail avec un
risque réel de la casser. (2) Aucun changement nécessaire dans les
services d'export existants (déjà testés) : cette fonction s'ajoute par-
dessus, sans les toucher.

Nécessite LibreOffice installé sur la machine qui fait tourner
l'application (`soffice` ou `libreoffice` dans le PATH) -- vérifié
explicitement, avec un message d'erreur clair plutôt qu'un plantage
générique si absent, puisque ce n'est pas garanti sur toutes les
machines (Windows notamment, où LibreOffice n'est pas toujours installé
par défaut).
"""
import shutil
import subprocess
import tempfile
from pathlib import Path


def _trouver_binaire_libreoffice() -> str:
    for nom in ("soffice", "libreoffice"):
        chemin = shutil.which(nom)
        if chemin:
            return chemin
    raise RuntimeError(
        "LibreOffice n'est pas installé (ou pas dans le PATH) sur cette machine : "
        "nécessaire pour convertir vers ODS ou PDF. Installe LibreOffice "
        "(https://www.libreoffice.org/) puis réessaie, ou utilise l'export XLSX "
        "en attendant."
    )


def _preparer_pour_pdf(chemin_xlsx: str) -> str:
    """Ajuste la mise en page (paysage, ajustée à la largeur d'une page,
    marges réduites) sur une COPIE du fichier, avant conversion PDF --
    corrige un rendu cassé signalé le 14/07/2026 : sans ce réglage,
    LibreOffice convertit avec les réglages d'impression par défaut d'un
    classeur (A4 portrait, marges standards), ce qui tronque et superpose
    le texte d'un tableau large comme l'Annexe 1 ou le Tableau 1a. N'af-
    fecte que la copie utilisée pour le PDF : les exports XLSX/ODS
    gardent leurs largeurs de colonnes habituelles, qui n'ont pas ce
    problème (une feuille de calcul n'est pas contrainte à une page).
    """
    import openpyxl
    from openpyxl.worksheet.page import PageMargins

    wb = openpyxl.load_workbook(chemin_xlsx)
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0  # 0 = autant de pages en hauteur que nécessaire
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins = PageMargins(left=0.3, right=0.3, top=0.4, bottom=0.4, header=0.2, footer=0.2)

    chemin_ajuste = str(Path(tempfile.mkdtemp()) / Path(chemin_xlsx).name)
    wb.save(chemin_ajuste)
    return chemin_ajuste


def convertir_xlsx(chemin_xlsx: str, format_cible: str) -> str:
    """Convertit un fichier .xlsx déjà généré vers `format_cible` ('ods'
    ou 'pdf'), et renvoie le chemin du fichier obtenu. Lève RuntimeError
    avec un message clair si LibreOffice n'est pas disponible, ou si la
    conversion elle-même échoue."""
    if format_cible not in ("ods", "pdf"):
        raise ValueError(f"Format de conversion non pris en charge : {format_cible!r}")

    binaire = _trouver_binaire_libreoffice()
    dossier_sortie = tempfile.mkdtemp()

    chemin_a_convertir = _preparer_pour_pdf(chemin_xlsx) if format_cible == "pdf" else chemin_xlsx

    resultat = subprocess.run(
        [
            binaire, "--headless", "--norestore",
            "--convert-to", format_cible,
            "--outdir", dossier_sortie,
            chemin_a_convertir,
        ],
        capture_output=True, text=True, timeout=60,
    )
    if resultat.returncode != 0:
        raise RuntimeError(
            f"Échec de la conversion vers {format_cible} : {resultat.stderr.strip() or resultat.stdout.strip()}"
        )

    nom_sortie = Path(chemin_a_convertir).stem + f".{format_cible}"
    chemin_sortie = str(Path(dossier_sortie) / nom_sortie)
    if not Path(chemin_sortie).exists():
        raise RuntimeError(
            f"La conversion vers {format_cible} n'a produit aucun fichier (sortie LibreOffice : "
            f"{resultat.stdout.strip()!r})"
        )
    return chemin_sortie
