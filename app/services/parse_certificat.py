"""Extrait les informations utiles d'un certificat d'étalonnage PDF
(format CERCA/LEA-Orano notamment) pour pré-remplir la création d'une
source -- demandé le 14/07/2026.

Important, à prendre au sérieux : ceci est une PROPOSITION à vérifier,
jamais une création automatique. Les certificats sont souvent d'anciens
documents scannés, et le texte obtenu par OCR peut être largement
corrompu (testé sur un vrai certificat scanné : "CARACTERISTIQUES" lu
"GARAGTERISTIQUES", "CONFORME" lu "GONFORME", un "I" majuscule confondu
avec un "l" minuscule, des séparateurs de date disparus ou remplacés par
des caractères aléatoires...). Plutôt que de deviner une valeur incer-
taine, chaque champ non extrait avec une confiance raisonnable est laissé
à None -- mieux vaut un champ vide à compléter à la main qu'une valeur
fausse avec l'air d'être fiable, dans un contexte de sûreté nucléaire.

Champs recherchés : radionucléide, activité (massique/spécifique de
préférence, sinon totale), unité, date de référence, masse délivrée,
incertitude relative élargie, référence et numéro de série du certificat,
classification (scellée/non scellée).
"""
import re
from datetime import date, datetime
from typing import Optional


def _extraire_texte(chemin_pdf: str) -> str:
    import pdfplumber
    textes = []
    with pdfplumber.open(chemin_pdf) as pdf:
        for page in pdf.pages:
            textes.append(page.extract_text() or "")
    return "\n".join(textes)


def _parser_date_tolerant(fragment: str) -> Optional[str]:
    """Essaie de reconstruire une date JJ/MM/AAAA à partir d'un fragment
    de texte proche (séparateurs corrects, disparus, ou remplacés par un
    caractère OCR aléatoire). Valide le résultat avec `date()` ET une
    plage d'années plausible (1980-2035) plutôt que de renvoyer un simple
    découpage de chiffres : un OCR abîmé insère ou supprime parfois un
    chiffre, et un découpage naïf donnerait alors une date fausse -- soit
    carrément invalide (rejetée par `date()`), soit valide mais absurde
    (ex: l'an 9120, toujours accepté par `date()` mais impossible pour un
    certificat réel) -- rejetée ici plutôt que renvoyée telle quelle."""
    def _valider(jour, mois, annee):
        try:
            d = date(int(annee), int(mois), int(jour))
        except ValueError:
            return None
        if not (1980 <= d.year <= 2035):
            return None
        return d.strftime("%Y-%m-%d")

    # Format avec séparateurs (/, -, ., ou un caractère OCR quelconque
    # entre les groupes de chiffres) : JJ ? MM ? AAAA
    m = re.search(r"(\d{1,2})\D{1,2}(\d{1,2})\D{0,2}(\d{4})", fragment)
    if m:
        resultat = _valider(*m.groups())
        if resultat:
            return resultat
    # Repli : un bloc de 8 chiffres consécutifs (séparateurs disparus).
    m = re.search(r"(\d{2})(\d{2})(\d{4})", fragment)
    if m:
        resultat = _valider(*m.groups())
        if resultat:
            return resultat
    return None


def extraire_certificat(chemin_pdf: str) -> dict:
    """Renvoie un dict de champs pré-remplis (None si non trouvé avec une
    confiance raisonnable), plus le texte brut extrait (pour que la
    personne puisse comparer avec l'original avant de valider)."""
    texte = _extraire_texte(chemin_pdf)

    resultat = {
        "radionuclide_nom": None,
        "activite": None,
        "unite_activite": None,
        "activite_est_specifique": None,
        "date_reference": None,
        "masse_delivree_g": None,
        "incertitude_pourcent": None,
        "reference_certificat": None,
        "numero_serie": None,
        "type_source": None,
        "texte_brut": texte,
    }

    # Radionucléide : cherché en priorité dans la ligne de données qui
    # suit l'en-tête "Radionucléide" (tableau de résultats, généralement
    # mieux reconnu par l'OCR qu'un nom en toutes lettres comme "CESIUM").
    # Le nom trouvé passe par le normaliseur déjà existant de
    # l'application (gère "137CS", "Cs137", "Cs-137"... indifféremment).
    from app.services.matieres_nucleaires import normaliser_nom_radionuclide
    m = re.search(r"Radionucl[ée1i]ide\s*\n.*?\b(\d{1,3}[A-Za-z]{1,3}|[A-Za-z]{1,3}\d{1,3})\b", texte)
    if m:
        resultat["radionuclide_nom"] = normaliser_nom_radionuclide(m.group(1))

    # Masse délivrée (g) -- "l'I majuscule confondu avec l minuscule" et
    # variantes d'accent tolérées en ne s'ancrant pas sur le tout premier
    # caractère du mot-clé.
    m = re.search(r"[Mm]asse\s+d[ée1]livr[ée1]e\s+([\d,\.]+)\s*g", texte)
    if m:
        resultat["masse_delivree_g"] = float(m.group(1).replace(",", "."))

    # Activité massique (concentration, Bq/unité de masse) en priorité ;
    # à défaut, une activité totale simple ("Activité" seule, en Bq).
    m = re.search(r"[Aa]ctivit[ée1]\s+massique\s+([\d,\.]+)\s*([a-zA-Zµ]*)Bq", texte)
    if m:
        resultat["activite"] = float(m.group(1).replace(",", "."))
        prefixe = m.group(2).strip()
        resultat["unite_activite"] = f"{prefixe}Bq/g" if prefixe else "Bq/g"
        resultat["activite_est_specifique"] = True
    else:
        m = re.search(r"[Aa]ctivit[ée1]\s*:?\s*([\d,\.]+)\s*([a-zA-Zµ]*)Bq(?!/)", texte)
        if m:
            resultat["activite"] = float(m.group(1).replace(",", "."))
            prefixe = m.group(2).strip()
            resultat["unite_activite"] = f"{prefixe}Bq" if prefixe else "Bq"
            resultat["activite_est_specifique"] = False

    # Date de référence -- chercher juste après la mention "date de
    # référence" (plus fiable que la date d'émission ou de contrôle,
    # qui ne correspond pas forcément à la même chose).
    m = re.search(r"[Dd]ate\s+de\s+r[ée1]f[ée1]rence.{0,40}", texte)
    if m:
        resultat["date_reference"] = _parser_date_tolerant(m.group(0))

    # Incertitude relative élargie (%). Le mot-clé "incertitude" commence
    # parfois par un "l" minuscule au lieu d'un "I" majuscule (confusion
    # OCR classique) -- on ne s'ancre donc pas sur cette première lettre.
    # La parenthèse "(% k=2)" contient elle-même un chiffre (le facteur
    # d'élargissement, presque toujours 2) : exclue explicitement avant de
    # capturer la vraie valeur d'incertitude qui la suit (bug trouvé en
    # testant : "1,5" était sinon lu comme "2", capturé dans "k=2").
    m = re.search(r"ncertitude relative [ée1]largie\s*\([^)]*\)\s*:?\s*([\d,\.]+)", texte)
    if m:
        resultat["incertitude_pourcent"] = float(m.group(1).replace(",", "."))

    # Référence produit : plutôt que de s'ancrer sur le mot-clé
    # "Référence" (le texte alentour est trop désordonné dans un
    # certificat scanné pour viser juste), on cherche directement un
    # motif de code produit plausible (lettres puis chiffres, en
    # majuscules, 6 caractères ou plus -- ex: "CS137ELSB45").
    m = re.search(r"\b([A-Z]{2,}\d{2,}[A-Z0-9]{0,10})\b", texte)
    candidats = re.findall(r"\b([A-Z]{2,}\d{2,}[A-Z0-9]{0,10})\b", texte)
    candidats_valables = [c for c in candidats if len(c) >= 6]
    if candidats_valables:
        resultat["reference_certificat"] = max(candidats_valables, key=len)
    m = re.search(r"[Ii]dentification\D{0,10}:?\s*(\d[\dA-Za-z/]{2,})", texte)
    if m:
        resultat["numero_serie"] = m.group(1)

    # Classification : scellée / non scellée.
    m = re.search(r"[Cc]lassification\s+[Ss]ource\s+(non\s+)?[Ss]cell[ée1]e", texte)
    if m:
        resultat["type_source"] = "non-scellée" if m.group(1) else "scellée"

    return resultat
