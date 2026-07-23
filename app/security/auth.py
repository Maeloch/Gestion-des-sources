"""Authentification et gestion des utilisateurs."""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from app.config import settings
from app.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

# Configuration du hachage des mots de passe
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Clé secrète pour JWT
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class AuthService:
    def __init__(self, user_repo):
        self.user_repo = user_repo
        self.access_token_expire_minutes = settings.access_token_expire_minutes

    def authenticate_user(self, username: str, password: str):
        user = self.user_repo.get_by_username(username)
        if not user:
            return False
        if not verify_password(password, user.hashed_password):
            return False
        return user

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    auth_service = AuthService(None)
    return auth_service.create_access_token(data, expires_delta)

def get_auth_service(db: Session = Depends(get_db)):
    from app.repositories.user import UserRepository
    user_repo = UserRepository(db)
    return AuthService(user_repo)
