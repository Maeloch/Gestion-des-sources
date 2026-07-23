"""Routes pour les utilisateurs : gestion des rôles (admin), changement de
mot de passe et demandes de changement de rôle (tout utilisateur)."""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models.user import User, UserDB, UserPublic, UserRoleUpdate
from app.models.role_request import (
    RoleRequestDB, RoleRequestCreate, RoleRequestTraitement, RoleRequest, StatutDemande,
)
from app.models.audit import AuditLogCreate
from app.repositories.user import UserRepository
from app.repositories.audit import AuditRepository
from app.security.auth import get_password_hash, verify_password
from app.security.permissions import get_current_admin, get_current_user
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])


class PasswordChange(BaseModel):
    mot_de_passe_actuel: str
    nouveau_mot_de_passe: str


@router.get("/", response_model=List[UserPublic])
async def list_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    repo = UserRepository(db)
    return repo.get_all()

@router.patch("/{user_id}/role", response_model=UserPublic)
async def set_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tu ne peux pas modifier ton propre rôle (demande à un autre administrateur).",
        )
    repo = UserRepository(db)
    updated_user = repo.set_role(user_id, payload.role)
    if not updated_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return updated_user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tu ne peux pas supprimer ton propre compte depuis cette page.",
        )
    repo = UserRepository(db)
    if not repo.delete(user_id):
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def changer_mon_mot_de_passe(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Un utilisateur change son propre mot de passe (nécessite de
    connaître l'ancien) — demandé le 11/07/2026."""
    if not verify_password(payload.mot_de_passe_actuel, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect.")
    if len(payload.nouveau_mot_de_passe) < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit faire au moins 8 caractères.")

    db_user = db.query(UserDB).filter(UserDB.id == current_user.id).first()
    db_user.hashed_password = get_password_hash(payload.nouveau_mot_de_passe)
    db.commit()

    AuditRepository(db).create(AuditLogCreate(
        utilisateur=current_user.username,
        action="UPDATE",
        table_modifiee="users",
        id_source=None,
        champ_modifie="mot_de_passe",
        valeur_avant="(changé par l'utilisateur)",
        valeur_apres="(changé par l'utilisateur)",
    ))
    return


@router.post("/me/demande-role", response_model=RoleRequest)
async def demander_changement_role(
    payload: RoleRequestCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Un utilisateur demande un changement de rôle ; un administrateur
    devra ensuite l'approuver ou la rejeter (voir GET/PATCH /users/demandes-role) —
    demandé le 11/07/2026."""
    if payload.role_demande == current_user.role:
        raise HTTPException(status_code=400, detail=f"Tu as déjà le rôle '{current_user.role.value}'.")

    existe_deja = db.query(RoleRequestDB).filter(
        RoleRequestDB.username == current_user.username,
        RoleRequestDB.statut == StatutDemande.en_attente,
    ).first()
    if existe_deja:
        raise HTTPException(
            status_code=400,
            detail="Tu as déjà une demande en attente. Attends qu'un administrateur la traite avant d'en soumettre une nouvelle.",
        )

    demande = RoleRequestDB(
        username=current_user.username,
        role_demande=payload.role_demande,
        commentaire=payload.commentaire,
    )
    db.add(demande)
    db.commit()
    db.refresh(demande)
    return demande


@router.get("/me/demande-role", response_model=List[RoleRequest])
async def mes_demandes_role(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """L'historique de mes propres demandes de changement de rôle."""
    return (
        db.query(RoleRequestDB)
        .filter(RoleRequestDB.username == current_user.username)
        .order_by(RoleRequestDB.date_demande.desc())
        .all()
    )


@router.get("/demandes-role", response_model=List[RoleRequest])
async def lister_demandes_role(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    """Toutes les demandes de changement de rôle, les plus récentes
    d'abord (réservé aux administrateurs)."""
    return db.query(RoleRequestDB).order_by(RoleRequestDB.date_demande.desc()).all()


@router.patch("/demandes-role/{demande_id}", response_model=RoleRequest)
async def traiter_demande_role(
    demande_id: int,
    payload: RoleRequestTraitement,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    """Approuve ou rejette une demande de changement de rôle. En cas
    d'approbation, le rôle est appliqué immédiatement (réutilise la même
    logique que la page Utilisateurs)."""
    demande = db.query(RoleRequestDB).filter(RoleRequestDB.id == demande_id).first()
    if not demande:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    if demande.statut != StatutDemande.en_attente:
        raise HTTPException(status_code=400, detail="Cette demande a déjà été traitée.")
    if payload.action not in ("approuver", "rejeter"):
        raise HTTPException(status_code=400, detail="Action invalide : 'approuver' ou 'rejeter' attendu.")

    from datetime import datetime
    demande.traite_par = current_user.username
    demande.date_traitement = datetime.utcnow()

    if payload.action == "approuver":
        demande.statut = StatutDemande.approuvee
        repo = UserRepository(db)
        utilisateur_cible = db.query(UserDB).filter(UserDB.username == demande.username).first()
        if not utilisateur_cible:
            raise HTTPException(status_code=404, detail=f"L'utilisateur '{demande.username}' n'existe plus.")
        repo.set_role(utilisateur_cible.id, demande.role_demande)
        AuditRepository(db).create(AuditLogCreate(
            utilisateur=current_user.username,
            action="UPDATE",
            table_modifiee="users",
            id_source=None,
            champ_modifie="role",
            valeur_avant=None,
            valeur_apres=f"{demande.username} -> {demande.role_demande.value} (demande approuvée)",
        ))
    else:
        demande.statut = StatutDemande.rejetee

    db.commit()
    db.refresh(demande)
    return demande
