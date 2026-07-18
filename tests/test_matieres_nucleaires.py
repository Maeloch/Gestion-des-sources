"""Tests du module matieres_nucleaires : codes matière EUR/National et
calcul de la masse d'un radioélément à partir de son activité."""
import math
from app.services.matieres_nucleaires import (
    parser_radionuclide, code_matiere, masse_radioelement_g, NOMBRE_AVOGADRO,
)


def test_parser_radionuclide():
    assert parser_radionuclide("233-U") == ("U", 233)
    assert parser_radionuclide("239-Pu") == ("Pu", 239)
    assert parser_radionuclide("3-H") == ("H", 3)
    assert parser_radionuclide("U-233") == ("U", 233)  # ordre inverse toléré
    assert parser_radionuclide("Cs-137") == ("Cs", 137)
    assert parser_radionuclide("") is None
    assert parser_radionuclide("sansformat") is None


def test_codes_matiere():
    assert code_matiere("233-U") == ("K", "V")
    assert code_matiere("238-U") == ("N", "N")
    assert code_matiere("235-U") == ("N", "N")
    assert code_matiere("239-Pu") == ("P", "P")
    assert code_matiere("240-Pu") == ("P", "P")
    assert code_matiere("232-Th") == ("T", "T")
    assert code_matiere("3-H") == (None, None)
    assert code_matiere("137-Cs") == (None, None)  # pas une matière nucléaire


def test_masse_radioelement_reference_connue():
    """Référence connue : l'activité massique du Pu-239 est d'environ
    2,3 GBq/g (demi-vie 24110 ans). 1 GBq doit donc correspondre à environ
    0,43 g."""
    masse = masse_radioelement_g(activite_bq=1e9, periode_annees=24110, nom_radionuclide="239-Pu")
    assert 0.40 < masse < 0.46


def test_masse_radioelement_isotope_inconnu_renvoie_none():
    assert masse_radioelement_g(activite_bq=1000, periode_annees=10, nom_radionuclide="137-Cs") is None


def test_masse_radioelement_sans_periode_renvoie_none():
    assert masse_radioelement_g(activite_bq=1000, periode_annees=None, nom_radionuclide="239-Pu") is None


def test_masse_radioelement_coherente_avec_la_formule():
    """Vérifie directement la formule physique : A = ln(2)/T½ x (m/M) x Na."""
    activite = 5e8
    periode_annees = 100
    masse = masse_radioelement_g(activite, periode_annees, "233-U")

    periode_s = periode_annees * 365.25 * 24 * 3600
    masse_molaire = 233.03963
    activite_recalculee = (math.log(2) / periode_s) * (masse / masse_molaire) * NOMBRE_AVOGADRO
    assert abs(activite_recalculee - activite) / activite < 0.001


def test_normalisation_sr90_y90_ne_garde_que_le_pere():
    """12/07/2026 : Y-90 est immédiatement à l'équilibre séculaire avec
    son père Sr-90 -- convention de l'application : ne nommer et
    catégoriser que par le père, quelle que soit la notation d'origine."""
    from app.services.matieres_nucleaires import normaliser_nom_radionuclide as n
    assert n("Sr-90+") == "Sr-90"
    assert n("90-Sr-Y") == "Sr-90"
    assert n("Sr-90") == "Sr-90"  # cas normal, inchangé
    assert n("Y-90") == "Y-90"  # un Y-90 isolé n'est pas renommé (prudence)


def test_est_matiere_nucleaire():
    """12/07/2026 : H-3, Li-6, et tout isotope de thorium/uranium/
    plutonium doivent être détectés comme matière nucléaire par défaut."""
    from app.services.matieres_nucleaires import est_matiere_nucleaire as mn
    assert mn("H-3") is True
    assert mn("Li-6") is True
    assert mn("Th-232") is True
    assert mn("U-235") is True
    assert mn("U-233") is True
    assert mn("Pu-239") is True
    assert mn("Pu-240") is True
    assert mn("Co-60") is False
    assert mn("Cs-137") is False
    assert mn("Li-7") is False  # seul Li-6 est concerné, pas tout le lithium


def test_normalisation_noms_radionuclides():
    """11/07/2026 : un même isotope apparaît sous des formes différentes
    selon le fichier/la personne qui saisit -- doit toujours donner le
    même résultat canonique 'Symbole-nombre' (comme LaraWeb), quel que
    soit l'ordre ou le séparateur dans le fichier source."""
    from app.services.matieres_nucleaires import normaliser_nom_radionuclide as n
    assert n("85 Kr") == "Kr-85"
    assert n("85Kr") == "Kr-85"
    assert n("Kr85") == "Kr-85"
    assert n("Kr 85") == "Kr-85"
    assert n("Kr-85") == "Kr-85"
    assert n("kr85") == "Kr-85"
    assert n("KR 85") == "Kr-85"
    assert n("Pu-239") == "Pu-239"
    assert n("239-Pu") == "Pu-239"
    assert n("cs137") == "Cs-137"


def test_normalisation_format_non_reconnu_inchange():
    """Un format qui ne correspond à aucun motif connu est laissé tel
    quel plutôt que de risquer une transformation erronée."""
    from app.services.matieres_nucleaires import normaliser_nom_radionuclide as n
    assert n("MELANGE") == "MELANGE"
    assert n("") == ""
