"""Routes pour les lieux."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session
from app.models.location import Location, LocationCreate, LocationUpdate, LocationFusion
from app.repositories.location import LocationRepository
from app.models.audit import AuditLogCreate
from app.repositories.audit import AuditRepository
from app.security.permissions import get_current_user, require_write_access
from app.database import get_db

router = APIRouter(prefix="/locations", tags=["locations"])

@router.get("/", response_model=List[Location])
async def list_locations(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    repo = LocationRepository(db)
    return repo.get_all()

@router.post("/", response_model=Location)
async def create_location(
    location: LocationCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = LocationRepository(db)
    return repo.create(location)


def _fusionner(db: Session, source_loc, cible_loc, utilisateur: str):
    """Réaffecte toutes les sources et tous les mouvements de `source_loc`
    vers `cible_loc`, puis supprime `source_loc`. Logique commune aux deux
    façons de déclencher une fusion : le bouton dédié (POST .../fusionner)
    et le renommage d'un lieu vers un nom déjà pris (PUT ..., voir
    update_location) -- extraite ici le 13/07/2026 pour ne pas dupliquer
    cette logique entre les deux routes."""
    from app.models.source import SourceDB
    from app.models.movement import MovementDB

    nb_habituel = db.query(SourceDB).filter(SourceDB.emplacement_habituel_id == source_loc.id).update(
        {"emplacement_habituel_id": cible_loc.id}
    )
    nb_actuel = db.query(SourceDB).filter(SourceDB.emplacement_actuel_id == source_loc.id).update(
        {"emplacement_actuel_id": cible_loc.id}
    )
    nb_mvt_de = db.query(MovementDB).filter(MovementDB.from_location_id == source_loc.id).update(
        {"from_location_id": cible_loc.id}
    )
    nb_mvt_vers = db.query(MovementDB).filter(MovementDB.to_location_id == source_loc.id).update(
        {"to_location_id": cible_loc.id}
    )

    nom_source_loc = source_loc.nom
    db.delete(source_loc)
    db.commit()
    db.refresh(cible_loc)

    AuditRepository(db).create(AuditLogCreate(
        utilisateur=utilisateur,
        action="UPDATE",
        table_modifiee="locations",
        id_source=None,
        champ_modifie="fusion_lieu",
        valeur_avant=nom_source_loc,
        valeur_apres=(
            f"fusionné dans '{cible_loc.nom}' ({nb_habituel} source(s) [habituel], "
            f"{nb_actuel} source(s) [actuel], {nb_mvt_de + nb_mvt_vers} mouvement(s) réaffectés)"
        ),
    ))
    return cible_loc


@router.put("/{location_id}", response_model=Location)
async def update_location(
    location_id: int,
    location_update: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = LocationRepository(db)
    db_location = repo.get_by_id(location_id)
    if not db_location:
        raise HTTPException(status_code=404, detail="Lieu non trouvé")

    # Renommer un lieu vers un nom déjà pris par un AUTRE lieu propose une
    # fusion plutôt que d'échouer avec une erreur de contrainte SQL --
    # demandé le 13/07/2026 : "accepter de renommer un lieu en un lieu
    # existant, et propagation de la fusion". Nécessite une confirmation
    # explicite (confirmer_fusion=true) pour éviter qu'une simple faute de
    # frappe déclenche une fusion silencieuse et irréversible.
    if location_update.nom and location_update.nom != db_location.nom:
        collision = (
            db.query(type(db_location))
            .filter(type(db_location).nom == location_update.nom, type(db_location).id != location_id)
            .first()
        )
        if collision:
            if not location_update.confirmer_fusion:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Un lieu nommé '{location_update.nom}' existe déjà (id {collision.id}). "
                        f"Fusionner '{db_location.nom}' dedans ? Toutes ses sources et mouvements "
                        "seraient réaffectés, puis ce lieu supprimé."
                    ),
                )
            return _fusionner(db, db_location, collision, current_user.username)

    db_location = repo.update(location_id, location_update)
    if not db_location:
        raise HTTPException(status_code=404, detail="Lieu non trouvé")
    return db_location

@router.post("/{location_id}/fusionner", response_model=Location)
async def fusionner_location(
    location_id: int,
    fusion: LocationFusion,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    """Fusionne le lieu `location_id` dans le lieu `fusion.cible_id` :
    toutes les sources et tous les mouvements qui référençaient
    `location_id` sont réaffectés au lieu cible, puis `location_id` est
    supprimé. Utile pour simplifier une liste de lieux devenue trop
    éclatée (ex: fusionner "Dess. 2" dans "Armoire des sources") — demandé
    le 11/07/2026. Voir aussi update_location : renommer un lieu vers un
    nom déjà pris déclenche la même fusion, de façon peut-être plus
    naturelle à découvrir."""
    repo = LocationRepository(db)
    source_loc = repo.get_by_id(location_id)
    if not source_loc:
        raise HTTPException(status_code=404, detail="Lieu à fusionner non trouvé")
    cible_loc = repo.get_by_id(fusion.cible_id)
    if not cible_loc:
        raise HTTPException(status_code=404, detail="Lieu cible non trouvé")
    if location_id == fusion.cible_id:
        raise HTTPException(status_code=400, detail="Impossible de fusionner un lieu avec lui-même")

    return _fusionner(db, source_loc, cible_loc, current_user.username)


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    repo = LocationRepository(db)

    from app.models.source import SourceDB
    sources_ici = db.query(SourceDB).filter(SourceDB.emplacement_actuel_id == location_id).count()
    if sources_ici > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Impossible de supprimer ce lieu : {sources_ici} source(s) y sont "
                "actuellement situées. Déplace-les d'abord vers un autre lieu."
            ),
        )

    if not repo.delete(location_id):
        raise HTTPException(status_code=404, detail="Lieu non trouvé")
    return
