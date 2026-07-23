"""Point d'entrée de l'application FastAPI."""
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.config import settings
from app.database import engine, Base, get_db
from app.security.permissions import get_current_user_optional, get_current_admin, require_audit_access, require_admin_or_mn, user_can_access_mn

# Migrations automatiques du schéma de la base de données. Sans danger à
# exécuter à chaque démarrage : ne font rien si la base est déjà à jour.
from app.scripts.migrate_add_role import migrate as _migrate_add_role
from app.scripts.migrate_add_source_fields import (
    migrate as _migrate_add_source_fields,
    migrate_consumptions as _migrate_consumptions,
    migrate_radionuclides as _migrate_radionuclides,
    migrate_volume_recipient as _migrate_volume_recipient,
)
from app.scripts.migrate_add_locations_movements import migrate as _migrate_locations_movements
from app.version import APP_VERSION
_migrate_add_role()
_migrate_add_source_fields()
_migrate_consumptions()
_migrate_radionuclides()
_migrate_volume_recipient()
_migrate_locations_movements()

from app.routes import (
    sources_router,
    radionuclides_router,
    audit_router,
    auth_router,
    users_router,
    consumptions_router,
    locations_router,
    movements_router,
    import_export_router,
    laraweb_router,
)

# Créer l'application FastAPI
app = FastAPI(
    title="Gestion des Sources Radioactives",
    description="API pour la gestion des sources radioactives et des radionucléides.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Configurer CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monter les fichiers statiques
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Configurer les templates
templates = Jinja2Templates(directory="app/templates")
# Utilisable directement dans les templates : {{ arrondir_scientifique(valeur) }}
# -- ajouté le 13/07/2026 pour appliquer partout le même arrondi fondé sur
# l'incertitude (voir units.py) plutôt qu'un nombre de décimales fixé au
# cas par cas dans chaque template (ex: l'ancien "%.3g"|format trouvé sur
# la quantité restante des sources).
from app.services.units import arrondir_scientifique as _arrondir_scientifique_jinja
templates.env.globals["arrondir_scientifique"] = _arrondir_scientifique_jinja
templates.env.globals["app_version"] = APP_VERSION


def _redirect_to_login_if_needed(current_user):
    """Les pages de consultation exigent désormais d'être connecté (cohérent
    avec le système de rôles : impossible de savoir ce qu'un visiteur anonyme
    a le droit de voir). Renvoie une redirection si personne n'est connecté,
    ou None si on peut continuer normalement."""
    if current_user is None:
        return RedirectResponse(url="/auth/login", status_code=303)
    return None


# Routes pour les pages HTML

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user=Depends(get_current_user_optional)):
    # "/" n'est plus une page d'accueil à part : elle redirige directement
    # vers Sources (connecté) ou la connexion (anonyme), pour éviter un
    # écran intermédiaire inutile.
    if current_user:
        return RedirectResponse(url="/sources", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)

@app.get("/sources", response_class=HTMLResponse)
async def list_sources(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user_optional)):
    redirect = _redirect_to_login_if_needed(current_user)
    if redirect:
        return redirect
    from app.repositories.source import SourceRepository
    from app.repositories.location import LocationRepository
    from app.services.units import quantite_restante_calculee, activite_actuelle_bq, formater_activite_bq, parser_unite_activite
    sources = SourceRepository(db).get_all()  # toutes : le filtre de statut est désormais géré côté client
    if not user_can_access_mn(current_user):
        sources = [s for s in sources if not s.matiere_nucleaire]
    locations = LocationRepository(db).get_all()

    for s in sources:
        s.quantite_calculee = quantite_restante_calculee(db, s)
        s.activite_max_bq = None
        for rn in s.radionuclides:
            if rn.periode:
                rn.activite_actuelle_bq_brute = activite_actuelle_bq(rn)
                try:
                    _, unite_base = parser_unite_activite(rn.unite_activite) if rn.unite_activite else (1.0, "Bq")
                except ValueError:
                    unite_base = "Bq"
                rn.activite_actuelle_affichee = formater_activite_bq(rn.activite_actuelle_bq_brute, unite_base)
                if rn.activite_actuelle_bq_brute is not None:
                    s.activite_max_bq = max(s.activite_max_bq or 0, rn.activite_actuelle_bq_brute)
            else:
                rn.activite_actuelle_bq_brute = None
                rn.activite_actuelle_affichee = None

    # Liste des radionucléides distincts actuellement présents (toutes
    # sources visibles confondues), pour le filtre dédié -- demandé le
    # 14/07/2026. Triée pour un menu déroulant stable et lisible.
    radionuclides_distincts = sorted({rn.nom for s in sources for rn in s.radionuclides})

    # Éligibilité au bouton "Emprunter" (page Sources) -- même logique que
    # "sources_disponibles" sur la page Mouvements (voir plus bas) : pas
    # d'emprunt déjà en cours, lieu habituel défini. Demandé le 22/07/2026,
    # à l'instar du bouton "Consommer" déjà présent.
    from app.repositories.movement import MovementRepository
    from app.models.source import is_archived
    tous_mouvements = MovementRepository(db).get_all()
    sources_avec_emprunt_ouvert = {m.source_id for m in tous_mouvements if m.date_retour_reelle is None}
    for s in sources:
        s.peut_emprunter = (
            s.id not in sources_avec_emprunt_ouvert
            and bool(s.emplacement_habituel_id)
            and not is_archived(s)
        )

    return templates.TemplateResponse(
        request=request,
        name="sources.html",
        context={
            "request": request,
            "sources": sources,
            "locations": locations,
            "radionuclides_distincts": radionuclides_distincts,
            "current_user": current_user,
        },
    )

@app.get("/sources/archive", response_class=HTMLResponse)
async def list_sources_archive(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user_optional)):
    redirect = _redirect_to_login_if_needed(current_user)
    if redirect:
        return redirect
    from app.repositories.source import SourceRepository
    sources = SourceRepository(db).get_all(archivees=True)
    if not user_can_access_mn(current_user):
        sources = [s for s in sources if not s.matiere_nucleaire]
    return templates.TemplateResponse(
        request=request,
        name="sources_archive.html",
        context={
            "request": request,
            "sources": sources,
            "current_user": current_user,
        },
    )

@app.get("/radionuclides", response_class=HTMLResponse)
async def list_radionuclides(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user_optional)):
    redirect = _redirect_to_login_if_needed(current_user)
    if redirect:
        return redirect
    from app.repositories.radionuclide import RadionuclideRepository
    from app.repositories.source import SourceRepository
    from app.services.decay import DecayService
    from app.services.units import (
        activite_actuelle_bq, parser_unite_activite, formater_activite_bq, formater_duree, normaliser_en_bq,
    )

    radionuclides = RadionuclideRepository(db).get_all()
    all_sources = SourceRepository(db).get_all()  # toutes, y compris archivées : nécessaire pour le calcul d'activité totale ci-dessous
    sources_actives = SourceRepository(db).get_all(archivees=False)  # pour le formulaire d'ajout uniquement
    if not user_can_access_mn(current_user):
        mn_source_ids = {s.id for s in all_sources if s.matiere_nucleaire}
        radionuclides = [r for r in radionuclides if r.source_id not in mn_source_ids]
        sources_actives = [s for s in sources_actives if not s.matiere_nucleaire]

    # Calcule l'activité actuelle (décroissance radioactive depuis date_reference)
    # pour affichage, sans modifier les valeurs de référence stockées en base.
    # Si le radionucléide est marqué "activité spécifique" (par unité de
    # quantité), calcule aussi l'activité totale de la source = activité
    # spécifique actuelle × quantité restante (formule du CDC), uniquement
    # quand la source a une quantité suivie.

    sources_by_id = {s.id: s for s in all_sources}
    for rn in radionuclides:
        if rn.periode:
            rn.activite_actuelle = DecayService.calculate_activity(
                initial_activity=rn.activite,
                half_life_years=rn.periode,
                initial_date=rn.date_reference,
            )
            rn.activite_actuelle_bq_normalisee = activite_actuelle_bq(rn)
        else:
            rn.activite_actuelle = None
            rn.activite_actuelle_bq_normalisee = None

        # Unité de base pour l'affichage : la partie après le préfixe
        # éventuel de l'unité saisie (ex: "kBq/g" -> "Bq/g").
        try:
            _, unite_base = parser_unite_activite(rn.unite_activite) if rn.unite_activite else (1.0, "Bq")
        except ValueError:
            unite_base = "Bq"

        rn.activite_actuelle_affichee = (
            formater_activite_bq(rn.activite_actuelle_bq_normalisee, unite_base)
            if rn.activite_actuelle_bq_normalisee is not None else None
        )
        rn.periode_affichee = formater_duree(rn.periode) if rn.periode is not None else None

        # Activité de référence : même traitement BestUnit que l'activité
        # actuelle (préfixe le plus lisible + arrondi par incertitude),
        # mais sans décroissance appliquée -- demandé le 12/07/2026, la
        # valeur brute telle quelle pouvait être peu lisible (ex : une
        # activité saisie en Bq alors qu'elle vaut plusieurs millions).
        try:
            activite_reference_bq = normaliser_en_bq(rn.activite, rn.unite_activite) if rn.unite_activite else rn.activite
        except ValueError:
            activite_reference_bq = rn.activite
        rn.activite_reference_bq_normalisee = activite_reference_bq
        rn.activite_reference_affichee = formater_activite_bq(activite_reference_bq, unite_base)

    return templates.TemplateResponse(
        request=request,
        name="radionuclides.html",
        context={
            "request": request,
            "radionuclides": radionuclides,
            "sources": sources_actives,
            "current_user": current_user,
        },
    )

@app.get("/consumptions", response_class=HTMLResponse)
async def list_consumptions(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user_optional)):
    redirect = _redirect_to_login_if_needed(current_user)
    if redirect:
        return redirect
    from app.repositories.consumption import ConsumptionRepository
    from app.repositories.source import SourceRepository
    from app.models.source import is_archived
    from app.services.units import quantite_restante_calculee, activite_utilisee_bq, formater_activite_bq, arrondir_scientifique
    consumptions = ConsumptionRepository(db).get_all()
    all_sources = SourceRepository(db).get_all()
    sources_actives = [s for s in all_sources if not is_archived(s)]
    if not user_can_access_mn(current_user):
        mn_source_ids = {s.id for s in all_sources if s.matiere_nucleaire}
        consumptions = [c for c in consumptions if c.source_id not in mn_source_ids]
        sources_actives = [s for s in sources_actives if not s.matiere_nucleaire]

    # Activité correspondant à la quantité consommée, calculée à la date
    # de CHAQUE consommation (décroissance appliquée) -- demandé le
    # 13/07/2026, purement pour l'affichage : rien n'est stocké en base.
    sources_par_id = {s.id: s for s in all_sources}
    for c in consumptions:
        source = sources_par_id.get(c.source_id)
        c.activite_utilisee_bq = activite_utilisee_bq(db, source, c) if source else None
        c.activite_utilisee_affichee = (
            formater_activite_bq(c.activite_utilisee_bq) if c.activite_utilisee_bq is not None else None
        )
        unite = source.unite_quantite.value if source and source.unite_quantite else ""
        c.quantite_utilisee_affichee = (
            f"{arrondir_scientifique(c.quantite_utilisee)} {unite}".strip()
            if c.quantite_utilisee is not None else "—"
        )
    # Seules les sources gaz/liquide, actives, avec une quantité connue
    # (calculée ou, à défaut, historique) peuvent être consommées.
    consommables = []
    for s in sources_actives:
        if s.etat_physique.value not in ("gaz", "liquide"):
            continue
        quantite = quantite_restante_calculee(db, s)
        if quantite is None:
            continue
        s.quantite_calculee = quantite
        consommables.append(s)
    # Sérialisé ici (pas dans le template) : permet d'utiliser tojson côté
    # Python de façon fiable, plutôt que d'interpoler des attributs bruts
    # dans du JavaScript -- une valeur Python None interpolée directement
    # produit le texte "None", invalide en JS, ce qui cassait silencieusement
    # tout le script de la page (bug trouvé le 12/07/2026 : le formulaire
    # semblait "ne rien faire" au clic, car aucun écouteur n'était jamais
    # attaché suite à cette erreur de script).
    import json as _json
    sources_consommables_json = _json.dumps({
        s.id: {
            "quantite": round(s.quantite_calculee, 6) if s.quantite_calculee is not None else None,
            "unite": s.unite_quantite.value if s.unite_quantite else "",
            "etat_physique": s.etat_physique.value if s.etat_physique else "",
        }
        for s in consommables
    })

    # Même logique de sécurité que sources_consommables_json ci-dessus,
    # pour le bouton "Modifier" de chaque ligne : passer les valeurs via
    # un objet JS construit côté Python plutôt que dans l'attribut
    # onclick, qui casserait dès qu'un commentaire contient un guillemet
    # (simple ou double) -- trouvé le 13/07/2026 en construisant cette
    # fonctionnalité, sur le même principe que le bug du 12/07/2026.
    consumptions_json = _json.dumps({
        c.id: {
            "masse_avant": c.masse_avant,
            "masse_apres": c.masse_apres,
            "quantite_utilisee": c.quantite_utilisee,
            "commentaire": c.commentaire,
        }
        for c in consumptions
    })

    return templates.TemplateResponse(
        request=request,
        name="consumptions.html",
        context={
            "request": request,
            "consumptions": consumptions,
            "sources_consommables": consommables,
            "sources_consommables_json": sources_consommables_json,
            "consumptions_json": consumptions_json,
            "current_user": current_user,
        },
    )

@app.get("/audit", response_class=HTMLResponse)
async def list_audit_logs(request: Request, db: Session = Depends(get_db), current_user=Depends(require_audit_access)):
    from app.repositories.audit import AuditRepository
    repo = AuditRepository(db)
    logs = repo.get_all(limit=100)
    tables_distinctes = sorted({log.table_modifiee for log in logs})
    return templates.TemplateResponse(
        request=request,
        name="audit.html",
        context={
            "request": request,
            "logs": logs,
            "tables_distinctes": tables_distinctes,
            "current_user": current_user,
        },
    )

@app.get("/locations", response_class=HTMLResponse)
async def list_locations(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user_optional)):
    redirect = _redirect_to_login_if_needed(current_user)
    if redirect:
        return redirect
    from app.repositories.location import LocationRepository
    repo = LocationRepository(db)
    locations = repo.get_all()
    return templates.TemplateResponse(
        request=request,
        name="locations.html",
        context={
            "request": request,
            "locations": locations,
            "current_user": current_user,
        },
    )

@app.get("/movements", response_class=HTMLResponse)
async def list_movements(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user_optional)):
    redirect = _redirect_to_login_if_needed(current_user)
    if redirect:
        return redirect
    from app.repositories.movement import MovementRepository
    from app.repositories.source import SourceRepository
    from app.repositories.location import LocationRepository

    movements = MovementRepository(db).get_all()
    all_sources = SourceRepository(db).get_all()
    all_locations = LocationRepository(db).get_all()

    if not user_can_access_mn(current_user):
        mn_source_ids = {s.id for s in all_sources if s.matiere_nucleaire}
        movements = [m for m in movements if m.source_id not in mn_source_ids]
        all_sources = [s for s in all_sources if not s.matiere_nucleaire]

    # Pour le formulaire "démarrer un emprunt" : seules les sources actives,
    # sans emprunt déjà en cours, ET ayant un lieu habituel défini
    # (obligatoire pour pouvoir démarrer puis clôturer un emprunt), peuvent
    # en démarrer un nouveau.
    from app.models.source import is_archived
    sources_avec_emprunt_ouvert = {m.source_id for m in movements if m.date_retour_reelle is None}
    sources_disponibles = [
        s for s in all_sources
        if s.id not in sources_avec_emprunt_ouvert and s.emplacement_habituel_id and not is_archived(s)
    ]

    return templates.TemplateResponse(
        request=request,
        name="movements.html",
        context={
            "request": request,
            "movements": movements,
            "sources_disponibles": sources_disponibles,
            "locations": all_locations,
            "current_user": current_user,
        },
    )

@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/sources", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "request": request,
            "current_user": current_user,
        },
    )

@app.get("/auth/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user=Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/sources", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={
            "request": request,
            "current_user": current_user,
        },
    )

@app.get("/import-export", response_class=HTMLResponse)
async def import_export_page(request: Request, current_user=Depends(require_admin_or_mn)):
    # La page est accessible aux admins et utilisateurs MN (l'export
    # concerne aussi les MN) ; la section import reste réservée aux
    # administrateurs (opération de masse), affichée conditionnellement
    # dans le template.
    return templates.TemplateResponse(
        request=request,
        name="import_export.html",
        context={
            "request": request,
            "current_user": current_user,
        },
    )

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_admin)):
    # Contrairement aux autres pages, celle-ci exige d'être administrateur
    # (get_current_admin, pas get_current_user_optional) : elle affiche les
    # emails de tous les utilisateurs et permet de gérer les rôles.
    from app.repositories.user import UserRepository
    from app.models.role_request import RoleRequestDB, StatutDemande
    repo = UserRepository(db)
    users = repo.get_all()
    demandes_en_attente = (
        db.query(RoleRequestDB)
        .filter(RoleRequestDB.statut == StatutDemande.en_attente)
        .order_by(RoleRequestDB.date_demande.asc())
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "request": request,
            "users": users,
            "demandes_en_attente": demandes_en_attente,
            "current_user": current_user,
        },
    )

# Inclure les routers de l'API JSON. IMPORTANT : ceci doit rester APRÈS
# toutes les routes de pages HTML ci-dessus. FastAPI/Starlette retient la
# première route qui correspond au chemin demandé ; comme certaines routes
# de l'API utilisent un paramètre dynamique (ex: GET /sources/{source_id}),
# les inclure trop tôt leur ferait intercepter par erreur des pages comme
# /sources/archive (qui serait alors comprise comme "la source dont
# l'identifiant est 'archive'"). En les incluant en dernier, les chemins
# fixes définis au-dessus restent prioritaires.
app.include_router(auth_router)
app.include_router(sources_router)
app.include_router(radionuclides_router)
app.include_router(consumptions_router)
app.include_router(audit_router)
app.include_router(users_router)
app.include_router(locations_router)
app.include_router(movements_router)
app.include_router(import_export_router)
app.include_router(laraweb_router)

# Lancer l'application
if __name__ == "__main__":
    import uvicorn
    from app.config import settings
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
