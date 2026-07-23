"""Promeut un compte existant au rôle administrateur — utile pour obtenir
ton tout premier compte admin (aucune autre façon de le faire : il faut
bien qu'un premier admin existe pour pouvoir en promouvoir d'autres depuis
l'interface).

    python -m app.scripts.promote_admin ton_nom_utilisateur

Le compte doit déjà exister (inscris-toi d'abord depuis /auth/register si
ce n'est pas encore fait).
"""
import argparse
from app.database import SessionLocal
from app.models.user import UserDB, UserRole


def promote(username: str) -> bool:
    db = SessionLocal()
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if not user:
            print(f"Aucun utilisateur nommé '{username}'. Inscris-toi d'abord depuis /auth/register.")
            return False
        if user.role == UserRole.admin:
            print(f"'{username}' est déjà administrateur.")
            return True
        ancien_role = user.role.value
        user.role = UserRole.admin
        db.commit()
        print(f"'{username}' est maintenant administrateur (rôle précédent : {ancien_role}).")
        return True
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Promouvoir un compte existant au rôle administrateur.")
    parser.add_argument("username", type=str, help="Nom d'utilisateur du compte à promouvoir")
    args = parser.parse_args()
    promote(args.username)


if __name__ == "__main__":
    main()
