"""Repository pour les utilisateurs."""
from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.user import UserDB, UserCreate

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[UserDB]:
        return self.db.query(UserDB).filter(UserDB.id == user_id).first()

    def get_by_username(self, username: str) -> Optional[UserDB]:
        return self.db.query(UserDB).filter(UserDB.username == username).first()

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
