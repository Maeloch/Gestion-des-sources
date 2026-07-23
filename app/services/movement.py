"""Service pour la gestion des emprunts (mouvements) de sources."""
from datetime import date as date_type, datetime
from sqlalchemy.orm import Session
from app.models.movement import MovementDB
from app.models.audit import AuditLogCreate
from app.models.source import is_archived
from app.repositories.source import SourceRepository
from app.repositories.location import LocationRepository
from app.repositories.movement import MovementRepository
from app.repositories.audit import AuditRepository


class MovementService:
    def __init__(
        self,
        source_repo: SourceRepository,
        location_repo: LocationRepository,
        movement_repo: MovementRepository,
        audit_repo: AuditRepository,
    ):
        self.source_repo = source_repo
        self.location_repo = location_repo
        self.movement_repo = movement_repo
        self.audit_repo = audit_repo

    def demarrer_emprunt(
        self,
        source_id: str,
        to_location_id: int,
        utilisateur: str,
        date_retour_prevue: date_type = None,
        commentaire: str = None,
    ) -> MovementDB:
        """Enregistre la sortie d'une source vers un lieu. Le lieu de départ
        est déduit automatiquement du lieu actuel de la source (pas besoin
        de le fournir). Lève une ValueError avec un message explicite si
        l'opération est impossible."""
        db_source = self.source_repo.get_by_id(source_id)
        if not db_source:
            raise ValueError(f"Aucune source avec l'identifiant '{source_id}'.")

        if is_archived(db_source):
            raise ValueError(
                f"La source '{source_id}' est archivée (statut : {db_source.etat_utilisation.value}) : "
                "impossible de démarrer un emprunt."
            )

        if not db_source.emplacement_habituel_id:
            raise ValueError(
                f"La source '{source_id}' n'a pas de lieu habituel défini. "
                "Renseigne-le d'abord depuis sa fiche (pop-up de modification) "
                "avant d'enregistrer un emprunt."
            )

        if self.movement_repo.get_open_movement_for_source(source_id):
            raise ValueError(
                f"La source '{source_id}' est déjà sortie (un emprunt est en cours). "
                "Marque d'abord son retour avant d'en enregistrer un nouveau."
            )

        to_location = self.location_repo.get_by_id(to_location_id)
        if not to_location:
            raise ValueError(f"Aucun lieu avec l'identifiant {to_location_id}.")

        # Un emprunt part toujours du lieu habituel de la source (pas de
        # son lieu "actuel", qui n'a de sens que pendant un emprunt en cours).
        from_location_id = db_source.emplacement_habituel_id

        db_movement = MovementDB(
            source_id=source_id,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            date_retour_prevue=date_retour_prevue,
            commentaire=commentaire,
            utilisateur=utilisateur,
            timestamp=datetime.utcnow(),
        )
        self.movement_repo.create(db_movement)

        db_source.emplacement_actuel_id = to_location_id
        self.source_repo.db.commit()

        self.audit_repo.create(AuditLogCreate(
            utilisateur=utilisateur,
            action="EMPRUNT",
            table_modifiee="movements",
            id_source=source_id,
            champ_modifie="emplacement_actuel_id",
            valeur_avant=str(from_location_id) if from_location_id else "aucun",
            valeur_apres=str(to_location_id),
        ))

        return db_movement

    def retourner_emprunt(
        self,
        movement_id: int,
        utilisateur: str,
        date_retour_reelle: date_type = None,
        commentaire: str = None,
    ) -> MovementDB:
        """Clôture un emprunt en cours : marque la source comme revenue à
        son lieu de départ. Lève une ValueError si l'emprunt n'existe pas
        ou est déjà clôturé."""
        db_movement = self.movement_repo.get_by_id(movement_id)
        if not db_movement:
            raise ValueError(f"Aucun mouvement avec l'identifiant {movement_id}.")

        if db_movement.date_retour_reelle is not None:
            raise ValueError("Cet emprunt a déjà été marqué comme retourné.")

        db_movement.date_retour_reelle = date_retour_reelle or date_type.today()
        if commentaire:
            db_movement.commentaire = (
                f"{db_movement.commentaire} | Retour : {commentaire}"
                if db_movement.commentaire else f"Retour : {commentaire}"
            )

        db_source = self.source_repo.get_by_id(db_movement.source_id)
        if db_source:
            db_source.emplacement_actuel_id = db_movement.from_location_id

        self.movement_repo.db.commit()
        self.movement_repo.db.refresh(db_movement)

        self.audit_repo.create(AuditLogCreate(
            utilisateur=utilisateur,
            action="RETOUR",
            table_modifiee="movements",
            id_source=db_movement.source_id,
            champ_modifie="emplacement_actuel_id",
            valeur_avant=str(db_movement.to_location_id),
            valeur_apres=str(db_movement.from_location_id) if db_movement.from_location_id else "aucun",
        ))

        return db_movement
