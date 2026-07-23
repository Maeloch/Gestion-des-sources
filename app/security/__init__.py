"""Module de sécurité."""
from app.security.auth import (
    AuthService,
    get_password_hash,
    verify_password,
    create_access_token,
    get_auth_service,  # ← Importé depuis auth.py, pas permissions.py
)
from app.security.permissions import (
    get_current_user,
    get_current_admin,
)

__all__ = [
    "AuthService",
    "get_password_hash",
    "verify_password",
    "create_access_token",
    "get_auth_service",
    "get_current_user",
    "get_current_admin",
]
