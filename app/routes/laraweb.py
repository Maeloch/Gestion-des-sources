"""Route pour interroger LaraWeb (avec mise en cache locale)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.lara_cache import LaraCacheEntry
from app.services.laraweb import get_or_fetch, LaraWebError
from app.security.permissions import require_write_access
from app.database import get_db

router = APIRouter(prefix="/laraweb", tags=["laraweb"])


@router.get("/{nuclide}", response_model=LaraCacheEntry)
async def consulter_nuclide(
    nuclide: str,
    actualiser: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_write_access),
):
    """Renvoie les données du nuclide (depuis le cache local si déjà
    connu, sinon récupérées depuis LaraWeb et mises en cache).
    ?actualiser=true force une nouvelle récupération même si déjà en cache."""
    try:
        entree = get_or_fetch(db, nuclide, forcer_actualisation=actualiser)
    except LaraWebError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return entree
