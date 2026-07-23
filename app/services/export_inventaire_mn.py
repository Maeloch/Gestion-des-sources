"""Génère un document imprimable pour l'inventaire physique (à la main)
des sources classées Matière Nucléaire -- demandé le 13/07/2026 : un
tableau avec l'identifiant de la source, son (ou ses) radionucléide(s),
son emplacement, et une case à cocher pour confirmer la présence
physique. Le document est destiné à être imprimé, complété en allant
vérifier chaque source, signé, puis conservé.

Simplifié le 14/07/2026, sur retour direct : la table n'a plus besoin
d'être aussi large -- les deux signatures n'ont de sens qu'une seule
fois pour tout le document (une personne vérifie l'ensemble des
sources, pas une par une), pas répétées sur chaque ligne. Elles
deviennent un bloc unique en bas de page.

Pas de modèle spécifique demandé : une ligne par SOURCE (pas par
radionucléide) semble plus pratique pour la tâche de vérification
elle-même (on va vérifier une source physique, pas un radionucléide) --
si une source porte plusieurs radionucléides, ils sont listés ensemble
dans la même cellule, séparés par une virgule.

Seules les sources actives (non archivées) sont incluses : on ne
vérifie pas physiquement une source détruite ou transférée.
"""
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


def generer_inventaire_mn(db, output_path: str) -> int:
    """Génère le PDF à `output_path`. Renvoie le nombre de sources
    listées (0 si aucune source MN active)."""
    from app.repositories.source import SourceRepository
    from app.models.source import is_archived

    sources = [
        s for s in SourceRepository(db).get_all()
        if s.matiere_nucleaire and not is_archived(s)
    ]
    sources.sort(key=lambda s: s.id)

    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        "TitreInventaire", parent=styles["Title"], alignment=TA_CENTER, fontSize=16,
    )
    style_cellule = ParagraphStyle("Cellule", parent=styles["Normal"], fontSize=9, leading=11)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )

    elements = [
        Paragraph("Inventaire physique des sources — Matières Nucléaires", style_titre),
        Spacer(1, 0.3 * cm),
        Paragraph(f"Date de l'inventaire : {date.today().strftime('%d/%m/%Y')}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    en_tetes = ["Source (ID)", "Radionucléide(s)", "Emplacement habituel", "Présent ?"]
    lignes = [en_tetes]
    for s in sources:
        noms_rn = ", ".join(rn.nom for rn in s.radionuclides) if s.radionuclides else "—"
        emplacement = s.emplacement_habituel.nom if s.emplacement_habituel else "—"
        lignes.append([
            Paragraph(s.id, style_cellule),
            Paragraph(noms_rn, style_cellule),
            Paragraph(emplacement, style_cellule),
            "",  # case à cocher : cellule vide, la bordure du tableau en dessine le cadre
        ])

    largeurs = [4 * cm, 6 * cm, 6 * cm, 3 * cm]
    table = Table(lignes, colWidths=largeurs, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1c3a52")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.75, colors.HexColor("#888888")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f6f8")]),
        ("TOPPADDING", (0, 1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
        ("MINROWHEIGHT", (0, 1), (-1, -1), 34),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(
        "Document à imprimer, compléter à la main en vérifiant chaque source, signer "
        "ci-dessous, et conserver.",
        styles["Italic"],
    ))
    elements.append(Spacer(1, 0.8 * cm))

    # Bloc de signatures unique pour tout le document (pas une par ligne) :
    # à adapter selon l'organisation retenue (ex. vérificateur et
    # contrôleur), avec la place d'inscrire nom et date à côté de chaque
    # signature.
    bloc_signatures = Table(
        [
            ["Vérifié par (nom, date, signature) :", "Contrôlé par (nom, date, signature) :"],
            ["", ""],
        ],
        colWidths=[13 * cm, 13 * cm],
        rowHeights=[0.8 * cm, 2.2 * cm],
    )
    bloc_signatures.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("BOX", (0, 0), (0, 1), 0.75, colors.HexColor("#888888")),
        ("BOX", (1, 0), (1, 1), 0.75, colors.HexColor("#888888")),
        ("LINEBELOW", (0, 0), (0, 0), 0.75, colors.HexColor("#888888")),
        ("LINEBELOW", (1, 0), (1, 0), 0.75, colors.HexColor("#888888")),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]))
    elements.append(bloc_signatures)

    doc.build(elements)
    return len(sources)
