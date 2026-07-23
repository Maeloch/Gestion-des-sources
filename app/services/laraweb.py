"""Service d'intégration LaraWeb (LNHB) : récupération, analyse et mise en
cache local des données de décroissance radioactive.

URL réelle confirmée le 10/07/2026 (le CDC initial indiquait
"/Laraweb/Results/", qui ne correspond plus à la structure actuelle du
site) :
    http://www.lnhb.fr/nuclides/{nom_du_nuclide}.lara.txt
    (ex: http://www.lnhb.fr/nuclides/Sr-90.lara.txt)

Format du fichier (texte, séparateur ';', un champ par ligne) :
    Nuclide ; Sr-90
    Element ; Strontium
    Z ; 38
    Half-life (a) ; 28.80 ; 0.07      <- unité "naturelle" (a/d/h...), pas toujours présente
    Half-life (s) ; 908.8E6 ; 2.2E6   <- toujours présente, unité fiable utilisée ici
    Specific activity (Bq/g) ; 5.103E12 ; 0.012E12
    Reference ; CEA/LNE-LNHB - 2005
    ... (émissions, non exploitées ici)

Les données sont mises en cache localement (table lara_cache) : comme il
s'agit de constantes physiques qui n'évoluent que très rarement, il n'y a
pas d'expiration automatique du cache — une actualisation manuelle reste
possible (voir refresh_nuclide).
"""
import re
from datetime import datetime
from typing import Optional

import requests

from app.models.lara_cache import LaraCacheDB

BASE_URL = "http://www.lnhb.fr/nuclides/"
SECONDES_PAR_AN = 365.25 * 24 * 3600
TIMEOUT_SECONDES = 15


class LaraWebError(Exception):
    """Levée en cas d'échec de récupération ou d'analyse d'un nuclide."""


def _parser_nombre(texte: str) -> Optional[float]:
    """'704E6' / '5.103E12' / '28.80' -> float. None si vide ou illisible."""
    texte = texte.strip()
    if not texte:
        return None
    try:
        return float(texte)
    except ValueError:
        return None


def parser_fichier_lara(contenu: str) -> dict:
    """Analyse le contenu texte d'un fichier .lara.txt et renvoie un dict
    avec les champs utiles. Lève LaraWebError si le format n'est pas
    reconnaissable (ex: page d'erreur HTML renvoyée à la place du fichier)."""
    if "Nuclide ;" not in contenu:
        raise LaraWebError("Format de réponse non reconnu (pas un fichier .lara.txt valide).")

    resultat = {
        "nuclide": None, "element": None, "z": None,
        "half_life_years": None, "half_life_seconds": None,
        "specific_activity_bq_g": None, "reference": None,
    }

    for ligne in contenu.splitlines():
        champs = [c.strip() for c in ligne.split(";")]
        if not champs or not champs[0]:
            continue
        label = champs[0]

        if label == "Nuclide" and len(champs) > 1:
            resultat["nuclide"] = champs[1]
        elif label == "Element" and len(champs) > 1:
            resultat["element"] = champs[1]
        elif label == "Z" and len(champs) > 1:
            try:
                resultat["z"] = int(champs[1])
            except ValueError:
                pass
        elif label.startswith("Half-life (s)") and len(champs) > 1:
            resultat["half_life_seconds"] = _parser_nombre(champs[1])
        elif label.startswith("Specific activity (Bq/g)") and len(champs) > 1:
            resultat["specific_activity_bq_g"] = _parser_nombre(champs[1])
        elif label == "Reference" and len(champs) > 1:
            resultat["reference"] = " ; ".join(champs[1:])

    if resultat["half_life_seconds"] is not None:
        resultat["half_life_years"] = resultat["half_life_seconds"] / SECONDES_PAR_AN

    if resultat["nuclide"] is None:
        raise LaraWebError("Champ 'Nuclide' introuvable dans la réponse : format inattendu.")

    return resultat


def fetch_nuclide(nom_nuclide: str) -> dict:
    """Récupère et analyse les données d'un nuclide directement depuis
    LaraWeb (sans passer par le cache). Lève LaraWebError en cas de
    problème réseau ou de nuclide inconnu."""
    url = f"{BASE_URL}{nom_nuclide}.lara.txt"
    try:
        reponse = requests.get(url, timeout=TIMEOUT_SECONDES)
    except requests.RequestException as e:
        raise LaraWebError(f"Impossible de contacter LaraWeb : {e}")

    if reponse.status_code == 404:
        raise LaraWebError(f"Nuclide '{nom_nuclide}' introuvable sur LaraWeb (vérifie le format, ex: 'Co-60').")
    if reponse.status_code != 200:
        raise LaraWebError(f"LaraWeb a répondu avec le code {reponse.status_code}.")

    return parser_fichier_lara(reponse.text)


def get_or_fetch(db, nom_nuclide: str, forcer_actualisation: bool = False) -> LaraCacheDB:
    """Renvoie les données en cache pour ce nuclide ; les récupère depuis
    LaraWeb et les met en cache si absentes (ou si forcer_actualisation=True)."""
    entree = db.query(LaraCacheDB).filter(LaraCacheDB.nuclide == nom_nuclide).first()
    if entree and not forcer_actualisation:
        return entree

    donnees = fetch_nuclide(nom_nuclide)

    if entree:
        for champ in ("element", "z", "half_life_years", "half_life_seconds", "specific_activity_bq_g", "reference"):
            setattr(entree, champ, donnees[champ])
        entree.fetched_at = datetime.utcnow()
    else:
        entree = LaraCacheDB(
            nuclide=nom_nuclide,
            element=donnees["element"],
            z=donnees["z"],
            half_life_years=donnees["half_life_years"],
            half_life_seconds=donnees["half_life_seconds"],
            specific_activity_bq_g=donnees["specific_activity_bq_g"],
            reference=donnees["reference"],
            fetched_at=datetime.utcnow(),
        )
        db.add(entree)

    db.commit()
    db.refresh(entree)
    return entree
