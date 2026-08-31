"""Tests sur les consommations (règles gaz/liquide) et les emprunts
(cycle sortie/retour, lieu habituel/actuel)."""
from app.main import app
from app.database import get_db

SOURCE_GAZ = {
    "id": "SRC-GAZ-T", "type": "non-scellée", "etat_physique": "gaz",
    "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
    "quantite": 10, "unite_quantite": "bar",
}
SOURCE_SOLIDE = {
    "id": "SRC-SOLIDE-T", "type": "scellée", "etat_physique": "solide",
    "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
}


def test_consommation_impossible_sur_source_solide(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_SOLIDE, "emplacement_habituel_id": default_location})
    resp = admin_client.post("/consumptions/", json={"source_id": SOURCE_SOLIDE["id"], "quantite_utilisee": 1})
    assert resp.status_code == 400
    assert "gaz" in resp.json()["detail"] or "liquide" in resp.json()["detail"]


def test_consommation_decremente_la_quantite(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_GAZ, "emplacement_habituel_id": default_location})
    resp = admin_client.post("/consumptions/", json={"source_id": SOURCE_GAZ["id"], "quantite_utilisee": 3})
    assert resp.status_code == 200

    source = admin_client.get(f"/sources/{SOURCE_GAZ['id']}").json()
    assert source["quantite"] == 7


def test_consommation_excessive_refusee(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_GAZ, "emplacement_habituel_id": default_location})
    resp = admin_client.post("/consumptions/", json={"source_id": SOURCE_GAZ["id"], "quantite_utilisee": 1000})
    assert resp.status_code == 400
    assert "insuffisante" in resp.json()["detail"]

    source = admin_client.get(f"/sources/{SOURCE_GAZ['id']}").json()
    assert source["quantite"] == 10


def test_consommation_enregistre_utilisateur(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_GAZ, "emplacement_habituel_id": default_location})
    admin_client.post("/consumptions/", json={"source_id": SOURCE_GAZ["id"], "quantite_utilisee": 1})
    consumptions = admin_client.get("/consumptions/").json()
    assert consumptions[0]["utilisateur"] is not None


def test_cycle_emprunt_retour_complet(admin_client):
    loc1 = admin_client.post("/locations/", json={"nom": "Armoire A"}).json()
    loc2 = admin_client.post("/locations/", json={"nom": "Labo B"}).json()
    admin_client.post("/sources/", json={**SOURCE_SOLIDE, "emplacement_habituel_id": loc1["id"]})

    source = admin_client.get(f"/sources/{SOURCE_SOLIDE['id']}").json()
    assert source["emplacement_actuel"]["id"] == loc1["id"]

    resp = admin_client.post("/movements/", json={"source_id": SOURCE_SOLIDE["id"], "to_location_id": loc2["id"]})
    assert resp.status_code == 200
    movement = resp.json()
    assert movement["from_location_id"] == loc1["id"]
    assert movement["to_location_id"] == loc2["id"]
    assert movement["date_retour_reelle"] is None

    source = admin_client.get(f"/sources/{SOURCE_SOLIDE['id']}").json()
    assert source["emplacement_actuel"]["id"] == loc2["id"]

    resp = admin_client.post("/movements/", json={"source_id": SOURCE_SOLIDE["id"], "to_location_id": loc1["id"]})
    assert resp.status_code == 400
    assert "déjà sortie" in resp.json()["detail"]

    resp = admin_client.patch(f"/movements/{movement['id']}/retour", json={})
    assert resp.status_code == 200
    assert resp.json()["date_retour_reelle"] is not None

    source = admin_client.get(f"/sources/{SOURCE_SOLIDE['id']}").json()
    assert source["emplacement_actuel"]["id"] == loc1["id"]

    resp = admin_client.post("/movements/", json={"source_id": SOURCE_SOLIDE["id"], "to_location_id": loc2["id"]})
    assert resp.status_code == 200


def test_bouton_marquer_retourne_sans_collision_de_guillemets(admin_client, default_location):
    """14/07/2026, bug réel signalé ("le bouton n'a pas d'effet") : même
    cause que d'autres boutons corrigés précédemment (radionucléide,
    consommation) -- {{ m.source_id | tojson }} dans un attribut
    onclick="..." produit ses propres guillemets doubles, qui entrent en
    collision avec ceux de l'attribut HTML et le tronquent
    (onclick="openRetourModal(1, "SRC-X")", invalide). Corrigé avec un
    attribut data-* (échappement HTML normal, pas de collision possible).
    Ce test vérifie le HTML réellement rendu, pas seulement la route
    backend (déjà couverte par test_cycle_emprunt_retour_complet, qui
    passait déjà avant ce correctif -- le bug était strictement côté
    template)."""
    admin_client.post("/sources/", json={
        "id": "SRC-BTN-RETOUR", "type": "scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
    })
    autre_lieu = admin_client.post("/locations/", json={"nom": "Autre lieu retour"}).json()
    admin_client.post("/movements/", json={"source_id": "SRC-BTN-RETOUR", "to_location_id": autre_lieu["id"]})

    page = admin_client.get("/movements")
    assert page.status_code == 200
    assert 'onclick="openRetourModal(' in page.text
    # La collision se manifeste par un guillemet double juste après la
    # virgule (tojson) au lieu de "this.dataset.sourceId" -- absent ici.
    assert ', "SRC-BTN-RETOUR")"' not in page.text
    assert "this.dataset.sourceId" in page.text
    assert 'data-source-id="SRC-BTN-RETOUR"' in page.text


def test_emprunt_impossible_sans_lieu_habituel(admin_client, default_location):
    """Un lieu habituel est obligatoire à la création (10/07/2026), donc ce
    scénario ne peut plus survenir que sur une source ancienne/importée
    sans lieu — simulé ici en vidant le champ directement en base, pour
    vérifier que la vérification de sécurité (pas seulement le formulaire)
    fonctionne toujours."""
    admin_client.post("/sources/", json={**SOURCE_SOLIDE, "emplacement_habituel_id": default_location})

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    from app.models.source import SourceDB
    db_source = db.query(SourceDB).filter(SourceDB.id == SOURCE_SOLIDE["id"]).first()
    db_source.emplacement_habituel_id = None
    db_source.emplacement_actuel_id = None
    db.commit()
    db.close()

    loc = admin_client.post("/locations/", json={"nom": "Un lieu"}).json()
    resp = admin_client.post("/movements/", json={"source_id": SOURCE_SOLIDE["id"], "to_location_id": loc["id"]})
    assert resp.status_code == 400
    assert "lieu habituel" in resp.json()["detail"]


def test_emprunt_impossible_sur_source_archivee(admin_client, default_location):
    admin_client.post("/sources/", json={**SOURCE_SOLIDE, "emplacement_habituel_id": default_location})
    admin_client.put(f"/sources/{SOURCE_SOLIDE['id']}", json={"etat_utilisation": "en déchet"})

    loc = admin_client.post("/locations/", json={"nom": "Un lieu"}).json()
    resp = admin_client.post("/movements/", json={"source_id": SOURCE_SOLIDE["id"], "to_location_id": loc["id"]})
    assert resp.status_code == 400
    assert "archivée" in resp.json()["detail"]


def test_suppression_lieu_occupe_refusee(admin_client):
    loc = admin_client.post("/locations/", json={"nom": "Armoire occupée"}).json()
    admin_client.post("/sources/", json={**SOURCE_SOLIDE, "emplacement_habituel_id": loc["id"]})

    resp = admin_client.delete(f"/locations/{loc['id']}")
    assert resp.status_code == 400


def test_fusion_de_lieux(admin_client):
    """11/07/2026 : pouvoir fusionner un lieu (ex: 'Dess. 2') dans un autre
    déjà existant, pour simplifier une liste de lieux devenue trop
    éclatée. Toutes les sources et mouvements doivent être réaffectés,
    et le lieu source supprimé."""
    loc_a = admin_client.post("/locations/", json={"nom": "Dess. 2"}).json()
    loc_b = admin_client.post("/locations/", json={"nom": "Armoire principale"}).json()

    admin_client.post("/sources/", json={
        **SOURCE_SOLIDE, "id": "SRC-FUSION", "emplacement_habituel_id": loc_a["id"],
    })

    resp = admin_client.post(f"/locations/{loc_a['id']}/fusionner", json={"cible_id": loc_b["id"]})
    assert resp.status_code == 200
    assert resp.json()["id"] == loc_b["id"]

    # La source doit maintenant pointer vers le lieu cible
    source = admin_client.get("/sources/SRC-FUSION").json()
    assert source["emplacement_habituel"]["id"] == loc_b["id"]
    assert source["emplacement_actuel"]["id"] == loc_b["id"]

    # Le lieu fusionné (source) ne doit plus exister
    lieux = admin_client.get("/locations/").json()
    assert loc_a["id"] not in [l["id"] for l in lieux]
    assert loc_b["id"] in [l["id"] for l in lieux]


def test_fusion_avec_soi_meme_refusee(admin_client):
    loc = admin_client.post("/locations/", json={"nom": "Un lieu"}).json()
    resp = admin_client.post(f"/locations/{loc['id']}/fusionner", json={"cible_id": loc["id"]})
    assert resp.status_code == 400


def test_renommage_en_collision_propose_fusion_puis_confirme(admin_client):
    """13/07/2026 : reproduit le bug réel signalé (500 Internal Server
    Error, UNIQUE constraint failed sur locations.nom) -- renommer un lieu
    vers un nom déjà pris par un AUTRE lieu doit maintenant renvoyer 409
    avec un message clair, et fusionner si confirmé explicitement, plutôt
    que planter."""
    loc_epicea = admin_client.post("/locations/", json={"nom": "EPICEA", "site": "SCA"}).json()
    loc_coffre = admin_client.post("/locations/", json={"nom": "Coffre à source d'EPICEA"}).json()
    admin_client.post("/sources/", json={
        **SOURCE_SOLIDE, "id": "SRC-RENOMMAGE", "emplacement_habituel_id": loc_coffre["id"],
    })

    # Sans confirmation : 409, pas 500, et rien n'est modifié.
    resp = admin_client.put(f"/locations/{loc_coffre['id']}", json={"nom": "EPICEA"})
    assert resp.status_code == 409
    assert "EPICEA" in resp.json()["detail"]
    lieux = admin_client.get("/locations/").json()
    assert loc_coffre["id"] in [l["id"] for l in lieux]  # toujours là, rien fusionné

    # Avec confirmation : la fusion a bien lieu.
    resp2 = admin_client.put(f"/locations/{loc_coffre['id']}", json={"nom": "EPICEA", "confirmer_fusion": True})
    assert resp2.status_code == 200
    assert resp2.json()["id"] == loc_epicea["id"]

    source = admin_client.get("/sources/SRC-RENOMMAGE").json()
    assert source["emplacement_habituel"]["id"] == loc_epicea["id"]
    lieux_apres = admin_client.get("/locations/").json()
    assert loc_coffre["id"] not in [l["id"] for l in lieux_apres]


def test_renommage_vers_nom_libre_fonctionne_normalement(admin_client):
    """Un renommage qui ne rentre en collision avec rien doit continuer à
    fonctionner tel quel, sans passer par la logique de fusion."""
    loc = admin_client.post("/locations/", json={"nom": "Ancien nom"}).json()
    resp = admin_client.put(f"/locations/{loc['id']}", json={"nom": "Nouveau nom"})
    assert resp.status_code == 200
    assert resp.json()["nom"] == "Nouveau nom"


def test_bouton_fusionner_retire_de_l_interface(admin_client):
    """14/07/2026, signalé comme sans effet -- retiré entièrement plutôt
    que corrigé, le renommage-fusion (voir test_renommage_en_collision...
    plus haut) restant l'unique chemin pour fusionner deux lieux. Vérifie
    que rien de cette fonctionnalité ne reste dans la page rendue."""
    admin_client.post("/locations/", json={"nom": "Un lieu quelconque"})
    page = admin_client.get("/locations")
    assert page.status_code == 200
    assert "Fusionner" not in page.text
    assert "openMergeModal" not in page.text
    assert "mergeModal" not in page.text


def test_bouton_supprimer_lieu_dans_la_popup_pas_sur_la_ligne(admin_client):
    """14/07/2026 : bug de collision de guillemets corrigé sur ce bouton
    à l'époque, quand il vivait encore sur la ligne du tableau. Depuis le
    31/07/2026, il vit dans la pop-up de modification (harmonisé avec le
    même patron que Radionucléides et Consommations) -- ce risque de
    collision n'existe donc plus du tout, le nom n'étant plus interpolé
    dans un attribut onclick mais lu depuis le champ du formulaire."""
    admin_client.post("/locations/", json={"nom": "Lieu à supprimer"})
    page = admin_client.get("/locations")
    assert page.status_code == 200
    # Plus de bouton Supprimer sur la ligne elle-même.
    assert 'onclick="deleteLocation(' not in page.text.split('id="locationModal"')[0]
    # Présent dans la pop-up, cause caché par défaut (visible seulement en modification).
    assert 'id="locationDeleteBtn"' in page.text
    assert "document.getElementById('nom').value" in page.text


def test_activite_specifique_utilise_quantite_initiale_pas_calcul_physique(admin_client, default_location):
    """12/07/2026 : bug critique signalé -- pour une activité SPÉCIFIQUE
    (concentration dans la solution, ex: 100 kBq/g), le calcul physique
    (masse d'isotope pur depuis une activité totale) ne doit JAMAIS
    s'appliquer : ça donnait des masses aberrantes (2.38e-09 g calculé au
    lieu des 5g réels), en confondant la concentration de LA SOLUTION avec
    l'activité massique de l'isotope PUR (LaraWeb). Doit utiliser
    quantite_initiale directement."""
    admin_client.post("/sources/", json={
        "id": "SRC-CO60-SPEC", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-07-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-CO60-SPEC", "nom": "Co-60", "activite": 100,
        "unite_activite": "kBq/g", "activite_est_specifique": True,
        "date_reference": "2026-07-01", "periode": 5.271,
    })

    source = admin_client.get("/sources/SRC-CO60-SPEC").json()
    # Doit rester proche de 5g (à la décroissance de la CONCENTRATION près,
    # qui ne change pas la masse physique) -- surtout pas 2.38e-09.
    assert source["quantite_calculee"] is not None
    assert 4.9 < source["quantite_calculee"] <= 5.0


def test_page_consommations_propose_source_avec_quantite_initiale(admin_client, default_location):
    """12/07/2026 : la page Consommations filtrait les sources proposées
    en vérifiant l'ancien champ source.quantite (jamais renseigné depuis
    que la quantité est calculée) au lieu de la quantité réellement
    calculée -- une source avec seulement quantite_initiale n'apparaissait
    donc jamais dans le formulaire, malgré une consommation possible via
    l'API elle-même."""
    admin_client.post("/sources/", json={
        "id": "SRC-DROPDOWN", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    page = admin_client.get("/consumptions")
    assert page.status_code == 200
    assert 'value="SRC-DROPDOWN"' in page.text


def test_page_consommations_ne_genere_pas_de_javascript_invalide(admin_client, default_location):
    """12/07/2026 : bug critique trouvé après signalement utilisateur --
    le champ source.quantite (brut, souvent None depuis que la quantité
    est calculée) était interpolé DIRECTEMENT dans un bloc <script>, sans
    passer par une sérialisation JSON sûre. Une valeur Python None
    produisait le texte littéral "None" dans le JS généré -- invalide
    (le mot-clé JS est "null"), ce qui levait une ReferenceError au
    chargement de la page et empêchait l'attachement de l'écouteur de
    soumission du formulaire : le bouton "Enregistrer" ne faisait
    silencieusement plus rien du tout."""
    admin_client.post("/sources/", json={
        "id": "SRC-JSBUG", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    page = admin_client.get("/consumptions")
    assert page.status_code == 200

    import re
    scripts = re.findall(r"<script>(.*?)</script>", page.text, re.DOTALL)
    assert len(scripts) >= 1
    for script in scripts:
        # Ni "None" ni "undefined" ne doivent apparaître comme valeur brute
        # injectée (le token JS correct est "null").
        assert re.search(r":\s*None\b", script) is None, f"token Python 'None' trouvé dans le JS généré : {script[:300]}"

    # Le stock JSON doit être une syntaxe JS valide (null, pas None).
    assert '"SRC-JSBUG"' in page.text
    assert re.search(r'"SRC-JSBUG":\s*\{"quantite":\s*5(\.0)?,\s*"unite":\s*"g",\s*"etat_physique":\s*"liquide"\}', page.text), page.text[:1500]


def test_consommation_possible_avec_isotope_hors_table_si_quantite_initiale(admin_client, default_location):
    """12/07/2026 : bug signalé -- une source liquide de Co-60 (isotope
    hors de la table de masses molaires connues, sans cache LaraWeb) ne
    pouvait pas du tout être consommée, faute de quantité initiale
    saisissable. Doit maintenant fonctionner dès que quantite_initiale
    est renseignée à la création."""
    admin_client.post("/sources/", json={
        "id": "SRC-CO60-LIQ", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-CO60-LIQ", "nom": "Co-60", "activite": 500000,
        "unite_activite": "Bq", "date_reference": "2026-01-01", "periode": 5.27,
    })

    source_avant = admin_client.get("/sources/SRC-CO60-LIQ").json()
    assert source_avant["quantite_calculee"] == 10  # pas de décroissance-mass calculable pour Co-60, repli sur quantite_initiale

    resp = admin_client.post("/consumptions/", json={"source_id": "SRC-CO60-LIQ", "quantite_utilisee": 3})
    assert resp.status_code == 200

    source_apres = admin_client.get("/sources/SRC-CO60-LIQ").json()
    assert source_apres["quantite_calculee"] == 7


def test_quantite_restante_absente_pour_source_solide_non_scellee(admin_client, default_location):
    """12/07/2026 : la quantité restante ne doit s'afficher que pour les
    sources gaz/liquide (consommables), pas pour toute source non-scellée
    -- une source solide non-scellée (ex : un mélange de référence) n'a
    pas de "quantité restante" à suivre au même sens."""
    admin_client.post("/sources/", json={
        "id": "SRC-SOLIDE-NS", "type": "non-scellée", "etat_physique": "solide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 5, "unite_quantite": "g",
    })
    page = admin_client.get("/sources")
    assert page.status_code == 200
    debut = page.text.find('table-id">SRC-SOLIDE-NS')
    ligne = page.text[debut:debut + 2000].split("</tr>")[0]
    assert "5 g" not in ligne and ">5.000 g<" not in ligne


def test_activite_totale_retiree_activite_reference_formatee(admin_client, default_location):
    """12/07/2026 : la colonne "Activité totale de la source" est retirée
    de la page Radionucléides (systématiquement N/A, et redondante avec
    l'activité déjà affichée par radionucléide sur la page Sources,
    demandé explicitement). "Activité de référence" doit en revanche être
    formatée façon BestUnit (préfixe le plus lisible), pas affichée brute."""
    admin_client.post("/sources/", json={
        "id": "SRC-ACTTOT", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-ACTTOT", "nom": "Co-60", "activite": 5000000,
        "unite_activite": "Bq", "date_reference": "2020-07-08", "periode": 5.27,
    })

    page = admin_client.get("/radionuclides")
    assert page.status_code == 200
    assert "Activité totale de la source" not in page.text
    assert "5.00 MBq" in page.text  # 5 000 000 Bq reformaté avec préfixe


def test_quantite_restante_jamais_calculee_depuis_lactivite(admin_client, default_location):
    """12/07/2026, sur signalement direct : la quantité restante d'une
    source ne doit JAMAIS être calculée depuis l'activité d'un
    radionucléide (masse d'isotope pur) -- même pour une activité non
    spécifique. Cette masse d'isotope n'a de sens que pour l'Annexe 1 et
    le Tableau 1a (matières nucléaires) ; "quantité restante" désigne
    toujours la quantité physique de LA SOURCE (masse de liquide pesée,
    pression de gaz), jamais une masse d'isotope déduite par le calcul.

    Avant cette correction, une source de Pu-239 (activité non spécifique)
    sans quantité initiale renseignée affichait malgré tout une "quantité
    restante" -- calculée depuis la décroissance, en grammes de plutonium
    pur. C'était trompeur : ce nombre ne correspond à rien de pesable pour
    une source scellée classique, ce n'est qu'une donnée réglementaire."""
    admin_client.post("/sources/", json={
        "id": "SRC-CALC", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        # Pas de quantite_initiale : volontairement, pour vérifier qu'aucun
        # calcul de repli depuis l'activité ne se déclenche.
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-CALC", "nom": "239-Pu", "activite": 2.2965e9,
        "unite_activite": "Bq", "date_reference": "2026-01-01", "periode": 24100,
    })

    source = admin_client.get("/sources/SRC-CALC").json()
    assert source["quantite_calculee"] is None

    # Avec une quantité initiale renseignée, en revanche, le suivi doit
    # fonctionner normalement (indépendamment de l'activité du Pu-239).
    admin_client.put("/sources/SRC-CALC", json={"quantite_initiale": 1.0, "unite_quantite": "g"})
    source = admin_client.get("/sources/SRC-CALC").json()
    assert source["quantite_calculee"] == 1.0

    resp = admin_client.post("/consumptions/", json={"source_id": "SRC-CALC", "quantite_utilisee": 0.3})
    assert resp.status_code == 200

    source_apres = admin_client.get("/sources/SRC-CALC").json()
    assert abs(source_apres["quantite_calculee"] - 0.7) < 0.01


def test_pesee_double_calcule_la_quantite_consommee(admin_client, default_location):
    """12/07/2026 : mode pesée double (masse_avant/masse_apres) -- la
    quantité consommée doit se déduire automatiquement de la différence,
    et la quantité restante suivante doit être la masse_apres telle
    quelle (pas une soustraction accumulée), pour absorber naturellement
    l'évaporation du solvant au fil du temps."""
    admin_client.post("/sources/", json={
        "id": "SRC-PESEE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })

    resp = admin_client.post("/consumptions/", json={
        "source_id": "SRC-PESEE", "masse_avant": 10.0, "masse_apres": 8.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["quantite_utilisee"] - 1.5) < 0.001
    assert data["masse_avant"] == 10.0
    assert data["masse_apres"] == 8.5

    source = admin_client.get("/sources/SRC-PESEE").json()
    assert source["quantite_calculee"] == 8.5


def test_pesee_double_signale_ecart_evaporation(admin_client, default_location):
    """13/07/2026 (corrigé) : l'écart se détecte entre deux PESÉES
    successives (la première établit la référence, rien à comparer avant
    elle), pas entre la première pesée et quantite_initiale -- ce sont
    deux grandeurs différentes (masse totale pesée vs masse de liquide
    seule, cf. quantite_restante_calculee)."""
    admin_client.post("/sources/", json={
        "id": "SRC-EVAP", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    # Première pesée : établit la référence (55g, récipient inclus), sans
    # rien prélever. Pas d'écart possible à ce stade (rien à comparer).
    resp1 = admin_client.post("/consumptions/", json={
        "source_id": "SRC-EVAP", "masse_avant": 55.0, "masse_apres": 55.0,
    })
    assert resp1.status_code == 200
    assert not (resp1.json()["commentaire"] or "")

    # Deuxième pesée : 54.0g avant prélèvement, alors que 55g étaient
    # attendus (1g d'écart, largement au-dessus du seuil de 1%) --
    # probable évaporation depuis la première pesée.
    resp2 = admin_client.post("/consumptions/", json={
        "source_id": "SRC-EVAP", "masse_avant": 54.0, "masse_apres": 53.0,
    })
    assert resp2.status_code == 200
    assert "évaporation" in (resp2.json()["commentaire"] or "").lower()

    source = admin_client.get("/sources/SRC-EVAP").json()
    # masse récipient déduite = 55 - 5 = 50 ; quantité restante = 53 - 50 = 3
    assert abs(source["quantite_calculee"] - 3.0) < 0.01


def test_pesee_de_controle_sans_prelevement(admin_client, default_location):
    """13/07/2026 : une pesée avec masse_avant == masse_apres (rien
    prélevé) doit être acceptée -- utile pour la toute première pesée
    après réception (récipient + liquide + tout), qui établit une
    référence pour les calculs futurs sans qu'aucune matière n'ait été
    prélevée à ce moment-là."""
    admin_client.post("/sources/", json={
        "id": "SRC-CONTROLE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    resp = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CONTROLE", "masse_avant": 55.0, "masse_apres": 55.0,
    })
    assert resp.status_code == 200
    assert resp.json()["quantite_utilisee"] == 0.0

    # L'audit doit distinguer cette pesée de contrôle (action PESEE) d'une
    # vraie consommation (action UTILISATION).
    audit = admin_client.get("/audit/").json()
    actions = [a["action"] for a in audit if a.get("id_source") == "SRC-CONTROLE"]
    assert "PESEE" in actions


def test_pesee_de_controle_avec_masse_apres_omise(admin_client, default_location):
    """13/07/2026 : seule masse_avant fournie (masse_apres complètement
    absente de la requête, pas seulement vide) doit aussi être traitée
    comme une pesée de contrôle -- ce repli doit exister côté API, pas
    seulement dans le JavaScript du formulaire (trouvé en vérifiant le
    comportement de l'API directement, indépendamment du frontend)."""
    admin_client.post("/sources/", json={
        "id": "SRC-CONTROLE-API", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    resp = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CONTROLE-API", "masse_avant": 55.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["quantite_utilisee"] == 0.0
    assert data["masse_apres"] == 55.0


def test_pesee_de_controle_reconcilie_source_ancienne_jamais_pesee(admin_client, default_location):
    """14/07/2026 : question posée directement -- une source utilisée
    depuis longtemps (quantité initiale connue au certificat, mais aucune
    pesée jamais enregistrée dans l'appli) doit pouvoir simplement
    déclarer sa quantité restante ACTUELLE, sans reconstituer tout
    l'historique des prélèvements passés. Contrairement au cas "réception,
    pesée totale du récipient", cette déclaration directe peut être
    inférieure à la quantité initiale (ex: 6g restants sur 10g au
    certificat, après des années d'usage non tracé) -- dans ce cas, la
    valeur déclarée devient directement la référence (aucune masse de
    récipient n'est déduite, ce calcul n'aurait pas de sens ici)."""
    admin_client.post("/sources/", json={
        "id": "SRC-ANCIENNE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2015-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    # Avant toute pesée : repli sur quantite_initiale (comportement déjà
    # existant, aucun historique de consommation).
    source_avant = admin_client.get("/sources/SRC-ANCIENNE").json()
    assert source_avant["quantite_calculee"] == 10.0

    # Déclaration directe : "il reste 6g aujourd'hui", sans rien peser de
    # récipient (la source est ouverte depuis longtemps).
    resp = admin_client.post("/consumptions/", json={
        "source_id": "SRC-ANCIENNE", "masse_avant": 6.0,
    })
    assert resp.status_code == 200
    assert resp.json()["quantite_utilisee"] == 0.0

    source_apres = admin_client.get("/sources/SRC-ANCIENNE").json()
    assert source_apres["quantite_calculee"] == 6.0  # la déclaration devient la référence, telle quelle

    # Un vrai prélèvement ultérieur se comporte ensuite normalement.
    admin_client.post("/consumptions/", json={
        "source_id": "SRC-ANCIENNE", "masse_avant": 6.0, "masse_apres": 5.5,
    })
    source_final = admin_client.get("/sources/SRC-ANCIENNE").json()
    assert source_final["quantite_calculee"] == 5.5


def test_modification_pesee_recalcule_quantite_utilisee(admin_client, default_location):
    """13/07/2026 : pouvoir corriger une pesée mal saisie -- si masse_avant
    ou masse_apres change, quantite_utilisee doit se recalculer en
    conséquence, pas rester incohérente avec la valeur corrigée."""
    admin_client.post("/sources/", json={
        "id": "SRC-CORRIGE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    conso = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CORRIGE", "masse_avant": 10.0, "masse_apres": 8.5,
    }).json()
    assert abs(conso["quantite_utilisee"] - 1.5) < 0.001

    # Erreur de saisie : c'était en fait 8.0g après, pas 8.5g.
    resp = admin_client.patch(f"/consumptions/{conso['id']}", json={"masse_apres": 8.0})
    assert resp.status_code == 200
    corrige = resp.json()
    assert corrige["masse_avant"] == 10.0  # inchangé
    assert corrige["masse_apres"] == 8.0


def test_modification_date_consommation(admin_client, default_location):
    """31/07/2026, demandé directement : la date pouvait déjà être fausse
    dès la première saisie (import d'une fiche mal transcrite,
    notamment), sans possibilité de la corriger après coup."""
    admin_client.post("/sources/", json={
        "id": "SRC-DATE-CORRIGEE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "g",
    })
    conso = admin_client.post("/consumptions/", json={
        "source_id": "SRC-DATE-CORRIGEE", "quantite_utilisee": 1,
    }).json()

    resp = admin_client.patch(f"/consumptions/{conso['id']}", json={"timestamp": "2019-03-15T00:00:00"})
    assert resp.status_code == 200
    assert resp.json()["timestamp"].startswith("2019-03-15")


def test_suppression_consommation(admin_client, default_location):
    """31/07/2026, demandé directement, suite à un import dupliqué par
    erreur : contrairement aux sources (jamais supprimables), une
    consommation en doublon ne correspond à aucun événement réel --
    rien à archiver, la supprimer ne perd aucune trace d'un fait qui ne
    s'est jamais produit."""
    admin_client.post("/sources/", json={
        "id": "SRC-CONSO-A-SUPPRIMER", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "g",
    })
    conso = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CONSO-A-SUPPRIMER", "quantite_utilisee": 1,
    }).json()

    resp = admin_client.delete(f"/consumptions/{conso['id']}")
    assert resp.status_code == 204

    fiche = admin_client.get("/sources/SRC-CONSO-A-SUPPRIMER/fiche").text
    assert "Aucune consommation enregistrée" in fiche


def test_suppression_consommation_inexistante_404(admin_client):
    resp = admin_client.delete("/consumptions/999999")
    assert resp.status_code == 404


def test_suppression_consommation_tracee_dans_audit(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-CONSO-AUDIT-SUPPR", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location, "quantite_initiale": 10, "unite_quantite": "g",
    })
    conso = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CONSO-AUDIT-SUPPR", "quantite_utilisee": 1,
    }).json()
    admin_client.delete(f"/consumptions/{conso['id']}")

    audit = admin_client.get("/audit").text
    assert "SRC-CONSO-AUDIT-SUPPR" in audit
    assert f"consommation#{conso['id']}" in audit


def test_modification_pesee_refusee_si_incoherente(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-CORRIGE-2", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    conso = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CORRIGE-2", "masse_avant": 10.0, "masse_apres": 8.5,
    }).json()
    resp = admin_client.patch(f"/consumptions/{conso['id']}", json={"masse_apres": 12.0})
    assert resp.status_code == 400


def test_modification_pesee_tracee_dans_audit(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-CORRIGE-3", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    conso = admin_client.post("/consumptions/", json={
        "source_id": "SRC-CORRIGE-3", "masse_avant": 10.0, "masse_apres": 8.5,
    }).json()
    admin_client.patch(f"/consumptions/{conso['id']}", json={"masse_apres": 8.0, "commentaire": "correction"})

    audit = admin_client.get("/audit/").json()
    entrees = [a for a in audit if a.get("id_source") == "SRC-CORRIGE-3" and "consommation#" in (a.get("champ_modifie") or "")]
    assert len(entrees) >= 1
    assert any("masse_apres" in e["champ_modifie"] for e in entrees)


def test_pesee_double_refusee_si_apres_superieur_a_avant(admin_client, default_location):
    admin_client.post("/sources/", json={
        "id": "SRC-PESEE-INVALIDE", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    resp = admin_client.post("/consumptions/", json={
        "source_id": "SRC-PESEE-INVALIDE", "masse_avant": 5.0, "masse_apres": 8.0,
    })
    assert resp.status_code == 400


def test_activite_utilisee_affichee_sur_page_consommations(admin_client, default_location):
    """13/07/2026 : l'activité utilisée doit être calculée (décroissance à
    la date de la consommation) et affichée, sans rien stocker en base."""
    admin_client.post("/sources/", json={
        "id": "SRC-ACT-UTIL", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2020-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 5, "unite_quantite": "g",
    })
    admin_client.post("/radionuclides/", json={
        "source_id": "SRC-ACT-UTIL", "nom": "Co-60", "activite": 100,
        "unite_activite": "kBq/g", "activite_est_specifique": True,
        "date_reference": "2020-07-08", "periode": 5.27,
    })
    resp = admin_client.post("/consumptions/", json={
        "source_id": "SRC-ACT-UTIL", "masse_avant": 5.0, "masse_apres": 4.0,
    })
    assert resp.status_code == 200

    page = admin_client.get("/consumptions")
    assert page.status_code == 200
    assert "SRC-ACT-UTIL" in page.text
    # Ne doit pas rester vide ("—") : une activité calculable doit s'afficher.
    debut = page.text.find("SRC-ACT-UTIL")
    ligne = page.text[debut:debut + 1000].split("</tr>")[0]
    assert "Bq" in ligne


def test_quantite_calculee_presente_des_la_reponse_de_creation(admin_client, default_location):
    """12/07/2026 : trouvé en vérifiant manuellement le point 4 -- la
    réponse de POST /sources/ elle-même ne calculait pas quantite_calculee
    (contrairement à GET /sources/{id}, qui le fait), donnant "null" dans
    la réponse de création malgré une quantite_initiale bien enregistrée."""
    resp = admin_client.post("/sources/", json={
        "id": "SRC-CALC-CREATION", "type": "non-scellée", "etat_physique": "liquide",
        "etat_utilisation": "en utilisation", "date_arrivee": "2026-01-01",
        "emplacement_habituel_id": default_location,
        "quantite_initiale": 10, "unite_quantite": "g",
    })
    assert resp.status_code == 200
    assert resp.json()["quantite_calculee"] == 10.0

    resp2 = admin_client.put(f"/sources/SRC-CALC-CREATION", json={"commentaire": "test"})
    assert resp2.status_code == 200
    assert resp2.json()["quantite_calculee"] == 10.0


def test_page_movements_redirige_vers_url_propre_apres_soumission(admin_client):
    """31/07/2026, signalé directement : après un emprunt réussi, la
    pop-up d'emprunt se rouvrait -- window.location.reload() gardait
    ?source=XXX dans l'URL (arrivée sur cette page depuis le bouton
    "Emprunter" d'une source), ce qui redéclenchait l'ouverture
    automatique de cette même pop-up juste après le succès. Les trois
    soumissions de cette page redirigent maintenant vers une URL propre
    plutôt que de recharger la même."""
    page = admin_client.get("/movements")
    assert "window.location.reload()" not in page.text
    assert page.text.count("window.location.href = '/movements'") == 3
