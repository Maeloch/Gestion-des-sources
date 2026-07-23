"""Gestion des permissions et des dépendances FastAPI."""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.config import settings
from app.security.auth import SECRET_KEY, ALGORITHM
from app.repositories.user import UserRepository
from app.database import get_db
from app.models.user import UserRole
from sqlalchemy.orm import Session

# auto_error=False : si l'en-tête "Authorization: Bearer ..." est absent, on ne bloque pas
# tout de suite. Cela permet de retomber sur le cookie de session (utilisé par le navigateur),
# tout en gardant la compatibilité avec un header Authorization classique (ex: /api/docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


def _extract_token(request: Request, header_token: Optional[str]) -> Optional[str]:
    """Récupère le token JWT depuis le header Authorization, sinon depuis le cookie de session."""
    if header_token:
        return header_token
    cookie_value = request.cookies.get("access_token")
    if cookie_value:
        return cookie_value.replace("Bearer ", "")
    return None


def _decode_user(token: str, db: Session):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    user_repo = UserRepository(db)
    user = user_repo.get_by_username(username)

    # Nombre de demandes de changement de rôle en attente, attaché ici
    # (pas dans chaque route individuelle) pour être disponible partout où
    # current_user l'est déjà, sans changement ailleurs -- utilisé par
    # base.html pour afficher un badge dans le bandeau. Calculé
    # uniquement pour un admin (seul rôle concerné), pour ne pas ajouter
    # une requête inutile aux autres. Demandé le 13/07/2026 : jusqu'ici,
    # rien ne signalait qu'une demande existait, un admin devait penser à
    # aller voir la page Utilisateurs de lui-même.
    if user is not None and user.role.value == "admin":
        from app.models.role_request import RoleRequestDB, StatutDemande
        user.demandes_role_en_attente = (
            db.query(RoleRequestDB)
            .filter(RoleRequestDB.statut == StatutDemande.en_attente)
            .count()
        )
    return user


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Exige un utilisateur authentifié (header Authorization OU cookie de session)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de valider les informations d'authentification",
        headers={"WWW-Authenticate": "Bearer"},
    )
    real_token = _extract_token(request, token)
    if not real_token:
        raise credentials_exception

    user = _decode_user(real_token, db)
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Comme get_current_user, mais renvoie None au lieu de lever une erreur 401.
    Utile pour les pages HTML publiques qui doivent simplement savoir si quelqu'un
    est connecté (pour afficher le bon menu), sans bloquer l'accès à la page."""
    real_token = _extract_token(request, token)
    if not real_token:
        return None
    return _decode_user(real_token, db)


async def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return current_user


async def require_audit_access(current_user: dict = Depends(get_current_user)):
    """Le journal d'audit est accessible aux administrateurs et aux
    utilisateurs MN (pas aux rôles 'utilisateur' ni 'lecteur')."""
    if current_user.role not in (UserRole.admin, UserRole.utilisateur_mn):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le journal d'audit est réservé aux administrateurs et aux utilisateurs MN.",
        )
    return current_user


async def require_admin_or_mn(current_user: dict = Depends(get_current_user)):
    """Accès réservé aux administrateurs et aux utilisateurs MN (ex : export
    de données). Distinct de require_audit_access uniquement par le message
    d'erreur affiché."""
    if current_user.role not in (UserRole.admin, UserRole.utilisateur_mn):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Réservé aux administrateurs et aux utilisateurs MN.",
        )
    return current_user


# --- Système de rôles à 4 niveaux --------------------------------------
#
# admin           : accès complet, y compris gestion des utilisateurs.
# utilisateur_mn  : peut créer/modifier/consommer, y compris les sources
#                   contenant de la Matière Nucléaire (MN).
# utilisateur     : comme utilisateur_mn, mais aucun accès aux sources MN.
# lecteur         : consultation seule, et aucun accès aux sources MN.

def user_can_write(user) -> bool:
    """Peut créer / modifier / consommer / supprimer (tout sauf lecteur)."""
    return user.role in (UserRole.admin, UserRole.utilisateur_mn, UserRole.utilisateur)


def user_can_access_mn(user) -> bool:
    """Peut voir et manipuler les sources contenant de la Matière Nucléaire."""
    return user.role in (UserRole.admin, UserRole.utilisateur_mn)


async def require_write_access(current_user: dict = Depends(get_current_user)):
    """Dépendance à utiliser sur toutes les routes de création / modification /
    suppression / consommation. Bloque uniquement le rôle 'lecteur'."""
    if not user_can_write(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ton rôle (lecteur) ne permet que la consultation, pas la modification.",
        )
    return current_user


def check_source_mn_access(source, current_user) -> None:
    """À appeler après avoir récupéré une source, avant de la renvoyer ou de
    la modifier. Si la source contient de la Matière Nucléaire et que
    l'utilisateur n'y a pas accès, on renvoie une 404 (et non 403) pour ne
    pas même confirmer l'existence de la source à quelqu'un qui n'y a pas
    accès."""
    if source is not None and getattr(source, "matiere_nucleaire", False) and not user_can_access_mn(current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source non trouvée")


def require_mn_access_for(matiere_nucleaire: bool, current_user) -> None:
    """À appeler avant de créer/modifier une source pour lui donner (ou
    laisser) le statut Matière Nucléaire = True."""
    if matiere_nucleaire and not user_can_access_mn(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ton rôle ne permet pas de créer ou modifier une source Matière Nucléaire.",
        )
