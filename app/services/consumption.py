"""Service pour la gestion des consommations."""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.source import SourceDB, EtatPhysique, is_archived
from app.models.consumption import ConsumptionDB, ConsumptionCreate
from app.models.audit import AuditLogCreate
from app.repositories.source import SourceRepository
from app.repositories.consumption import ConsumptionRepository
from app.repositories.audit import AuditRepository
from app.services.units import quantite_restante_calculee

# Types physiques pour lesquels une "consommation" (dépense progressive
# d'une quantité) a un sens : masse pour un liquide, pression pour un gaz.
# Une source scellée/solide se suit par décroissance radioactive (voir
# DecayService), pas par consommation de quantité.
TYPES_CONSOMMABLES = (EtatPhysique.gaz, EtatPhysique.liquide)

# Écart entre la masse "avant" annoncée et la dernière pesée totale
# connue, en deçà duquel on ne le signale pas (variance de pesée normale
# -- au-delà, probable évaporation à noter). Volontairement généreux :
# mieux vaut rater un petit écart que harceler l'utilisateur pour du
# bruit de mesure.
SEUIL_ECART_SIGNALE = 0.01  # 1% de la dernière pesée


class ConsumptionService:
    def __init__(
        self,
        source_repo: SourceRepository,
        consumption_repo: ConsumptionRepository,
        audit_repo: AuditRepository,
        db: Session = None,
    ):
        self.source_repo = source_repo
        self.consumption_repo = consumption_repo
        self.audit_repo = audit_repo
        self.db = db or source_repo.db

    def use_source(
        self,
        source_id: str,
        utilisateur: str,
        quantite_utilisee: float = None,
        masse_avant: float = None,
        masse_apres: float = None,
        commentaire: str = None,
    ) -> ConsumptionDB:
        """Utilise une source de type gaz ou liquide -- ou enregistre une
        simple pesée de contrôle, sans prélèvement. Deux façons
        d'enregistrer la quantité consommée :

        1. `quantite_utilisee` directement (mode simple -- typiquement
           pour le gaz, où "peser" n'a pas de sens).
        2. `masse_avant` + `masse_apres` (pesée -- typiquement pour le
           liquide : on pèse le récipient plein avant tout prélèvement
           éventuel, puis à nouveau après). `quantite_utilisee` est alors
           dérivée comme `masse_avant - masse_apres`. Si les deux valeurs
           sont ÉGALES, c'est une pesée de contrôle sans prélèvement --
           utile par exemple pour la toute première pesée après réception
           (fiole + liquide + bouchon + étiquette, tout, sans rien
           prélever) : elle établit une référence utilisable pour les
           calculs futurs (voir quantite_restante_calculee, qui en déduit
           la masse du récipient seul). `masse_apres` devient dans tous
           les cas la nouvelle quantité totale de référence -- ce qui
           absorbe naturellement l'évaporation du solvant au fil du temps
           (la pesée réelle fait foi, pas un décompte accumulé). Si
           `masse_avant` diffère sensiblement de la dernière pesée totale
           connue, l'écart est noté automatiquement dans le commentaire
           (probable évaporation depuis la dernière pesée), sans bloquer
           l'enregistrement : c'est un phénomène normal, pas une erreur.

        Lève une ValueError avec un message explicite si l'opération est
        impossible ; renvoie l'enregistrement de consommation créé sinon.
        """
        db_source = self.source_repo.get_by_id(source_id)
        if not db_source:
            raise ValueError(f"Aucune source avec l'identifiant '{source_id}'.")

        if is_archived(db_source):
            raise ValueError(
                f"La source '{source_id}' est archivée (statut : {db_source.etat_utilisation.value}) : "
                "impossible d'y enregistrer une nouvelle consommation."
            )

        if db_source.etat_physique not in TYPES_CONSOMMABLES:
            raise ValueError(
                f"La source '{source_id}' est de type '{db_source.etat_physique.value}' : "
                "seules les sources gaz (pression) ou liquide (masse) peuvent être "
                "consommées. Une source scellée/solide se suit par décroissance radioactive."
            )

        # Seule masse_avant fournie (ni masse_apres, ni quantite_utilisee) :
        # pesée de contrôle implicite, rien de prélevé. Ce repli doit
        # exister ici (pas seulement côté frontend) pour rester cohérent
        # quel que soit l'appelant -- trouvé le 13/07/2026 en vérifiant le
        # comportement de l'API directement, indépendamment du formulaire.
        if masse_avant is not None and masse_apres is None and quantite_utilisee is None:
            masse_apres = masse_avant

        pesee_double = masse_avant is not None and masse_apres is not None
        if not pesee_double and quantite_utilisee is None:
            raise ValueError(
                "Renseigne soit la quantité consommée directement, soit une pesée "
                "(avant, et éventuellement après un prélèvement)."
            )
        # < et non <= : une pesée de CONTRÔLE (rien prélevé) a
        # légitimement masse_avant == masse_apres -- seul masse_apres >
        # masse_avant est physiquement impossible (on ne peut pas avoir
        # PLUS de matière après un prélèvement, même nul).
        if pesee_double and masse_avant < masse_apres:
            raise ValueError(
                f"La masse après ({masse_apres}) ne peut pas dépasser la masse avant "
                f"({masse_avant}) : un prélèvement ne peut pas ajouter de matière."
            )

        unite = db_source.unite_quantite.value if db_source.unite_quantite else ""
        quantite_attendue = quantite_restante_calculee(self.db, db_source)

        commentaire_final = commentaire
        derniere_pesee_totale = None
        consommations_existantes = sorted(
            (db_source.consumptions or []), key=lambda c: c.timestamp or datetime.min
        )
        pesees_existantes = [c for c in consommations_existantes if c.masse_apres is not None]
        if pesees_existantes:
            derniere_pesee_totale = pesees_existantes[-1].masse_apres

        if pesee_double:
            quantite_utilisee = masse_avant - masse_apres
            # L'écart se compare à la dernière pesée TOTALE connue (même
            # grandeur que masse_avant : récipient + liquide), pas à la
            # quantité restante calculée -- qui, une fois la masse du
            # récipient déduite (voir quantite_restante_calculee), est en
            # masse de LIQUIDE SEUL, une grandeur différente et non
            # directement comparable. Bug trouvé le 13/07/2026 en
            # implémentant cette correction.
            if derniere_pesee_totale is not None and derniere_pesee_totale > 0:
                ecart = masse_avant - derniere_pesee_totale
                if abs(ecart) > SEUIL_ECART_SIGNALE * derniere_pesee_totale:
                    note_ecart = (
                        f"[Écart de {ecart:+.3g} {unite} par rapport à la dernière pesée "
                        f"({derniere_pesee_totale:.3g} {unite}) — probable évaporation ou "
                        "écart de pesée depuis la dernière mesure.]"
                    )
                    commentaire_final = f"{commentaire_final} {note_ecart}" if commentaire_final else note_ecart
        else:
            if quantite_attendue is None:
                raise ValueError(
                    f"La source '{source_id}' n'a pas de quantité connue (ni pesée précédente, "
                    "ni quantité initiale renseignée) : impossible de vérifier ce qu'il en reste."
                )
            if quantite_attendue < quantite_utilisee:
                raise ValueError(
                    f"Quantité insuffisante : il ne reste que {quantite_attendue:.3g} {unite} "
                    f"sur la source '{source_id}', tu as demandé {quantite_utilisee} {unite}."
                )

        # Repli de compatibilité (sources importées avant le système de
        # quantité calculée, sans quantite_initiale ni pesée déjà
        # enregistrée) : la valeur stockée doit être décrémentée
        # directement, car quantite_restante_calculee() s'appuie dessus
        # telle quelle dans ce cas précis (voir sa docstring).
        utilise_repli_legacy = (
            db_source.quantite_initiale is None
            and not pesees_existantes
            and db_source.quantite is not None
        )
        valeur_avant = quantite_attendue if quantite_attendue is not None else db_source.quantite
        if utilise_repli_legacy:
            db_source.quantite -= quantite_utilisee
            self.source_repo.db.commit()

        consumption = ConsumptionCreate(
            source_id=source_id,
            quantite_utilisee=quantite_utilisee,
            masse_avant=masse_avant,
            masse_apres=masse_apres,
            commentaire=commentaire_final,
        )
        db_consumption = self.consumption_repo.create(consumption)
        db_consumption.utilisateur = utilisateur
        # Correspondance automatique vers un compte réel (31/08/2026) :
        # utilisateur correspond toujours à current_user.username pour une
        # action en direct, donc cette correspondance réussit
        # systématiquement ici -- voir audit.py pour le même principe.
        from app.repositories.user import UserRepository
        correspondant = UserRepository(self.db).get_by_username(utilisateur) if utilisateur else None
        if correspondant:
            db_consumption.utilisateur_id = correspondant.id
        self.consumption_repo.db.commit()
        self.consumption_repo.db.refresh(db_consumption)

        # La quantité restante "après" doit refléter la même logique que
        # quantite_restante_calculee() (déduction de la masse du
        # récipient le cas échéant) -- recalculée ici après coup, plutôt
        # que ré-implémentée à la main, pour ne jamais diverger.
        db_source_rafraichi = self.source_repo.get_by_id(source_id)
        valeur_apres = quantite_restante_calculee(self.db, db_source_rafraichi)

        self.audit_repo.create(AuditLogCreate(
            utilisateur=utilisateur,
            action="UTILISATION" if quantite_utilisee else "PESEE",
            table_modifiee="sources",
            id_source=source_id,
            champ_modifie="quantite",
            valeur_avant=str(round(valeur_avant, 3)) if valeur_avant is not None else None,
            valeur_apres=str(round(valeur_apres, 3)) if valeur_apres is not None else None,
        ))

        return db_consumption
