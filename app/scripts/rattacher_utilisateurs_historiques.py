"""Rattache les consommations, mouvements et logs d'audit déjà en base
(dont le champ `utilisateur` est un simple texte, sans `utilisateur_id`)
à un véritable enregistrement utilisateur -- demandé le 31/08/2026.

Pour chaque nom rencontré : rattaché à un compte existant s'il
correspond exactement, sinon un enregistrement historique est créé
(jamais connectable -- voir `UserCreateHistorique`) pour que l'action ne
reste jamais sans utilisateur rattaché, même si cette personne ne
travaille plus avec les sources depuis longtemps.

Usage :
    python -m app.scripts.rattacher_utilisateurs_historiques

Sûr à exécuter plusieurs fois : ne traite que les lignes dont
`utilisateur_id` est encore vide, donc un deuxième passage ne fait rien
sur ce qui a déjà été rattaché.
"""
from app.database import SessionLocal
from app.models.consumption import ConsumptionDB
from app.models.movement import MovementDB
from app.models.audit import AuditLogDB
from app.repositories.user import UserRepository


TABLES = [
    ("consumptions", ConsumptionDB),
    ("movements", MovementDB),
    ("audit_logs", AuditLogDB),
]


def rattacher(db=None) -> dict:
    """Fait le rattachement proprement dit. Renvoie un rapport détaillé
    (par table : combien de lignes rattachées à un compte déjà existant,
    combien à un enregistrement historique nouvellement créé, et les
    noms concernés) -- jamais silencieux, pour que ce qui a été créé
    puisse être relu et vérifié plutôt que supposé correct."""
    ferme_a_la_fin = db is None
    db = db or SessionLocal()
    repo_utilisateurs = UserRepository(db)
    rapport = {}

    try:
        for nom_table, Modele in TABLES:
            lignes_rattachees_a_existant = 0
            noms_historiques_crees = set()
            lignes_traitees = 0

            lignes = (
                db.query(Modele)
                .filter(Modele.utilisateur_id.is_(None))
                .filter(Modele.utilisateur.isnot(None))
                .all()
            )
            for ligne in lignes:
                nom = ligne.utilisateur.strip()
                if not nom:
                    continue
                existait_deja = repo_utilisateurs.get_by_username_insensible_casse(nom) is not None
                utilisateur = repo_utilisateurs.get_ou_creer_historique(nom)
                ligne.utilisateur_id = utilisateur.id
                lignes_traitees += 1
                if existait_deja:
                    lignes_rattachees_a_existant += 1
                else:
                    noms_historiques_crees.add(nom)

            db.commit()
            rapport[nom_table] = {
                "lignes_traitees": lignes_traitees,
                "rattachees_a_un_compte_existant": lignes_rattachees_a_existant,
                "utilisateurs_historiques_crees": sorted(noms_historiques_crees),
            }
    finally:
        if ferme_a_la_fin:
            db.close()

    return rapport


def _afficher_rapport(rapport: dict) -> None:
    total_traite = sum(r["lignes_traitees"] for r in rapport.values())
    if total_traite == 0:
        print("Rien à rattacher : toutes les lignes ont déjà un utilisateur_id renseigné.")
        return

    for nom_table, r in rapport.items():
        if r["lignes_traitees"] == 0:
            continue
        print(f"\n{nom_table} : {r['lignes_traitees']} ligne(s) rattachée(s) "
              f"({r['rattachees_a_un_compte_existant']} vers un compte déjà existant).")
        if r["utilisateurs_historiques_crees"]:
            print(f"  Enregistrement(s) historique(s) créé(s) (jamais connectable, "
                  f"consultable depuis la page Utilisateurs) : "
                  f"{', '.join(r['utilisateurs_historiques_crees'])}")


if __name__ == "__main__":
    _afficher_rapport(rattacher())
