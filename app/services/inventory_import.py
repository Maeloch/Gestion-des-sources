"""Import des sources depuis deux formats de fichiers Excel reconnus :

1. Le format "inventaire SCA" historique (feuilles "Sources scellées",
   "Sources non scellées", "Sources consommables"), avec une structure de
   colonnes métier bien plus riche que le schéma de l'application (~35-49
   colonnes : identifiants réglementaires IRSN/GISEL, pourcentages
   isotopiques, lieux détaillés, etc.) Les libellés de colonnes varient
   légèrement d'un export à l'autre (ex: repères de note de bas de page
   "[4]", ou site "SERAC"/"SCA" dans "DATE ARRIVEE ..."), d'où une
   correspondance par PRÉFIXE plutôt que par égalité stricte (voir _get).

2. Le format d'export de l'application elle-même (feuilles "Sources" et
   "Radionucléides", voir app/scripts/export_excel.py) — permet de
   réimporter un fichier précédemment exporté (fusion depuis une autre
   instance, restauration partielle, etc.)

Ce module ne modifie PAS le schéma de l'application : il fait de son mieux
pour faire correspondre les colonnes du fichier à ce qui existe déjà, et
regroupe le reste dans le champ `commentaire` pour ne rien perdre
silencieusement. Voir RAPPORT_DIAGNOSTIC_ET_CORRECTIONS.md pour le détail
des choix de correspondance.

Utilisable en ligne de commande :
    python -m app.scripts.import_inventaire mon_fichier.xlsx
ou via la page "Import" du site (upload direct).
"""
import re
from datetime import date, datetime
from typing import Optional

import openpyxl

from app.database import SessionLocal
from app.models.source import SourceDB, SourceType, EtatPhysique, EtatUtilisation, UniteQuantite
from app.models.radionuclide import RadionuclideDB
from app.models.location import LocationDB
from app.models.audit import AuditLogCreate
from app.repositories.audit import AuditRepository
from app.services.matieres_nucleaires import normaliser_nom_radionuclide, est_matiere_nucleaire

SECONDES_PAR_AN = 365.25 * 24 * 3600

# Feuilles reconnues du format "inventaire SCA", et l'état physique par
# défaut à utiliser pour cette feuille quand rien d'autre ne permet de le
# déterminer. Corrigé le 11/07/2026 : "Sources non scellées" défaut à
# 'solide' (pas 'liquide') -- une source non scellée est souvent une
# référence solide (ex: mélanges alpha Pu/Am/Cm), pas forcément un
# liquide ; seule "Sources consommables" (par nature gaz/liquide) garde le
# défaut liquide. L'ancien défaut faisait apparaître ces sources dans
# l'onglet "Consommables" au lieu de "Non scellées" dans l'interface.
FEUILLES_A_IMPORTER = {
    "Sources scellées": EtatPhysique.solide,
    "Sources non scellées": EtatPhysique.solide,
    "Sources consommables": EtatPhysique.liquide,
}

MOTS_GAZ = ("gaz", "gazeux", "bar", "pression")
MOTS_LIQUIDE = ("liquide", "solution")


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().upper())


def _trouver_entete(ws):
    """Cherche la ligne d'en-tête (contient 'RADIONUCLEIDE') dans les 5
    premières lignes, et construit un dict {NOM_COLONNE_NORMALISE: index}."""
    for r in range(1, 6):
        vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        if any(v and "RADIONUCLEIDE" in _normalise(v) for v in vals):
            col_map = {}
            for c in range(1, ws.max_column + 1):
                v = ws.cell(row=r, column=c).value
                if v:
                    col_map[_normalise(v)] = c
            return r, col_map
    raise ValueError("Ligne d'en-tête introuvable (pas de colonne 'RADIONUCLEIDE' dans les 5 premières lignes).")


def _get(row_cells, col_map, *noms):
    """Renvoie la première valeur non vide trouvée parmi plusieurs noms de
    colonnes possibles, en comparant par PRÉFIXE (une fois normalisé)
    plutôt que par égalité stricte.

    Nécessaire car le même type de colonne porte des libellés légèrement
    différents d'un fichier à l'autre : "ACTIVITE NOMINALE [4]" contre
    "ACTIVITE NOMINALE (BQ)", "DATE ARRIVEE SERAC" contre "DATE ARRIVEE
    SCA", "ETAT [2]" contre "ETAT"... Une égalité stricte faisait échouer
    la correspondance silencieusement (la ligne était importée, mais sans
    activité ni période, sans qu'aucune erreur ne le signale) — trouvé en
    analysant un deuxième fichier réel le 11/07/2026.
    """
    for nom in noms:
        nom_norm = _normalise(nom)
        for cle, idx in col_map.items():
            if cle.startswith(nom_norm) and idx <= len(row_cells):
                val = row_cells[idx - 1]
                if val not in (None, ""):
                    return val
    return None


def _to_date(val) -> Optional[date]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val).strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _to_float(val) -> Optional[float]:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ".").strip())
    except ValueError:
        return None


def _est_valeur_erreur_formule(val) -> bool:
    """Détecte une cellule Excel contenant une erreur de formule non
    calculée (#NAME?, #REF!, #VALUE!, #N/A...) -- ajouté le 14/07/2026,
    suite à un cas réel : une formule VBA personnalisée (allant chercher
    une donnée sur LaraWeb) ou une formule normale, si elle n'a jamais
    été recalculée par Excel avant l'enregistrement du fichier (macros
    désactivées, calcul manuel, réseau indisponible au moment du calcul),
    ne laisse aucune valeur mise en cache -- openpyxl (qui ne sait pas
    lui-même exécuter une formule) lit alors soit rien du tout (None),
    soit le code d'erreur figé dans le fichier. Le premier cas était déjà
    géré silencieusement (traité comme "rien à renseigner") ; ce second
    cas ne l'était pas et pouvait laisser une valeur d'erreur brute
    filer jusqu'en base. Les deux sont maintenant signalés."""
    return isinstance(val, str) and val.strip().startswith("#")


def _deviner_etat_physique(feuille: str, infos_diverses, commentaires) -> EtatPhysique:
    texte = f"{infos_diverses or ''} {commentaires or ''}".lower()
    if any(mot in texte for mot in MOTS_GAZ):
        return EtatPhysique.gaz
    if any(mot in texte for mot in MOTS_LIQUIDE):
        return EtatPhysique.liquide
    return FEUILLES_A_IMPORTER.get(feuille, EtatPhysique.solide)


def _deviner_etat_utilisation(utilisation_brute) -> EtatUtilisation:
    """Déduit l'état d'utilisation depuis la colonne "UTILISATION" du
    fichier, documentée dans son onglet "Remarques" (légende) : UT (en
    Utilisation), DEP (Dépôt/Stockage), SE (Sans Emploi). Correspondance :
    UT -> en_utilisation (correspondance directe) ; DEP -> remisée (le
    sens le plus proche de "en dépôt/stockage" dans nos propres états) ;
    SE -> en_attente (ni utilisée ni définitivement écartée).

    Avant le 12/07/2026, cette colonne n'était pas exploitée : toute
    source importée était mise en "en_utilisation" par défaut, quel que
    soit son statut réel dans le fichier source. J'ai aussi envisagé
    d'utiliser la couleur de certaines lignes comme signal supplémentaire
    (beaucoup de lignes "SE" sont colorées) mais le motif ne tient pas sur
    toutes les feuilles du fichier (aucune couleur sur "Sources non
    scellées", et sur "Sources consommables" la couleur ne sépare plus du
    tout les statuts) : pas assez fiable pour l'utiliser, la colonne
    UTILISATION seule est donc la source de vérité ici.

    Sans valeur reconnue (colonne vide ou texte inattendu), repli sur
    "en_utilisation" comme avant, plutôt que de deviner."""
    if not utilisation_brute:
        return EtatUtilisation.en_utilisation
    valeur = _normalise(utilisation_brute)
    if valeur.startswith("UT"):
        return EtatUtilisation.en_utilisation
    if valeur.startswith("DEP"):
        return EtatUtilisation.remisee
    if valeur.startswith("SE"):
        return EtatUtilisation.en_attente
    return EtatUtilisation.en_utilisation


def _get_or_create_location(db, cache: dict, nom, site, batiment, piece):
    """Renvoie (location, a_ete_cree)."""
    if not nom:
        return None, False
    key = (nom, site, batiment, piece)
    if key in cache:
        return cache[key], False
    existing = db.query(LocationDB).filter(LocationDB.nom == nom).first()
    if existing:
        cache[key] = existing
        return existing, False
    loc = LocationDB(nom=nom, site=site, batiment=batiment, piece=piece)
    db.add(loc)
    db.flush()
    cache[key] = loc
    return loc, True


def _parse_lieu_stockage(lieu_stockage):
    """'Saclay/389/72' -> ('Saclay', '389', '72'). Tolère l'absence de
    certains segments."""
    if not lieu_stockage:
        return None, None, None
    parts = [p.strip() for p in str(lieu_stockage).split("/")]
    site = parts[0] if len(parts) > 0 and parts[0] else None
    batiment = parts[1] if len(parts) > 1 and parts[1] else None
    piece = parts[2] if len(parts) > 2 and parts[2] else None
    return site, batiment, piece


def _extraire_radionuclide(row_cells, col_map, source_id, date_reference_defaut):
    """Construit un RadionuclideDB à partir d'une ligne, ou None si aucun
    radionucléide n'y est renseigné (ou aucune activité exploitable)."""
    radionuclide_nom = _get(row_cells, col_map, "RADIONUCLEIDE")
    if not radionuclide_nom:
        return None

    activite = _to_float(_get(row_cells, col_map, "ACTIVITE NOMINALE"))
    activite_specifique = _to_float(_get(row_cells, col_map, "ACTIVITE SPECIFIQUE NOMINALE"))
    est_specifique = activite is None and activite_specifique is not None
    activite_finale = activite if activite is not None else activite_specifique
    if activite_finale is None:
        return None

    periode_s = _to_float(_get(row_cells, col_map, "PERIODE (S)"))
    periode_annees = (periode_s / SECONDES_PAR_AN) if periode_s else None

    return RadionuclideDB(
        source_id=source_id,
        nom=normaliser_nom_radionuclide(str(radionuclide_nom).strip()),
        activite=activite_finale,
        unite_activite="Bq/g" if est_specifique else "Bq",
        date_reference=date_reference_defaut,
        periode=periode_annees,
        activite_est_specifique=est_specifique,
    )


def _importer_format_sca(wb, db, rapport, location_cache, mettre_a_jour_existantes=False):
    """Importe les feuilles du format "inventaire SCA" historique (voir
    en-tête du module)."""
    for feuille, _ in FEUILLES_A_IMPORTER.items():
        if feuille not in wb.sheetnames:
            rapport["avertissements"].append(f"Feuille '{feuille}' absente du fichier, ignorée.")
            continue
        ws = wb[feuille]
        try:
            header_row, col_map = _trouver_entete(ws)
        except ValueError as e:
            rapport["avertissements"].append(f"Feuille '{feuille}' : {e}")
            continue

        rapport["feuilles_traitees"].append(feuille)

        # Mémorise la dernière source vue sur cette feuille : certaines
        # lignes n'ont pas d'identifiant propre mais portent un
        # radionucléide supplémentaire pour la source précédente (cas des
        # sources "MELANGE" à plusieurs isotopes, chacun sur sa ligne,
        # l'identifiant n'étant renseigné que sur la première) — trouvé en
        # analysant un deuxième fichier réel le 11/07/2026.
        dernier_id_vu = None
        derniere_date_arrivee = None

        for r in range(header_row + 1, ws.max_row + 1):
            row_cells = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]

            source_id_brut = _get(row_cells, col_map, "N° IRSN", "N°IRSN", "N° [1]")
            source_id = str(source_id_brut).strip() if source_id_brut is not None else ""

            if not source_id:
                # Pas d'identifiant exploitable (vide, ou cellule ne
                # contenant que des espaces). Distingue deux cas par la
                # présence ou non d'une date d'arrivée :
                # - ID ET date d'arrivée vides tous les deux : très
                #   probablement une ligne de mélange (radionucléide
                #   supplémentaire pour la source précédente, elle ne
                #   répète jamais les colonnes "administratives").
                # - Date d'arrivée renseignée malgré l'absence d'ID : très
                #   probablement une source à part entière ayant
                #   simplement perdu son identifiant (trouvé sur un cas
                #   réel le 11/07/2026) -- on ne devine pas un identifiant,
                #   on avertit pour une saisie manuelle plutôt que de
                #   rattacher à tort ses données à la source précédente.
                radionuclide_ici = _get(row_cells, col_map, "RADIONUCLEIDE")
                date_arrivee_ici = _get(row_cells, col_map, "DATE ARRIVEE")

                if dernier_id_vu is not None and radionuclide_ici and not date_arrivee_ici:
                    try:
                        rn = _extraire_radionuclide(row_cells, col_map, dernier_id_vu, derniere_date_arrivee)
                        if rn is not None:
                            db.add(rn)
                            db.flush()
                            rapport["radionuclides_crees"] += 1
                            if est_matiere_nucleaire(rn.nom):
                                source_melange = db.query(SourceDB).filter(SourceDB.id == dernier_id_vu).first()
                                if source_melange and not source_melange.matiere_nucleaire:
                                    source_melange.matiere_nucleaire = True
                                    db.flush()
                    except Exception as e:
                        rapport["avertissements"].append(
                            f"{feuille} ligne {r} : radionucléide supplémentaire pour '{dernier_id_vu}' ignoré ({e})."
                        )
                    continue

                a_des_donnees = any(v not in (None, "") for v in row_cells[1:20])
                if a_des_donnees:
                    rapport["avertissements"].append(
                        f"{feuille} ligne {r} : identifiant vide ou illisible, ligne ignorée bien qu'elle "
                        f"contienne des données (radionucléide : {radionuclide_ici or 'aucun'}"
                        f"{', date d’arrivée : ' + str(date_arrivee_ici) if date_arrivee_ici else ''}) "
                        "— à vérifier et importer manuellement si besoin."
                    )
                # Important : on "oublie" la dernière source vue ici. Sans
                # ça, une ligne de mélange plus loin (ID et date vides) se
                # rattacherait à tort à cette source, même après un ou
                # plusieurs "trous" (lignes orphelines) entre les deux --
                # bug réel trouvé le 12/07/2026 : un Po-210 sans rapport
                # s'était retrouvé rattaché à SCA-0167, 4 lignes plus haut,
                # à travers 3 lignes orphelines intercalées. Le rattachement
                # "ligne de mélange" ne doit s'appliquer qu'à la ligne
                # immédiatement suivante d'une vraie source.
                dernier_id_vu = None
                derniere_date_arrivee = None
                continue

            try:
                existante = db.query(SourceDB).filter(SourceDB.id == source_id).first()
                if existante and not mettre_a_jour_existantes:
                    rapport["sources_ignorees_deja_presentes"].append((feuille, r, source_id))
                    dernier_id_vu = None  # une source déjà connue : ne pas y rattacher les lignes de mélange suivantes
                    continue

                etat = _get(row_cells, col_map, "ETAT")
                etat_norm = _normalise(etat) if etat else None
                if etat_norm == "S":
                    type_source = SourceType.scellee
                elif etat_norm == "NS":
                    type_source = SourceType.non_scellee
                else:
                    type_source = SourceType.scellee if feuille == "Sources scellées" else SourceType.non_scellee

                date_arrivee = _to_date(_get(row_cells, col_map, "DATE ARRIVEE")) or date.today()
                mn = _get(row_cells, col_map, "MN")
                matiere_nucleaire = bool(mn) and _normalise(mn) in ("OUI", "O", "TRUE", "1")

                infos_diverses = _get(row_cells, col_map, "INFORMATIONS DIVERSES")
                commentaires_orig = _get(row_cells, col_map, "Commentaires")
                etat_physique = _deviner_etat_physique(feuille, infos_diverses, commentaires_orig)
                if not any(mot in f"{infos_diverses or ''} {commentaires_orig or ''}".lower() for mot in MOTS_GAZ + MOTS_LIQUIDE) and feuille != "Sources scellées":
                    rapport["avertissements"].append(
                        f"{source_id} : état physique deviné par défaut ({etat_physique.value}), à vérifier."
                    )

                utilisation_brute = _get(row_cells, col_map, "UTILISATION")
                etat_utilisation = _deviner_etat_utilisation(utilisation_brute)

                fournisseur = _get(row_cells, col_map, "FOURNISSEUR (OU FABRICANT)")
                num_source_fabricant = _get(row_cells, col_map, "N° DE SOURCE")
                num_certificat = _get(row_cells, col_map, "REFERENCE NORME")
                reference_catalogue = _get(row_cells, col_map, "REFERENCE CATALOGUE")

                masse = _to_float(_get(row_cells, col_map, "MASSE(G)", "MASSE (G)"))
                ratio = _to_float(_get(row_cells, col_map, "RAPPORT QUANTITE RESTANTE / INITIALE"))
                quantite_initiale = (masse / ratio) if (masse and ratio and ratio > 0) else None
                unite_quantite = UniteQuantite.g if masse is not None else None

                lieu_stockage_brut = _get(row_cells, col_map, "LIEU DE STOCKAGE (SITE/ BATIMENT /PIECE)")
                armoire = _get(row_cells, col_map, "ARMOIRE DE STOCKAGE")
                utilisateur_gisel = _get(row_cells, col_map, "UTILISATEUR / LIBELLE GISEL")
                site, batiment, piece = _parse_lieu_stockage(lieu_stockage_brut)

                loc_nom = armoire or (f"Stockage {site}" if site else None) or utilisateur_gisel
                location, lieu_cree = _get_or_create_location(db, location_cache, loc_nom, site, batiment, piece)
                if lieu_cree:
                    rapport["lieux_crees"] += 1

                lieu_stockage_txt = " / ".join(x for x in [lieu_stockage_brut, armoire] if x) or (utilisateur_gisel or "")

                # Regroupe tout ce qui n'a pas de champ dédié, pour ne
                # rien perdre silencieusement.
                extras = []
                for label, noms in [
                    ("Code GISEL", ("CODE GISEL",)),
                    ("N° compte UES", ("N° COMPTE UES",)),
                    ("Mode décroiss.", ("MODE DE DECROISS.", "MODE DE DECROISS")),
                    ("Radiotox.", ("RADIOTOX.", "RADIOTOX")),
                    ("Contrôle étanchéité", ("DATE DU DERNIER CONTRÔLE D'ETANCHEITE",)),
                    ("Date fabrication", ("DATE DE FABRICATION",)),
                    ("Utilisation", ("UTILISATION",)),
                    ("Utilisateur", ("UTILISATEUR / LIBELLE GISEL",)),
                    ("Lieu d'utilisation", ("LIEU D'UTILISATION (SITE/ BATIMENT /PIECE)",)),
                    ("Devenir", ("DEVENIR",)),
                    ("Infos diverses", ("INFORMATIONS DIVERSES",)),
                    ("Infos complémentaires", ("INFORMATIONS COMPLEMENTAIRES",)),
                    ("Date péremption", ("Date de péremption",)),
                ]:
                    v = _get(row_cells, col_map, *noms)
                    if v not in (None, ""):
                        extras.append(f"{label}: {v}")
                if commentaires_orig:
                    extras.append(f"Commentaire d'origine: {commentaires_orig}")
                commentaire = f"[Import inventaire {feuille}] " + " | ".join(extras) if extras else f"[Import inventaire {feuille}]"

                champs = dict(
                    type=type_source,
                    etat_physique=etat_physique,
                    etat_utilisation=etat_utilisation,
                    date_arrivee=date_arrivee,
                    lieu_stockage=lieu_stockage_txt[:100],
                    matiere_nucleaire=matiere_nucleaire,
                    quantite=masse,
                    unite_quantite=unite_quantite,
                    fournisseur=str(fournisseur)[:150] if fournisseur else None,
                    commentaire=commentaire[:1000],
                    quantite_initiale=quantite_initiale,
                    num_source_fabricant=str(num_source_fabricant)[:100] if num_source_fabricant else None,
                    num_certificat_etalonnage=str(num_certificat)[:100] if num_certificat else None,
                    reference_catalogue=str(reference_catalogue)[:100] if reference_catalogue else None,
                    emplacement_habituel_id=location.id if location else None,
                    emplacement_actuel_id=location.id if location else None,
                )

                if existante:
                    # Mode mise à jour (mettre_a_jour_existantes=True) :
                    # remplace les champs de la source déjà présente par
                    # ceux du fichier -- demandé le 14/07/2026, pour
                    # pouvoir corriger un fichier déjà importé (export,
                    # correction à la main, réimport) sans devoir tout
                    # ressaisir. Les radionucléides déjà associés ne sont
                    # pas touchés, pour ne pas risquer de les dupliquer.
                    for champ, valeur in champs.items():
                        setattr(existante, champ, valeur)
                    db.flush()
                    rapport["sources_mises_a_jour"].append((feuille, r, source_id))
                    dernier_id_vu = source_id
                    derniere_date_arrivee = date_arrivee
                    continue

                db_source = SourceDB(id=source_id, **champs)
                db.add(db_source)
                db.flush()

                rn = _extraire_radionuclide(row_cells, col_map, source_id, date_arrivee)
                if rn is not None:
                    db.add(rn)
                    db.flush()
                    rapport["radionuclides_crees"] += 1
                    if est_matiere_nucleaire(rn.nom) and not db_source.matiere_nucleaire:
                        db_source.matiere_nucleaire = True
                        db.flush()

                rapport["sources_creees"].append((feuille, r, source_id))
                dernier_id_vu = source_id
                derniere_date_arrivee = date_arrivee

            except Exception as e:
                db.rollback()
                rapport["sources_ignorees_erreur"].append((feuille, r, source_id, str(e)))
                dernier_id_vu = None
                continue

        db.commit()


def _importer_format_export_app(wb, db, rapport, location_cache, mettre_a_jour_existantes=False):
    """Importe le format généré par l'export de l'application elle-même
    (feuilles "Sources" et "Radionucléides", voir export_excel.py) —
    mapping direct, un champ du fichier = un champ du modèle.

    Correctif du 14/07/2026 : les colonnes "Emplacement habituel"/
    "Emplacement actuel" (écrites par l'export, voir export_excel.py)
    n'étaient jamais relues -- une source réimportée par ce chemin se
    retrouvait donc toujours sans lieu du tout, quel que soit le lieu
    qu'elle avait au moment de l'export. Un vrai trou, pas un choix
    voulu : l'autre format d'import (SCA historique) gère ses propres
    lieux depuis le début, celui-ci avait été oublié."""
    ws = wb["Sources"]
    headers = [c.value for c in ws[1]]
    col = {h: i for i, h in enumerate(headers) if h}

    def val(row, nom):
        idx = col.get(nom)
        if idx is None:
            return None
        v = row[idx].value if idx < len(row) else None
        return v if v not in (None, "") else None

    rapport["feuilles_traitees"].append("Sources (export application)")

    for row in ws.iter_rows(min_row=2):
        source_id = val(row, "ID")
        if not source_id or not str(source_id).strip():
            continue
        source_id = str(source_id).strip()

        try:
            existante = db.query(SourceDB).filter(SourceDB.id == source_id).first()
            if existante and not mettre_a_jour_existantes:
                rapport["sources_ignorees_deja_presentes"].append(("Sources (export application)", row[0].row, source_id))
                continue

            type_brut = val(row, "Type")
            etat_physique_brut = val(row, "État physique")
            etat_utilisation_brut = val(row, "État d'utilisation")
            unite_brute = val(row, "Unité de quantité")

            loc_habituel, cree_h = _get_or_create_location(
                db, location_cache, val(row, "Emplacement habituel"), None, None, None
            )
            if cree_h:
                rapport["lieux_crees"] += 1
            loc_actuel, cree_a = _get_or_create_location(
                db, location_cache, val(row, "Emplacement actuel"), None, None, None
            )
            if cree_a:
                rapport["lieux_crees"] += 1

            champs = dict(
                type=SourceType(type_brut) if type_brut else SourceType.scellee,
                etat_physique=EtatPhysique(etat_physique_brut) if etat_physique_brut else EtatPhysique.solide,
                etat_utilisation=EtatUtilisation(etat_utilisation_brut) if etat_utilisation_brut else EtatUtilisation.en_utilisation,
                date_arrivee=_to_date(val(row, "Date d'arrivée")) or date.today(),
                lieu_stockage=str(val(row, "Lieu de stockage") or ""),
                emplacement_habituel_id=loc_habituel.id if loc_habituel else None,
                emplacement_actuel_id=(loc_actuel or loc_habituel).id if (loc_actuel or loc_habituel) else None,
                fournisseur=val(row, "Fournisseur"),
                matiere_nucleaire=_normalise(val(row, "Matière nucléaire") or "") == "OUI",
                quantite=_to_float(val(row, "Quantité restante")),
                quantite_initiale=_to_float(val(row, "Quantité initiale")),
                unite_quantite=UniteQuantite(unite_brute) if unite_brute else None,
                volume_recipient_litres=_to_float(val(row, "Volume récipient (L)")),
                num_certificat_etalonnage=val(row, "Numéro certificat"),
                num_source_fabricant=val(row, "Numéro fabricant"),
                lien_dossier_admin=val(row, "Lien dossier"),
                commentaire=val(row, "Commentaire"),
            )

            if existante:
                # Mode mise à jour : voir la note équivalente dans
                # _importer_format_sca -- même principe, les
                # radionucléides déjà associés ne sont pas touchés.
                for champ, valeur in champs.items():
                    setattr(existante, champ, valeur)
                db.flush()
                rapport["sources_mises_a_jour"].append(("Sources (export application)", row[0].row, source_id))
                continue

            db_source = SourceDB(id=source_id, **champs)
            db.add(db_source)
            db.flush()
            rapport["sources_creees"].append(("Sources (export application)", row[0].row, source_id))
        except Exception as e:
            db.rollback()
            rapport["sources_ignorees_erreur"].append(("Sources (export application)", row[0].row, source_id, str(e)))

    db.commit()

    if "Radionucléides" in wb.sheetnames:
        ws_rn = wb["Radionucléides"]
        rn_headers = [c.value for c in ws_rn[1]]
        rn_col = {h: i for i, h in enumerate(rn_headers) if h}

        def rn_val(row, nom):
            idx = rn_col.get(nom)
            if idx is None:
                return None
            v = row[idx].value if idx < len(row) else None
            return v if v not in (None, "") else None

        # Sources reconnues comme "déjà présentes et mises à jour" dans CET
        # import -- seules elles bénéficient de la réconciliation complète
        # des radionucléides (ajout ET suppression, voir plus bas) : demandé
        # le 14/07/2026, pour qu'ajouter/supprimer des lignes dans le
        # fichier réimporté se répercute bien en base (ex: retirer une
        # entrée erronée type "MELANGE GAMMA", qui n'est pas un vrai
        # radionucléide). Pour toute autre source (nouvellement créée dans
        # ce même import, ou pas concernée par l'option mise à jour), le
        # comportement reste inchangé : on ajoute ce qui manque, sans
        # jamais rien supprimer.
        sources_mises_a_jour_ids = {sid for (_, _, sid) in rapport["sources_mises_a_jour"]}

        # Regroupées par source, pour pouvoir comparer "ce que dit le
        # fichier" à "ce qu'il y a en base" source par source (plusieurs
        # lignes du fichier peuvent concerner la même source).
        lignes_par_source: dict = {}
        for row in ws_rn.iter_rows(min_row=2):
            source_id = rn_val(row, "ID Source")
            nom = rn_val(row, "Nom")
            if not source_id or not nom:
                continue
            lignes_par_source.setdefault(str(source_id).strip(), []).append(row)

        # Une source mise à jour dont TOUS les radionucléides ont été
        # retirés du fichier n'a plus aucune ligne du tout -- sans cet
        # ajout, elle n'apparaîtrait jamais ci-dessous, et ses
        # radionucléides existants ne seraient donc jamais réconciliés
        # (aucune suppression ne se produirait). Trouvé le 14/07/2026 en
        # vérifiant ce cas limite précis sur l'archive livrée.
        for source_id in sources_mises_a_jour_ids:
            lignes_par_source.setdefault(source_id, [])

        for source_id, rows in lignes_par_source.items():
            if not db.query(SourceDB).filter(SourceDB.id == source_id).first():
                rapport["avertissements"].append(
                    f"Radionucléide(s) ignoré(s) : la source '{source_id}' n'existe pas (ni importée, ni déjà présente)."
                )
                continue

            # Construit ce que le fichier décrit pour cette source : nom
            # normalisé -> champs. Une ligne invalide (activité illisible,
            # etc.) est signalée et simplement absente de ce dict -- elle
            # ne sera donc ni créée ni considérée comme "à garder" en
            # réconciliation (comportement prudent : une ligne cassée
            # n'entraîne jamais la suppression accidentelle d'un
            # radionucléide valide du même nom).
            radionucleides_fichier = {}
            for row in rows:
                nom = rn_val(row, "Nom")
                try:
                    activite = _to_float(rn_val(row, "Activité de référence"))
                    if activite is None:
                        continue
                    nom_normalise = normaliser_nom_radionuclide(str(nom).strip())

                    periode_brute = rn_val(row, "Période (années)")
                    lien_brut = rn_val(row, "Lien LaraWeb")
                    for nom_champ, valeur_brute in (("Période (années)", periode_brute), ("Lien LaraWeb", lien_brut)):
                        if _est_valeur_erreur_formule(valeur_brute):
                            rapport["avertissements"].append(
                                f"Radionucléide '{nom_normalise}' (source '{source_id}') : la colonne "
                                f"'{nom_champ}' contient une erreur de formule non calculée ({valeur_brute!r}) "
                                "-- probablement une formule (macro VBA ou autre) jamais recalculée par Excel "
                                "avant l'enregistrement du fichier. Cette valeur n'a pas été importée ; "
                                "recalcule le fichier (Excel : Ctrl+Alt+F9, macros activées) puis réimporte, "
                                "ou renseigne-la à la main."
                            )

                    radionucleides_fichier[nom_normalise] = dict(
                        activite=activite,
                        unite_activite=rn_val(row, "Unité") or "Bq",
                        date_reference=_to_date(rn_val(row, "Date de référence")) or date.today(),
                        periode=_to_float(periode_brute),
                        activite_est_specifique=_normalise(rn_val(row, "Activité spécifique ?") or "") == "OUI",
                        lien_laraweb=None if _est_valeur_erreur_formule(lien_brut) else lien_brut,
                    )
                except Exception as e:
                    rapport["avertissements"].append(f"Radionucléide '{nom}' (source '{source_id}') ignoré : {e}.")

            existants = {
                r.nom: r for r in db.query(RadionuclideDB).filter(RadionuclideDB.source_id == source_id).all()
            }

            if source_id in sources_mises_a_jour_ids:
                for nom_rn, champs in radionucleides_fichier.items():
                    if nom_rn in existants:
                        for champ, valeur in champs.items():
                            setattr(existants[nom_rn], champ, valeur)
                        rapport["radionuclides_mis_a_jour"] += 1
                    else:
                        db.add(RadionuclideDB(source_id=source_id, nom=nom_rn, **champs))
                        rapport["radionuclides_crees"] += 1
                for nom_rn, obj in existants.items():
                    if nom_rn not in radionucleides_fichier:
                        rapport["radionuclides_supprimes"].append((source_id, nom_rn))
                        db.delete(obj)
            else:
                # Comportement historique, inchangé pour toute source non
                # concernée par une mise à jour dans cet import : on
                # ajoute ce qui manque, sans jamais rien supprimer ni
                # modifier ce qui existe déjà.
                for nom_rn, champs in radionucleides_fichier.items():
                    if nom_rn not in existants:
                        db.add(RadionuclideDB(source_id=source_id, nom=nom_rn, **champs))
                        rapport["radionuclides_crees"] += 1

            db.flush()
        db.commit()


def importer_fichier(file_path: str, db=None, utilisateur: str = None, nom_fichier_original: str = None, mettre_a_jour_existantes: bool = False) -> dict:
    """Importe un fichier Excel, en détectant automatiquement son format
    parmi les deux reconnus (inventaire SCA historique, ou export de
    l'application elle-même) — les deux peuvent aussi coexister dans un
    même classeur, auquel cas les deux sont traités.

    Renvoie un rapport détaillé (sources créées / ignorées, avertissements)
    — ne lève pas d'exception pour une ligne individuelle en erreur (elle
    est juste consignée dans le rapport).

    `utilisateur`, s'il est fourni, journalise l'import dans l'audit
    (nom d'utilisateur, nombre de sources créées, feuilles traitées) —
    demandé le 11/07/2026 : cette action de masse n'était jusqu'ici pas
    tracée dans le journal. `nom_fichier_original`, s'il est fourni, est
    utilisé dans ce message d'audit à la place de `file_path` (utile
    quand `file_path` est un nom de fichier temporaire opaque, ex: upload
    web).

    `mettre_a_jour_existantes` (défaut : False, comportement historique
    inchangé) : si vrai, une source déjà présente est mise à jour avec les
    valeurs du fichier plutôt qu'ignorée -- demandé le 14/07/2026, pour
    permettre le cycle "exporter, corriger le fichier à la main,
    réimporter" (jusqu'ici impossible : la correction était silencieusement
    ignorée). Ses radionucléides déjà associés ne sont pas modifiés, pour
    ne pas risquer d'en créer des doublons."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    rapport = {
        "feuilles_traitees": [],
        "sources_creees": [],
        "sources_mises_a_jour": [],
        "sources_ignorees_deja_presentes": [],
        "sources_ignorees_erreur": [],
        "radionuclides_crees": 0,
        "radionuclides_mis_a_jour": 0,
        "radionuclides_supprimes": [],
        "lieux_crees": 0,
        "avertissements": [],
    }
    location_cache = {}

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)

        a_feuilles_sca = any(f in wb.sheetnames for f in FEUILLES_A_IMPORTER)
        a_feuille_export_app = "Sources" in wb.sheetnames

        if a_feuilles_sca:
            _importer_format_sca(wb, db, rapport, location_cache, mettre_a_jour_existantes)
        if a_feuille_export_app:
            _importer_format_export_app(wb, db, rapport, location_cache, mettre_a_jour_existantes)
        if not a_feuilles_sca and not a_feuille_export_app:
            rapport["avertissements"].append(
                "Aucune feuille reconnue dans ce fichier (ni le format inventaire SCA, ni le format d'export de l'application)."
            )

        if utilisateur:
            nom_fichier = nom_fichier_original or (file_path.split("/")[-1] if isinstance(file_path, str) else "fichier")
            AuditRepository(db).create(AuditLogCreate(
                utilisateur=utilisateur,
                action="IMPORT",
                table_modifiee="sources",
                id_source=None,
                champ_modifie="import_fichier",
                valeur_avant=None,
                valeur_apres=(
                    f"{nom_fichier} : {len(rapport['sources_creees'])} source(s) créée(s), "
                    f"{len(rapport['sources_mises_a_jour'])} mise(s) à jour, "
                    f"{rapport['radionuclides_crees']} radionucléide(s), "
                    f"{len(rapport['sources_ignorees_deja_presentes'])} déjà présente(s), "
                    f"{len(rapport['sources_ignorees_erreur'])} en erreur "
                    f"(feuilles : {', '.join(rapport['feuilles_traitees']) or 'aucune'})"
                ),
            ))

        return rapport
    finally:
        if close_db:
            db.close()
