# Gestion des Sources Radioactives

**Version 0.1.21** — affichée en bas de la barre latérale de l'application. En cas
de doute sur la version que tu es en train de tester (par exemple si tu as
plusieurs dossiers de versions différentes sur ta machine), regarde le pied
de page : le numéro doit correspondre à celui annoncé dans le message de
livraison. Le numéro de version est incrémenté à chaque livraison à partir
de maintenant.

Application web de suivi des sources radioactives : inventaire, radionucléides
associés (avec calcul de décroissance), consommations, mouvements entre
lieux de stockage, et journal d'audit des actions effectuées.

**Stack technique :** Python 3.12 · FastAPI · SQLAlchemy · SQLite · Jinja2
(pages HTML classiques, pas de framework JavaScript) · JWT pour l'authentification.

> Pour l'historique des corrections apportées à cette version et la liste des
> chantiers restants, voir le rapport fourni séparément
> (`RAPPORT_DIAGNOSTIC_ET_CORRECTIONS.md`). Pour la comparaison avec le
> cahier des charges initial, voir `ANALYSE_CDC_VS_APPLICATION.md` — le CDC
> prévoyait initialement Python + **Flet** (interface graphique native) ;
> décision prise le 07/07/2026 de rester sur cette architecture web
> (FastAPI + navigateur), jugée suffisamment simple et robuste pour l'usage
> prévu (7 utilisateurs).

## 1. Installation (à faire une seule fois)

Il te faut Python 3.10 ou plus récent. Pour vérifier ce que tu as :

```bash
python3 --version
```

Depuis le dossier du projet (celui qui contient ce fichier), crée un
environnement virtuel et installe les dépendances :

```bash
python3 -m venv venv

# Sur Mac / Linux :
source venv/bin/activate
# Sur Windows (PowerShell) :
venv\Scripts\Activate.ps1

pip install -e .
```

Un environnement virtuel, c'est juste un dossier isolé où Python installe les
bibliothèques du projet sans toucher au reste de ton ordinateur. Il faut
l'activer (`source venv/bin/activate` ou l'équivalent Windows) à chaque fois
que tu ouvres un nouveau terminal pour travailler sur ce projet — tu sauras
que c'est fait quand tu vois `(venv)` apparaître au début de la ligne de
commande.

## 2. Lancer l'application

Toujours depuis le dossier du projet, avec l'environnement virtuel activé :

```bash
uvicorn app.main:app --reload
```

Puis ouvre un navigateur à l'adresse : **http://127.0.0.1:8000**

`--reload` fait redémarrer le serveur automatiquement à chaque modification
du code — pratique pendant le développement. Pour arrêter le serveur :
`Ctrl+C` dans le terminal.

La documentation interactive de l'API (générée automatiquement par FastAPI)
est disponible sur **http://127.0.0.1:8000/api/docs**.

## 3. Se connecter et les rôles

La base de données fournie (`data/database.sqlite`) contient déjà un compte
(`GDO`), mais toi seul connais son mot de passe. Au premier démarrage,
l'application migre automatiquement ce compte vers le nouveau système de
rôles (voir ci-dessous), sans rien te demander.

**4 rôles existent désormais :**

| Rôle | Peut consulter | Peut créer/modifier/consommer | Sources Matière Nucléaire (MN) |
|---|---|---|---|
| **admin** | tout | tout | oui |
| **utilisateur_mn** | tout | tout, sauf gestion des utilisateurs | oui |
| **utilisateur** | tout sauf MN | tout sauf MN, sauf gestion des utilisateurs | non (invisibles) |
| **lecteur** | tout sauf MN | rien | non (invisibles) |

Une source « Matière Nucléaire » est invisible (pas juste bloquée) pour les
rôles `utilisateur` et `lecteur` : elle n'apparaît dans aucune liste, et y
accéder directement renvoie "non trouvée", comme si elle n'existait pas.
Une source se classe aussi automatiquement en Matière Nucléaire dès qu'un
radionucléide de H-3, Li-6, thorium, uranium ou plutonium (tout isotope)
lui est ajouté — sans attendre que quelqu'un coche la case à la main.

Chacun peut changer son propre mot de passe et demander un changement de
rôle depuis le menu utilisateur (bandeau, en haut à droite) — la demande
apparaît alors sur la page Utilisateurs pour qu'un administrateur
l'approuve ou la rejette. Un point rouge sur l'avatar (et un décompte à
côté de "Utilisateurs & rôles" dans le menu) signale à tout administrateur
qu'une ou plusieurs demandes attendent, sur n'importe quelle page — pas
besoin d'aller vérifier la page Utilisateurs par réflexe.

C'est la façon normale de changer le rôle de quelqu'un — pas de script en
ligne de commande à écrire pour ça. `promote_admin.py` reste utile pour
un seul cas précis : obtenir ton tout premier compte admin (aucun autre
moyen, il faut bien qu'un premier admin existe pour approuver quoi que ce
soit depuis l'interface). Les rôles en base : `admin`, `utilisateur_mn`,
`utilisateur`, `lecteur` (voir `app/models/user.py`, classe `UserRole`).

Pour repartir avec des comptes de test connus, deux options :

**a) Utiliser le script de démonstration** (crée un compte `admin` /
`admin123` et une source d'exemple, sans toucher aux données existantes) :

```bash
python -m app.scripts.seed_db
```

**b) Créer ton propre compte** via la page **Inscription**
(http://127.0.0.1:8000/auth/register), puis te promouvoir toi-même
administrateur avec :

```bash
python -m app.scripts.promote_admin ton_nom_utilisateur
```

C'est la façon la plus directe d'obtenir ton tout premier compte admin (il
faut nécessairement un premier admin pour pouvoir en promouvoir d'autres
ensuite depuis la page **Utilisateurs** — aucune interface ne peut créer ce
tout premier admin toute seule). Par sécurité, un nouveau compte démarre
toujours en `lecteur` (le rôle le plus restreint) tant que tu ne l'as pas
promu explicitement.

## 4. Structure du projet

```
app/
  main.py            -> point d'entrée, pages HTML
  config.py          -> lecture de la configuration (.env)
  database.py        -> connexion à la base de données
  models/            -> définition des tables (SQLAlchemy) + schémas de validation (Pydantic)
  repositories/       -> accès aux données (créer/lire/modifier/supprimer en base)
  services/           -> logique métier (décroissance radioactive, consommation, etc.)
  routes/             -> endpoints de l'API et pages HTML
  security/           -> authentification et permissions
  templates/          -> pages HTML (Jinja2)
  static/             -> CSS
  scripts/            -> scripts autonomes (seed, import/export Excel)
data/database.sqlite  -> la base de données (⚠️ à sauvegarder régulièrement !)
```

L'architecture sépare volontairement chaque responsabilité dans sa propre
couche (modèle → dépôt de données → logique métier → route). C'est plus de
fichiers qu'une appli "tout dans un seul fichier", mais c'est ce qui permet
d'ajouter des fonctionnalités une par une sans casser le reste — une bonne
base pour la suite.

## 5. Sauvegarder ta base de données

`data/database.sqlite` contient toutes tes données. C'est un fichier unique :
pour la sauvegarder, il suffit de le copier ailleurs (clé USB, cloud...)
régulièrement, surtout avant tout essai un peu risqué.

## 6. Limites connues (état au 10/07/2026)

- Tableaux réglementaires MN 2a et 3a (récolement) toujours en attente —
  voir section 13.
- Une consommation/pesée peut être corrigée après coup (bouton
  "Modifier") si mal saisie — chaque champ modifié reste tracé dans
  l'audit, mais ce n'est pas un historique strictement immuable (voir
  rapport détaillé, discussion AQ).
- Pas de fiche détaillée par source (regroupant ses radionucléides,
  mouvements, consommations sur une seule page).
- Un radionucléide reste rattaché à une seule source (pas de vrai
  catalogue de radioéléments partagé entre plusieurs sources) — voir
  `ANALYSE_CDC_VS_APPLICATION.md` pour le détail.
- Pas de sauvegarde/restauration automatique de la base (recommandé en
  attendant : copier régulièrement `data/database.sqlite` ailleurs).
- L'intégration LaraWeb reste un brouillon (pas de récupération réelle des
  données depuis le site du LNHB).
- Un emprunt ne gère qu'un aller-retour simple entre le lieu habituel d'une
  source et un autre lieu (pas de chaîne à plusieurs étapes du type
  lieu A → lieu B → lieu C).

## 7. Lieux et emprunts (savoir où sont tes sources)

**Un lieu est obligatoire pour créer une source** (depuis le 10/07/2026 —
le champ texte libre "lieu de stockage" a été retiré, jugé redondant avec
le lieu structuré à l'usage). Si aucun lieu n'existe encore, utilise le
bouton "+ Lieu" sur la page Sources (ou sur Mouvements) avant de créer ta
première source.

Deux notions distinctes sur une source :
- **Emplacement habituel** : là où elle vit normalement (ex : l'armoire des
  sources, IRMA). Se règle directement dans la pop-up de modification de la
  source, comme n'importe quel autre champ — ce n'est pas un emprunt.
- **Emplacement actuel** : là où elle se trouve *en ce moment*. Identique à
  l'emplacement habituel tant qu'aucun emprunt n'est en cours. Seul celui-ci
  est affiché dans le tableau (pas de colonne séparée pour l'habituel).

Pour emprunter une source (page **Mouvements**) : choisis la source (seules
celles ayant un emplacement habituel défini sont proposées) et le lieu de
destination ; une date de retour prévue est facultative. La source
n'apparaît alors plus disponible pour un nouvel emprunt tant que celui-ci
n'est pas clôturé ("Marquer retourné").

**Cas des sources liquides qui restent définitivement dans ton labo une
fois ouvertes** : il suffit de ne jamais cliquer sur "Marquer retourné".
L'emprunt reste "en cours" indéfiniment, ce qui correspond exactement à
"cette source est maintenant chez moi".

Un lieu (page **Lieux**, accessible depuis Mouvements) peut avoir un nom,
un site/service (ex : "IRMA", "EPICEA"), un bâtiment et une pièce — tous
facultatifs sauf le nom. Pour simplifier une liste de lieux devenue trop
éclatée, le bouton **Fusionner** déplace toutes les sources et tous les
mouvements d'un lieu vers un autre (avec confirmation), puis supprime le
premier. Autre façon d'arriver au même résultat, sans doute plus naturelle
à découvrir : renommer un lieu vers un nom déjà utilisé par un autre lieu
propose directement la même fusion.

## 7bis. Quantité restante, quantité initiale et unités d'activité

La quantité **restante** d'une source **n'est plus saisie directement** :
elle se calcule et s'affiche en lecture seule sur la page Sources (masquée
pour les sources scellées, où le concept ne s'applique pas). Elle désigne
toujours la quantité **physique** de la source (masse de liquide pesée,
pression de gaz) — **jamais** une masse d'isotope déduite de l'activité :
ce calcul-là (masse de matière nucléaire pure) n'a de sens que pour
l'Annexe 1 et le Tableau 1a, et s'obtient séparément.

Deux sources possibles, dans cet ordre :

1. La pesée la plus récente enregistrée lors d'une consommation (voir
   ci-dessous, pesée double avant/après prélèvement) — la valeur la plus
   fiable, qui reflète la réalité du moment (y compris l'évaporation
   éventuelle du solvant).
2. Repli : **quantité initiale**, un champ que tu renseignes à la création
   de la source (côte à côte avec son unité), moins les quantités
   consommées enregistrées en mode simple.

**Enregistrer une consommation** (page Consommations) propose deux modes,
selon l'état physique de la source :
- **Liquide** : pesée. Tu renseignes la masse pesée (récipient + contenu —
  plus sûr de peser fermé que d'ouvrir pour peser le liquide seul), et
  éventuellement une seconde masse après un prélèvement. Si tu laisses la
  seconde masse vide, c'est une **pesée de contrôle** (rien n'est
  prélevé) — utile en particulier pour la toute première pesée après
  réception d'une source (fiole + liquide + bouchon + étiquette, sans
  rien prélever) : elle sert de référence pour la suite.

  La quantité restante affichée est en masse de **liquide seul**, pas la
  masse totale pesée : la masse du récipient (fiole, bouchon, étiquette)
  est déduite automatiquement à partir de la toute première pesée moins
  la quantité initiale connue (celle du certificat d'étalonnage), en
  supposant une évaporation négligeable entre la réception et cette
  première pesée. Chaque pesée suivante réutilise cette même masse de
  récipient. Si `masse_avant` diffère sensiblement de la pesée précédente,
  l'écart (probable évaporation du solvant) est noté automatiquement dans
  le commentaire, sans bloquer l'enregistrement : c'est la pesée réelle
  qui fait foi, pas un calcul théorique.

  Une consommation déjà enregistrée peut être corrigée (bouton
  "Modifier") en cas d'erreur de saisie — chaque champ modifié reste
  tracé dans l'audit (avant/après), pour concilier ce droit à l'erreur
  avec un minimum de traçabilité.
- **Gaz** : quantité directe (peser un gaz n'a pas de sens), comme avant.

Une source peut aussi porter, en plus de sa quantité (masse ou pression),
un **volume de récipient** distinct (côte à côte avec son unité, mL ou L)
— utile en particulier pour un liquide, dont la masse volumique n'est pas
celle de l'eau.

Les unités d'activité gèrent les préfixes usuels — n, µ (ou u), m, k, M, G,
T — sur Bq, Bq/g, Bq/m3, Bq/L, Bq/mL, Bq/cm3 (ex : "MBq", "kBq/g"). Une
activité saisie avec un préfixe non reconnu est refusée plutôt que mal
interprétée. Les noms de radionucléides sont standardisés automatiquement
au format "Symbole-nombre" (ex : "Kr-85", comme LaraWeb), quel que soit
l'ordre ou le séparateur saisi. La période radioactive s'affiche dans
l'unité de temps la plus lisible (s, min, h, j ou ans selon sa durée),
plutôt que toujours en années. L'état physique (solide/liquide/gaz)
s'affiche avec une icône et une couleur distinctive.

## 8. Archivage des sources

Une source dont l'état d'utilisation passe à **remisée**, **en déchet**,
**transférée** ou **détruite** sort automatiquement de la liste active : elle
n'apparaît plus dans `/sources`, ni dans les menus de la page Radionucléides
(ajout), Consommations, ou Mouvements (démarrer un emprunt). Elle reste
consultable dans **Archives des sources** (lien en haut de la page Sources).

Impossible d'ajouter un radionucléide, une consommation ou un emprunt sur
une source archivée. Une fois archivée, seul un **administrateur** peut
encore la modifier (page Archives, bouton "Corriger") — pour corriger une
erreur de saisie, ou la remettre en circulation en repassant son état sur
"En utilisation" ou "En attente".

## 8bis. Tri, pagination et activité utilisée

Chaque tableau (Sources, Radionucléides, Consommations, Mouvements,
Lieux, Audit) se trie en cliquant sur un en-tête de colonne (flèche
↑/↓, un second clic inverse le sens) et se pagine — un menu déroulant
choisit le nombre de lignes par page (10/20/50/100/Tout), avec une
navigation page précédente/suivante et le total de lignes affiché.
Le tri et la pagination fonctionnent ensemble et, sur Sources et Audit,
avec les filtres déjà en place (onglets, cases à cocher) : la pagination
s'applique toujours au résultat déjà filtré, jamais avant.

Sur la page **Consommations**, une colonne **Activité utilisée** affiche
l'activité (Bq) correspondant à la quantité consommée, calculée à la
date de CETTE consommation précise (décroissance radioactive appliquée
depuis la date de référence du radionucléide) — purement pour
l'affichage, aucune valeur n'est stockée en base.

## 9. Import / Export (réservé aux administrateurs)

Page **Import/Export** (lien dans le menu, admin uniquement) :

Trois des exports ci-dessous (liste des sources, Annexe 1, Tableau 1a)
sont disponibles en **XLSX, ODS (LibreOffice Calc) et PDF** — en
anticipation d'une réduction de la dépendance à Microsoft. La conversion
vers ODS/PDF se fait via LibreOffice en ligne de commande : nécessite
LibreOffice installé sur la machine qui fait tourner l'application
(message d'erreur explicite sinon, l'export XLSX restant disponible dans
tous les cas).

- **Import** : upload direct, deux formats reconnus automatiquement — le
  fichier d'inventaire Excel historique (feuilles "Sources scellées",
  "Sources non scellées", "Sources consommables") ou un fichier déjà
  exporté par cette application (feuille "Sources", voir plus bas).
  Correspondance des colonnes par préfixe (pas par égalité stricte) :
  tolère les petites variantes de libellé d'un export à l'autre (ex :
  "ACTIVITE NOMINALE [4]" ou "ACTIVITE NOMINALE (BQ)" sont reconnus de la
  même façon). Une source déjà présente (même identifiant) est ignorée,
  jamais écrasée — l'import peut être relancé sans risque de doublon ou de
  perte de corrections déjà faites à la main. Une ligne sans identifiant
  mais avec un radionucléide est rattachée à la source précédente si elle
  n'a pas non plus de date d'arrivée (cas des sources "mélange"
  multi-isotopes) ; sinon, elle est signalée comme orpheline plutôt que
  rattachée à tort. Beaucoup de colonnes du fichier source n'ont pas de
  champ dédié dans l'application ; elles sont regroupées automatiquement
  dans le champ "Commentaire" de chaque source pour ne rien perdre.
  L'état d'utilisation (en utilisation / remisée / en attente) est déduit
  de la colonne "UTILISATION" du fichier (UT / DEP / SE — voir sa légende
  dans son onglet "Remarques") ; sans valeur reconnue, "en utilisation"
  par défaut, comme avant. Un
  rapport détaillé (créées / ignorées / erreurs / avertissements) s'affiche
  après chaque import — lis en particulier les avertissements sur l'état
  physique deviné par défaut, et sur les lignes orphelines. Chaque import
  est tracé dans le journal d'audit (action "IMPORT").
- **Importer depuis un certificat** (page Sources, bouton "Importer depuis
  un certificat (PDF)") : lit un certificat d'étalonnage PDF (format
  CERCA/LEA-Orano notamment) et pré-remplit la création d'une source et de
  son radionucléide (activité, unité, spécifique ou non, date de
  référence, masse délivrée, référence du certificat). **Une proposition à
  vérifier, jamais une création automatique** : les certificats sont
  souvent d'anciens documents scannés, dont le texte lu par OCR peut être
  largement abîmé (accents, chiffres, voire des mots entiers déformés) —
  un champ que l'extraction ne peut pas lire avec une confiance
  raisonnable est laissé vide plutôt que deviné (mieux vaut compléter à la
  main qu'une valeur fausse avec l'air fiable). Une fois la source
  enregistrée, la pop-up d'ajout du radionucléide détecté s'ouvre
  automatiquement, pré-remplie — à vérifier avant de valider, comme le
  reste.
- **Export liste des sources** : fichier Excel à deux feuilles (Sources +
  Radionucléides), toutes sources actives et archivées confondues.
- **Export Annexe 1** : formulaire réglementaire "Inventaire Physique Des
  Matières Nucléaires" (mise en forme officielle conservée), une ligne par
  radionucléide des sources Matière Nucléaire : codes matière EUR/National
  (déduits automatiquement du radionucléide), désignation, référence
  catalogue, date de référence, masse de source, et masse en radioélément
  (calculée à partir de l'activité actuelle et de la période). Colonnes
  "Teneur en éléments %" et "Total par matière" volontairement laissées
  vides (à préciser). La date du jour est renseignée automatiquement
  (cellule I4).
- **Inventaire physique (Matières Nucléaires)** : document PDF à imprimer
  (paysage, en-tête répété sur chaque page), une ligne par source Matière
  Nucléaire active — identifiant, radionucléide(s), emplacement habituel,
  une case à cocher (bordure du tableau, à cocher à la main) pour
  confirmer la présence physique, et deux emplacements de signature. À
  compléter en allant vérifier chaque source, signer, et conserver.

Les tableaux réglementaires MN 1a/2a/3a (récapitulatif par matière,
comparaison avec la comptabilité nationale IRSN) restent à construire —
en cours de discussion avec toi sur leurs règles précises.

## 10. Interface (barre latérale + bandeau)

Refonte visuelle du 10/07/2026 : barre latérale à gauche (Sources,
Mouvements, Consommations, Import/Export, Audit — ces deux dernières
visibles par les admins et utilisateurs MN), bandeau en haut avec le menu
utilisateur (rôle affiché, accès à la gestion des utilisateurs pour les
admins, déconnexion).

**Page Sources** (point d'entrée de l'application, "/" y redirige) :
trois onglets — Scellées / Consommables (gaz ou liquide) / Non scellées —
et un filtre par statut (par défaut : "En utilisation" + "En attente"
seulement ; les statuts archivés sont décochables au choix, ce qui rend la
page Archives dédiée optionnelle). Deux boutons directs : "+ Ajouter une
source" et "+ Ajouter un Rn" (avec sélecteur de source et recherche
LaraWeb intégrée, sans quitter la page).

**Page Mouvements** : bouton "+ Lieu" pour créer un lieu sans quitter la
page (lien "Gérer tous les lieux" pour la liste complète).

**Page Audit** : filtre par type de modification et par table concernée,
tri par date (récent/ancien).

**Export** désormais accessible aux utilisateurs MN, en plus des
administrateurs (l'import reste réservé aux admins).

## 11. Tests automatisés

Une suite de tests couvre les pages (aucune page ne doit planter, quel que
soit le rôle), les permissions par rôle, le cloisonnement Matière
Nucléaire, l'archivage, les règles de consommation, et le cycle complet
d'emprunt/retour. Pour les lancer :

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Les tests utilisent une base de données en mémoire entièrement séparée :
ils ne touchent jamais à `data/database.sqlite`. À relancer après toute
modification du code, avant de considérer un changement terminé.

## 12. Intégration LaraWeb

Sur la page **Radionucléides**, bouton "Chercher sur LaraWeb" à côté du nom
du radionucléide : récupère (et met en cache localement, de façon
définitive — ces données n'évoluent pas) la période radioactive et
l'activité massique depuis le site du LNHB, et pré-remplit le champ
"Période". URL réelle utilisée : `http://www.lnhb.fr/nuclides/{nuclide}.lara.txt`
(ex : Co-60, Pu-239 — le CDC initial indiquait une autre adresse, obsolète).

L'activité massique récupérée sert aussi, en priorité sur le calcul
physique par défaut, au calcul de la masse d'un radioélément dans les
exports Annexe 1 et Tableau 1a (plus précis, et couvre bien plus
d'isotopes que la table de masses molaires codée en dur).

**Note technique** : la récupération réseau elle-même n'a pas pu être
testée en conditions réelles depuis mon environnement de développement
(accès réseau restreint) — le code de récupération (bibliothèque `requests`
standard) est cependant testé unitairement (analyse du format) et par un
test d'intégration avec requête réseau simulée à partir de vraies données
capturées sur le site. À tester une fois en conditions réelles ; dis-moi
si le format a changé ou si une adaptation est nécessaire.

## 13. Tableau 1a

Page Import/Export, bouton "Télécharger le Tableau 1a" : réorganise les
masses déjà calculées pour l'Annexe 1, sommées par catégorie de matière et
triées par lieu (IRMA / EPICEA / Total), mise en forme officielle
conservée. La date du jour est renseignée automatiquement (cellule H3,
"Inventaire du"). Règles :

- Le lieu retenu est l'**emplacement actuel** de la source (comparaison au
  champ "site" du lieu, insensible à la casse : "IRMA" ou "EPICEA").
  Une source Matière Nucléaire ailleurs (ou sans emplacement suivi) est
  comptée dans "Total" mais absente des colonnes IRMA/EPICEA — un
  avertissement te le signale (visible en-tête de la réponse HTTP pour
  l'instant, pas encore affiché dans l'interface).
- Uranium : catégorisé automatiquement (enrichi ≥20 %, 10-20 %, <10 %,
  naturel, appauvri) à partir du % massique d'U-235 calculé sur l'ensemble
  des isotopes d'uranium (hors U-233, qui a sa propre ligne) d'une même
  source, avec une tolérance de ±0,05 point autour de la composition
  naturelle exacte (99,2742 % U-238, 0,7202 % U-235, 0,0055 % U-234,
  indiquée le 10/07/2026) pour distinguer "naturel" d'un léger écart de
  calcul.
- Pour les 3 lignes "Uranium enrichi", la seconde colonne (masse de
  l'isotope U-235 seul) est également renseignée, comme demandé.
- **Deutérium et Lithium-6 enrichi** : ces deux isotopes sont stables (non
  radioactifs), leur masse ne peut donc pas être déduite d'une activité —
  ces deux lignes restent à zéro avec le système actuel. Une vraie saisie
  de masse directe serait nécessaire pour les couvrir.

Tableaux 2a/3a : toujours en attente, comme convenu.

Détails complets et suggestions de priorités : voir
`RAPPORT_DIAGNOSTIC_ET_CORRECTIONS.md`.
