"""Repository pour les utilisateurs."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.user import UserDB, UserCreate, UserCreateHistorique, UserRole

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[UserDB]:
        return self.db.query(UserDB).filter(UserDB.id == user_id).first()

    def get_by_username(self, username: str) -> Optional[UserDB]:
        return self.db.query(UserDB).filter(UserDB.username == username).first()

    def get_by_username_insensible_casse(self, username: str) -> Optional[UserDB]:
        """Comme get_by_username, mais insensible à la casse -- utilisée
        spécifiquement par get_ou_creer_historique ci-dessous (31/08/2026) :
        un nom transcrit depuis une fiche papier ("GDO") doit se
        rattacher au compte réel même s'il a été enregistré autrement
        ("Gdo", "gdo"...) -- une différence de casse ne désigne jamais
        deux personnes différentes, contrairement à une orthographe
        vraiment différente (qui, elle, ne doit surtout pas être
        rapprochée automatiquement, voir la discussion sur la
        correspondance stricte). N'affecte PAS get_by_username
        elle-même : la connexion et le reste de l'application continuent
        de fonctionner exactement comme avant."""
        return self.db.query(UserDB).filter(UserDB.username.ilike(username)).first()

    def get_by_email(self, email: str) -> Optional[UserDB]:
        return self.db.query(UserDB).filter(UserDB.email == email).first()

    def get_all(self) -> List[UserDB]:
        return self.db.query(UserDB).all()

    def create(self, user: UserCreate) -> UserDB:
        from app.security.auth import get_password_hash
        db_user = UserDB(
            username=user.username,
            email=user.email,
            hashed_password=get_password_hash(user.password),
            full_name=user.full_name,
            role=user.role,
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def create_historique(self, user: UserCreateHistorique) -> UserDB:
        """Crée un enregistrement pour quelqu'un qui a réalisé une action
        tracée mais n'a et n'aura jamais de compte -- voir
        UserCreateHistorique. Toujours is_active=False, ni email ni mot
        de passe : jamais connectable. Le rôle "lecteur" est une valeur
        de repli imposée par la colonne (non nullable), jamais exercée
        puisqu'un compte is_active=False ne peut jamais se connecter."""
        db_user = UserDB(
            username=user.username,
            full_name=user.full_name,
            is_active=False,
            role=UserRole.lecteur,
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def get_ou_creer_historique(self, nom: str) -> UserDB:
        """Trouve un utilisateur existant par nom (insensible à la
        casse), ou crée un enregistrement historique s'il n'existe pas
        -- réutilisé par la migration (données déjà en base) et l'import
        de consommations historiques, pour qu'une action ne reste jamais
        sans utilisateur rattaché (demandé le 31/08/2026)."""
        existant = self.get_by_username_insensible_casse(nom)
        if existant:
            return existant
        return self.create_historique(UserCreateHistorique(username=nom))

    def delete(self, user_id: int) -> bool:
        db_user = self.get_by_id(user_id)
        if not db_user:
            return False
        self.db.delete(db_user)
        self.db.commit()
        return True

    def set_role(self, user_id: int, role) -> Optional[UserDB]:
        db_user = self.get_by_id(user_id)
        if not db_user:
            return None
        db_user.role = role
        self.db.commit()
        self.db.refresh(db_user)
        return db_user
