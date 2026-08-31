"""Tests du favicon -- demandé le 31/07/2026, uvicorn journalisait
régulièrement des 404 sur /favicon.ico (les navigateurs sondent cette
adresse à la racine du site, indépendamment des balises <link> du
<head>)."""


def test_favicon_racine_repond_200_pas_404(admin_client):
    resp = admin_client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.headers["content-type"] in ("image/vnd.microsoft.icon", "image/x-icon")


def test_favicon_svg_accessible(admin_client):
    resp = admin_client.get("/static/favicon.svg")
    assert resp.status_code == 200


def test_apple_touch_icon_accessible(admin_client):
    resp = admin_client.get("/static/apple-touch-icon.png")
    assert resp.status_code == 200


def test_balises_favicon_presentes_dans_le_head(admin_client):
    """Les balises <link> du <head>, en plus de la route dédiée : la
    plupart des navigateurs les utilisent en priorité pour l'onglet et
    les favoris, /favicon.ico n'étant qu'un repli."""
    page = admin_client.get("/sources")
    assert 'rel="icon" type="image/svg+xml" href="/static/favicon.svg' in page.text
    assert 'rel="icon" type="image/x-icon" href="/static/favicon.ico' in page.text
    assert 'rel="apple-touch-icon" href="/static/apple-touch-icon.png' in page.text
