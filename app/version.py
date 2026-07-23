"""Numéro de version de l'application.

À incrémenter à chaque nouvelle version livrée (demandé le 10/07/2026,
pour ne plus avoir de doute sur la version réellement testée). Affiché en
bas de chaque page, et utilisé pour invalider le cache du navigateur sur
les fichiers statiques (CSS) à chaque changement de version — ce qui
corrige au passage un probable souci de cache expliquant les pop-up qui ne
s'affichaient plus correctement.
"""
APP_VERSION = "0.1.26"
