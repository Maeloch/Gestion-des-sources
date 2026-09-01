"""Modèle pour les utilisateurs, avec un système de rôles à 4 niveaux.

`is_active` (31/08/2026) distingue un compte réel (peut se connecter,
apparaît dans les listes de sélection pour une nouvelle action) d'un
enregistrement historique (ex: quelqu'un qui a quitté le service et dont
le nom apparaît sur une fiche papier ancienne) : ni mot de passe ni
email utilisables, jamais connectable, mais reste une fiche à part
entière avec son historique -- pour qu'aucune action passée ne se
retrouve jamais sans utilisateur rattaché (voir
services/utilisateurs_historiques.py pour le raisonnement complet)."""
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
    # nullable (31/08/2026) : un enregistrement historique (is_active=False)
    # n'a ni l'un ni l'autre -- appliqué au niveau service, pas ici, pour
    # un message d'erreur clair côté métier plutôt qu'une contrainte SQL brute.
    email = Column(String(100), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=True)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.lecteur, nullable=False)

# Modèles Pydantic
class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    is_active: bool = True

class UserCreate(UserBase):
    # Une vraie inscription (compte qui pourra se connecter) exige email
    # et mot de passe -- contrairement à UserCreateHistorique ci-dessous.
    email: EmailStr
    password: str
    # Un utilisateur qui s'inscrit lui-même démarre "lecteur" (accès le plus
    # restreint) par sécurité : c'est ensuite à un administrateur de lui
    # donner plus de droits depuis la page Utilisateurs.
    role: UserRole = UserRole.lecteur

class UserCreateHistorique(BaseModel):
    """Créer un enregistrement pour quelqu'un qui a réalisé une action
    tracée (consommation, mouvement...) mais n'a et n'aura jamais de
    compte -- ni email, ni mot de passe, ni rôle applicatif. Toujours
    is_active=False (voir UserDB) : jamais connectable, jamais proposé
    pour une nouvelle action, mais garde sa fiche et son historique."""
    username: str
    full_name: Optional[str] = None

class User(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: Optional[str] = None
    role: UserRole
    hashed_password: Optional[str] = None

class UserPublic(UserBase):
    """Comme User, mais sans hashed_password : c'est ce schéma qu'il faut
    utiliser pour toute réponse API, afin de ne jamais exposer le hash du
    mot de passe au client."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: Optional[str] = None
    role: UserRole

class UserRoleUpdate(BaseModel):
    role: UserRole
