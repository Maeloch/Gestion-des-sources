"""Règles de correspondance pour les matières nucléaires, utilisées par
l'export Annexe 1 (et plus tard 1a/2a/3a) — d'après les indications
fournies le 10/07/2026.

Les noms de radionucléides suivent le format "{nombre de masse}-{symbole}"
(ex: "233-U", "239-Pu", "232-Th", "3-H"), cohérent avec les données déjà en
base (import de l'inventaire historique).
"""
import math
import re
from typing import Optional, Tuple

# Nombre d'Avogadro (mol-1)
NOMBRE_AVOGADRO = 6.02214076e23

# Masses molaires (g/mol) des isotopes concernés par la comptabilité
# matières nucléaires. Valeurs des masses atomiques standard de ces
# isotopes (constantes physiques, indépendantes de tes données).
MASSES_MOLAIRES_G_PAR_MOL = {
    ("H", 3): 3.01605,      # Tritium
    ("Th", 232): 232.03806,
    ("U", 233): 233.03963,
    ("U", 234): 234.04095,
    ("U", 235): 235.04393,
    ("U", 238): 238.05079,
    ("Pu", 238): 238.04956,
    ("Pu", 239): 239.05216,
    ("Pu", 240): 240.05381,
    ("Pu", 241): 241.05685,
    ("Pu", 242): 242.05874,
}


def normaliser_nom_radionuclide(nom: str) -> str:
    """Standardise un nom de radionucléide vers le format canonique
    "{Symbole}-{nombre de masse}" (ex: "Kr-85") quel que soit l'ordre, la
    présence d'un séparateur, ou la casse dans le fichier source — trouvé
    le 11/07/2026 : un même isotope apparaît sous des formes différentes
    selon le fichier ou la personne qui a saisi ("85 Kr", "85Kr", "Kr85",
    "Kr 85"...). C'est ce format (symbole puis nombre) qu'utilise LaraWeb
    (voir laraweb.py), et c'est aussi le plus naturel à l'oral (élément
    puis numéro atomique) — corrigé le 12/07/2026, la version précédente
    faisait "85-Kr" (nombre puis symbole), dans le mauvais sens.

    parser_radionuclide (ci-dessous) accepte les deux sens indifféremment,
    donc ce choix n'affecte pas la catégorisation des matières nucléaires.

    Si le nom ne correspond à aucun des motifs reconnus (nombre + lettres,
    dans un ordre ou l'autre, séparés ou non par un espace/tiret), il est
    renvoyé tel quel plutôt que de risquer une transformation erronée.
    """
    if not nom:
        return nom
    nom = nom.strip()

    # Cas particulier Sr-90/Y-90 (12/07/2026) : le fils Y-90 est
    # immédiatement à l'équilibre séculaire avec son père Sr-90 (demi-vie
    # du fils ~64h, largement plus courte que celle du père ~28,8 ans).
    # Convention de l'application (demandée explicitement) : on ne nomme
    # et catégorise que par le père, quelle que soit la notation d'origine
    # rencontrée dans les fichiers sources ("Sr-90+", "90-Sr-Y"...).
    compact = re.sub(r"[\s\-]", "", nom).upper()
    if re.fullmatch(r"(SR90|90SR)(\+|/?Y(90)?)?", compact):
        return "Sr-90"

    # "85 Kr", "85Kr", "85-Kr" (nombre puis symbole)
    m = re.match(r"^(\d+)\s*-?\s*([A-Za-zÀ-ÿ]+)$", nom)
    if not m:
        # "Kr 85", "Kr85", "Kr-85" (symbole puis nombre)
        m2 = re.match(r"^([A-Za-zÀ-ÿ]+)\s*-?\s*(\d+)$", nom)
        if m2:
            nombre, symbole = m2.group(2), m2.group(1)
        else:
            return nom  # format non reconnu : laissé tel quel plutôt que deviner
    else:
        nombre, symbole = m.group(1), m.group(2)

    # Casse standard d'un symbole chimique : première lettre majuscule,
    # le reste en minuscules (ex: "KR" ou "kr" -> "Kr").
    symbole = symbole[0].upper() + symbole[1:].lower()

    return f"{symbole}-{nombre}"


def est_matiere_nucleaire(nom_normalise: str) -> bool:
    """Vrai si ce radionucléide doit classer sa source comme Matière
    Nucléaire par défaut : H-3 (tritium), Li-6, et tout isotope de
    thorium, uranium ou plutonium — demandé le 12/07/2026. Li-6 n'est pas
    radioactif, mais reste une matière nucléaire au sens réglementaire
    (utilisation dans la production de tritium).

    Attend un nom déjà normalisé (format "Symbole-nombre", voir
    normaliser_nom_radionuclide) ; robuste malgré tout à un nom non
    normalisé grâce à parser_radionuclide, qui accepte les deux sens.
    """
    if not nom_normalise:
        return False
    parsed = parser_radionuclide(nom_normalise)
    if not parsed:
        return False
    symbole, nombre = parsed
    if symbole == "H" and nombre == 3:
        return True
    if symbole == "Li" and nombre == 6:
        return True
    return symbole in ("Th", "U", "Pu")


def parser_radionuclide(nom: str) -> Optional[Tuple[str, int]]:
    """'233-U' -> ('U', 233). Renvoie None si le format ne correspond pas."""
    if not nom or "-" not in nom:
        return None
    gauche, droite = nom.split("-", 1)
    gauche, droite = gauche.strip(), droite.strip()
    # Le nombre de masse peut être du côté gauche ("233-U") ou droit ("U-233")
    if gauche.isdigit():
        return droite, int(gauche)
    if droite.isdigit():
        return gauche, int(droite)
    return None


def code_matiere(nom_radionuclide: str) -> Tuple[Optional[str], Optional[str]]:
    """Renvoie (code_EUR, code_National) pour un radionucléide donné,
    d'après les correspondances indiquées :
    - U-233 : K (EUR) / V (National)
    - Plutonium (tout isotope) : P / P
    - Thorium (tout isotope) : T / T
    - Uranium (hors 233) : N / N
    - H-3 (tritium) : pas de code
    - Tout autre radionucléide (non concerné par la comptabilité MN) : pas de code
    """
    parsed = parser_radionuclide(nom_radionuclide)
    if not parsed:
        return None, None
    symbole, nombre_masse = parsed

    if symbole == "U" and nombre_masse == 233:
        return "K", "V"
    if symbole == "U":
        return "N", "N"
    if symbole == "Pu":
        return "P", "P"
    if symbole == "Th":
        return "T", "T"
    if symbole == "H" and nombre_masse == 3:
        return None, None
    return None, None


def masse_depuis_activite_specifique(activite_bq: float, specific_activity_bq_g: float) -> Optional[float]:
    """m = A / (activité spécifique). Utilisé en priorité quand la donnée
    LaraWeb (plus précise, et couvrant bien plus d'isotopes que la table
    ci-dessus) est disponible en cache."""
    if not activite_bq or not specific_activity_bq_g:
        return None
    return activite_bq / specific_activity_bq_g


def masse_radionuclide_g(db, radionuclide, activite_bq: float) -> Optional[float]:
    """Calcule la masse (g) d'un radionucléide à partir de son activité (Bq),
    en préférant l'activité spécifique connue via LaraWeb (mise en cache),
    repli sur le calcul physique à partir de la masse molaire codée en dur
    si l'isotope n'est pas encore en cache. Factorisé le 10/07/2026 (logique
    dupliquée jusque-là entre l'Annexe 1 et le Tableau 1a)."""
    from app.models.lara_cache import LaraCacheDB
    cache_entry = db.query(LaraCacheDB).filter(LaraCacheDB.nuclide == radionuclide.nom).first()
    if cache_entry and cache_entry.specific_activity_bq_g:
        masse = masse_depuis_activite_specifique(activite_bq, cache_entry.specific_activity_bq_g)
        if masse is not None:
            return masse
    return masse_radioelement_g(activite_bq, radionuclide.periode, radionuclide.nom)


# Composition de l'uranium naturel, en % massique (indiqué le 10/07/2026) :
# 99,2742 % U-238, 0,7202 % U-235, 0,0055 % U-234.
POURCENTAGE_U235_NATUREL = 0.7202
TOLERANCE_NATUREL_POINTS = 0.05  # marge autour de 0,7202 % pour tenir compte de l'arrondi/calcul


def categoriser_uranium(pourcentage_u235: float) -> str:
    """Classe un lot d'uranium (hors U-233, qui a sa propre catégorie) dans
    l'une des 5 catégories réglementaires du Tableau 1a, à partir de son
    pourcentage massique en U-235.

    Le seuil "naturel" est une tolérance (±0,05 point) autour de la
    composition naturelle exacte (0,7202 %), pas une égalité stricte — les
    arrondis de calcul rendraient une égalité stricte peu fiable. À
    ajuster si cette marge ne convient pas.
    """
    if pourcentage_u235 >= 20:
        return "enrichi_20_plus"
    if pourcentage_u235 >= 10:
        return "enrichi_10_20"
    if pourcentage_u235 > POURCENTAGE_U235_NATUREL + TOLERANCE_NATUREL_POINTS:
        return "enrichi_moins_10"
    if pourcentage_u235 < POURCENTAGE_U235_NATUREL - TOLERANCE_NATUREL_POINTS:
        return "appauvri"
    return "naturel"


def masse_radioelement_g(activite_bq: float, periode_annees: float, nom_radionuclide: str) -> Optional[float]:
    """Calcule la masse (g) d'un radioélément à partir de son activité
    (Bq — utiliser l'activité ACTUELLE/restante, pas la référence/initiale),
    de sa période radioactive (années), et de sa masse molaire (déduite du
    nom du radionucléide). Renvoie None si la masse molaire de cet isotope
    n'est pas connue (pas dans MASSES_MOLAIRES_G_PAR_MOL), ou si une donnée
    nécessaire manque (activité ou période).

    Formule : A = ln(2)/T½ × (m/M) × N_A  =>  m = A × T½ × M / (ln(2) × N_A)
    """
    if activite_bq is None or not periode_annees:
        return None
    parsed = parser_radionuclide(nom_radionuclide)
    if not parsed:
        return None
    masse_molaire = MASSES_MOLAIRES_G_PAR_MOL.get(parsed)
    if masse_molaire is None:
        return None

    periode_secondes = periode_annees * 365.25 * 24 * 3600
    masse_g = (activite_bq * periode_secondes * masse_molaire) / (math.log(2) * NOMBRE_AVOGADRO)
    return masse_g
