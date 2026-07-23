"""Modèle pour les utilisateurs, avec un système de rôles à 4 niveaux."""
from sqlalchemy import Column, Integer, String, Boolean, Enum
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional
from enum import Enum as PyEnum
from app.database import Base


class UserRole(str, PyEnum):
    """Les 4 niveaux d'accès de l'application, du plus au moins permissif.

    - admin : accès complet, y compris la gestion des utilisateurs.
    - utilisateur_mn : peut tout créer/modifier/consommer, y compris les
      sources contenant de la Matière Nucléaire (MN).
    - utilisateur : comme utilisateur_mn, mais sans aucun accès (ni lecture,
      ni écriture) aux sources marquées "matière nucléaire".
    - lecteur : consultation uniquement (aucune création/modification/
      consommation/suppression), et sans accès aux sources MN non plus.
    """
    admin = "admin"
    utilisateur_mn = "utilisateur_mn"
    utilisateur = "utilisateur"
    lecteur = "lecteur"


# Modèle SQLAlchemy
class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), default=UserRole.lecteur, nullable=False)

# Modèles Pydantic
class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: str
    # Un utilisateur qui s'inscrit lui-même démarre "lecteur" (accès le plus
    # restreint) par sécurité : c'est ensuite à un administrateur de lui
    # donner plus de droits depuis la page Utilisateurs.
    role: UserRole = UserRole.lecteur

class User(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: UserRole
    hashed_password: str

class UserPublic(UserBase):
    """Comme User, mais sans hashed_password : c'est ce schéma qu'il faut
    utiliser pour toute réponse API, afin de ne jamais exposer le hash du
    mot de passe au client."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: UserRole

class UserRoleUpdate(BaseModel):
    role: UserRole
