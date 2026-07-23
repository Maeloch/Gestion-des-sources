# Analyse : cahier des charges vs application actuelle

Comparaison faite en relisant le CDC section par section et en vérifiant
chaque point directement dans le code (pas de suppositions). Le lien vers le
prototype C n'a techniquement pas pu être récupéré de mon côté (restriction
sur les URLs que je peux consulter) — colle-moi son contenu si tu veux que
je vérifie des détails métier précis qui y figureraient.

## 0. Le point le plus important : l'environnement technique cible

**Décision prise le 07/07/2026 : on reste sur FastAPI + HTML, pas de
bascule vers Flet.** Raisons données : l'existant est rapide et
fonctionnel, et il n'y a pas de bénéfice à se lancer dans un outil non
maîtrisé pour une équipe de 7 personnes. Cette section reste ci-dessous
pour mémoire (elle explique le contexte de ce choix), mais n'est plus un
sujet ouvert.

Le CDC est explicite :

> Python, **Flet**, SQLite, PC infogéré, fonctionnement autonome

**L'application actuelle n'est pas construite avec Flet.** C'est une
application web classique : FastAPI (serveur) + pages HTML (Jinja2) +
SQLAlchemy + SQLite. Ça fonctionne, c'est une architecture saine et
répandue — mais ce n'est pas ce que demandait le CDC, et ça change des
choses concrètes pour ton contexte :

| | Application actuelle (FastAPI + HTML) | Flet (demandé par le CDC) |
|---|---|---|
| Lancement | Ouvrir un terminal, activer un environnement virtuel, taper une commande, puis ouvrir un navigateur à une adresse | Double-clic sur un exécutable (`.exe` sous Windows) |
| Adapté à un "PC infogéré" | Fonctionne, mais suppose Python installé et accessible, et à l'aise avec un terminal | Conçu pour ça : un seul fichier à distribuer, sans installation Python visible pour l'utilisateur final |
| Multi-postes | Peut être ouvert depuis plusieurs postes du réseau si le serveur tourne quelque part (mais ce n'est pas configuré comme ça actuellement : SQLite + un seul process) | Plutôt pensé mono-poste (sauf à utiliser le mode "app web" de Flet, qui revient alors à la même logique que maintenant) |
| Ce qui existe déjà | Tout ce qu'on a construit ensemble depuis le début de cette conversation | Rien : il faudrait reconstruire l'interface (pas la base de données ni la logique métier, qui sont réutilisables) |

Je le signale maintenant, avant d'aller plus loin, parce que c'est le genre
de décision qui vaut mieux être prise consciemmentqu'en continuant
à empiler des fonctionnalités sur une base qui ne correspond pas à ce que
tu avais initialement demandé. Trois options s'offrent à toi, honnêtement :

1. **Continuer avec FastAPI + HTML** (l'existant). Le plus rapide, rien à
   jeter. Fonctionne très bien tant que l'app tourne sur un poste avec
   Python installé et qu'on t'apprend deux commandes à lancer (ce qu'on a
   déjà commencé à faire). Ce n'est pas ce que demandait le CDC, mais rien
   n'empêche de considérer que le besoin réel a évolué depuis que ce CDC a
   été écrit.
2. **Réécrire l'interface en Flet**, en gardant les modèles de données, la
   logique métier (décroissance, consommation, permissions) et la base
   SQLite tels quels — seule la couche présentation (actuellement
   `templates/` + `routes/`) serait à refaire. C'est un chantier réel, pas
   un simple portage.
3. **Un entre-deux** : garder FastAPI mais l'empaqueter pour qu'il se lance
   plus simplement (icône à double-cliquer qui démarre le serveur et ouvre
   le navigateur automatiquement), sans migrer vers Flet.

Je ne peux pas trancher ça à ta place — c'est une vraie question de priorités
et de contraintes de déploiement chez toi. Mon avis technique est en bas de
ce document.

---

## 1. Modèle métier : Source radioactive

| Champ du CDC | Existe dans l'appli ? |
|---|---|
| id_source | ✅ (`id`) |
| type_source (scellée/non-scellée) | ✅ (`type`) |
| etat_physique (solide/liquide/gaz) | ✅ |
| **fournisseur** | ❌ absent (seul `num_source_fabricant`, le numéro, existe — pas le nom du fournisseur/fabricant) |
| numero_fabricant | ✅ (`num_source_fabricant`) |
| certificat_etalonnage | ✅ (`num_certificat_etalonnage`) |
| date_arrivee | ✅ |
| emplacement | ✅ (`lieu_stockage`, en texte libre pour l'instant — un vrai système de Lieux existe en base mais n'est pas encore relié aux sources, voir section 6) |
| statut | ⚠️ existe (`etat_utilisation`) mais **valeurs différentes** : l'appli propose *en utilisation / remisée / en déchet / en attente* ; le CDC voulait *en utilisation / stockée / déchet / **transférée** / **détruite***. "Transférée" et "détruite" n'existent pas actuellement. |
| lien_dossier | ✅ (`lien_dossier_admin`) |
| matiere_nucleaire | ✅ — et c'est même devenu la base du cloisonnement d'accès par rôle |
| **commentaire** | ❌ absent sur la source elle-même (existe seulement sur consommations et mouvements) |

## 2. Inventaire matière (quantités liquide/gaz)

Le CDC veut, pour chaque source consommable :

- **Liquide** : masse actuelle **et** masse initiale
- **Gaz** : pression actuelle, pression initiale, **et volume du récipient**

**❌ Écart réel.** L'appli actuelle ne stocke qu'une seule quantité
(`quantite`, qui diminue à chaque consommation) : la valeur *initiale* n'est
gardée nulle part une fois qu'on commence à consommer, et le *volume du
récipient* (pour les gaz) n'existe pas du tout comme champ. Aujourd'hui, il
est donc impossible d'afficher "il reste 40% de la quantité initiale" ou de
calculer une pression à partir d'un volume connu. Ce sont des champs à
ajouter.

## 3. Radioéléments : relation N:N

C'est l'écart de structure le plus important après la question Flet.

Le CDC décrit clairement **deux notions séparées** :
- le radioélément en tant que tel (ex. Co-60), avec sa **période** (propriété
  physique universelle) et ses données LaraWeb — indépendant de toute source ;
- l'association entre une source donnée et un radioélément donné, avec une
  **activité de référence propre à cette source** — une relation N:N (une
  source peut avoir plusieurs radioéléments, un même radioélément peut être
  présent dans plusieurs sources).

Le CDC liste d'ailleurs explicitement une table `source_radionuclides`
séparée de `radionuclides`.

**⚠️ L'application actuelle conflate les deux dans une seule table.** La
table `radionuclides` mélange à la fois les infos "type de radioélément"
(nom, période) et les infos "association à une source" (activité,
date de référence) dans une seule ligne par source. Concrètement, si Co-60
est présent dans 10 sources différentes, sa période (5,27 ans, une
constante physique) est recopiée 10 fois — avec un risque réel qu'une
saisie diffère d'une ligne à l'autre par erreur.

C'est fonctionnel tel quel (j'ai testé), mais ce n'est pas la structure que
demandait le CDC, et une vraie table de catalogue des radioéléments (avec
import LaraWeb, voir section 4) demanderait cette séparation. À
restructurer si on veut suivre le CDC à la lettre.

## 4. Décroissance radioactive

| Demandé | État |
|---|---|
| Formule A(t)=A0×exp(-ln2×t/T½) | ✅ implémentée telle quelle, vérifiée |
| Activité à la date de référence | ✅ (c'est la valeur stockée) |
| Activité actuelle | ✅ affichée, calculée à la volée (jamais stockée, conforme au CDC) |
| **Activité à une date choisie** | ❌ pas d'interface pour choisir une date arbitraire ; seule "aujourd'hui" est calculé |
| **Activité totale de la source** (= activité spécifique × quantité restante, pour liquide/gaz) | ❌ pas calculée du tout actuellement |

## 5. Consommation des sources

| Demandé | État |
|---|---|
| Enregistrer une utilisation (liquide/gaz) | ✅ |
| Diminution de la quantité disponible | ✅ |
| Historique conservé | ✅ |
| Impossible d'obtenir une quantité négative | ✅ (vérifié, message d'erreur clair si quantité insuffisante) |
| Recalcul automatique des activités | ⚠️ partiel : la décroissance temporelle est recalculée, mais pas "l'activité totale" liée à la quantité restante (dépend de l'écart n°4) |
| Historiser utilisateur, date, quantité, commentaire | ⚠️ date/quantité/commentaire ✅ ; **l'utilisateur n'est pas stocké directement sur la consommation elle-même** (seulement indirectement, via une entrée séparée dans le journal d'audit) |

## 6. Intégration LaraWeb

**❌ Pas implémentée.** Ce qui existe (`LaraWebService`) est un brouillon
avec 4 isotopes codés en dur en guise d'exemple ; il n'y a ni appel réel au
site du LNHB, ni parsing de fichier `.lara`, ni cache SQLite (`lara_cache`,
demandé par le CDC, n'existe pas), ni gestion des radionucléides inconnus.
C'est un chantier complet à faire, pas juste un ajustement.

## 7. Gestion des utilisateurs

Le CDC demandait 3 rôles ; sur ta demande, on est passés à 4 (admin,
utilisateur MN, utilisateur, lecteur) — c'est une évolution assumée du CDC,
pas un oubli, donc rien à corriger ici. En revanche :

**❌ Un point du CDC n'est couvert par aucun des 4 rôles actuels** : le
rôle `user_limited` du CDC voulait *"aucun accès aux activités supérieures
à un seuil d'activité configurable"* — une restriction basée sur le **niveau
d'activité** (en Bq), configurable, en plus du cloisonnement Matière
Nucléaire déjà en place. Ce seuil configurable n'existe pas du tout
actuellement : le cloisonnement actuel est uniquement binaire (MN oui/non),
pas basé sur un seuil numérique.

## 8. Journalisation / audit

| Demandé | État |
|---|---|
| date, utilisateur, action, table, valeur avant/après | ✅ |
| **Adresse IP** | ❌ champ absent du journal d'audit |
| Aucune suppression physique | ✅ de fait (aucune route ne permet de supprimer une entrée), mais ce n'est pas une contrainte activement imposée en base (rien n'empêche techniquement qu'on l'oublie si une route de suppression était ajoutée un jour par erreur) |
| **Extraction sur une période donnée** | ❌ le journal ne se filtre que par nombre d'entrées (`limit`), pas par plage de dates |
| Consultable depuis l'interface | ✅ |

## 9. Interface utilisateur

| Demandé | État |
|---|---|
| Tableau filtrable, recherche rapide, tri, pagination | ❌ les tableaux (sources, radionucléides...) affichent tout sans filtre ni recherche ni pagination — correct pour quelques dizaines de lignes, ça deviendra pénible au-delà |
| Source : création / modification / **visualisation détaillée** | Création et modification ✅ (pop-up ajoutées dans notre dernier échange) ; **visualisation détaillée** (une fiche par source regroupant ses radionucléides, mouvements, consommations) ❌ n'existe pas |
| Consommation : saisie, historique | ✅ |
| Radioéléments : activités calculées, infos LaraWeb | Activités ⚠️ partiel (voir section 4) ; infos LaraWeb ❌ |
| Audit : consultation | ✅ |
| **Export CSV / JSON** | ❌ seul un export Excel existe, et uniquement en ligne de commande (pas accessible depuis le site) |

## 10. Schéma de base de données

CDC : `sources`, `radionuclides`, `source_radionuclides`, `users`, `roles`,
`consumptions`, `audit_log`, `lara_cache`.

Existant : `sources`, `radionuclides` (conflate radionuclides +
source_radionuclides, section 3), `users` (le rôle est une colonne, pas une
table séparée — un choix raisonnable tant qu'il n'y a que 4 rôles fixes,
mais différent du schéma suggéré), `consumptions`, `audit_logs`, plus
`locations` et `movements` qui n'étaient pas dans le CDC (ajoutés à ta
demande). Manque : `source_radionuclides` séparée, `lara_cache`.

## 11. Sécurité

| Demandé | État |
|---|---|
| Authentification | ✅ |
| Gestion des rôles | ✅ |
| Validation des saisies | ⚠️ basique (Pydantic vérifie les types), pas de règles métier poussées au-delà |
| Prévention des suppressions accidentelles | ✅ partiel (confirmation avant suppression, blocage si une source a un historique) |
| **Sauvegarde automatique de la base** | ❌ n'existe pas du tout |
| **Restauration** | ❌ n'existe pas du tout |

## 12. Livrables du CDC

| Demandé | État |
|---|---|
| Architecture détaillée | ⚠️ documentée au fil de nos échanges (rapport de corrections), pas comme un document d'architecture autonome |
| Schéma SQL complet documenté (clés, index, contraintes) | ⚠️ existe dans le code (modèles SQLAlchemy) mais pas comme document dédié |
| Diagramme relationnel | ❌ pas produit |
| Structure IHM Flet | ❌ sans objet tant que la question Flet n'est pas tranchée |
| Code des fonctions Python | ✅ |
| Stratégie de sauvegarde | ❌ |
| Stratégie de tests | ❌ (pytest est prévu comme dépendance mais aucun test n'existe) |
| Plan de déploiement | ❌ (le README couvre le lancement en développement, pas un vrai plan de déploiement pour poste "infogéré") |
| Propositions d'évolutions futures | ✅ (sections "feuille de route" de nos rapports précédents) |

---

## Ce qui ne doit *pas* être fait (ou à reconsidérer avant de continuer)

- **Ne pas continuer à enrichir la table `radionuclides` actuelle** (par
  exemple lui ajouter les futurs champs LaraWeb comme `origine_laraweb`)
  sans d'abord décider si on la sépare en deux tables comme le veut le CDC
  (section 3) — sinon on construit une deuxième couche sur une fondation
  qu'il faudra de toute façon reprendre.
- **Ne pas ajouter de dépendance à un service cloud/SaaS.** Le CDC est
  explicite : fonctionnement autonome, sans dépendance cloud. Le seul appel
  externe prévu (LaraWeb, section 6) est un site public de référence
  scientifique (LNHB), pas un service commercial — c'est cohérent avec le
  CDC, à condition de garder un cache local et de ne jamais rendre l'appli
  dépendante de sa disponibilité pour fonctionner au quotidien.
- **Ne pas construire de fonctionnalité de suppression pour le journal
  d'audit**, même "réservée aux admins" — le CDC est explicite : aucune
  suppression physique, jamais.
- **Ne pas généraliser la modification/suppression aux consommations**
  sans y réfléchir spécifiquement (déjà signalé dans notre précédent
  échange) : ça casserait la cohérence entre quantité affichée et
  historique réel.

---

## Mon avis sur la question Flet

Honnêtement : si "PC infogéré" signifie que tes utilisateurs finaux ne sont
pas censés ouvrir un terminal ni gérer un environnement Python — ce que ta
propre expérience de lancement (le message d'erreur qu'on a débuggé
ensemble il y a deux échanges) illustre bien à quel point ça peut vite
coincer — alors **Flet correspond mieux à la contrainte de départ** qu'une
appli FastAPI+navigateur. Ce n'est pas un jugement sur la qualité de ce
qu'on a construit ensemble (qui fonctionne bien et qu'on a testé à fond) :
c'est une question de modèle de distribution.

Cela dit, une bonne partie du travail n'est pas perdue dans tous les cas :
les modèles de données, les règles métier (décroissance, permissions par
rôle, cloisonnement MN, règles de consommation) sont indépendants de la
couche d'affichage et seraient réutilisables presque tels quels dans une
version Flet — seule la couche `templates/` + une partie de `routes/`
serait à refaire.

## Suites données à cette analyse

- **Flet : tranché** (07/07/2026), on reste sur FastAPI (voir section 0).
- **Écarts comblés le 07/07/2026** (voir `RAPPORT_DIAGNOSTIC_ET_CORRECTIONS.md`,
  section 9) : champs manquants sur les sources (fournisseur, commentaire,
  quantité initiale, volume du récipient), statuts "transférée"/"détruite",
  utilisateur sur les consommations, activité totale de la source (avec
  distinction activité spécifique/totale — à vérifier avec tes collègues,
  voir rapport).
- **Toujours ouverts** : relation N:N radioéléments/sources (section 3),
  intégration LaraWeb réelle (section 6), seuil d'activité configurable
  (section 7), adresse IP et filtrage par période sur l'audit (section 8),
  recherche/tri/pagination et fiche détaillée par source (section 9),
  export CSV/JSON (section 9), sauvegarde/restauration automatique
  (section 11).
- **Lieux et mouvements** : implémentés le 08/07/2026 sur la base d'un
  exemple concret que tu as fourni (voir `RAPPORT_DIAGNOSTIC_ET_CORRECTIONS.md`,
  section 10) — cycle d'emprunt avec lieu habituel / lieu actuel, retour
  prévu et réel.
