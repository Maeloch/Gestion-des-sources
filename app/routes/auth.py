"""Routes pour l'authentification."""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from app.security.auth import AuthService, get_auth_service, create_access_token
from app.security.permissions import get_current_user, get_current_admin
from app.models.user import UserCreate, UserPublic
from app.repositories.user import UserRepository
from app.database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/logout")
async def logout(request: Request):
    # Redirige vers la page de connexion et supprime le cookie de session
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response
    
@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
):
    user = auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth_service.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    # Définis un cookie HTTP-only
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=int(access_token_expires.total_seconds()),
    )
    return response
    
    #return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", response_model=UserPublic)
async def register_user(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    user_repo = UserRepository(db)
    existing_user = user_repo.get_by_username(user.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà utilisé")

    existing_email = user_repo.get_by_email(user.email)
    if existing_email:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    new_user = user_repo.create(user)
    return new_user
