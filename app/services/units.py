"""Gestion des unités d'activité et de leurs préfixes SI (multiples et
sous-multiples). Jusqu'ici, l'application traitait toute valeur d'activité
comme un nombre brut sans tenir compte du préfixe de son unité (ex : une
activité de "5" avec unité "MBq" était utilisée telle quelle, comme si
c'était 5 Bq au lieu de 5 000 000 Bq) — corrigé le 10/07/2026 suite à une
question directe à ce sujet.

Unités de base reconnues : Bq, Bq/g, Bq/m3, Bq/L, Bq/mL, Bq/cm3.
Préfixes reconnus : n (nano, x10⁻⁹), µ ou u (micro, x10⁻⁶), m (milli, x10⁻³),
aucun (x1), k (kilo, x10³), M (méga, x10⁶), G (giga, x10⁹), T (téra, x10¹²).
"""
from typing import Tuple, Optional
from datetime import datetime
import math

PREFIXES_SI = {
    "n": 1e-9,
    "µ": 1e-6, "u": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
}

# Du plus long au plus court, pour ne pas confondre "Bq" et "Bq/g" au moment
# de retirer le préfixe (voir parser_unite_activite).
UNITES_BASE_RECONNUES = ["Bq/cm3", "Bq/mL", "Bq/m3", "Bq/L", "Bq/g", "Bq"]


def parser_unite_activite(unite_str: str) -> Tuple[float, str]:
    """'MBq' -> (1e6, 'Bq'). 'kBq/g' -> (1e3, 'Bq/g'). 'Bq' -> (1.0, 'Bq').

    Lève ValueError si l'unité n'est pas reconnue : mieux vaut refuser
    clairement que de deviner un facteur possiblement faux pour un calcul
    de masse de matière radioactive.
    """
    if not unite_str:
        raise ValueError("Unité d'activité manquante.")
    unite_str = unite_str.strip()

    for base in UNITES_BASE_RECONNUES:
        if unite_str.endswith(base):
            prefixe = unite_str[: -len(base)]
            if prefixe in PREFIXES_SI:
                return PREFIXES_SI[prefixe], base

    raise ValueError(
        f"Unité d'activité non reconnue : '{unite_str}'. Attendu : un préfixe "
        f"parmi {sorted(p for p in PREFIXES_SI if p)} (ou aucun) suivi d'une "
        f"unité parmi {UNITES_BASE_RECONNUES} — ex. 'MBq', 'kBq/g', 'Bq/m3'."
    )


def normaliser_en_bq(valeur: float, unite_str: str) -> float:
    """Convertit une valeur d'activité vers l'unité de base SANS préfixe
    (Bq ou Bq/g ou Bq/m3...). Lève ValueError si l'unité de base n'est pas
    une des variantes de Bq (ex: refuse une unité de masse pure)."""
    facteur, base = parser_unite_activite(unite_str)
    return valeur * facteur


def formater_duree(annees: float) -> str:
    """Formate une durée (donnée en années, comme le champ `periode`) dans
    l'unité de temps la plus lisible -- secondes, minutes, heures, jours ou
    années -- sur le même principe que formater_activite_bq (choisir la
    représentation la plus lisible), mais avec des facteurs de conversion
    non-métriques (60, 24, 365.25) plutôt que des préfixes SI.

    Utile notamment pour la période radioactive : une demi-vie de
    quelques secondes (Po-214) ou quelques jours (I-131) est illisible
    exprimée en années ("6,52e-8 ans"), alors que "58,4 µs" ou "8,02 j"
    se lit immédiatement.
    """
    if annees is None:
        return "—"
    secondes = annees * 365.25 * 24 * 3600
    abs_s = abs(secondes)

    if abs_s == 0:
        return "0 s"
    if abs_s < 1:
        # Sous la seconde : préfixes SI habituels (ms, µs, ns...).
        return formater_activite_bq(secondes, "s")
    if abs_s < 60:
        return f"{arrondir_scientifique(secondes)} s"
    if abs_s < 3600:
        return f"{arrondir_scientifique(secondes / 60)} min"
    if abs_s < 86400:
        return f"{arrondir_scientifique(secondes / 3600)} h"
    if abs_s < 365.25 * 86400:
        return f"{arrondir_scientifique(secondes / 86400)} j"
    # Au-delà d'un an : pas d'unité de temps plus grande vers laquelle
    # basculer, contrairement aux préfixes SI d'activité (M, G, T...) qui
    # peuvent toujours grandir. Pour une grande valeur (des milliers ou
    # millions d'années, ex: 24100 ans pour le Pu-239), l'écriture
    # scientifique reste la plus lisible -- volontairement laissée en
    # %.3g plutôt que l'arrondi par incertitude, sur retour explicite.
    return f"{annees:.3g} ans"


def quantite_restante_calculee(db, source) -> Optional[float]:
    """Quantité restante PHYSIQUE d'une source consommable (masse de
    liquide, pression de gaz — ce qu'on pèse ou qu'on lit sur un
    manomètre), PAS la masse de l'isotope qu'elle contient.

    Corrigé le 12/07/2026, sur signalement direct : la version précédente
    calculait cette quantité depuis l'activité du radionucléide (via
    masse_radionuclide_g, qui donne la masse de l'ISOTOPE PUR) dès que
    l'activité n'était pas "spécifique" -- ce qui n'a pas de sens ici :
    "quantité restante" doit toujours désigner la quantité physique de LA
    SOURCE (le liquide qu'on pèse, le gaz dont on lit la pression), jamais
    une masse d'isotope. Cette dernière n'a de sens que pour l'Annexe 1 et
    le Tableau 1a (matières nucléaires), qui l'obtiennent directement via
    masse_radionuclide_g -- complètement indépendamment de cette fonction
    désormais.

    Trois sources possibles, dans cet ordre de préférence :

    1. La pesée la plus récente (dernière consommation portant une masse
       "après", pas forcément le tout dernier enregistrement si des
       consommations simples ont eu lieu après une pesée), **corrigée de
       la masse du récipient** si la quantité initiale est connue -- voir
       ci-dessous. Sans quantité initiale connue, utilisée telle quelle.

       Correction ajoutée le 13/07/2026, sur retour direct : en pratique,
       on ne pèse jamais le liquide seul (plus sûr de peser le récipient
       fermé : fiole + liquide + bouchon + étiquette). La toute première
       pesée réelle sert donc à déduire la masse du récipient seul :
       masse_recipient = première_pesée - quantite_initiale (masse de
       liquide connue du certificat). Cette masse de récipient, supposée
       constante, est ensuite retranchée de chaque pesée totale
       ultérieure pour obtenir la masse de liquide restante. Si cette
       déduction donnait un résultat négatif (donnée incohérente), la
       pesée est utilisée telle quelle plutôt que de fausser le résultat.
    2. Repli : quantité initiale renseignée à la création de la source,
       moins la somme des quantités consommées (mode simple, sans pesée
       -- utilisé notamment pour les sources gaz, où peser n'a pas de
       sens physique, ou avant toute pesée réelle).
    3. Repli historique : champ `quantite` brut (sources importées avant
       ce système, sans quantité initiale distincte).

    Renvoie None si aucune des méthodes n'est possible.
    """
    consommations = sorted(
        (source.consumptions or []), key=lambda c: c.timestamp or datetime.min
    )
    pesees = [c for c in consommations if c.masse_apres is not None]

    if pesees:
        derniere_pesee = pesees[-1].masse_apres
        if source.quantite_initiale is not None:
            premiere_pesee = pesees[0].masse_avant if pesees[0].masse_avant is not None else pesees[0].masse_apres
            masse_recipient = premiere_pesee - source.quantite_initiale
            if masse_recipient >= 0:
                return derniere_pesee - masse_recipient
        return derniere_pesee

    if source.quantite_initiale is not None:
        consomme = sum((c.quantite_utilisee or 0) for c in consommations)
        return source.quantite_initiale - consomme

    # Repli pour compatibilité avec les sources important déjà une
    # quantité directement depuis le fichier source, sans quantité
    # initiale distincte (import historique -- beaucoup des 240 sources
    # importées le 11/07/2026 sont dans ce cas). Cette valeur stockée est
    # tenue à jour par décrément direct à chaque consommation (voir
    # ConsumptionService.use_source), donc utilisée telle quelle ici, sans
    # recalcul.
    return source.quantite


def activite_actuelle_bq(radionuclide, a_la_date=None) -> Optional[float]:
    """Activité d'un radionucléide à une date donnée (décroissance depuis
    sa date de référence appliquée), normalisée en Bq (ou Bq/g pour une
    activité spécifique) — c'est-à-dire le préfixe (MBq, kBq...) de
    l'unité saisie est pris en compte. Renvoie None si la période n'est
    pas renseignée (pas de décroissance calculable).

    `a_la_date` : date à laquelle calculer l'activité (par défaut :
    aujourd'hui). Généralisé le 13/07/2026 pour calculer l'activité au
    moment précis d'une consommation passée (voir activite_utilisee_bq),
    pas seulement "l'activité actuelle" au sens strict.
    """
    from app.services.decay import DecayService
    if not radionuclide.periode:
        return None
    activite_normalisee = normaliser_en_bq(radionuclide.activite, radionuclide.unite_activite)
    return DecayService.calculate_activity(
        initial_activity=activite_normalisee,
        half_life_years=radionuclide.periode,
        initial_date=radionuclide.date_reference,
        current_date=a_la_date,
    )


def _quantite_avant_consommation(source, consumption) -> Optional[float]:
    """Quantité de liquide restante juste AVANT une consommation donnée
    (pas aujourd'hui) -- utilisé pour calculer l'activité utilisée d'une
    consommation portant sur une activité TOTALE (pas une concentration),
    où il faut connaître la proportion de la quantité totale que
    représente cette consommation à ce moment précis."""
    if consumption.masse_avant is not None and source.quantite_initiale is not None:
        toutes_pesees = sorted(
            [c for c in (source.consumptions or []) if c.masse_apres is not None],
            key=lambda c: c.timestamp or datetime.min,
        )
        if toutes_pesees:
            premiere = toutes_pesees[0].masse_avant if toutes_pesees[0].masse_avant is not None else toutes_pesees[0].masse_apres
            masse_recipient = premiere - source.quantite_initiale
            if masse_recipient >= 0:
                return consumption.masse_avant - masse_recipient
        return consumption.masse_avant

    if source.quantite_initiale is not None:
        anterieures = [
            c for c in (source.consumptions or [])
            if c.id != consumption.id and (c.timestamp or datetime.min) < (consumption.timestamp or datetime.min)
        ]
        consomme_avant = sum((c.quantite_utilisee or 0) for c in anterieures)
        return source.quantite_initiale - consomme_avant

    return None


def activite_utilisee_bq(db, source, consumption) -> Optional[float]:
    """Activité (Bq) correspondant à la quantité consommée lors d'une
    consommation donnée, calculée au moment DE CETTE CONSOMMATION (pas
    aujourd'hui) -- demandé le 13/07/2026, purement pour l'affichage :
    rien n'est stocké en base, tout est recalculé à la demande.

    Utilise le premier radionucléide de la source (même simplification
    que pour la quantité restante, voir quantite_restante_calculee). Deux
    cas :
    1. Activité SPÉCIFIQUE (concentration, ex. Bq/g) : la concentration
       à la date de la consommation, décroissance appliquée, multipliée
       par la quantité consommée -- direct.
    2. Activité TOTALE (pas une concentration) : la quantité consommée
       n'est qu'une fraction de la quantité totale à ce moment-là ;
       l'activité utilisée est cette même fraction de l'activité totale
       à la date de la consommation.

    Renvoie None si aucun calcul n'est possible (pas de radionucléide
    exploitable, pas de période renseignée, ou -- pour le cas 2 -- pas de
    quantité de référence connue à cette date).
    """
    if not source.radionuclides or not consumption.quantite_utilisee:
        return None
    rn = source.radionuclides[0]
    if not rn.periode:
        return None

    date_conso = consumption.timestamp.date() if consumption.timestamp else datetime.today().date()
    activite_a_la_date = activite_actuelle_bq(rn, a_la_date=date_conso)
    if activite_a_la_date is None:
        return None

    if rn.activite_est_specifique:
        return activite_a_la_date * consumption.quantite_utilisee

    quantite_avant = _quantite_avant_consommation(source, consumption)
    if not quantite_avant or quantite_avant <= 0:
        return None
    return activite_a_la_date * (consumption.quantite_utilisee / quantite_avant)


def arrondir_scientifique(valeur: float, incertitude: float = None) -> str:
    """Arrondit et formate une valeur selon son incertitude, sur le même
    principe que res_round.m (LNHB, fourni par l'utilisateur — voir sa
    docstring d'origine) : le nombre de décimales affichées se déduit de
    l'incertitude, plutôt que d'être fixé arbitrairement (auparavant :
    toujours 3 chiffres significatifs, via '%.3g').

    Sans incertitude connue -- le cas de toute l'application pour
    l'instant, aucune incertitude n'y étant encore suivie -- une
    incertitude arbitraire de 1% de la valeur est utilisée, comme demandé
    le 12/07/2026 (le suivi de vraies incertitudes est prévu comme
    prochain chantier, après la version 1.0 : ce paramètre `incertitude`
    est donc déjà prêt à recevoir une vraie valeur le moment venu, sans
    changer l'appelant).
    """
    if valeur == 0:
        return "0"
    if not incertitude or incertitude <= 0:
        incertitude = abs(valeur) * 0.01
    # Plafond défensif à 12 décimales : au-delà, la valeur est de toute
    # façon négligeable pour un usage réel, et un nombre de décimales
    # illimité peut produire un mur de zéros illisible, voire un
    # dépassement de capacité pour une valeur extrême (trouvé le
    # 13/07/2026 sur un cas réel). formater_activite_bq gère par ailleurs
    # son propre seuil de négligeabilité en amont (sous 1 nBq -> "0"),
    # donc ce plafond ne sert ici que de filet de sécurité générique.
    nb_chif = min(max(-1 - math.floor(math.log10(incertitude / 50)), 1), 12)
    facteur = 10 ** nb_chif
    v_arrondi = round(valeur * facteur) / facteur
    return f"{v_arrondi:.{nb_chif}f}"


def formater_activite_bq(valeur_bq: float, unite_base: str = "Bq") -> str:
    """Formate une activité avec le préfixe le plus lisible (ex :
    1 250 000 -> "1.25 MBq", 45 -> "45 Bq"). Purement pour l'affichage.

    `unite_base` permet de formater une activité spécifique/concentration
    (ex: unite_base="Bq/g" -> "148 kBq/g") : le préfixe s'insère toujours
    juste avant "Bq", jamais entre le "/" et le dénominateur — ajouté le
    12/07/2026 pour afficher clairement l'activité totale d'une source à
    partir de son activité spécifique (avant, seul le Bq pur était géré,
    le "/g" etc. était perdu à l'affichage).
    """
    if valeur_bq is None:
        return "—"
    abs_v = abs(valeur_bq)
    # Sous 1 nBq (le plus petit préfixe reconnu), la valeur est jugée
    # négligeable et affichée comme nulle plutôt que formatée telle
    # quelle -- demandé le 13/07/2026 sur un cas réel (IRMA-0060) où une
    # activité infime (bien au-delà de la simple précision flottante)
    # produisait un "0,000...0002643 nBq" avec plusieurs centaines de
    # zéros, voire un dépassement de capacité pour les valeurs les plus
    # extrêmes (le nombre de décimales calculé par arrondir_scientifique
    # devenant lui-même astronomique).
    if abs_v != 0 and abs_v < PREFIXES_SI["n"]:
        return f"0 {unite_base}"
    if abs_v == 0:
        return f"0 {unite_base}"
    meilleurs = sorted(
        ((p, f) for p, f in PREFIXES_SI.items()),
        key=lambda x: -x[1],
    )
    for prefixe, facteur in meilleurs:
        if abs_v >= facteur:
            mantisse = valeur_bq / facteur
            return f"{arrondir_scientifique(mantisse)} {prefixe}{unite_base}"
    # valeur plus petite que le plus petit préfixe connu (nano) : afficher tel quel
    plus_petit_prefixe, plus_petit_facteur = meilleurs[-1]
    return f"{arrondir_scientifique(valeur_bq / plus_petit_facteur)} {plus_petit_prefixe}{unite_base}"
