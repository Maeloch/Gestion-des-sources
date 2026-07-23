"""Tests du module de gestion des unités et préfixes SI d'activité."""
import pytest
from app.services.units import parser_unite_activite, normaliser_en_bq, formater_activite_bq


def test_prefixes_reconnus():
    assert parser_unite_activite("Bq") == (1.0, "Bq")
    assert parser_unite_activite("kBq") == (1e3, "Bq")
    assert parser_unite_activite("MBq") == (1e6, "Bq")
    assert parser_unite_activite("GBq") == (1e9, "Bq")
    assert parser_unite_activite("mBq") == (1e-3, "Bq")
    assert parser_unite_activite("µBq") == (1e-6, "Bq")
    assert parser_unite_activite("uBq") == (1e-6, "Bq")


def test_unites_composees():
    assert parser_unite_activite("Bq/g") == (1.0, "Bq/g")
    assert parser_unite_activite("kBq/g") == (1e3, "Bq/g")
    assert parser_unite_activite("MBq/g") == (1e6, "Bq/g")
    assert parser_unite_activite("Bq/m3") == (1.0, "Bq/m3")
    assert parser_unite_activite("kBq/m3") == (1e3, "Bq/m3")


def test_unite_non_reconnue_leve_erreur():
    with pytest.raises(ValueError):
        parser_unite_activite("BqXYZ")
    with pytest.raises(ValueError):
        parser_unite_activite("grammes")
    with pytest.raises(ValueError):
        parser_unite_activite("")


def test_normaliser_en_bq():
    assert normaliser_en_bq(5, "MBq") == 5_000_000
    assert normaliser_en_bq(150, "kBq/g") == 150_000
    assert normaliser_en_bq(3, "Bq") == 3


def test_formater_activite_bq_choisit_le_prefixe_lisible():
    """12/07/2026 : le nombre de décimales vient désormais de
    arrondir_scientifique (incertitude à 1%, voir res_round.m/LNHB), pas
    d'un nombre de chiffres significatifs fixé arbitrairement."""
    assert formater_activite_bq(1_250_000) == "1.250 MBq"
    assert formater_activite_bq(45) == "45.00 Bq"
    assert formater_activite_bq(999) == "999.0 Bq"
    assert formater_activite_bq(1000) == "1.000 kBq"
    assert formater_activite_bq(0.003) == "3.000 mBq"
    assert formater_activite_bq(0) == "0 Bq"


def test_formater_activite_bq_avec_denominateur():
    """12/07/2026 : le préfixe doit s'insérer juste avant 'Bq', pas entre
    le '/' et le dénominateur (ex: 'kBq/g', jamais 'Bq/kg')."""
    assert formater_activite_bq(148000, "Bq/g") == "148.0 kBq/g"
    assert formater_activite_bq(45310, "Bq/g") == "45.31 kBq/g"


def test_formater_duree_choisit_l_unite_de_temps_lisible():
    """12/07/2026 : sur le même principe que formater_activite_bq, mais
    avec des facteurs de conversion non-métriques (60, 24, 365.25). Le
    repli "ans" (plus aucune unité de temps plus grande vers laquelle
    basculer) reste volontairement en écriture scientifique %.3g, sur
    retour explicite."""
    from app.services.units import formater_duree
    assert formater_duree(5.271) == "5.27 ans"
    assert formater_duree(24100) == "2.41e+04 ans"
    assert formater_duree(1 / 365.25) == "1.000 j"
    assert formater_duree(1 / (365.25 * 24)) == "1.000 h"
    # Po-214 : demi-vie ~164.3 microsecondes
    assert formater_duree(164.3e-6 / (365.25 * 24 * 3600)) == "164.3 µs"


def test_formater_activite_bq_valeur_infime_donne_zero():
    """13/07/2026, sur un cas réel (IRMA-0060) : une activité infime (bien
    en dessous du nBq) produisait un mur de plusieurs centaines de zéros,
    voire un dépassement de capacité pour les valeurs les plus extrêmes.
    Sous 1 nBq, la valeur est maintenant jugée négligeable et affichée
    comme "0"."""
    assert formater_activite_bq(2.643e-322) == "0 Bq"  # plantait avant (OverflowError)
    assert formater_activite_bq(5e-10) == "0 Bq"  # juste sous 1 nBq
    assert formater_activite_bq(1.5e-9) == "1.500 nBq"  # juste au-dessus : affiché normalement
    assert formater_activite_bq(0) == "0 Bq"


def test_arrondir_scientifique_imite_res_round():
    """12/07/2026 : port du cœur de res_round.m (LNHB, fourni par
    l'utilisateur) -- le nombre de décimales se déduit de l'incertitude
    (arbitrairement 1% de la valeur si non fournie), pas fixé d'avance."""
    from app.services.units import arrondir_scientifique
    assert arrondir_scientifique(45.31) == "45.31"
    assert arrondir_scientifique(0) == "0"
    # Avec une incertitude explicite, cohérent avec res_round.m
    assert arrondir_scientifique(1.234, incertitude=0.05) == "1.23"
