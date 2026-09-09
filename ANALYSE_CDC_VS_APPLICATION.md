# Analyse : cahier des charges vs application actuelle

Rafraîchi le 01/09/2026 — la précédente version datait du 08/07/2026 (deux
mois de travail dans l'intervalle). Chaque point ci-dessous a été revérifié
directement dans le code de la V0.1.43, pas supposé à partir de la version
précédente de ce document.

**Important, demandé explicitement le 01/09/2026 : ce document sert à
mesurer l'écart, pas à dicter ce qu'il faut corriger.** Plusieurs écarts
identifiés ici sont des choix délibérés, pas des oublis — signalés comme
tels ci-dessous plutôt que comme un "manque".

## 0. L'environnement technique cible — tranché, définitivement

**Décision prise le 07/07/2026, reconfirmée le 01/09/2026 : on reste sur
FastAPI + HTML, Flet abandonné.** Le CDC demandait Python + Flet (une
application de bureau, exécutable à double-cliquer, pensée pour un poste
"infogéré" sans terminal visible). Raison du choix, redite le 01/09 : Flet
correspondait au cahier des charges au moment où il a été écrit, mais la
solution HTML actuelle fonctionne très bien en pratique — pas de bénéfice
à reconstruire l'interface dans un outil non maîtrisé pour une équipe de 7
personnes. Ce n'est plus un sujet ouvert, à ne pas rouvrir.

---

## 1. Modèle métier : Source radioactive

| Champ du CDC | État au 01/09/2026 |
|---|---|
| id_source, type_source, etat_physique, numero_fabricant, certificat_etalonnage, date_arrivee, lien_dossier, matiere_nucleaire | ✅ (inchangé depuis juillet) |
| **fournisseur** | ✅ résolu (`app/models/source.py`) |
| **commentaire** | ✅ résolu, sur la source elle-même en plus des consommations/mouvements |
| statut (etat_utilisation) | ✅ résolu : "transférée" et "détruite" ajoutés le 04/07/2026 pour correspondre au CDC, en plus des valeurs déjà présentes |
| emplacement | ✅ résolu et dépassé : système de Lieux relié aux sources (emplacement habituel/actuel), avec cycle d'emprunt/retour complet (Mouvements) — pas prévu par le CDC, ajouté sur demande le 08/07/2026 |

## 2. Inventaire matière (quantités liquide/gaz)

| Demandé | État |
|---|---|
| Masse actuelle **et** initiale (liquide) | ✅ résolu (`quantite_initiale`) |
| Pression actuelle, initiale, **volume du récipient** (gaz) | ✅ résolu (`volume_recipient`) |

## 3. Radioéléments : relation N:N

**Écart maintenu délibérément, pas à corriger — décision du 01/09/2026.**

Le CDC voulait deux tables séparées (catalogue des radioéléments avec
période/LaraWeb, distinct de leur association à une source). L'application
garde tout dans une seule table `radionuclides` (une ligne par source, la
période recopiée à chaque fois). Techniquement toujours vrai — mais la
solution N:N est devenue inutile en pratique : le cache LaraWeb
(`lara_cache`, résolu en section 6) joue déjà le rôle de référence partagée
pour les données physiques (période, activité spécifique), sans nécessiter
de restructurer le schéma. Rien à faire ici.

## 4. Décroissance radioactive

| Demandé | État |
|---|---|
| Formule A(t)=A0×exp(-ln2×t/T½) | ✅ |
| Activité à la date de référence / activité actuelle | ✅ |
| **Activité à une date choisie** | ⚠️ partiellement résolu : `activite_actuelle_bq()` accepte un paramètre de date depuis le service (utilisé par le spectre-type, qui expose une date de référence choisie par l'utilisateur) — mais la page Radionucléides elle-même n'offre toujours pas de sélecteur de date direct, seul "aujourd'hui" y est calculé |
| **Activité totale de la source** (activité spécifique × quantité restante) | ⚠️ à vérifier avec toi : le calcul de quantité restante existe (`quantite_restante_calculee`) et l'activité par radionucléide aussi (`activites_par_radionuclide_bq`, généralisée le 30/07 pour plusieurs radionucléides), mais je ne trouve pas de fonction qui les combine explicitement en un seul nombre "activité totale actuelle" affiché comme tel — possible que ce soit déjà ce que montre une page sans que j'aie retrouvé le bon nom de fonction ; à confirmer plutôt que d'affirmer un état que je ne suis pas sûr d'avoir bien vérifié |

## 5. Consommation des sources

| Demandé | État |
|---|---|
| Enregistrement, historique, impossible d'obtenir une quantité négative | ✅ (inchangé) |
| **Utilisateur historisé directement sur la consommation** | ✅ largement dépassé (31/08/2026) : `utilisateur_id`, lien vers un véritable compte (ou un enregistrement historique si la personne n'a pas de compte), fiche utilisateur, fusion de doublons |

## 6. Intégration LaraWeb

**✅ Résolu.** `laraweb.py` fait un vrai appel HTTP au LNHB (`fetch_nuclide`),
avec cache SQLite (`lara_cache`, table dédiée — présente, contrairement à ce
que disait la version précédente de ce document) et récupération à la
demande (`get_or_fetch`). Le brouillon à 4 isotopes codés en dur mentionné
en juillet n'existe plus.

## 7. Gestion des utilisateurs

Toujours 4 rôles (admin, utilisateur MN, utilisateur, lecteur) — évolution
assumée du CDC (3 rôles prévus), non remise en cause.

**Seuil d'activité configurable (rôle `user_limited` du CDC) : écart
maintenu délibérément — décision du 01/09/2026, avec une raison
réglementaire précise.** Le CDC voulait restreindre l'accès aux activités
au-delà d'un seuil configurable. Non implémenté, et volontairement laissé
ainsi : la réglementation impose, a priori, davantage de secret sur
l'**emplacement** d'une source que sur son **niveau d'activité** — cloisonner
par seuil d'activité ne répondrait donc pas au bon besoin de confidentialité.
Trace conservée ici pour mémoire, au cas où cette analyse évoluerait.

**Gestion admin renforcée des comptes** : demandée le 01/09/2026 (changer le
mot de passe d'un utilisateur, révoquer son accès) — voir
`RAPPORT_DIAGNOSTIC_ET_CORRECTIONS.md` pour l'état de sa réalisation.

## 8. Journalisation / audit

| Demandé | État |
|---|---|
| date, utilisateur, action, table, valeur avant/après | ✅ |
| Aucune suppression physique | ✅ de fait (toujours aucune route de suppression) |
| Consultable depuis l'interface | ✅ |
| **Adresse IP** | ❌ toujours absent du journal d'audit |
| **Extraction sur une période donnée** | ❌ toujours limité à un nombre d'entrées (`limit`), pas de filtre par plage de dates |

## 9. Interface utilisateur

| Demandé | État |
|---|---|
| Tableau filtrable, recherche rapide, tri, pagination | ✅ résolu (`rendreFiltrable`/`rendreTableTriable`/`rendrePaginable`, présents sur toutes les listes) |
| Source : création / modification / **visualisation détaillée** | ✅ résolu : fiche par source (radionucléides, mouvements, consommations, audit réunis) |
| Consommation : saisie, historique | ✅ |
| Radioéléments : activités calculées, infos LaraWeb | ✅ (LaraWeb réel, voir section 6) |
| Audit : consultation | ✅ |
| **Export CSV / JSON** | ❌ toujours absent — Excel existe et est maintenant accessible depuis l'interface (pas seulement en ligne de commande comme en juillet), mais CSV/JSON n'existent pas |

## 10. Schéma de base de données

CDC : `sources`, `radionuclides`, `source_radionuclides`, `users`, `roles`,
`consumptions`, `audit_log`, `lara_cache`.

Existant au 01/09/2026 : `sources`, `radionuclides` (toujours conflaté avec
`source_radionuclides`, voir section 3 — assumé, pas à corriger),
`users` (rôle toujours en colonne, pas une table séparée — toujours
raisonnable pour 4 rôles fixes), `consumptions`, `audit_logs`, `lara_cache`
(✅ présent, résolu), plus `locations` et `movements` (hors CDC, ajoutés sur
demande).

## 11. Sécurité

| Demandé | État |
|---|---|
| Authentification, gestion des rôles | ✅ |
| Validation des saisies | ⚠️ basique (inchangé depuis juillet) |
| Prévention des suppressions accidentelles | ✅ résolu et étendu : sources, consommations avec historique, et désormais utilisateurs portant de l'historique, tous protégés contre la suppression directe |
| **Sauvegarde automatique de la base** | ✅ résolu partiellement : une sauvegarde horodatée est faite avant chaque mise à jour (`appliquer_version.py`) |
| **Restauration** | ❌ toujours absente : les sauvegardes existent sur disque, mais aucune procédure ni interface ne les restaure |

## 12. Livrables du CDC

| Demandé | État |
|---|---|
| Architecture détaillée | ⚠️ inchangé : documentée au fil des rapports, pas comme document autonome |
| Schéma SQL documenté | ⚠️ inchangé : dans le code (modèles SQLAlchemy), pas comme document dédié |
| Diagramme relationnel | ❌ toujours pas produit |
| Structure IHM Flet | — sans objet, Flet abandonné (section 0) |
| Code des fonctions Python | ✅ |
| Stratégie de sauvegarde | ⚠️ existe en pratique (voir section 11) mais pas documentée comme stratégie à part |
| Stratégie de tests | ✅ résolu de fait : 260 tests automatisés couvrent largement l'application (relancés avant chaque livraison), même si aucun document ne décrit cette stratégie en tant que telle |
| Plan de déploiement | ⚠️ inchangé : le README couvre le lancement, pas un plan de déploiement formel pour poste infogéré |
| Propositions d'évolutions futures | ✅ (sections "feuille de route" des rapports) |

---

## Écarts maintenus délibérément (pas des oublis, ne pas les "corriger")

- **Relation N:N radioéléments/sources** (section 3) : devenue inutile en
  pratique, le cache LaraWeb remplit ce rôle.
- **Seuil d'activité configurable** (section 7) : la confidentialité
  réglementaire porte davantage sur l'emplacement que sur l'activité — cette
  restriction ne répondrait pas au bon besoin. Trace conservée si l'analyse
  évolue.
- **Flet** (section 0) : tranché, l'existant fonctionne bien pour une équipe
  de 7 personnes.

## Toujours ouverts (constatés, pas nécessairement à traiter)

Adresse IP et filtrage par période sur l'audit (section 8), export
CSV/JSON (section 9), restauration de sauvegarde (section 11), sélecteur de
date libre pour l'activité et confirmation de l'activité totale de la
source (section 4), livrables formels séparés — diagramme relationnel, plan
de déploiement (section 12).

## Ce qui ne doit toujours pas être fait

- Pas de dépendance à un service cloud/SaaS commercial (LaraWeb reste un
  site public de référence scientifique, pas un service commercial — cohérent
  avec le CDC).
- Pas de fonctionnalité de suppression pour le journal d'audit, même
  réservée aux admins.
