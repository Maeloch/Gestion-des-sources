# Rapport de diagnostic et corrections — V0.1.2

## En résumé

Ton application ne démarrait pas et, même en la forçant à démarrer, presque
aucune action ne fonctionnait (connexion, création de source, etc.). Ce
n'est pas parce que le travail de ton stagiaire était mauvais : au contraire,
l'architecture choisie (séparation modèles / accès aux données / logique
métier / routes) est une bonne pratique, plus rigoureuse que ce que fait la
plupart des débutants. Le problème, c'est qu'il reste une vingtaine de petits
bugs — surtout des erreurs d'inattention (copier-coller, variable oubliée,
dépendance non notée) — qui bloquaient chacun une partie de l'appli, un peu
comme une chaîne de dominos.

J'ai identifié et corrigé tous les bugs que j'ai trouvés, puis j'ai testé
l'application de bout en bout (inscription, connexion, création de source,
ajout d'un radionucléide, consommation, suppression, déconnexion...) pour
vérifier que ça fonctionne réellement, pas seulement "à la lecture du code".

**Aujourd'hui, l'application démarre et les fonctions principales marchent.**
Il reste en revanche des fonctionnalités non terminées (voir section 4) —
c'est normal, un stagiaire qui n'a pas eu le temps de finir laisse
justement ce genre de trous.

---

## 1. Comment j'ai procédé

Plutôt que de deviner, j'ai réellement fait tourner ton code dans un
environnement de test : installation des dépendances, lancement du serveur,
et une série de requêtes simulant un vrai utilisateur (inscription →
connexion → création de source → ajout de radionucléide → consommation →
vérification de l'audit → déconnexion). Chaque bug listé ci-dessous a été
**observé concrètement** (message d'erreur réel), pas juste repéré à la
lecture. J'ai utilisé une copie de travail de ta base de données pendant les
tests, puis je l'ai restaurée à l'identique de l'originale à la fin (seules
les corrections de code sont conservées ; tes données ne contiennent aucune
trace de mes tests).

---

## 2. Ce qui empêchait l'application de fonctionner

### 2.1 Deux dépendances manquantes (l'appli ne démarrait même pas)

`pyproject.toml` (la liste des bibliothèques nécessaires) oubliait :
- `email-validator`, nécessaire pour valider les adresses email ;
- `argon2-cffi`, nécessaire pour le hachage des mots de passe (le code
  demande l'algorithme "argon2", mais seul "bcrypt" était listé).

Sans la deuxième, l'inscription plantait avec une erreur
`MissingBackendError`. Les deux sont maintenant ajoutées à
`pyproject.toml` et installées.

### 2.2 Le bug le plus grave : impossible de rester connecté

C'est le bug qui rendait l'application quasiment inutilisable. Il y avait
deux problèmes empilés :

**a) Une erreur de code toute simple.** Dans
`app/security/permissions.py`, la fonction qui vérifie qu'on est bien
connecté utilisait une variable `request` qui n'était jamais définie :

```python
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")   # 'request' n'existe pas !
```

**b) Un choix d'architecture inachevé.** Le serveur enregistre la connexion
dans un cookie (une petite information stockée par le navigateur), mais la
vérification cherchait le "ticket" de connexion à un autre endroit (un
en-tête HTTP `Authorization`), que le navigateur n'envoie jamais dans ce
contexte. Résultat : même une fois l'erreur de variable corrigée, la
connexion aurait quand même été refusée à chaque fois.

J'ai réécrit cette fonction pour qu'elle accepte les deux méthodes (cookie
*ou* en-tête), avec le cookie comme méthode principale utilisée par le site.
Ce bug touchait strictement **toutes** les actions protégées (créer,
modifier, supprimer quoi que ce soit) : c'est celui qui avait le plus
d'impact.

### 2.3 Quatre bugs de copier-coller qui empêchaient de créer des données

En regardant le code d'enregistrement en base de données, j'ai trouvé 4
endroits où une fonction avait manifestement été copiée depuis une autre et
mal adaptée : elle renvoyait le résultat sous le mauvais nom de variable.
Exemple dans `app/repositories/radionuclide.py` :

```python
def create(self, radionuclide: RadionuclideCreate) -> RadionuclideDB:
    db_radionuclide = RadionuclideDB(**radionuclide.model_dump())
    self.db.add(db_radionuclide)
    self.db.commit()
    self.db.refresh(db_radionuclide)
    return db_movement   # <- devrait être db_radionuclide
```

Le même bug (retourner `db_movement` au lieu de la bonne variable) existait
dans la création des **radionucléides**, des **lieux** et des
**consommations**. Résultat concret : la ligne était bien enregistrée en
base (le `commit()` a lieu avant l'erreur), mais l'utilisateur recevait quand
même un message d'erreur — assez déroutant, puisque l'action avait en
réalité fonctionné. Les 4 occurrences sont corrigées.

### 2.4 Un bug qui bloquait toutes les pages "Sources"

Un modèle de données (`Source`, dans `app/models/source.py`) faisait
référence à un autre type de données (`Radionuclide`) par son nom écrit
entre guillemets, sans jamais importer ce type — une "référence non
résolue". Résultat : **dès qu'une réponse contenant une source devait être
construite, l'application plantait**, ce qui bloquait la liste des sources,
la création, la modification... même une fois le bug de connexion corrigé.
J'ai corrigé l'import manquant, et j'en ai profité pour faire en sorte
qu'une source affiche désormais la liste de ses radionucléides associés
(c'était visiblement l'intention d'origine).

### 2.5 Le journal d'audit faisait planter les créations/modifications

Chaque fois qu'une action devait être enregistrée dans le journal d'audit
(traçabilité : qui a fait quoi et quand), le code envoyait un simple
dictionnaire Python là où la fonction attendait un objet structuré et
validé (Pydantic) :

```python
audit_repo.create({             # un dict brut...
    "utilisateur": current_user.username,
    "action": "CREATE",
    ...
})
```

...alors que `AuditRepository.create()` attendait un objet créé avec
`AuditLogCreate(...)`. Comme pour le bug de copier-coller (2.3),
l'enregistrement principal réussissait, mais l'écriture du journal d'audit
qui suivait immédiatement après plantait, et l'utilisateur recevait une
erreur malgré une action en réalité réussie. Corrigé aux 5 endroits
concernés (création/modification/suppression de source, création de
radionucléide, et dans le service de consommation).

### 2.6 Suppression d'une source : deux bugs différents

- **Suppression simple** : le code tentait de "rafraîchir" l'objet juste
  après l'avoir supprimé et validé en base — une opération impossible que
  SQLAlchemy refuse. Corrigé en retirant cette ligne inutile.
- **Suppression d'une source ayant un historique** (consommations ou
  mouvements associés) : la base de données refusait l'opération (elle
  tentait de "détacher" les enregistrements liés en mettant leur référence
  à vide, ce que la structure de la table interdit), ce qui provoquait un
  plantage brutal. J'ai ajouté une vérification propre : si une source a des
  consommations ou mouvements associés, la suppression est désormais
  **refusée avec un message clair**, plutôt qu'un plantage — pour éviter de
  perdre silencieusement de l'historique, ce qui est particulièrement
  important pour un outil de traçabilité de sources radioactives.

### 2.7 Autres plantages corrigés

- `app/scripts/seed_db.py` (script pour générer des données de démonstration)
  utilisait par erreur les classes de *validation* (Pydantic) au lieu des
  classes de *base de données* (SQLAlchemy) — deux familles de classes qui
  portent des noms très proches dans ce projet (`Source` vs `SourceDB`,
  etc.), ce qui explique la confusion. Corrigé, et rendu rejouable sans
  erreur si on le lance plusieurs fois.
- Créer une source avec un identifiant déjà utilisé provoquait un plantage
  brut (erreur de contrainte SQL). Remplacé par un message clair : *"Une
  source avec l'identifiant [...] existe déjà."*

---

## 3. Ce qui fonctionnait "à moitié" (pas de plantage, mais résultat faux ou incomplet)

- **La déconnexion ne déconnectait pas vraiment** : le bouton redirigeait
  vers la page de connexion, mais sans jamais supprimer le cookie de
  session — l'utilisateur restait donc connecté. Corrigé.
- **Le menu du site ne reflétait jamais le bon état de connexion**
  (le code cherchait l'info au mauvais endroit, pour la même raison qu'en
  2.2). Corrigé : le menu est maintenant calculé correctement côté serveur.
- **La page de connexion échouait silencieusement** : après un login
  réussi, le code JavaScript de la page tentait de lire une réponse au
  format qui n'était en réalité jamais renvoyée par le serveur, et
  échouait sans redirection ni message. Corrigé.
- **Les catégories de source s'affichaient de façon technique et illisible**
  dans les tableaux (`SourceType.scellee` au lieu de `scellée`) à cause
  d'une subtilité Python sur l'affichage des énumérations. Corrigé dans le
  tableau des sources et dans l'export Excel (`export_excel.py`), qui avait
  le même souci.
- **Le hash du mot de passe était renvoyé par l'API** lors de l'inscription
  et dans la liste des utilisateurs — jamais le mot de passe en clair, mais
  ce n'est pas une information à exposer côté client. Corrigé (un schéma de
  réponse dédié, sans ce champ, est utilisé partout).
- **Le formulaire "Ajouter une source" du site était bloqué en permanence**,
  même connecté, car il vérifiait la présence d'un jeton dans un
  emplacement du navigateur (`localStorage`) qui n'était en réalité jamais
  rempli — le site utilise un cookie, pas cet emplacement. Corrigé.

---

## 4. Fonctionnalités déjà écrites… mais jamais branchées

C'est une découverte utile : certaines fonctionnalités importantes étaient
déjà codées et fonctionnelles en elles-mêmes, mais jamais appelées nulle
part dans l'application. Autrement dit, le travail existait, il manquait
juste le "fil électrique" pour les relier au reste.

- **Calcul de décroissance radioactive** (`app/services/decay.py`) :
  entièrement fonctionnel (formule standard vérifiée), mais jamais utilisé.
  Je l'ai branché sur la page "Radionucléides", qui affiche désormais une
  colonne **Activité actuelle**, recalculée à chaque affichage à partir de
  l'activité de référence et de la période radioactive.
- **Décrément de quantité lors d'une consommation**
  (`app/services/consumption.py`) : la logique pour vérifier la quantité
  disponible, la décrémenter, et journaliser l'action existait, mais la
  route utilisait un autre chemin qui l'ignorait complètement — enregistrer
  une consommation ne faisait donc rien diminuer. Branché : une consommation
  diminue maintenant réellement la quantité restante de la source, et
  refuse proprement si la quantité demandée dépasse le stock disponible.
- **`app/services/laraweb.py`** (récupération de la période radioactive
  depuis la base LARA du LNHB) : encore un "brouillon" (4 isotopes codés en
  dur, pas de vraie connexion au site), et toujours non branché. Je ne l'ai
  pas touché — le compléter suppose une vraie décision sur comment
  interroger ce site (voir section 5).

---

## 5. Ce qu'il reste à faire

Je n'ai corrigé que ce qui était cassé ou à moitié fait ; je n'ai pas ajouté
de nouvelles fonctionnalités de mon propre chef au-delà de brancher
l'existant (section 4). Voici ce qui manque encore, à peu près par ordre
d'utilité :

| Priorité | Sujet | Détail |
|---|---|---|
| Haute | Interface pour modifier/supprimer | Le site ne propose de formulaire que pour *créer* une source. Modifier ou supprimer une source, ou créer/gérer radionucléides, lieux, mouvements, consommations, n'est possible que via `/api/docs`. |
| Moyenne | Fiche détaillée d'une source | Une page qui regroupe, pour une source donnée : ses radionucléides, son historique de mouvements et de consommations. |
| Moyenne | LaraWeb | Décider si on veut une vraie intégration (récupérer automatiquement la période radioactive d'un isotope) ou si la saisie manuelle suffit. |
| Basse | Import/export Excel accessibles depuis le site | Fonctionnent en ligne de commande, pas encore avec un bouton sur le site. |
| Basse | SQLite vs MySQL | Le fichier `.env` est prêt pour MySQL, mais le code utilise SQLite en dur. À trancher selon si l'appli sera utilisée par une seule personne (SQLite suffit) ou plusieurs en même temps sur un serveur partagé (MySQL recommandé). |
| Basse | Tests automatisés | `pytest` est prévu dans les dépendances mais aucun test n'existe. Utile pour éviter que de nouveaux bugs similaires repassent inaperçus. |

*(La gestion des administrateurs, listée ici initialement, a été ajoutée le
03/07/2026 — voir section 4bis ci-dessous.)*

## 4bis. Ajouté depuis le rapport initial : gestion des administrateurs

Il n'existait aucun moyen, depuis l'application, de faire d'un utilisateur un
administrateur. Ajouté :

- Une page **Utilisateurs** (`/users`, lien visible dans le menu uniquement
  pour les administrateurs) listant tous les comptes, avec un bouton pour
  promouvoir/rétrograder ou supprimer chaque utilisateur.
- Une route API `PATCH /users/{id}/admin` (réservée aux administrateurs).
- Une protection : un administrateur ne peut pas modifier son propre statut
  ni supprimer son propre compte (pour éviter de se retrouver bloqué dehors
  par erreur) — il faut qu'un *autre* administrateur s'en charge.

Pour le tout premier administrateur, il faut toujours passer par
`python -m app.scripts.seed_db` (crée `admin` / `admin123`) ou une
modification directe de la base — c'est le seul cas qu'aucune interface ne
peut résoudre (il faut bien un premier admin pour en créer d'autres).

---

## 6. Fichiers modifiés

`pyproject.toml`, `.env` (nouvelle clé secrète), `app/main.py`,
`app/models/source.py`, `app/models/user.py`,
`app/repositories/{radionuclide,location,consumption,source,user}.py`,
`app/routes/{sources,radionuclides,consumptions,auth,users}.py`,
`app/services/consumption.py`, `app/scripts/{seed_db,export_excel}.py`,
`app/security/permissions.py`,
`app/templates/base.html`, `app/templates/sources.html`,
`app/templates/radionuclides.html`, `app/templates/auth/login.html`,
`app/templates/users.html` (nouveau, page de gestion des administrateurs).

Ta base de données (`data/database.sqlite`) n'a pas été modifiée : c'est
exactement le fichier que tu as fourni.

---

## 7. Deuxième vague de changements (04/07/2026) : rôles et cloisonnement Matière Nucléaire

À ta demande, le système binaire admin/non-admin est remplacé par **4 rôles** :
`admin`, `utilisateur_mn`, `utilisateur`, `lecteur` (détail dans le README).
Points techniques notables :

- **Migration automatique.** Ta base de données existante utilisait une
  colonne `is_admin` (vrai/faux). Elle est maintenant remplacée par une
  colonne `role`. Comme l'application ne recrée jamais les tables déjà
  existantes automatiquement, j'ai écrit une migration
  (`app/scripts/migrate_add_role.py`) qui ajoute cette colonne et déduit le
  rôle de chacun à partir de l'ancien statut admin — elle s'exécute
  **automatiquement à chaque démarrage** de l'application, sans rien à faire
  de ton côté, et ne fait rien si elle a déjà tourné. Ton compte `GDO`
  (non-admin dans l'ancien système) passera à `utilisateur_mn` (accès complet
  hors administration) pour ne pas perdre de droits par rapport à avant.
- **Cloisonnement Matière Nucléaire.** Le champ `matiere_nucleaire` existait
  déjà sur les sources, mais rien ne s'en servait. Il gouverne maintenant
  l'accès : une source MN est totalement invisible (pas seulement bloquée)
  pour les rôles `utilisateur` et `lecteur`, à la fois dans les listes, les
  accès directs, et pour tout ce qui s'y rattache (radionucléides,
  consommations). J'ai appliqué cette règle à la fois dans l'API et dans les
  pages du site — j'ai d'ailleurs trouvé, en le faisant, que les pages du
  site (contrairement à l'API) ne filtraient rien du tout et étaient même
  consultables sans être connecté : corrigé au passage (connexion désormais
  obligatoire pour consulter les données).
- **Auto-modification.** Comme pour l'ancien statut admin, un utilisateur ne
  peut pas changer son propre rôle (il faut qu'un autre administrateur s'en
  charge), pour éviter un blocage accidentel.

### Radionucléides : formulaire d'ajout

La page **Radionucléides** propose maintenant un formulaire pour en ajouter
un à une source existante (nom, activité, unité, date de référence, période
optionnelle). Le menu déroulant des sources respecte le cloisonnement MN.
Une source peut recevoir plusieurs radionucléides, chacun avec sa propre
activité — ajouter un radionucléide n'affecte pas les autres déjà présents
sur la même source.

### Consommations : règles gaz/liquide

La logique de consommation (déjà branchée lors de la première vague de
corrections) est maintenant plus précise et donne des messages clairs et
distincts selon le problème :

- source de type solide/scellée → *"seules les sources gaz (pression) ou
  liquide (masse) peuvent être consommées"* ;
- quantité non renseignée sur la source → message dédié ;
- quantité demandée supérieure au stock → message donnant le stock restant
  exact et son unité.

La page **Consommations** propose un formulaire dont le menu déroulant ne
liste que les sources gaz/liquide ayant une quantité renseignée (et
respectant le cloisonnement MN), avec un rappel de la quantité restante
lorsque tu choisis une source.

### Comptes de test utilisés pendant la vérification

J'ai testé les 4 rôles avec des comptes dédiés (créés puis supprimés de ta
base avant livraison) : création/consultation/modification/suppression de
sources MN et non-MN, ajout de radionucléides, consommations valides et
invalides, changement de rôle, auto-modification bloquée. Tout est passant.

### Ce qui reste en attente

Lieux et mouvements : tu as indiqué vouloir préciser les règles séparément.
Je n'ai donc pas touché à leur fonctionnement (ils restent, comme avant,
accessibles uniquement aux administrateurs, sans notion de rôle affinée ni
de cloisonnement MN) — à revoir une fois que tu m'auras donné le contexte.

### Fichiers ajoutés ou modifiés dans cette deuxième vague

`app/models/user.py` (rôles), `app/repositories/user.py`,
`app/security/permissions.py`, `app/routes/{users,sources,radionuclides,consumptions}.py`,
`app/services/consumption.py`, `app/scripts/seed_db.py`, `app/main.py`,
`app/templates/{base,sources,radionuclides,consumptions,users}.html`,
`app/scripts/migrate_add_role.py` (nouveau).

---

## 8. Troisième vague de changements (05/07/2026)

### Modifier / supprimer sources et radionucléides

Les pages **Sources** et **Radionucléides** fonctionnent maintenant sur le
même principe : un bouton **"+ Ajouter..."** ouvre une pop-up (fenêtre
modale) avec le formulaire ; chaque ligne du tableau a des boutons
**Modifier** (ouvre la même pop-up, pré-remplie) et **Supprimer**
(demande confirmation). Ces boutons sont masqués pour le rôle lecteur,
cohérent avec le reste de l'application.

Pour les sources, j'ai aussi ajouté au formulaire trois champs qui
existaient dans la base de données mais n'apparaissaient dans aucun
formulaire jusqu'ici : n° de certificat d'étalonnage, n° source fabricant,
lien vers le dossier administratif.

Techniquement, les routes de modification/suppression pour les sources
existaient déjà côté API (ajoutées lors de la première vague) ; celles pour
les radionucléides n'existaient pas du tout et ont été créées à cette
occasion — avec les mêmes règles de permissions et le même cloisonnement
Matière Nucléaire que la création (voir section 7).

**Choix délibéré : les consommations restent créables mais non
modifiables/supprimables.** Une consommation représente un événement passé
qui a déjà modifié la quantité restante d'une source ; permettre de la
modifier ou de la supprimer après coup demanderait de recalculer et
"annuler" cet effet, avec un risque de désynchronisation entre la quantité
affichée et l'historique réel. Le journal d'audit obéit à la même logique
(jamais modifiable). Si tu as besoin de corriger une consommation saisie
par erreur, dis-le moi : on peut réfléchir à une fonctionnalité dédiée
("annuler la dernière consommation d'une source", par exemple) plutôt que
d'autoriser une modification libre.

### Journal d'audit ouvert aux utilisateurs MN

Le journal d'audit (page et API) était réservé aux administrateurs ; il est
désormais aussi accessible au rôle `utilisateur_mn` (pas aux rôles
`utilisateur` ni `lecteur`). Le lien "Audit" dans le menu est masqué pour
les rôles qui n'y ont pas accès, pour éviter d'afficher un lien qui mène à
une erreur.

### Lieux et mouvements

Toujours en attente de tes précisions (comme convenu) : je n'y ai pas
touché dans cette vague.

### Fichiers ajoutés ou modifiés dans cette troisième vague

`app/routes/radionuclides.py` (ajout modification/suppression),
`app/routes/audit.py`, `app/security/permissions.py` (accès audit),
`app/main.py` (page audit), `app/templates/base.html` (lien audit masqué),
`app/templates/sources.html` et `app/templates/radionuclides.html`
(refonte avec pop-up), `app/static/style.css` (style des pop-up).

---

## 9. Quatrième vague de changements (07/07/2026) : combler des écarts avec le CDC

Suite à la lecture du cahier des charges initial (voir
`ANALYSE_CDC_VS_APPLICATION.md` pour la comparaison complète), et à ta
décision de rester sur l'architecture FastAPI actuelle (pas de bascule vers
Flet), j'ai comblé les écarts les plus structurants côté données — ceux qui
touchaient directement les formulaires tout juste mis en place, pour éviter
d'avoir à y revenir une troisième fois.

### Nouveaux champs sur les sources

`fournisseur`, `commentaire`, `quantite_initiale` (quantité de départ,
conservée séparément de la quantité restante), `volume_recipient_litres`
(pour les sources gaz). Deux nouveaux statuts dans "État d'utilisation" :
*transférée* et *détruite* (les 4 valeurs existantes sont conservées, rien
n'est supprimé).

**Migration automatique** (`app/scripts/migrate_add_source_fields.py`,
comme pour les rôles) : ajoute ces colonnes à ta base existante au premier
démarrage. Pour `quantite_initiale`, comme cette information n'était pas
suivie avant, la migration recopie par défaut la quantité *actuelle* de tes
sources déjà existantes comme quantité initiale — c'est une approximation
(on ne peut pas deviner une vraie valeur historique qui n'a jamais été
saisie). Si tu connais les vraies quantités de départ, corrige-les
manuellement via la pop-up de modification.

### Utilisateur sur les consommations

Le CDC demandait que chaque consommation historise qui l'a faite. C'était
déjà le cas indirectement (journal d'audit), mais pas sur l'enregistrement
de consommation lui-même : corrigé (nouveau champ `utilisateur`, rétabli
via une migration automatique, vide pour les consommations déjà
enregistrées avant cet ajout puisque cette information n'existait pas encore).

### Activité totale de la source (avec une précaution importante)

Le CDC demande : *"activité totale = activité spécifique × quantité
restante"* pour les sources liquides/gazeuses. Ce calcul suppose que la
valeur d'activité saisie pour un radionucléide est une **activité
spécifique** (par gramme, par litre...) et non déjà une activité totale.

Comme rien ne permettait de distinguer les deux cas, et qu'une
multiplication par la quantité serait **fausse** si l'activité saisie est
déjà un total (elle donnerait un nombre plus grand mais dénué de sens),
j'ai ajouté une case à cocher explicite **"Cette activité est une activité
spécifique"** sur chaque radionucléide. Par défaut (case décochée), le
comportement est inchangé (l'activité est déjà considérée comme un total,
comme c'était le cas jusqu'ici pour tous les radionucléides déjà saisis).
Ce n'est que lorsque la case est cochée que la page Radionucléides calcule
et affiche l'activité totale de la source.

**À vérifier de ton côté** : comment tes collègues saisissent-ils
réellement l'activité d'un radionucléide sur une source liquide/gaz —
comme une concentration (spécifique) ou déjà comme un total ? Ça
déterminera si cette case doit être cochée par défaut pour ce type de
source, ou si le fonctionnement actuel (décoché par défaut) convient.

### Ce qui n'a pas été touché dans cette vague

Volontairement laissés pour une prochaine fois (chantiers plus lourds, pas
directement liés aux formulaires existants) : la relation N:N entre
sources et radioéléments (section 3 de l'analyse CDC), l'intégration
LaraWeb réelle, le seuil d'activité configurable pour le rôle le plus
restreint, l'adresse IP et le filtrage par période sur le journal d'audit,
la sauvegarde/restauration automatique, la recherche/tri/pagination des
tableaux, la fiche détaillée par source, l'export CSV/JSON, et bien sûr
lieux et mouvements (toujours en attente de tes précisions).

### Fichiers ajoutés ou modifiés dans cette quatrième vague

`app/models/{source,consumption,radionuclide}.py`, `app/main.py` (calcul
activité totale + migrations), `app/services/consumption.py` (utilisateur),
`app/templates/{sources,radionuclides}.html` (nouveaux champs),
`app/scripts/migrate_add_source_fields.py` (nouveau).

---

## 10. Cinquième vague de changements (08/07/2026) : lieux et emprunts

Implémenté à partir de ton exemple concret (source rangée dans l'armoire
IRMA, bâtiment 389, pièce 72 ; empruntée pour ton labo EPICEA ; sources
liquides qui restent définitivement une fois ouvertes).

### Modèle retenu

Deux notions séparées sur une source, plutôt qu'une seule :
- **Emplacement habituel** (`emplacement_habituel_id`) : son lieu de
  rangement par défaut. Se modifie directement dans sa fiche, ce n'est pas
  un emprunt.
- **Emplacement actuel** (`emplacement_actuel_id`) : où elle se trouve
  vraiment maintenant. Mis à jour automatiquement par les emprunts.

**Remarque sur une erreur de conception initiale, corrigée avant
livraison** : ma première version ne distinguait pas ces deux notions — la
toute première "mise en rangement" d'une source était traitée comme un
emprunt à part entière, qui restait "en cours" indéfiniment et bloquait
tout emprunt réel ultérieur. Je l'ai détecté en testant moi-même le
scénario complet, et corrigé en séparant clairement "où elle vit" (un champ
normal) d'"un emprunt temporaire" (avec retour).

Un lieu (`locations`) a maintenant : nom, site/service (ex. "IRMA",
"EPICEA"), bâtiment, pièce — tous facultatifs sauf le nom.

Un mouvement (`movements`) représente un **emprunt** : date de sortie
(automatique), lieu de départ (déduit automatiquement de l'emplacement
habituel — pas besoin de le préciser), lieu d'arrivée (à choisir), date de
retour *prévue* (facultative), date de retour *réelle* (remplie seulement
au retour — tant qu'elle est vide, la source est "sortie"), utilisateur,
commentaire.

**Règles appliquées** :
- Une source ne peut avoir qu'un seul emprunt ouvert à la fois (message
  clair si on tente d'en démarrer un second).
- Un emprunt exige que la source ait un emplacement habituel défini.
- Suppression d'un lieu bloquée si des sources s'y trouvent actuellement.
- Mêmes permissions que le reste de l'application (rôle lecteur : lecture
  seule ; cloisonnement Matière Nucléaire respecté ; plus besoin d'être
  administrateur, contrairement à l'ancien comportement qui réservait les
  mouvements aux admins sans raison particulière).
- Chaque emprunt et retour est journalisé dans l'audit (actions "EMPRUNT"
  et "RETOUR", ajoutées à la liste des actions valides).

**Sources liquides qui restent définitivement chez toi** : aucune règle
spéciale nécessaire — il suffit de ne jamais cliquer sur "Marquer
retourné". L'emprunt reste ouvert indéfiniment, ce qui représente
correctement "cette source vit maintenant ici".

### Testé

Cycle complet (emprunt → vérification qu'un second emprunt est bloqué →
retour → vérification du retour au lieu habituel), cloisonnement MN sur les
mouvements, modification/suppression d'un lieu, protection contre la
suppression d'un lieu occupé, rendu des 3 pages concernées.

### Limite assumée

Un emprunt ne gère qu'un aller-retour simple (lieu habituel ↔ un autre
lieu), pas une chaîne à plusieurs étapes (lieu A → B → C sans repasser par
le lieu habituel). D'après ta description, ce n'est pas ton usage courant ;
dis-moi si j'ai mal évalué ce point.

### Fichiers ajoutés ou modifiés dans cette cinquième vague

`app/models/{location,movement,source,audit}.py`,
`app/repositories/{location,movement}.py`, `app/services/movement.py`
(nouveau), `app/routes/{locations,movements,sources}.py`, `app/main.py`,
`app/templates/{locations,movements,sources}.html`,
`app/scripts/migrate_add_locations_movements.py` (nouveau).

---

## 11. Sixième vague de changements (09/07/2026) : archivage des sources

À ta demande : une source remisée, en déchet, transférée ou détruite sort
de la circulation active.

### Ce qui a été fait

- La liste principale des sources (`/sources`) ne montre plus que les
  sources actives (en utilisation, en attente).
- Nouvelle page **Archives des sources** (`/sources/archive`, lien depuis
  la page Sources) listant les sources dans les 4 états archivés.
- Une source archivée n'apparaît plus dans les menus déroulants "ajouter un
  radionucléide", "enregistrer une consommation", "démarrer un emprunt" —
  et ces trois actions sont explicitement bloquées côté serveur si on tente
  de les forcer (message clair, pas une erreur brute).
- Modifier une source déjà archivée est réservé aux **administrateurs**
  (tous les autres rôles reçoivent un message explicite), y compris pour la
  remettre en circulation en repassant son état sur "En utilisation" ou "En
  attente" — c'est le mécanisme de correction d'erreur que tu as demandé.
- L'historique déjà existant (radionucléides, consommations, mouvements
  déjà enregistrés) d'une source archivée reste visible normalement : seule
  la création de nouvelles entrées est bloquée, rien n'est masqué a
  posteriori.

### Un bug de routage trouvé et corrigé en testant

En testant la nouvelle page `/sources/archive`, j'ai découvert qu'elle
répondait "Source non trouvée" au lieu de s'afficher : FastAPI, en cas de
chemins qui se ressemblent, retient la première route déclarée qui
correspond — et la route de l'API `GET /sources/{id}` (déclarée tôt dans le
fichier) interceptait `/sources/archive` en comprenant "archive" comme un
identifiant de source, avant même que la page ne soit essayée. Corrigé en
déplaçant l'inclusion des routes d'API après toutes les pages du site
(aucun changement visible pour toi, sauf que ça fonctionne).

### Non traité (hors périmètre de ta demande)

Export des archives (CSV/JSON/Excel) : reste sur la liste plus large des
exports non encore implémentés (section 9 de l'analyse CDC).

### Fichiers ajoutés ou modifiés dans cette sixième vague

`app/models/source.py` (états archivés), `app/repositories/source.py`,
`app/routes/sources.py`, `app/routes/radionuclides.py`,
`app/services/{consumption,movement}.py`, `app/main.py` (nouvelle page +
réorganisation du routage), `app/templates/sources.html` (lien),
`app/templates/sources_archive.html` (nouveau).

---

## 12. Septième vague de changements (10/07/2026) : import / export

À partir du vrai fichier d'inventaire que tu as fourni (13 feuilles
examinées en détail).

### Import

Nouveau module `app/services/inventory_import.py`, accessible depuis la
page **Import/Export** (upload direct) ou en ligne de commande
(`python -m app.scripts.import_inventaire fichier.xlsx`). Importe les 3
feuilles "Sources scellées", "Sources non scellées", "Sources
consommables" — j'ai délibérément exclu "Sources scellees à verifier" de
l'import automatique : à la lecture, c'est une liste de contrôle
périodique dérivée de "Sources scellées" (5 lignes, sous-ensemble), pas une
quatrième catégorie de sources à part entière. Dis-moi si je me trompe.

**Choix de correspondance principaux** (colonne fichier → champ
application) :
- N° IRSN → identifiant de la source (utilisé tel quel, pas régénéré)
- ETAT (S/NS) → type scellée/non-scellée
- MN, RADIONUCLEIDE, ACTIVITE NOMINALE, PERIODE (S, convertie en années),
  FOURNISSEUR → champs équivalents déjà existants
- ACTIVITE SPECIFIQUE NOMINALE (Bq/g), utilisée à la place de l'activité
  nominale quand celle-ci est absente → coche automatiquement "activité
  spécifique"
- LIEU DE STOCKAGE (site/bâtiment/pièce) + ARMOIRE DE STOCKAGE → un Lieu
  structuré (dédupliqué : même armoire = même lieu réutilisé, pas recréé à
  chaque ligne), utilisé comme emplacement habituel *et* actuel de la
  source
- RAPPORT QUANTITE RESTANTE/INITIALE, quand la masse est connue → sert à
  recalculer la quantité initiale
- Tout le reste sans champ dédié (code GISEL, n° compte UES, réf.
  catalogue, mode de décroissance, radiotoxicité, date de contrôle
  d'étanchéité, date de fabrication, devenir, infos diverses...) → regroupé
  dans le commentaire de la source, pour ne rien perdre silencieusement

**Deux choix qui méritaient réflexion plutôt qu'un raccourci pris à
l'aveugle**, trouvés en étudiant le fichier réel :
- **Le statut à l'import** : j'ai d'abord voulu déduire le statut
  (actif/remisé/...) de la colonne "DEVENIR" — erreur évitée en testant :
  DEVENIR décrit une destination *prévue* (ex: "retour autorisé"), pas
  l'état *actuel*. Comme les 3 feuilles importées sont par construction les
  sources actives de l'inventaire (les archivées sont dans des feuilles
  "...ARCHIVES" séparées, non importées), toutes les sources importées le
  sont avec le statut "en utilisation".
- **L'état physique** (solide/liquide/gaz) : aucune colonne dédiée dans le
  fichier. Déduit du texte libre ("Informations diverses") quand il
  contient "gaz"/"liquide" ; sinon, solide par défaut pour "Sources
  scellées", liquide par défaut pour les deux autres feuilles (choix le
  plus probable pour ce contexte, mais un vrai défaut, pas une certitude).
  Chaque cas deviné est listé dans les avertissements du rapport d'import.

**Testé sur ton fichier réel** : 33 sources importées, 2 doublons
d'identifiant détectés dans le fichier lui-même et correctement ignorés
(CEA-2023-01 et CEA-2023-03 apparaissent chacun deux fois), 0 erreur, 7
lieux créés (dédupliqués), décroissance radioactive vérifiée correcte sur
les données réelles importées (ex : 85-Kr, activité recalculée cohérente
avec sa période de 10,7 ans).

### Export

- **Liste des sources** (`app/scripts/export_excel.py`, enrichi) : deux
  feuilles (Sources avec tous les champs actuels, Radionucléides),
  actives + archivées.
- **Annexe 1** (`app/services/export_annexe1.py`, nouveau) : la mise en
  forme officielle du formulaire ("DSM/SAC/CCSIMN/MN/PR/01") est
  réutilisée à l'identique (extraite de ton fichier et conservée comme
  modèle dans `app/resources/annexe1_template.xlsx`), avec uniquement les
  colonnes fiables pré-remplies (désignation, nombre, masse si connue) pour
  chaque source Matière Nucléaire — le reste (colonnes de mesure physique)
  reste volontairement vide.

### Non traité (comme convenu)

Tableaux MN 1a/2a/3a : nécessitent soit un suivi des teneurs isotopiques
et une catégorisation réglementaire précise (1a), soit une donnée externe
à laquelle l'application n'a pas accès — la comptabilité nationale de
l'IRSN (2a/3a). En attente de ton retour sur l'usage réel de la page
Import/Export avant d'y revenir.

### Fichiers ajoutés dans cette septième vague

`app/services/inventory_import.py`, `app/services/export_annexe1.py`,
`app/scripts/import_inventaire.py`, `app/routes/import_export.py`,
`app/resources/annexe1_template.xlsx`, `app/templates/import_export.html`,
`app/scripts/export_excel.py` (enrichi), `app/main.py`,
`app/templates/base.html` (lien menu).

---

## 13. Correctif urgent (10/07/2026) : le menu ne reconnaissait plus la connexion

Tu as signalé un problème d'accès (page d'accueil montrant le formulaire
d'ajout de source de façon incohérente, menu affichant uniquement
Connexion/Inscription après connexion). J'ai reproduit précisément le
scénario avant de corriger.

**Cause trouvée** : dans `base.html` (le gabarit commun à toutes les
pages), le lien "Audit" testait `current_user.role.value` **sans vérifier
d'abord que `current_user` n'était pas vide** — contrairement à tous les
autres tests similaires du même fichier, qui commencent bien par
`current_user and ...`. Cet oubli remonte au moment où j'avais ouvert
l'audit aux utilisateurs MN (en plus des admins).

**Conséquence réelle, empiriquement confirmée** : pour un visiteur non
connecté, cette ligne provoquait une erreur (`'None' has no attribute
'role'`), qui faisait planter **toute la page en HTTP 500** — y compris,
plus grave, la page de connexion elle-même (`/auth/login`), puisqu'elle
utilise aussi ce gabarit commun. Un visiteur non connecté qui essayait de
consulter une page protégée (donc redirigé vers la connexion) tombait
ensuite sur une page de connexion cassée.

**Corrigé**, et vérifié par un test complet reproduisant ton scénario
(compte de test avec le même profil que GDO — rôle utilisateur_mn issu de
la migration) : page d'accueil anonyme à nouveau HTTP 200, page de
connexion HTTP 200, et après connexion le menu affiche bien "Connecté(e) :
[nom]" avec les liens attendus pour ce rôle.

**Par précaution**, j'ai aussi ajouté ce même garde-fou (`current_user
and ...` avant tout `current_user.role...`) à tous les autres endroits
similaires du site (Sources, Radionucléides, Consommations, Mouvements,
Lieux, Archives des sources) — ils n'étaient pas concrètement cassés
(leurs pages redirigent déjà les visiteurs non connectés avant d'afficher
le contenu), mais autant fermer cette catégorie de bug partout plutôt que
d'attendre qu'elle se reproduise ailleurs.

### Fichiers modifiés

`app/templates/base.html`, `app/templates/{sources,radionuclides,
consumptions,movements,locations,sources_archive}.html`.

---

## 14. Tests automatisés (10/07/2026)

Le bug de la section 13 (détecté manuellement, par toi) a montré la limite
d'une vérification uniquement manuelle sur une application qui grandit.
J'ai construit une première suite de tests automatisés (`tests/`,
`pytest`), absente jusqu'ici (c'était un des manques identifiés dès
l'analyse du CDC initial).

**59 tests, tous passants**, organisés en 3 fichiers :
- `test_pages_smoke.py` : vérifie qu'**aucune page ne plante jamais**
  (erreur 500), pour chaque page × chaque état de connexion (anonyme,
  lecteur, utilisateur MN). C'est le test qui aurait détecté le bug de la
  section 13 en une fraction de seconde — je l'ai vérifié concrètement en
  réintroduisant temporairement le bug : il échoue exactement sur les 3
  pages concernées, puis repasse au vert une fois corrigé.
- `test_sources_permissions.py` : création/modification/suppression de
  sources, cloisonnement Matière Nucléaire par rôle, archivage et
  protection contre la modification d'une source archivée par un
  non-administrateur.
- `test_consumption_movement.py` : règles de consommation (types gaz/
  liquide uniquement, quantité insuffisante refusée), cycle complet
  emprunt → blocage d'un second emprunt → retour → nouvel emprunt possible.

**Un vrai bug supplémentaire trouvé en construisant ces tests**, distinct
de celui de la section 13 : le cookie de session avait une durée de vie
(`Max-Age`) exprimée en nombre à virgule (ex. `1800.0`) plutôt qu'en entier
comme l'exige la norme des cookies HTTP. Les navigateurs et `curl` sont
tolérants et l'acceptaient quand même, ce qui fait qu'il n'a jamais causé
de souci que tu aies pu observer — mais un client plus strict (celui
utilisé par les tests automatisés) le refusait purement et simplement,
rendant la connexion inopérante à ses yeux. Corrigé (`app/routes/auth.py`).

Pour lancer les tests : voir README, section 9. À exécuter après chaque
modification, avant de considérer un changement terminé — je vais
maintenant m'en servir moi-même systématiquement plutôt que de tout
revérifier manuellement à chaque fois.

### Fichiers ajoutés

`tests/__init__.py`, `tests/conftest.py`, `tests/test_pages_smoke.py`,
`tests/test_sources_permissions.py`, `tests/test_consumption_movement.py`.

### Fichiers modifiés

`app/routes/auth.py` (cookie Max-Age), `pyproject.toml` (dépendance httpx
pour les tests).

---

## 15. V0.1.6 (10/07/2026) : versionnage, cache CSS, devenir admin facilement

Trois retours traités.

### Numéro de version visible partout

Demandé pour ne plus jamais avoir de doute sur la version réellement
testée. Le numéro (`app/version.py`, actuellement `0.1.6`) s'affiche
désormais en bas de chaque page. Je l'incrémenterai à chaque livraison à
partir de maintenant — vérifie-le systématiquement en cas de doute.

### Pop-up qui ne s'affichaient plus comme des pop-up

Le CSS des pop-up (`app/static/style.css`) était bien présent et
correctement servi par le serveur — j'ai vérifié précisément (contenu de la
réponse HTTP). L'explication la plus probable est donc un cache navigateur
ayant gardé une ancienne version de ce fichier CSS (d'avant l'ajout des
pop-up), plutôt qu'un vrai bug applicatif.

**Corrigé structurellement plutôt que de simplement te demander de vider
ton cache une fois** : le lien vers le CSS inclut maintenant le numéro de
version (`style.css?v=0.1.6`). À chaque changement de version, le
navigateur considère que c'est un fichier différent et le retélécharge
automatiquement — ce type de souci ne peut plus se reproduire à l'avenir,
même sans action de ta part.

### Devenir administrateur sans compte de démo séparé

Avant : la seule façon d'obtenir un premier compte admin était de créer un
compte séparé "admin" via `seed_db.py`, séparé de ton compte réel. Nouveau
script dédié :

```bash
python -m app.scripts.promote_admin ton_nom_utilisateur
```

Promeut directement un compte déjà existant (le tien) en admin. Sans effet
si le compte est déjà admin ; message clair si le nom n'existe pas encore
(il faut d'abord s'inscrire via `/auth/register`).

### Fichiers ajoutés

`app/version.py`, `app/scripts/promote_admin.py`.

### Fichiers modifiés

`app/main.py` (version exposée à tous les templates), `app/templates/base.html`
(affichage version + cache-busting CSS).

---

## 16. V0.1.7 (10/07/2026) : Annexe 1 complète

D'après tes indications précises sur le mapping des colonnes.

### Règles appliquées

- **Codes matière (EUR / National)**, déduits automatiquement du nom du
  radionucléide (format "233-U", "239-Pu"...) :
  - U-233 → K / V
  - Plutonium (tout isotope) → P / P
  - Thorium (tout isotope) → T / T
  - Uranium hors 233 → N / N
  - H-3 (tritium) → pas de code
  - Tout autre radionucléide (pas une matière nucléaire au sens de ce
    tableau, ex. Cs-137) → pas de code, mais la ligne reste générée si la
    source est marquée Matière Nucléaire.
- **Une ligne par radionucléide**, pas par source : une source Matière
  Nucléaire contenant 2 radionucléides différents donne 2 lignes (même
  désignation/référence catalogue, codes et masses différents).
- **Masse en radioélément** : calculée par la vraie formule physique
  (activité = ln2/période × (masse/masse molaire) × nombre d'Avogadro,
  résolue pour la masse), à partir de **l'activité actuelle** (décroissance
  déjà appliquée), comme demandé — pas l'activité de référence/initiale.
  Vérifiée contre une valeur de référence connue (activité massique du
  Pu-239, ≈ 2,3 GBq/g) avant de considérer le calcul fiable. Les masses
  molaires des isotopes concernés (H-3, Th-232, U-233/234/235/238,
  Pu-238 à 242) sont des constantes physiques, indépendantes de tes
  données (`app/services/matieres_nucleaires.py`).
- **Désignation** = identifiant de la source ; **Identification** =
  référence catalogue (nouveau champ dédié sur la source, `reference_catalogue`
  — avant noyé dans le commentaire lors de l'import, maintenant un vrai
  champ modifiable depuis la fiche d'une source) ; **nombre** = toujours 1 ;
  **Date** = date de référence du radionucléide ; **Masse de source** =
  quantité de la source (masse ou pression selon le cas).

### Toujours en suspens (à préciser)

- Colonne "Teneur en éléments %" : pas de donnée correspondante actuellement.
- Colonne "Total par matière" : semble être un agrégat (somme par matière),
  pas une valeur ligne par ligne — à confirmer avant implémentation.
- Codes matière pour Deutérium et Lithium-6 enrichi (présents dans le
  Tableau 1a, mais pas mentionnés dans tes indications) : pas encore
  couverts.

### Testé

6 nouveaux tests automatisés sur le module de calcul (dont la vérification
contre la référence Pu-239, et une vérification inverse de la formule
physique elle-même) ; test manuel avec une source portant 5 radionucléides
différents (un par catégorie de code) : codes, désignation, référence
catalogue et masses calculées tous corrects ; mise en forme du gabarit
officiel toujours intacte après remplissage.

### Fichiers ajoutés

`app/services/matieres_nucleaires.py`, `tests/test_matieres_nucleaires.py`.

### Fichiers modifiés

`app/models/source.py` (champ `reference_catalogue`), `app/services/export_annexe1.py`
(réécrit), `app/services/inventory_import.py` (utilise le nouveau champ),
`app/templates/sources.html` (champ ajouté au formulaire),
`app/scripts/migrate_add_locations_movements.py`.

---

## 17. V0.1.8 (10/07/2026) : LaraWeb réel + Tableau 1a

### LaraWeb

Recherche effective de la vraie structure du site avant d'écrire le code
(plutôt que de deviner à partir du CDC, qui s'est révélé indiquer une URL
obsolète : `/Laraweb/Results/` au lieu de la vraie `/nuclides/`). Format
confirmé sur plusieurs nuclides réels (Sr-90, Pu-239, U-235, Po-212,
Ra-226...) avant d'écrire le parseur.

- `app/services/laraweb.py` (entièrement réécrit) : récupère et analyse le
  fichier texte du nuclide, extrait la période (déduite de la ligne
  "Half-life (s)", toujours présente et en unité fiable, plutôt que la
  ligne "Half-life (a/d/h)" qui n'existe pas pour toutes les demi-vies) et
  l'activité massique ("Specific activity (Bq/g)").
- Mise en cache locale (table `lara_cache`, comme prévu au CDC) : pas
  d'expiration automatique (ces données n'évoluent pas), actualisation
  manuelle possible (`?actualiser=true`).
- Bouton "Chercher sur LaraWeb" sur le formulaire d'un radionucléide :
  pré-remplit la période automatiquement.
- L'activité massique récupérée est réutilisée en priorité (plus précise,
  plus d'isotopes couverts) dans le calcul de masse pour l'Annexe 1 et le
  Tableau 1a, avec repli sur le calcul physique par masse molaire si
  l'isotope n'est pas encore en cache.

**Limite de test à connaître** : mon environnement de développement a un
accès réseau restreint à une liste blanche de domaines, qui n'inclut pas
lnhb.fr. Je n'ai donc pas pu tester la requête réseau réelle depuis mon
bac à sable. Ce que j'ai fait à la place : récupéré manuellement de vraies
réponses du site (via un autre outil de recherche web dont je dispose), et
testé le parseur ainsi que tout le circuit fetch→cache→API avec ces
vraies données mais une requête réseau simulée. Le code de requête
lui-même (`requests.get`) est standard et direct. À vérifier une fois en
conditions réelles chez toi — dis-moi si ça coince.

### Tableau 1a

`app/services/export_tableau1a.py` (nouveau) : réutilise les mêmes calculs
de masse que l'Annexe 1, les agrège par catégorie de matière et par lieu
(IRMA / EPICEA / Total, déduit du "site" de l'emplacement actuel de la
source), et catégorise automatiquement l'uranium par bande d'enrichissement
à partir des proportions de l'uranium naturel indiquées le 10/07/2026
(99,2742 % U-238, 0,7202 % U-235, 0,0055 % U-234 — voir
`app/services/matieres_nucleaires.py::categoriser_uranium`, tolérance de
±0,05 point autour de la valeur naturelle exacte).

Une source Matière Nucléaire dont le lieu actuel n'est ni IRMA ni EPICEA
(ou dont le lieu n'est pas suivi) est comptée dans la colonne "Total"
uniquement, avec un avertissement (actuellement remonté dans un en-tête
HTTP de la réponse, pas encore affiché proprement dans l'interface — à
améliorer si tu veux plus de visibilité dessus).

Deutérium et Lithium-6 enrichi : isotopes stables, donc sans "activité" —
ces deux lignes du tableau resteront toujours à zéro avec l'approche
actuelle (basée sur la décroissance radioactive). Je n'ai pas de solution
immédiate à proposer sans une saisie de masse directe dédiée.

### Testé

10 nouveaux tests automatisés : parseur LaraWeb contre 3 nuclides réels
(cas normal, cas de demi-vie très courte, cas de réponse invalide),
pipeline complet avec réseau simulé (vérifie aussi que le deuxième appel
utilise bien le cache sans refaire de requête), catégorisation uranium sur
les 5 bandes, et un test de bout en bout du Tableau 1a avec une source de
Plutonium et une source d'uranium reconstituée exactement à 30 %
d'enrichissement (donc "≥20 %") — vérifié cellule par cellule, y compris
la colonne séparée pour la masse d'U-235 seul. Complété par une
vérification manuelle sur serveur réel avec examen ligne par ligne du
fichier Excel généré, et test du cas d'avertissement (source hors
IRMA/EPICEA).

### Fichiers ajoutés

`app/models/lara_cache.py`, `app/routes/laraweb.py`,
`app/services/export_tableau1a.py`, `app/resources/tableau1a_template.xlsx`,
`tests/test_laraweb.py`, `tests/test_tableau1a.py`.

### Fichiers modifiés

`app/services/laraweb.py` (réécrit), `app/services/__init__.py`,
`app/services/matieres_nucleaires.py` (catégorisation uranium + masse
depuis activité spécifique), `app/services/export_annexe1.py` (priorité
LaraWeb), `app/scripts/migrate_add_locations_movements.py` (table
lara_cache), `app/main.py`, `app/routes/__init__.py`,
`app/templates/radionuclides.html` (bouton LaraWeb),
`app/templates/import_export.html` (bouton Tableau 1a),
`app/routes/import_export.py`.

---

## 17. V0.1.9 (10/07/2026) : refonte de l'interface

D'après ta liste de suggestions ("au débotté"), avec quelques choix de
conception que j'ai dû trancher moi-même — détaillés ci-dessous.

### Système visuel

Avant de coder, un vrai système de design plutôt qu'un habillage au cas
par cas : palette encre bleu-nuit (barre latérale) + accent sarcelle
(boutons, liens, éléments actifs) + doré discret réservé aux badges
Matière Nucléaire, typographie IBM Plex (Sans pour l'interface, Mono pour
les identifiants/valeurs — activités, dates, ID de sources). Choix
délibéré pour ne pas tomber dans les rendus "par défaut" d'une interface
générée (fond crème + serif + terracotta, ou noir + accent acide).

### Structure

- **Barre latérale** (gauche, fixe) : Sources, Mouvements, Consommations,
  Import/Export et Audit (ces deux dernières visibles par les admins et
  utilisateurs MN uniquement). Repliable sur mobile/écran étroit.
- **Bandeau** (haut) : menu utilisateur avec le rôle affiché, accès à la
  gestion des utilisateurs pour les admins, déconnexion.
- **"/"** redirige maintenant directement vers `/sources` (connecté) ou
  `/auth/login` (anonyme) — plus de page d'accueil séparée, la page
  Sources devient le vrai point d'entrée. `index.html` supprimé (plus
  utilisé par aucune route).

### Page Sources

- Trois onglets **Scellées / Consommables / Non scellées**, calculés à
  partir du type et de l'état physique de chaque source (une source
  scellée va dans "Scellées" ; une non-scellée gaz ou liquide va dans
  "Consommables" ; le reste dans "Non scellées").
- Filtre de statut (case à cocher par statut, "En utilisation" + "En
  attente" cochés par défaut) qui **remplace la page Archives séparée** :
  décocher les statuts actifs et cocher les statuts archivés donne
  exactement la même liste qu'avant sur `/sources/archive` (page toujours
  présente, gardée en secours, mais plus mise en avant).
- Deux boutons directs, comme demandé : **+ Ajouter une source** et
  **+ Ajouter un Rn** (nouvelle pop-up avec sélecteur de source et
  recherche LaraWeb intégrée, sans quitter la page).

### Page Mouvements

Bouton **+ Lieu** (pop-up de création rapide) en plus du bouton d'emprunt.
La page dédiée `/locations` reste accessible via un lien ("Gérer tous les
lieux") pour la modification/suppression d'un lieu existant.

### Export ouvert aux utilisateurs MN

Nouvelle permission `require_admin_or_mn` (`app/security/permissions.py`),
appliquée aux 3 routes d'export (liste des sources, Annexe 1, Tableau 1a)
et à la page Import/Export elle-même. **L'import reste réservé aux
administrateurs** (opération de masse, risque différent) — la section
import est masquée côté template pour un utilisateur MN, pas seulement
protégée côté serveur.

### Page Audit

Filtre par type de modification (CREATE/UPDATE/DELETE/UTILISATION/
EMPRUNT/RETOUR) et par table concernée, tri par date (récent/ancien
d'abord). **Bug préexistant corrigé au passage** : la colonne Action
affichait littéralement "AuditAction.CREATE" au lieu de "CREATE" depuis la
toute première version de cette page — jamais repéré parce que je testais
surtout l'API, pas la page elle-même à l'œil. Trouvé en construisant le
filtre (qui a besoin de la valeur propre pour fonctionner), corrigé
partout où le même oubli (`.value` manquant) pouvait exister.

### Choix non explicitement demandés, à valider

- Les alertes JavaScript de confirmation ("Source ajoutée avec succès !")
  ont été retirées un peu partout : le rechargement de page suffit à
  montrer que ça a fonctionné, et ça correspond mieux à une interface qui
  ne "parle" pas plus que nécessaire. Dis-moi si tu préfères les
  retrouver.
- "Ajouter un Rn" depuis la page Sources exige quand même de choisir une
  source dans une liste déroulante (impossible de rattacher un
  radionucléide à rien) : je n'ai pas trouvé de moyen plus direct sans
  contexte supplémentaire (par exemple, ouvrir depuis la ligne d'une
  source précise plutôt que depuis un bouton général).

### Testé

Les 76 tests automatisés existants adaptés et repassés au vert (2 tests
mis à jour pour refléter le nouveau comportement intentionnel de "/" qui
redirige désormais, plus 1 nouveau test sur l'accès export MN). Suite
complète des 8 pages vérifiée manuellement sur serveur réel : chargement,
JavaScript de chaque page validé syntaxiquement, classement correct dans
les 3 onglets testé avec une source de chaque catégorie, export vérifié
pour un compte MN non-admin, import vérifié bloqué pour ce même compte,
mise en surbrillance du lien actif dans la barre latérale vérifiée.

### Fichiers ajoutés

`app/static/style.css` (réécrit intégralement).

### Fichiers modifiés

`app/main.py` ("/" redirige, permission audit/export, contexte audit),
`app/security/permissions.py` (nouvelle permission `require_admin_or_mn`),
`app/templates/base.html` (réécrit), `app/templates/sources.html`
(réécrit), `app/templates/movements.html` (réécrit), `app/templates/audit.html`
(réécrit), `app/templates/import_export.html` (réécrit),
`app/templates/{radionuclides,consumptions,locations,sources_archive,users}.html`
(mise en page), `app/templates/auth/{login,register}.html` (réécrits),
`app/routes/import_export.py` (permission export), `tests/test_pages_smoke.py`
(2 tests adaptés), `tests/test_laraweb.py` (1 test ajouté).

### Fichiers supprimés

`app/templates/index.html` (plus référencé par aucune route).

---

## 18. V0.1.10 (10/07/2026) : 5 retours sur l'IHM

### (1) Audit trop imprécis

Avant : modifier une source produisait un seul événement générique
("toutes les valeurs"). Maintenant : un événement par champ **réellement**
modifié, avec sa valeur avant et après (ex : `etat_utilisation` : "en
utilisation" → "en déchet"). Un champ envoyé par le formulaire mais
identique à l'existant ne produit plus d'entrée trompeuse. Testé
(`test_audit_precis_par_champ_modifie`, `test_audit_ignore_les_champs_fournis_mais_inchanges`).

### (2) Lieu de stockage / emplacement habituel redondants

Le champ texte libre "Lieu de stockage" est retiré du formulaire (la
colonne reste en base pour ne pas perdre les données déjà importées, mais
n'est plus utilisée). **L'emplacement habituel devient obligatoire à la
création d'une source** — ta remarque était juste, c'est plus logique
ainsi. Un 3ᵉ bouton "+ Lieu" sur la page Sources (identique à celui de
Mouvements) permet de créer un lieu sans quitter la page, pour ne pas se
retrouver bloqué. Le tableau n'affiche plus que l'emplacement **actuel**
(plus de colonne "habituel" séparée).

### (3) Quantité restante : calculée, plus saisie

Changement le plus structurant. La quantité restante n'est plus un champ
du formulaire : elle est **calculée** à partir de l'activité actuelle du
radionucléide (décroissance, comme pour l'Annexe 1/Tableau 1a) moins la
somme des consommations déjà enregistrées.

**Ta question sur les unités et multiples était fondée — vrai manque
corrigé au passage.** Jusqu'ici, une activité saisie "150" avec l'unité
"MBq" était utilisée telle quelle en interne, comme si c'était 150 Bq
(facteur ×10⁶ ignoré). Nouveau module `app/services/units.py` qui reconnaît
les préfixes n, µ/u, m, k, M, G, T sur Bq, Bq/g, Bq/m3, Bq/L, Bq/mL, Bq/cm3,
et normalise systématiquement avant tout calcul. **Ce bug touchait aussi
les exports Annexe 1 et Tableau 1a déjà livrés** (corrigé au même endroit).
Testé unitairement (5 tests) et vérifié manuellement sur le serveur réel
(150 MBq → affiché "148 MBq" après décroissance, pas "148 Bq").

Simplification assumée, à valider à l'usage : si une source a plusieurs
radionucléides, seul le premier sert à ce calcul (en pratique une source
consommable n'en a normalement qu'un). La consommation vérifie maintenant
la quantité calculée en priorité, avec repli sur l'ancien mécanisme
(champ stocké, décrémenté directement) pour les sources qui n'ont pas de
radionucléide exploitable — notamment celles importées avant ce
changement, dont beaucoup n'ont pas de masse molaire connue.

### (4) Renommage et navigation

"Rn" → "radionucléide" partout dans l'interface. Lien "Gérer tous les
radionucléides →" ajouté sur la page Sources (pendant du lien "Gérer tous
les lieux →" déjà présent sur Mouvements).

### (5) Radionucléides et activité visibles sur la page Sources

Nouvelle colonne listant, pour chaque source, ses radionucléides avec leur
activité **actuelle** (décroissance appliquée), normalisée et affichée
avec le préfixe le plus lisible (ex : "148 MBq", pas "148000000 Bq"). Les
quantités (ex. 3/5g) ne sont pas encore affichées, comme convenu ("on
verra à l'usage").

### Deux corrections de bugs d'édition trouvées en cours de route

Deux fois pendant cette vague, une insertion de nouvelle fonction dans un
fichier existant a accidentellement effacé la ligne de signature de la
fonction suivante (`def admin_client(...)` dans les tests, puis `def
activite_actuelle_bq(...)` dans le nouveau module d'unités) — repéré
immédiatement par la suite de tests (erreurs "fixture not found" /
`NameError`), corrigé avant de continuer. Mentionné par souci de
transparence : la suite de tests a fait exactement ce pour quoi elle a été
construite.

### Testé

86 tests automatisés (5 nouveaux sur les unités, 2 sur l'audit précis, 2
sur le lieu obligatoire, 1 sur la quantité calculée). Vérification manuelle
complète sur serveur réel : création d'une source sans lieu_stockage,
ajout d'un radionucléide en MBq et vérification de son affichage décroissant
correctement normalisé, bouton "+ Lieu" fonctionnel depuis Sources,
absence confirmée des champs retirés (lieu de stockage, quantité éditable,
colonne emplacement habituel).

### Fichiers ajoutés

`app/services/units.py`, `tests/test_units.py`.

### Fichiers modifiés

`app/models/source.py` (lieu_stockage facultatif, emplacement_habituel_id
obligatoire à la création, quantite_calculee), `app/repositories/source.py`
(défaut lieu_stockage), `app/routes/sources.py` (audit précis, validation
du lieu, quantite_calculee), `app/services/consumption.py` (vérification
contre la quantité calculée), `app/services/matieres_nucleaires.py`
(fonction commune `masse_radionuclide_g`), `app/services/export_annexe1.py`
et `export_tableau1a.py` (utilisent l'activité normalisée + la fonction
commune), `app/main.py` (calculs pour l'affichage), `app/templates/sources.html`
(réécrit), `tests/conftest.py` (fixture `default_location`),
`tests/test_sources_permissions.py`, `tests/test_consumption_movement.py`,
`tests/test_tableau1a.py` (lieu obligatoire injecté).

---

## 19. V0.1.11 (11/07/2026) : robustesse de l'import, second fichier réel

À partir d'un deuxième fichier d'inventaire réel que tu as fourni
(différent du premier, "Inv Int Sources SCA CMo avril-2016"), analysé en
détail avant de toucher au code — comme pour le premier.

### Ce qui n'allait pas, trouvé en important réellement ce fichier

- **0 radionucléide importé** : les libellés de colonnes d'activité
  diffèrent légèrement entre les deux fichiers ("ACTIVITE NOMINALE [4]"
  ici contre "ACTIVITE NOMINALE (BQ)" dans le premier ; même chose pour
  "ETAT [2]"/"ETAT", "DATE ARRIVEE SERAC"/"DATE ARRIVEE SCA") — la
  correspondance par égalité stricte échouait silencieusement, sans la
  moindre erreur ni avertissement. **Corrigé : la correspondance des
  colonnes se fait maintenant par préfixe**, insensible à ces variantes.
- **"0 non-scellée" alors que 32 sources avaient été importées** : ces 32
  sources (Pu-239, Am-241, Cm-244...) étaient bien créées, mais avec un
  état physique deviné par défaut à "liquide" (calé sur le premier
  fichier), ce qui les faisait apparaître dans l'onglet "Consommables" au
  lieu de "Non scellées". **Corrigé : "Sources non scellées" défaut
  maintenant à "solide"** (comme "Sources scellées") ; seule "Sources
  consommables" garde le défaut liquide.
- **Sources "mélange" incomplètes** : certaines sources (ex :
  "MELANGE Multi-ALPHA") ont chacun de leurs isotopes sur une ligne
  séparée, l'identifiant n'étant renseigné que sur la première ligne. Les
  lignes suivantes (sans identifiant) étaient jusqu'ici purement ignorées.
  **Corrigé : une ligne sans identifiant mais avec un radionucléide est
  désormais rattachée à la source précédente** — à une condition
  importante : **seulement si elle n'a pas non plus de date d'arrivée**.
  Trouvé en testant : une ligne peut aussi être une source à part entière
  ayant simplement perdu son identifiant (une vraie source Am-241 de 1997
  avait un identifiant réduit à un espace) ; si je l'avais rattachée
  aveuglément à la source précédente, j'aurais silencieusement corrompu
  les données de cette dernière. Ce genre de ligne est maintenant signalé
  comme orpheline dans les avertissements plutôt que rattaché à tort ou
  perdu silencieusement.
- **Identifiant réduit à un espace** : une cellule contenant uniquement un
  espace passait le test de non-vacuité avant le nettoyage (`.strip()`),
  produisant une source avec un identifiant vide en base. Corrigé (le test
  se fait maintenant après nettoyage).

### Import de l'export de l'application elle-même

Comme demandé, l'import reconnaît maintenant aussi le format que
l'application exporte elle-même (feuille "Sources", correspondance directe
champ à champ) — permet de réimporter un fichier précédemment exporté
(fusion depuis une autre instance, restauration partielle...). Trouvé en
testant ce cas précisément : `export_sources_to_excel()` ne prenait pas la
session de base de données en paramètre (contrairement à `generer_annexe1`/
`generer_tableau1a`), utilisait donc toujours la vraie base plutôt que
celle de la requête en cours — incohérent, et impossible à tester
proprement. Corrigé au passage.

### Audit de l'import

Chaque import (par le site ou en ligne de commande) crée maintenant une
entrée d'audit (action "IMPORT") résumant le nombre de sources/radionucléides
créés et les feuilles traitées, avec le nom du fichier réellement uploadé
(pas le nom de fichier temporaire technique).

### Vérifié à trois reprises avant de considérer le travail terminé

1. Le nouveau fichier (avril-2016) : 240 sources créées (241 avant
   correction du bug d'identifiant vide), 260 radionucléides, correctement
   répartis dans les 3 onglets de l'interface.
2. Le premier fichier (format "ACTIVITE NOMINALE (BQ)", en-tête ligne 2) :
   reproduit synthétiquement (le fichier original n'était plus dans mes
   fichiers de travail, cette conversation étant très longue) et réimporté
   avec succès, aucune régression.
3. Cycle complet export → réimport : nombres de sources et radionucléides
   strictement identiques des deux côtés.

### Fichiers ajoutés

`tests/test_inventory_import_robustesse.py` (5 tests).

### Fichiers modifiés

`app/services/inventory_import.py` (réécrit en profondeur), `app/models/audit.py`
(action IMPORT), `app/routes/import_export.py` (utilisateur + nom de
fichier pour l'audit, session db passée à l'export), `app/scripts/export_excel.py`
(accepte une session db en paramètre), `app/scripts/import_inventaire.py`,
`app/templates/import_export.html`.

---

## 20. V0.1.12 (11/07/2026) : 6 modifications

### (1) Fusion de lieux

Nouveau bouton "Fusionner" sur chaque lieu (page Lieux) : choisir un lieu
cible, confirmation explicite obligatoire ("Es-tu sûr ?..."), puis toutes
les sources (emplacement habituel ET actuel) et tous les mouvements
référençant le lieu fusionné sont réaffectés au lieu cible, qui est
ensuite supprimé. Actions tracées dans l'audit.

### (2) Mot de passe et demande de changement de rôle

Deux nouvelles options dans le menu utilisateur (bandeau, en haut à
droite) : "Changer mon mot de passe" (nécessite l'ancien) et "Demander un
changement de rôle" (avec message facultatif pour l'admin). Les demandes
apparaissent sur la page Utilisateurs, avec un bouton Approuver/Rejeter
par demande — approuver applique le rôle immédiatement, comme si tu
l'avais fait toi-même depuis cette page.

### (3) Quantité restante et unités

La quantité restante n'est plus affichée pour les sources scellées (le
concept ne s'y applique pas). Le sélecteur d'unité (g, mg, µg, kg, mL, L,
Pa, kPa, bar) est de retour dans le formulaire — un oubli de la refonte
précédente : la quantité était devenue calculée, mais j'avais aussi
supprimé l'unité par erreur, alors qu'elle reste nécessaire pour
l'affichage.

### (4) Normalisation des noms de radionucléides

Nouvelle fonction `normaliser_nom_radionuclide()` : peu importe l'ordre
("Kr 85"/"85 Kr"), la présence d'un séparateur ("Kr85"/"Kr-85") ou la
casse, le résultat est toujours le format canonique "85-Kr" qu'attendent
LaraWeb et le module Matières Nucléaires. Appliquée à la création/
modification d'un radionucléide et à l'import (les deux formats de
fichier).

### (5) et (6) Colonnes séparées et tri sur toutes les colonnes

La colonne combinée "Radionucléides (activité actuelle)" de la page
Sources est séparée en deux : "Radionucléides" et "Activité actuelle
(Bq)" — nécessaire pour que le tri par activité ait un sens. Système de
tri générique (nouveau fichier `app/static/sortable.js`, réutilisé
partout) ajouté sur Sources, Radionucléides, Mouvements, Lieux et
Consommations : cliquer un en-tête de colonne trie le tableau selon
celle-ci (flèche ↑/↓, un second clic inverse le sens). Le tri se fait sur
la valeur réelle (ex : l'activité en Bq), pas sur le texte affiché.

**Bug préexistant trouvé et corrigé en cours de route** : sur plusieurs
pages (Sources, Mouvements, Lieux), le bloc `<script>` gérant l'affichage
(onglets, filtre) était placé à l'intérieur du bloc réservé aux rôles non-
lecteur, alors que le tableau lui-même est visible par tous les rôles —
un lecteur voyait donc des onglets et un filtre qui ne faisaient
strictement rien au clic. Trouvé en ajoutant le tri (qui devait, lui,
fonctionner pour tous les rôles) et corrigé partout où le même problème
existait : le script d'affichage (onglets/filtre/tri) est maintenant
toujours en dehors du bloc réservé à l'écriture.

### Testé

101 tests automatisés (10 nouveaux : fusion de lieux, mot de passe,
demandes de rôle, normalisation des noms). Vérification manuelle
complète sur serveur réel pour les 6 points, y compris la confirmation
que le tri/filtre fonctionne désormais réellement pour un compte lecteur,
et validation JS de toutes les pages modifiées (22 scripts).

### Fichiers ajoutés

`app/static/sortable.js`, `app/models/role_request.py`,
`tests/test_users_roles.py`.

### Fichiers modifiés

`app/models/source.py` (UniteQuantite enrichi), `app/models/location.py`
(schéma LocationFusion), `app/routes/locations.py` (route fusion),
`app/routes/users.py` (mot de passe, demandes de rôle), `app/routes/radionuclides.py`
(normalisation du nom), `app/services/matieres_nucleaires.py`
(normaliser_nom_radionuclide), `app/services/inventory_import.py`
(normalisation à l'import), `app/scripts/migrate_add_locations_movements.py`
(table role_requests), `app/main.py` (calculs pour tri, demandes en
attente), `app/templates/{base,sources,radionuclides,movements,locations,consumptions,users}.html`,
`app/static/style.css` (style des en-têtes triables),
`tests/test_consumption_movement.py`, `tests/test_matieres_nucleaires.py`.

---

## 21. V0.1.13 (12/07/2026) : 5 correctifs sur la 0.1.12

### (1) Sens du nom de radionucléide inversé

`normaliser_nom_radionuclide()` produisait "85-Kr" (nombre puis symbole).
Corrigé vers "Kr-85" (symbole puis nombre), comme LaraWeb et plus naturel
à l'oral. `parser_radionuclide()` (catégorisation Matières Nucléaires)
acceptait déjà les deux sens indifféremment : ce changement ne touche que
l'affichage/la saisie, pas les calculs.

### (2) Source liquide non consommable — régression réelle

En rendant la quantité restante "calculée, pas saisie" (V0.1.10), j'avais
supprimé toute façon de saisir une quantité de départ. Résultat : pour
n'importe quel isotope hors de la table de masses molaires connues (U, Pu,
Th, H) et sans cache LaraWeb — donc la plupart en pratique, dont ton
exemple de Co-60 — le calcul ne donnait jamais rien, et la consommation
devenait impossible. **Repli ajouté** : `quantite_restante_calculee()`
utilise maintenant, à défaut de calcul physique possible, la **quantité
initiale** (nouveau champ à nouveau saisissable à la création) moins les
consommations déjà enregistrées.

### (3) Champs valeur + unité côte à côte

Le sélecteur d'unité et le champ "Volume du récipient en litres" qui le
suivait n'avaient aucun rapport (unité de quantité contre volume physique
du contenant) — source de confusion légitime. Réorganisé : "Quantité
initiale" et son unité sont maintenant côte à côte ([valeur] [unité]),
pareil pour "Activité de référence" et son unité (sur la page
Radionucléides et sur la pop-up rapide de Sources). Le volume du récipient
reste, mais clairement noté comme une grandeur distincte.

### (4) Activité totale de la source affichée "N/A"

Même cause que (2) : le calcul utilisait l'ancien champ `source.quantite`
(jamais renseigné). Utilise maintenant la quantité calculée (méthode 1 ou
2 de la section 7bis du README). Affichage aussi reformaté : "45.3 kBq/g"
et "181 kBq" (unité correctement reportée, y compris pour une
concentration) plutôt que des nombres bruts sans unité. Le tri par
colonne reste basé sur la valeur numérique brute en Bq (attribut caché),
pas sur le texte affiché.

### (5) Bouton "+ Ajouter une source" silencieux sans lieu

Bug trouvé : quand aucun lieu n'existe, le clic sur "+ Ajouter une source"
ne faisait rigoureusement rien (le code sortait avant même d'ouvrir la
pop-up contenant le message d'avertissement). Corrigé : la pop-up s'ouvre
toujours ; le message ("Aucun lieu n'existe encore...") est maintenant
aussi mis en évidence visuellement plutôt qu'en texte discret.

### Testé

102 tests automatisés (2 nouveaux : consommation d'un isotope hors table
avec quantité initiale, activité totale depuis activité spécifique).
Vérification manuelle complète sur serveur réel des 5 points, y compris
rejouer l'exemple exact donné (Co-60, 5g à 100 kBq/g au 08/07/2020) :
affiche bien "45.3 kBq/g" et "181 kBq" après une consommation de 1g.

### Fichiers modifiés

`app/services/matieres_nucleaires.py` (sens de normalisation), `app/services/units.py`
(repli quantité initiale, formater_activite_bq accepte un dénominateur),
`app/main.py` (activité totale depuis la quantité calculée), `app/templates/sources.html`
(quantité initiale resaisissable, pairage valeur+unité, correction du
bouton), `app/templates/radionuclides.html` (pairage valeur+unité,
affichage formaté), `app/static/style.css` (classe champ-valeur-unite),
`tests/test_matieres_nucleaires.py`, `tests/test_inventory_import_robustesse.py`,
`tests/test_consumption_movement.py`.

---

## 22. V0.1.14 (12/07/2026) : bug critique + affichage valeur/unité partout

### Bug critique : confusion concentration / activité massique

À partir de 4 captures d'écran montrant un cas réel (Co-60 liquide, 5g à
100 kBq/g) : quantité restante calculée à 2,38e-9 g (au lieu de 5g),
source impossible à consommer, activité totale fausse.

**Cause exacte** : `quantite_restante_calculee()` passait l'activité
SPÉCIFIQUE (concentration dans LA SOLUTION, ex. 100 kBq/g de solution) à
la fonction qui calcule la masse d'un isotope PUR à partir d'une activité
TOTALE (en s'appuyant sur l'activité massique réelle de l'isotope, mise en
cache depuis LaraWeb — ex. l'activité massique réelle du Co-60 pur, de
l'ordre de 41 TBq/g). Diviser une concentration de solution par l'activité
massique du Co-60 pur donnait une masse aberrante, sans rapport avec la
réalité. **Corrigé** : le calcul physique (décroissance → masse) ne
s'applique plus du tout quand `activite_est_specifique` est vrai ; dans ce
cas, seule la quantité initiale moins les consommations est utilisée (la
décroissance change la concentration, pas la masse physique de la
solution).

Cette même confusion touchait aussi l'affichage de "l'activité actuelle"
sur la page Sources (affichait "99,5 kBq" au lieu de "99,5 kBq/g" — l'unité
de la concentration était perdue), et le filtre de la page Consommations
(vérifiait l'ancien champ jamais renseigné, empêchant purement et
simplement la source d'apparaître dans le formulaire). Les trois corrigés
ensemble et revérifiés en rejouant ton scénario exact.

### Valeur + unité partout, avec l'esprit BestUnit

- Colonne "Unité" retirée de la page Radionucléides (redondante : chaque
  valeur affiche déjà son unité juste à côté).
- "Activité actuelle (calculée)" → "Activité actuelle" (le mot "actuelle"
  suffit).
- Nouvelle fonction `formater_duree()` : la période radioactive s'affiche
  maintenant dans l'unité de temps la plus lisible (secondes, minutes,
  heures, jours ou années) plutôt que toujours en années — ex. "164 µs"
  pour une demi-vie de quelques microsecondes plutôt qu'un nombre illisible
  en années.

### Icônes d'état physique

Solide / liquide / gaz ont maintenant chacun une petite icône et une
couleur distinctive (sur le même principe que les badges de statut),
partout où l'état physique d'une source est affiché (Sources, Archives).

### Découverte importante, pas encore traitée : légende et couleurs du fichier Excel

En cherchant l'explication que tu mentionnes, j'ai trouvé l'onglet
**"Remarques"** du fichier d'inventaire (que je n'avais jamais examiné) :
il contient une légende complète, notamment pour la colonne que j'importe
actuellement sous "Utilisation" (regroupée dans le commentaire, jamais
utilisée pour déduire le statut réel) :
- **UT** : en Utilisation
- **DEP** : Dépôt / Stockage
- **SE** : Sans Emploi
- (colonne DEVENIR, séparée : **RA** = Rapatriement au fournisseur, **REM**
  = Remplacement — une destination prévue, pas le statut actuel)

Et pour les lieux : **Dess. N°** = desserte à sources, **Caroth. N°** =
carothèque, **Boite n°** = boîte de déchets, **Cellule** = château de
stockage IRRMA, **Arm. Bac. N°** = armoire BACCARA.

Je n'ai pas encore vérifié la correspondance exacte avec les couleurs de
cellule (certaines lignes utilisent une couleur indexée du palette Excel
historique, ex. index 23, dont la valeur RGB précise dépend du classeur).
Je n'ai pas non plus décidé comment faire correspondre UT/DEP/SE à mes 6
statuts actuels (`en_utilisation`/`remisée`/`en_déchet`/`en_attente`/
`transférée`/`détruite`) — ce n'est pas un choix évident, et je préfère
t'en parler avant d'agir : veux-tu que j'utilise cette colonne pour
déduire l'état d'utilisation à l'import (au lieu du "en utilisation" par
défaut actuel) ? Si oui, quelle correspondance te semble juste pour DEP et
SE ? Les sources déjà importées ne seraient pas mises à jour
automatiquement (l'import ignore les identifiants déjà présents) — il
faudrait soit les corriger à la main, soit que j'écrive un script
spécifique de mise à jour ponctuelle si tu le souhaites.

### Incident technique en cours de session

Mon environnement de travail a été réinitialisé au milieu de cette
session (perte du dossier de travail et de l'environnement Python,
probablement un redémarrage de conteneur). L'archive précédemment livrée
(V0.1.13) n'a heureusement pas été affectée : je l'ai réextraite et j'y ai
réappliqué tous les correctifs de cette session à l'identique. Mentionné
par souci de transparence.

Au passage, cet incident a révélé que le script `init_db.py` (recréation
d'une base neuve depuis zéro) n'importait pas les modèles `LaraCacheDB` et
`RoleRequestDB`, ajoutés plus tard — corrigé, même si en usage normal tu
pars toujours d'une base existante (migrations automatiques au démarrage).

### Testé

106 tests automatisés (4 nouveaux), plus vérification manuelle complète
sur serveur réel en rejouant ton scénario exact (SCA-001, Co-60, 5g à
100 kBq/g) : affiche "5 g", "99,5 kBq/g", "398 kBq" après consommation
d'1g, et la source apparaît bien dans le formulaire de consommation.

### Fichiers ajoutés

`app/templates/_macros.html` (icône d'état physique, réutilisable).

### Fichiers modifiés (cette session)

`app/services/units.py` (correctif critique + formater_duree), `app/main.py`
(3 routes corrigées : sources, radionuclides, consumptions),
`app/templates/radionuclides.html` (colonne Unité retirée, période
formatée), `app/templates/sources.html` et `sources_archive.html` (icône
d'état physique), `app/static/style.css` (styles des icônes),
`app/scripts/init_db.py` (imports complétés), `tests/test_units.py`,
`tests/test_consumption_movement.py`.

---

## 23. V0.1.15 (12/07/2026) : page Consommations et tri — deux bugs, origine tracée

### Réponse directe à la question posée : qu'est-ce qui a causé ces régressions ?

Rien de ce que tu as demandé n'était problématique en soi — les deux bugs
viennent de lacunes dans mon propre travail, pas d'une mauvaise idée de ta
part. Détail exact ci-dessous, sans arrondir les angles.

### Bug 1 : le tri ne triait rien (tous les tableaux)

**Cause** : dans `sortable.js`, le code construisait le nom de la
propriété JavaScript à lire par `'sort' + cle` (ex: `'sort' + 'id'` =
`'sortid'`, tout en minuscules). Mais un attribut HTML `data-sort-id`
devient, une fois lu par le navigateur, `dataset.sortId` — avec un I
majuscule (règle standard du DOM : camelCase après le premier tiret).
`dataset['sortid']` (minuscule) ne correspond à rien : ça renvoyait
toujours `undefined`, donc chaque comparaison valait "vide contre vide" —
aucune ligne ne changeait de place, mais le clic et la flèche
fonctionnaient bien (eux ne dépendent pas de cette valeur), d'où le
symptôme exact que tu as décrit. **Corrigé** : reconstruction correcte du
nom de propriété (première lettre en majuscule après "sort"). Vérifié
avec un vrai DOM (jsdom) sur le HTML réellement produit par le serveur, en
simulant un clic sur l'en-tête ID : l'ordre des lignes change bien dans un
sens puis dans l'autre.

Origine : introduit dès la construction de cette fonction (V0.1.12, en
réponse à ta demande de pouvoir trier chaque colonne). Un bug
d'implémentation classique (erreur de casse JavaScript), pas une
conséquence d'un choix de conception discutable — et une lacune de test de
ma part : j'avais vérifié que le clic déclenchait bien quelque chose,
jamais que les lignes se réordonnaient réellement.

### Bug 2 : la consommation ne se répercutait nulle part

**Cause** : la page Consommations construisait un objet JavaScript en
interpolant directement `{{ s.quantite }}` (le champ brut, historique)
dans un bloc `<script>`. Tant que ce champ était toujours rempli (avant la
V0.1.10, quand la quantité restante était saisie à la main), ça
fonctionnait. Mais depuis que la quantité se calcule (`quantite_initiale`
moins consommations, cf. section 7bis), `source.quantite` est très
généralement `None` — et Jinja, sans passer par une sérialisation JSON
sûre, transforme ça en texte littéral `None` dans le JavaScript généré.
`None` n'est pas un mot-clé JavaScript (le bon mot est `null`) : le
navigateur essayait de le lire comme une variable non définie, ce qui
levait une erreur au chargement de la page — **avant** la ligne qui
attache l'écouteur de soumission du formulaire. Résultat : le bouton
"Enregistrer" ne faisait plus rien du tout, silencieusement (le formulaire
HTML se soumettait tout seul sans passer par mon code, sans aller nulle
part d'utile). **Corrigé** : le JSON est maintenant construit et
sérialisé côté Python (`json.dumps`, qui convertit correctement `None`
vers `null`), passé au template comme une chaîne déjà sûre.

Origine : le changement "quantité calculée, pas saisie" (répondant à ta
demande du 10/07/2026) a rendu `source.quantite` fréquemment vide — un
changement de conception légitime et correctement implémenté ailleurs.
Le bug lui-même vient de ce que je n'ai pas ressaisi cette page
spécifique à ce moment-là pour vérifier ses propres usages de ce champ :
une lacune de suivi de ma part, pas un défaut de ta demande initiale.
J'ai corrigé les autres usages de `source.quantite` (affichage, filtre
d'éligibilité) au fil des sessions précédentes, mais j'avais raté celui-ci,
enterré dans un bloc `<script>` où Jinja ne signale aucune erreur au
rendu (le texte "None" est syntaxiquement un identifiant JS valide, donc
`node --check` ne le détecte pas non plus — seule l'exécution réelle le
révèle, d'où la vérification par simulation DOM cette fois plutôt qu'un
simple contrôle de syntaxe).

### Page Consommations alignée sur le reste de l'application

Bouton "+ Enregistrer une consommation" ouvrant une pop-up (au lieu du
formulaire toujours affiché en bas de page), et quantité à consommer
appariée à son unité ([valeur] [unité]), comme le reste de l'application.

### Rien de perdu

Les deux bugs empêchaient une action de se produire (rien n'était
enregistré) plutôt que de corrompre des données existantes — donc rien à
réparer côté données, juste le geste à refaire une fois la version
installée.

### Testé

107 tests automatisés (1 nouveau, qui vérifie spécifiquement l'absence du
token "None" dans le JavaScript généré par cette page). Vérification
manuelle complète sur serveur réel : rejeu de ton scénario exact (source
liquide, consommation de 1g) avec confirmation dans les trois endroits
attendus (tableau Consommations, quantité recalculée sur Sources, entrée
d'audit). Tri vérifié avec un vrai moteur DOM (jsdom) sur le HTML réel du
serveur, pas seulement une vérification de syntaxe.

### Fichiers modifiés

`app/static/sortable.js` (correction du nom de propriété dataset),
`app/main.py` (sérialisation JSON sûre pour Consommations, quantité
calculée attachée aux sources), `app/templates/consumptions.html`
(réécrit : bouton + pop-up, pairage valeur/unité, sérialisation sûre),
`tests/test_consumption_movement.py`.

---

## 24. V0.1.16 (12/07/2026) : quantité restante, pesée double, correctifs d'import

### (1) La quantité restante ne représente plus jamais une masse d'isotope

Signalé directement : le calcul utilisait la masse d'isotope pur (déduite
de l'activité) dès qu'elle était disponible, y compris pour l'affichage
"Quantité restante" — ce qui n'a pas de sens pour une source non-MN ou
pour une lecture physique (peser une source, lire une pression). Corrigé
radicalement : `quantite_restante_calculee()` ne s'appuie plus jamais sur
l'activité. Elle vient uniquement de pesées réelles (quantité initiale, ou
la pesée la plus récente enregistrée — voir point 5). La masse d'isotope
reste calculée, mais exclusivement pour l'Annexe 1 et le Tableau 1a, de
façon complètement indépendante désormais.

### (2) "(Bq)" retiré du titre de colonne

Comme pour Radionucléides il y a deux versions : l'unité étant déjà
affichée à côté de chaque valeur, la préciser aussi dans le titre de
colonne est redondant.

### (3) Bug d'import trouvé (SCA-0167/Po-210) et suppression facilitée

**Cause exacte** : mon rattachement des lignes "de mélange" (radionucléide
supplémentaire sans identifiant propre) ne réinitialisait jamais le
pointeur "dernière source vue" après une ligne orpheline. Résultat : à
travers 3 lignes orphelines intercalées (chacune avec sa propre date
d'arrivée, donc correctement signalée comme orpheline), un Po-210 sans
rapport s'est retrouvé rattaché à SCA-0167, 4 lignes plus haut. Corrigé :
le pointeur se réinitialise maintenant à chaque ligne qui ne correspond
pas à une vraie ligne de mélange immédiatement adjacente. Réimporté et
vérifié : SCA-0167 ne contient plus que du Co-60, Po-210 n'apparaît plus
nulle part.

La suppression d'un radionucléide existait déjà (page Radionucléides),
mais pas facilement accessible depuis Sources. Un petit bouton "×" a été
ajouté à côté de chaque radionucléide listé sur la page Sources, pour
corriger ce genre de cas directement sans naviguer ailleurs.

### (4) Masse et volume séparés, avec unités appariées

Le champ "Volume du récipient en litres" (hardcodé, sans rapport clair
avec la quantité juste au-dessus) est remplacé par un couple valeur+unité
(`volume_recipient` + `unite_volume`, mL ou L), distinct de la quantité
(masse ou pression). Utile en particulier pour un liquide : masse et
volume sont deux informations différentes (la masse volumique d'une
solution radioactive n'est pas celle de l'eau). L'ancien champ est
conservé en base pour compatibilité, mais plus utilisé par le formulaire.
Pas de nouvelle brique "unit" complète construite pour l'instant : mon avis
est que l'énumération légère déjà en place (`UniteQuantite`, qui couvre
déjà mL/L) suffit à ce stade — je réutilise cette même liste plutôt que
d'en ajouter une autre. À rouvrir si le besoin s'élargit franchement.

Je n'ai pas tenté d'extraire rétroactivement les informations de volume/
pression du fichier avril-2016 (elles y sont en texte libre dans les
commentaires, ex. "gaz 700 l initial pression 100 bars..." — pas une
colonne structurée) : l'information n'est pas perdue (elle est dans le
commentaire de chaque source concernée), juste pas encore éclatée dans les
nouveaux champs. Peux se faire au cas par cas si besoin.

### (5) Pesée double avant/après prélèvement

Sur la page Consommations, le formulaire propose maintenant deux modes
selon l'état physique de la source choisie :
- **Liquide** : masse pesée avant prélèvement (récipient + contenu) et
  après. La quantité consommée se déduit automatiquement de la différence.
- **Gaz** : quantité directe, comme avant (peser un gaz n'a pas de sens).

**La méthode retenue pour gérer l'évaporation** : plutôt que de calculer
un budget théorique (quantité initiale moins consommations cumulées), la
quantité de référence devient **la dernière pesée "après" enregistrée**,
directement. Concrètement : si tu pèses 9,5g avant un prélèvement alors
que 10g étaient attendus depuis la dernière fois, l'écart (probable
évaporation du solvant) est noté automatiquement dans le commentaire de la
consommation — mais n'empêche pas l'enregistrement, et surtout ne fausse
rien : c'est la pesée réelle qui devient la nouvelle référence, pas un
calcul qui ignorerait l'écart. Le "cas 1" que tu décris (pesée initiale
seule, sans prélèvement) se fait via la quantité initiale de la source
elle-même (pop-up de modification), pas via cette page — enregistrer une
"consommation" sans rien consommer n'aurait pas de sens dans le journal.

### (6) Fichier Excel à venir

Bonne idée, sans hésitation — un fichier préparé à l'avance, avec les
colonnes qui te semblent pertinentes (masse, volume, code couleur/statut
explicites...), me permettra de construire un import bien plus fiable
qu'en devinant après coup. Dès que tu l'as, je le regarde en détail avant
de proposer quoi que ce soit.

### Testé

112 tests automatisés (7 nouveaux : quantité jamais calculée depuis
l'activité, pesée double, détection d'écart, calcul manquant à la
création). Vérification manuelle complète sur serveur réel : réimport du
fichier réel avec le correctif SCA-0167, pesée double avec écart
d'évaporation rejouée de bout en bout, suppression rapide de
radionucléide, validation JS de toutes les pages modifiées.

### Fichiers ajoutés

(aucun nouveau fichier — extensions de fichiers existants uniquement.)

### Fichiers modifiés

`app/services/units.py` (quantite_restante_calculee radicalement
simplifiée), `app/services/consumption.py` (pesée double, détection
d'écart), `app/services/inventory_import.py` (correctif du rattachement
après ligne orpheline), `app/models/consumption.py` (masse_avant/
masse_apres), `app/models/source.py` (volume_recipient/unite_volume),
`app/routes/sources.py` (quantite_calculee manquante à la création/
modification), `app/routes/consumptions.py` (nouveaux champs transmis),
`app/scripts/migrate_add_source_fields.py` (deux nouvelles migrations),
`app/main.py` (enregistrement des migrations, JSON avec état physique),
`app/templates/sources.html` (titre de colonne, bouton suppression
rapide, couple volume+unité), `app/templates/consumptions.html` (deux
modes de saisie selon l'état physique), `tests/test_consumption_movement.py`
(tests ajoutés, et deux tests fusionnés par erreur lors d'une récupération
précédente séparés à nouveau).

---

## 25. V0.1.17 (12/07/2026) : import affiné, Sr-90/Y-90, arrondi scientifique

### Versionnement (question, pas de code)

Expliqué en réponse directe : convention SemVer (MAJEUR.MINEUR.CORRECTIF),
et pourquoi rester en 0.x tant que des ajustements de fond comme ceux de
ce message continuent d'apparaître — voir l'échange en tête de session.

### Import : statut déduit de la colonne UTILISATION, couleurs écartées

Réexaminé le fichier réel en profondeur, cette fois en croisant valeurs de
la colonne "UTILISATION" (légende dans l'onglet "Remarques" : UT/DEP/SE)
et couleurs de cellule. Constat honnête : **la couleur n'est pas un signal
fiable** — sur "Sources non scellées" aucune ligne n'est colorée, et sur
"Sources consommables" la couleur ne sépare plus du tout les statuts
(présente sur UT, DEP, SE et même les lignes vides). En revanche, 100% des
lignes "SE" de "Sources scellées" sont colorées, et 0% des "DEP" — un
indice réel mais pas assez généralisable pour construire quoi que ce soit
dessus. La colonne UTILISATION elle-même, en clair et documentée, est
fiable : utilisée maintenant pour déduire l'état (UT → en_utilisation,
DEP → remisée, SE → en_attente), plutôt que le "toujours en_utilisation"
d'avant. Réimporté et vérifié : 127 en utilisation, 97 remisées, 19 en
attente (au lieu de 243 en utilisation).

### BestUnit sur "Activité de référence", "Activité totale" retirée

Comme demandé : l'activité de référence est maintenant reformatée avec le
préfixe le plus lisible, comme l'activité actuelle et la période. La
colonne "Activité totale de la source" (systématiquement N/A depuis que
la quantité restante ne se calcule plus depuis l'activité, cf. la session
précédente) est retirée de la page Radionucléides — redondante avec les
activités par radionucléide déjà affichées sur la page Sources, comme
remarqué.

### Quantité restante réservée aux sources gaz/liquide

Elle ne s'affiche plus que pour l'état physique gaz ou liquide (le critère
exact de l'onglet "Consommables"), plus pour toute source non-scellée —
une source solide non-scellée (ex : un mélange de référence) n'a pas de
quantité "restante" à suivre au même sens.

### Sr-90/Y-90 : convention "père uniquement"

Le fils Y-90, à l'équilibre séculaire immédiat avec son père Sr-90 (demi-
vie ~64h contre ~28,8 ans), n'apparaît plus séparément. "Sr-90+",
"90-Sr-Y" et variantes proches sont normalisés vers "Sr-90" simple, à la
saisie comme à l'import.

### Arrondi scientifique façon res_round.m (LNHB)

Porté le cœur de ta fonction `res_round.m` (le calcul du nombre de
décimales à partir de l'incertitude) : les valeurs affichées (activités,
mantisses de période) utilisent maintenant ce calcul plutôt qu'un nombre
fixe de chiffres significatifs, avec une incertitude arbitraire de 1% en
attendant un vrai suivi d'incertitude. Résultat concret : "45,31 kBq/g"
au lieu de "45,3 kBq/g" (un chiffre de plus, justifié par le calcul).
**Le repli en écriture scientifique pour les grandes périodes en années
(ex : "2,41e+04 ans") est volontairement laissé intact**, explicitement
complimenté — l'arrondi par incertitude ne s'applique qu'aux mantisses
(valeurs déjà ramenées à une échelle lisible par un préfixe ou une unité
de temps), pas à ce repli sans unité "plus grande" disponible.

### Matières nucléaires classées automatiquement

H-3, Li-6, et tout isotope de thorium/uranium/plutonium classent
désormais leur source en Matière Nucléaire dès leur ajout, sans attendre
que quelqu'un coche la case à la main — y compris si l'utilisateur qui
ajoute le radionucléide n'a lui-même pas accès aux sources MN (le
classement doit se déclencher justement dans ce cas, pas être contourné).

### Testé

117 tests automatisés. Vérification manuelle complète sur serveur réel :
réimport du fichier réel avec la nouvelle répartition de statuts,
Sr-90/Y-90 et classement MN automatique rejoués de bout en bout, absence
confirmée de la colonne retirée, validation JS des pages modifiées.

### Fichiers modifiés

`app/services/units.py` (arrondir_scientifique, intégration dans
formater_activite_bq/formater_duree), `app/services/matieres_nucleaires.py`
(cas Sr-90/Y-90, est_matiere_nucleaire), `app/services/inventory_import.py`
(statut déduit de UTILISATION, classement MN automatique), `app/routes/radionuclides.py`
(classement MN automatique à la création/modification), `app/main.py`
(activité de référence formatée, activité totale retirée), `app/templates/radionuclides.html`
(colonne retirée, texte d'introduction mis à jour), `app/templates/sources.html`
(quantité restante réservée gaz/liquide), `tests/test_units.py`,
`tests/test_matieres_nucleaires.py`, `tests/test_sources_permissions.py`,
`tests/test_consumption_movement.py`.

---

## 26. V0.1.18 (13/07/2026) : notification des demandes de rôle

### Question posée, lacune trouvée en y répondant

En expliquant comment promouvoir un utilisateur (pas de script dédié à
écrire : le mécanisme de demande/approbation déjà en place suffit), la
question "qui reçoit le message, comment ?" a mis le doigt sur un vrai
manque : **rien ne notifiait jamais un administrateur qu'une demande
existait**. Il fallait penser à aller voir la page Utilisateurs de
soi-même, sans aucun signal ailleurs.

### Corrigé : badge dans le bandeau

Un point rouge apparaît sur l'avatar (visible sur n'importe quelle page,
sans ouvrir le menu), et le lien "Utilisateurs & rôles" affiche le
décompte ("(1 en attente)"). Techniquement, le nombre de demandes en
attente est calculé une seule fois, au moment où l'utilisateur courant est
identifié (`_decode_user`, un point unique déjà utilisé par toutes les
pages) — donc disponible partout sans avoir dû modifier chaque route une
par une. Calculé uniquement pour un compte admin, pour ne pas ajouter de
requête inutile aux autres rôles.

### Rôles en base, pour référence

`admin`, `utilisateur_mn`, `utilisateur`, `lecteur` (voir `app/models/user.py`,
classe `UserRole`) — pas besoin de les retenir en pratique, `promote_admin.py`
reste le seul script en ligne de commande nécessaire (uniquement pour le
tout premier compte admin, qui ne peut par définition être créé autrement).

### Testé

118 tests automatisés (1 nouveau). Vérification manuelle complète sur
serveur réel en rejouant le scénario exact décrit (GDO admin, CMO lecteur
demandant utilisateur_mn) : badge absent avant la demande, présent avec le
bon décompte après, disparaît après approbation, rôle de CMO
effectivement changé.

### Fichiers modifiés

`app/security/permissions.py` (calcul du décompte dans `_decode_user`),
`app/templates/base.html` (badge sur l'avatar et le lien), `app/static/style.css`
(style du badge), `tests/test_users_roles.py`.

---

## 27. V0.1.19 (13/07/2026) : fusion par renommage, valeurs infimes, pesée de contrôle

### Bouton de suppression rapide de radionucléide : retiré

Cause exacte trouvée : `{{ rn.nom | tojson }}` produit une chaîne
JSON *avec ses propres guillemets doubles*, insérée dans un attribut HTML
`onclick="..."` lui-même délimité par des guillemets doubles — collision,
attribut tronqué (`onclick="supprimerRadionuclideRapide(1, "Cs-137")"`,
invalide). Retiré comme demandé plutôt que corrigé, la suppression
d'origine (page Radionucléides) restant la seule voie.

### Fusion de lieux par renommage en collision

Comme proposé : renommer un lieu vers un nom déjà pris par un AUTRE lieu
renvoie maintenant une erreur claire (409) proposant la fusion, plutôt que
le 500 Internal Server Error du journal joint (`UNIQUE constraint failed:
locations.nom`). Une confirmation explicite est nécessaire (`confirmer_fusion:
true`) avant que la fusion n'ait lieu réellement, pour qu'une simple faute
de frappe ne déclenche jamais une fusion accidentelle. La logique de
fusion elle-même (déjà existante) est réutilisée telle quelle, pas
dupliquée. Le bouton "Fusionner" dédié reste disponible en parallèle.

### Valeurs d'activité infimes : "0" au lieu d'un mur de zéros

Cause exacte : `arrondir_scientifique()` (le port de res_round.m de la
session précédente) n'avait pas de plafond sur le nombre de décimales
calculées depuis l'incertitude -- pour une valeur assez infime, ce nombre
devenait astronomique, produisant plusieurs centaines de zéros voire un
dépassement de capacité pur et simple (reproduit et confirmé : `OverflowError:
int too large to convert to float`). Corrigé à deux niveaux : toute
valeur sous 1 nBq est maintenant directement affichée "0" (le seuil que
tu as demandé), et `arrondir_scientifique()` a aussi reçu un plafond
défensif à 12 décimales, pour ne plus jamais planter même dans un
appel imprévu avec une valeur extrême.

### Pesée de contrôle, masse du récipient déduite, et corrections a posteriori

Le chantier le plus substantiel de cette session, à partir du
cheminement complet décrit (réception, pesée totale, premier
prélèvement) :

- **Pesée de contrôle** : `masse_avant` == `masse_apres` (ou `masse_apres`
  simplement laissée vide, auto-complétée à la même valeur) est
  maintenant acceptée -- une pesée sans rien prélever, utile en
  particulier pour la toute première pesée après réception. Tracée dans
  l'audit sous une action distincte (`PESEE`), pour la différencier d'une
  vraie consommation (`UTILISATION`).
- **Masse du récipient déduite automatiquement** : la quantité restante
  affichée est en masse de LIQUIDE, pas la masse totale pesée (récipient
  inclus) -- comme tu l'as souligné, ce sont deux grandeurs différentes,
  et on ne peut pas peser le liquide seul sans ouvrir le récipient.
  `quantite_restante_calculee()` déduit maintenant la masse du récipient
  à partir de la toute première pesée réelle moins la quantité initiale
  connue (celle du certificat), et la retranche de chaque pesée totale
  suivante. Testé avec ton scénario exact (réception 5,027g de liquide
  connu, première pesée totale à 55g, prélèvement ramenant à 54,5g de
  pesée totale) : donne bien ~4,527g de liquide restant.
- **Détection d'écart corrigée** : elle comparait, par erreur, la nouvelle
  pesée à la quantité de LIQUIDE restante -- une grandeur différente
  d'une pesée totale, jamais directement comparable. Compare maintenant
  la nouvelle pesée à la pesée totale précédente.
- **Correction d'une pesée déjà enregistrée** : nouvelle route (bouton
  "Modifier" sur chaque ligne de la page Consommations). Modifier
  `masse_avant` ou `masse_apres` recalcule automatiquement `quantite_utilisee`
  en cohérence. Chaque champ modifié reste tracé dans l'audit
  (`consommation#N.champ`, avant/après) -- pas idéal du point de vue
  assurance qualité au sens strict, mais l'audit préserve une
  traçabilité complète de toute correction, ce qui semble le compromis
  le plus raisonnable entre droit à l'erreur et rigueur.
- Le même piège de guillemets que pour le bouton de suppression rapide
  (voir plus haut) a été anticipé cette fois : les valeurs de chaque
  consommation (pouvant contenir guillemets et apostrophes dans un
  commentaire) sont transmises via un objet JSON construit côté Python
  (même patron que pour les sources consommables), jamais interpolées
  directement dans un attribut HTML.

### Testé

125 tests automatisés (12 nouveaux ou corrigés). Vérification manuelle
complète sur serveur réel : scénario de fusion par renommage rejoué de
bout en bout, valeurs infimes qui plantaient confirmées corrigées, pesée
de contrôle puis prélèvement avec masse de récipient déduite rejoués avec
les chiffres de ton scénario, et surtout, un commentaire piège contenant
à la fois guillemets et apostrophes enregistré et modifié avec succès,
vérifié par exécution JS réelle (moteur DOM, pas seulement une relecture
de code) -- le contenu du commentaire ressort intact des deux côtés.

### Fichiers modifiés

`app/services/units.py` (masse du récipient déduite, seuil de
négligeabilité, plafond défensif), `app/services/consumption.py` (pesée
de contrôle, détection d'écart corrigée, action PESEE), `app/models/consumption.py`
(ConsumptionUpdate), `app/models/audit.py` (action PESEE), `app/models/location.py`
(confirmer_fusion), `app/repositories/consumption.py` (méthode update),
`app/routes/consumptions.py` (route PATCH), `app/routes/locations.py`
(réécrit : logique de fusion extraite, renommage-collision), `app/main.py`
(consumptions_json), `app/templates/sources.html` (bouton retiré),
`app/templates/consumptions.html` (réécrit : pesée simplifiée, bouton
Modifier), `app/templates/locations.html` (gestion du 409, note),
`app/templates/audit.html` (filtre PESEE), `tests/test_units.py`,
`tests/test_consumption_movement.py`.

---

## 28. V0.1.20 (13/07/2026) : pagination, activité utilisée, exports ODS/PDF

### Pagination générique, coopérant avec le tri et les filtres existants

Nouveau module `paginate.js` : menu déroulant (10/20/50/100/Tout) + page
précédente/suivante, ajouté à tous les tableaux (Sources, Radionucléides,
Consommations, Mouvements, Lieux, Audit). Point délicat : Sources et
Audit ont chacun leur propre filtre (onglets, cases à cocher) qui
manipule déjà `style.display` sur chaque ligne — la pagination devait se
poser PAR-DESSUS sans le casser. Un premier essai (lire directement
`style.display` pour savoir quelles lignes sont "éligibles") s'est révélé
buggé : la pagination masque elle-même des lignes, et se les faisait
ensuite passer pour "exclues par le filtre" au tour suivant (le total
affiché rétrécissait à chaque changement de taille de page). Corrigé
avec un marqueur dédié (`data-filtre-ok`), distinct de `style.display` —
vérifié avec un vrai moteur DOM sur les 240 sources du fichier réel :
tri, changement d'onglet et pagination restent cohérents ensemble dans
tous les cas testés.

### Activité utilisée, à la date de la consommation

Nouvelle colonne sur la page Consommations : l'activité (Bq)
correspondant à la quantité consommée, calculée à la date DE CETTE
CONSOMMATION (décroissance depuis la référence du radionucléide) --
purement pour l'affichage, rien n'est stocké en base. Deux cas : activité
spécifique (concentration × quantité consommée, direct) et activité
totale (la quantité consommée est une fraction de la quantité totale à ce
moment-là, l'activité utilisée est cette même fraction).

### Arrondi (res_round) audité dans toute l'application

Recherche systématique de tout affichage numérique brut restant. Trouvé
et corrigé : la quantité restante des sources utilisait encore l'ancien
`"%.3g"|format(...)`. `arrondir_scientifique` est maintenant enregistrée
comme fonction Jinja globale (utilisable directement dans les templates),
et la quantité utilisée sur Consommations passe par elle aussi. Les
exports réglementaires Annexe 1/Tableau 1a (qui utilisent un `round(x,3)`
fixe) ont été volontairement laissés de côté : ce sont des documents
officiels, un changement de précision là-bas mérite une confirmation
explicite plutôt qu'une extension automatique du même chantier.

### "Quantité restante" masquée hors de l'onglet Consommables

La colonne entière (pas seulement son contenu) disparaît sur les onglets
Scellées et Non scellées, où elle n'a jamais de valeur à afficher.

### Inventaire physique MN (nouveau document imprimable)

Nouvel export PDF (`reportlab`) : une ligne par source Matière Nucléaire
active, avec son identifiant, son (ou ses) radionucléide(s), son
emplacement habituel, une case à cocher (bordure du tableau) et deux
emplacements de signature. Titre et date générés automatiquement.

### Exports ODS et PDF, en plus de XLSX

Ajouté en cours de session (demande complémentaire) : les trois exports
existants (liste des sources, Annexe 1, Tableau 1a) sont maintenant aussi
disponibles en ODS (LibreOffice Calc) et PDF, en anticipation d'une
réduction de la dépendance à Microsoft. Choix technique : convertir le
XLSX déjà généré (via LibreOffice en ligne de commande, `--headless
--convert-to`) plutôt que réécrire chaque export dans une bibliothèque
Python différente -- une conversion fidèle (couleurs, cellules
fusionnées, en particulier pour la mise en forme officielle de l'Annexe
1) aurait été difficile à garantir en dupliquant cette logique ailleurs.
Nécessite LibreOffice installé sur la machine qui fait tourner
l'application ; message d'erreur explicite si absent (l'export XLSX
reste disponible dans tous les cas, sans dépendance à LibreOffice).

### Testé

136 tests automatisés (14 nouveaux). Vérification manuelle complète sur
serveur réel avec le fichier d'inventaire réel (240 sources) : pagination
et tri croisés avec le changement d'onglet, activité utilisée et quantité
arrondie affichées correctement sur un cas réel (source Cs-137 du
certificat joint), export d'inventaire MN généré sur les vraies sources
MN (3 pages), et les 9 combinaisons export×format (xlsx/ods/pdf ×
sources/annexe1/tableau1a) vérifiées individuellement, en-tête
d'avertissement du Tableau 1a confirmé préservé quel que soit le format.

### Fichiers ajoutés

`app/static/paginate.js`, `app/services/export_inventaire_mn.py`,
`app/services/convert_export.py`, `tests/test_export_inventaire_mn.py`,
`tests/test_export_formats.py`.

### Fichiers modifiés

`app/static/sortable.js` (redéclenche la pagination après un tri),
`app/static/style.css` (styles pagination + masquage colonne),
`app/services/units.py` (activite_utilisee_bq, activite_actuelle_bq
généralisée à une date arbitraire), `app/main.py` (fonction Jinja globale
arrondir_scientifique, activité utilisée sur Consommations), `app/routes/import_export.py`
(routes d'export réécrites pour accepter plusieurs formats),
`app/templates/{sources,radionuclides,consumptions,movements,locations,audit}.html`
(pagination, marqueur filtre, colonne masquée), `app/templates/import_export.html`
(boutons ODS/PDF), `pyproject.toml` (reportlab, pdfplumber en dev),
`tests/test_consumption_movement.py`.

---

## 29. V0.1.21 (14/07/2026) : lieux à l'import, mise en page PDF, import certificat

### Bug confirmé : lieux jamais renseignés à l'import du propre format de l'application

Vérifié comme suspecté : l'export écrit bien "Emplacement habituel" et
"Emplacement actuel" (deux colonnes, voir `export_excel.py`), mais l'import
de ce même format ne les relisait jamais -- une vraie lacune, pas un choix
voulu (l'autre format d'import, historique SCA, gère ses lieux depuis le
début). Trouvé aussi pourquoi le test existant ne l'avait jamais détecté :
il réimportait une source déjà présente, donc ignorée avant même
d'atteindre le code de création où vivait le bug -- jamais le scénario
réel visé (restaurer une source qui n'existe plus). Corrigé, et un
nouveau test exerce maintenant le vrai scénario (export, suppression,
réimport, vérification du lieu).

### PDF Annexe 1 / Tableau 1a : mise en page corrigée

Confirmé sur les PDF joints : convertis sans réglage, LibreOffice utilise
les paramètres d'impression par défaut du classeur (A4 portrait, marges
standards) -- désastreux pour un tableau large, d'où le texte tronqué et
superposé signalé. Corrigé : avant la conversion PDF spécifiquement (pas
XLSX ni ODS, qui n'ont pas ce problème), la feuille est réglée en paysage,
A4 explicite (le classeur avait un format "Letter" ambigu une fois
tourné), ajustée à la largeur d'une page, marges réduites -- sur une copie
temporaire, sans toucher au fichier XLSX/ODS d'origine. Vérifié : 3 pages
→ 1 page pour l'Annexe 1 de test, texte propre à l'extraction.

### Date d'inventaire ajoutée

Annexe 1 (cellule I4, en face de "Date") et Tableau 1a (cellule H3, en
face de "Inventaire du") reçoivent maintenant la date du jour
automatiquement.

### Import depuis un certificat d'étalonnage PDF (nouvelle fonctionnalité)

Nouveau bouton sur la page Sources : lit un certificat PDF et pré-remplit
la création d'une source et de son radionucléide. Testé sur le certificat
réel fourni (un document scanné, texte OCR sévèrement abîmé par endroits
-- "CARACTERISTIQUES" lu "GARAGTERISTIQUES", "CONFORME" lu "GONFORME", un
"I" majuscule confondu avec un "l" minuscule, des séparateurs de date
disparus). Plutôt que de deviner une valeur incertaine à partir de ce
bruit, chaque champ non extrait avec une confiance raisonnable est laissé
vide : sur ce document précis, la date de référence n'a par exemple pas pu
être reconstituée de façon fiable (les chiffres semblaient décalés) et
reste donc à compléter à la main -- un champ vide plutôt qu'une date
fausse avec l'air d'être fiable, dans un contexte de sûreté nucléaire.
Les champs extraits avec confiance sur ce même document : radionucléide
(Cs-137), activité massique (876 kBq/g, spécifique), masse délivrée
(5,027 g), incertitude (1,5%), classification (non scellée).

**Ceci est une proposition à vérifier, jamais une création automatique** :
la pop-up de création de source s'ouvre pré-remplie avec un encart
récapitulant ce qui a été trouvé, et une fois la source enregistrée, la
pop-up d'ajout du radionucléide détecté s'ouvre à son tour automatiquement
(les valeurs transitent par `sessionStorage`, le temps du rechargement de
page qui suit la création) -- toujours à valider par un clic explicite,
jamais silencieux. Vérifié avec un vrai moteur DOM en deux temps (avant et
après un rechargement de page simulé), pas seulement une relecture de
code.

### Testé

147 tests automatisés (14 nouveaux ou corrigés sur cette session), dont un ensemble dédié à
l'extraction de certificat, avec le vrai document fourni comme cas de
test (protégé par `skipif` pour ne pas faire échouer la suite sur une
machine où ce fichier précis n'existe pas).

### Fichiers ajoutés

`app/services/parse_certificat.py`, `tests/test_parse_certificat.py`.

### Fichiers modifiés

`app/services/inventory_import.py` (lieux restaurés à l'import du format
export application), `app/services/convert_export.py` (mise en page avant
conversion PDF), `app/services/export_annexe1.py` et `export_tableau1a.py`
(date d'inventaire), `app/routes/sources.py` (route d'extraction
certificat), `app/templates/sources.html` (bouton, pop-up pré-remplie,
reprise après rechargement), `pyproject.toml` (pdfplumber en dépendance
principale), `tests/test_inventory_import_robustesse.py`, `tests/test_export_formats.py`.

---

## 30. V0.1.22 (14/07/2026) : mise à jour à l'import, doublon de radionucléides corrigé

### Question posée, vérifiée avant de répondre

"Je peux importer, exporter, corriger le fichier et réimporter ?" —
reproduit le scénario exact avant de répondre : source créée, exportée,
un champ corrigé dans le fichier obtenu, réimporté. Résultat sans rien
changer : la correction était silencieusement ignorée (la source déjà
présente était simplement passée, jamais mise à jour). Pas prévu à
l'origine, confirmé concrètement plutôt que supposé.

### Corrigé : option explicite de mise à jour à l'import

Nouvelle case à cocher sur la page Import : "Mettre à jour les sources
déjà présentes (au lieu de les ignorer)", décochée par défaut (rien ne
change si elle n'est pas cochée). Cochée, une source déjà présente est
mise à jour avec les valeurs du fichier plutôt qu'ignorée -- pour les
deux formats d'import. Rejoué le scénario exact avec l'option activée :
la correction ("Fournisseur CORRIGE (le bon)") est bien appliquée cette
fois. Les radionucléides déjà associés à une source ne sont volontairement
jamais touchés par cette option (seuls les champs de la source elle-même
le sont).

### Bug distinct trouvé en testant : doublon de radionucléides à tout réimport

En écrivant le test "l'option ne touche pas aux radionucléides", trouvé
autre chose : la partie qui importe la feuille "Radionucléides" d'un
fichier exporté créait un nouveau radionucléide à chaque réimport, sans
jamais vérifier qu'un équivalent n'existait pas déjà -- un bug préexistant,
indépendant de la nouvelle option (il touchait déjà tout réimport d'un
fichier avec cette feuille, y compris avant cette session). Corrigé :
vérifie maintenant qu'un radionucléide de même nom n'existe pas déjà pour
cette source avant d'en créer un nouveau.

### Testé

150 tests automatisés (5 nouveaux). Vérification manuelle complète sur
serveur réel : scénario exact rejoué de bout en bout (import, export,
correction du fichier, réimport avec la case cochée) avec confirmation
que "Fournisseur CORRIGE (le bon)" et "Corrigé à la main" sont bien
repris tels quels dans la source.

### Fichiers modifiés

`app/services/inventory_import.py` (option de mise à jour dans les deux
formats d'import, correction du doublon de radionucléides), `app/routes/import_export.py`
(paramètre de formulaire, décompte des mises à jour dans la réponse),
`app/templates/import_export.html` (case à cocher, affichage du
décompte), `tests/test_inventory_import_robustesse.py`.

---

## 31. V0.1.23 (14/07/2026) : trois boutons cassés, lieu de stockage simplifié, filtres avancés

### "Marquer retourné" et "Supprimer" (lieux) : même bug trouvé deux fois de plus

Le bouton "Marquer retourné" (Mouvements) signalé sans effet : cause
identique aux bugs de boutons déjà rencontrés (radionucléide, pesée) --
`{{ m.source_id | tojson }}` dans un attribut `onclick="..."` produit ses
propres guillemets doubles, qui entrent en collision avec ceux de
l'attribut HTML et le tronquent. Plutôt que de corriger seulement ce cas,
recherche systématique du même motif dans tout le code : trouvé une
deuxième occurrence non signalée, le bouton "Supprimer" d'un lieu, très
probablement cassé aussi. Les deux corrigés avec un attribut `data-*`
(échappement HTML normal, aucune collision possible) -- vérifiés avec un
vrai moteur DOM en mode d'exécution réelle (pas seulement une relecture
de code) : les deux ouvrent maintenant leur pop-up correctement.

### "Fusionner" (lieux) : retiré

Cassé par le même motif. Plutôt que de le corriger, retiré entièrement
(bouton, pop-up, JS) : le renommage-fusion (renommer un lieu vers un nom
déjà pris propose de fusionner) fonctionne déjà et reste l'unique chemin.
La route API dédiée reste en place (déjà testée, toujours fonctionnelle),
seule son unique porte d'entrée dans l'interface a disparu.

### Lieu de stockage : simplifié

Confirmé : les colonnes "Emplacement habituel/actuel" de l'export
étaient déjà à jour, mais une colonne "Lieu de stockage" isolée
affichait encore un texte figé au moment de l'import, jamais mis à jour
depuis (une fusion ou un renommage de lieu ne le changeait pas). Retirée
entièrement de l'export Excel des sources ; Emplacement habituel/actuel
devient la seule source de vérité affichée.

### Filtres avancés sur Sources, et ergonomie de consommation

Trois ajouts, en réponse à "à réfléchir, propose moi des choses" :
- Recherche libre sur l'identifiant (ex : "SCA-" affiche uniquement les
  identifiants qui contiennent ce texte), combinable avec le filtre par
  radionucléide et les filtres déjà en place (onglet, statut).
- Filtre par radionucléide : un menu déroulant, réutilisant
  l'attribut déjà présent pour le tri (`data-sort-radionuclides`) plutôt
  que d'en ajouter un dédié.
- Bouton "Consommer" directement sur chaque ligne de source gaz/liquide
  active : ouvre la pop-up de consommation de la page Consommations,
  déjà pré-remplie sur cette source précise (transmis par
  `?source=XXX` dans l'URL). Répond directement à "c'est assez pénible
  d'avoir toutes les sources consommables dans un menu déroulant" en
  évitant complètement ce menu pour ce cas d'usage.
- En complément, pour le cas où on arrive quand même directement sur la
  page Consommations : le menu déroulant de sélection de source est
  remplacé par un champ texte avec suggestions natives (`datalist` HTML,
  aucune bibliothèque tierce), tapable au clavier. Comme un champ texte
  accepte n'importe quelle saisie contrairement à un menu déroulant, une
  vérification explicite au moment de la soumission bloque toute saisie
  qui ne correspond à aucune source connue, avec un message clair.

### Testé

161 tests automatisés (10 nouveaux). Vérification manuelle complète avec
un vrai moteur DOM (mode d'exécution réelle, pas une simple relecture) :
les trois boutons corrigés/retirés, la recherche et le filtre par
radionucléide combinés (avec deux sources portant des radionucléides
différents), et le flux complet "Consommer" depuis Sources jusqu'à la
pop-up de consommation pré-remplie sur la bonne page.

### Fichiers modifiés

`app/templates/movements.html` (bouton "Marquer retourné" corrigé),
`app/templates/locations.html` (bouton "Fusionner" retiré, "Supprimer"
corrigé), `app/scripts/export_excel.py` (colonne "Lieu de stockage"
retirée), `app/main.py` (liste des radionucléides distincts pour le
filtre), `app/templates/sources.html` (recherche, filtre radionucléide,
bouton Consommer), `app/templates/consumptions.html` (champ texte avec
datalist, présélection depuis l'URL, validation à la soumission),
`tests/test_consumption_movement.py`, `tests/test_export_formats.py`,
`tests/test_ergonomie_ui.py` (nouveau).

---

## 32. V0.1.24 (14/07/2026) : recherche généralisée, réimport réconcilié, réconciliation quantité restante expliquée

### Recherche libre généralisée à tous les tableaux

Nouveau module `filtrable.js` : une case de recherche libre par tableau,
qui compare le texte tapé à toutes les données de chaque ligne (attributs
déjà utilisés pour le tri, plus le texte visible des cellules en repli).
Appliqué directement à Radionucléides (demande explicite -- "je m'en
sors avec CTRL+F, mais pas optimal"), Mouvements, Lieux, Consommations,
et intégré de façon composable dans le filtre déjà en place sur Audit
(sans écraser ses propres critères -- cases à cocher, dates). En
implémentant l'intégration à Audit, trouvé que ses lignes ne portaient
l'information recherchable (source, utilisateur, champ modifié) que
dans le texte visible des cellules, pas en attribut dédié comme les
autres tableaux -- corrigé en cherchant aussi ce texte en repli.

### Inventaire physique MN : mise en page simplifiée

Comme demandé : les deux colonnes de signature (répétées sur chaque
ligne, rendant le tableau inutilement large) sont retirées, remplacées
par un bloc de signatures unique en bas du document.

### Réimport : deux bugs réels confirmés et corrigés

**Formules VBA non reprises** ("Période", "Lien LaraWeb", des formules
personnalisées allant chercher une donnée sur LaraWeb). Confirmé
empiriquement : openpyxl (qui ne sait pas exécuter une formule
lui-même) lit uniquement la dernière valeur mise en cache par Excel --
si le fichier est enregistré sans qu'Excel ait recalculé cette formule
(macros désactivées, calcul manuel, réseau indisponible au moment du
calcul), la cellule ne contient alors aucune valeur exploitable, parfois
un code d'erreur brut (`#NAME?`). C'était jusqu'ici silencieusement
ignoré ; maintenant détecté et signalé clairement dans le rapport
d'import, avec la marche à suivre pour l'éviter.

**Ajout/suppression de lignes radionucléides non synchronisé** (cas
réel : une entrée erronée "MELANGE GAMMA", qui n'est pas un vrai
radionucléide, supprimée dans le fichier réimporté ne se répercutait
pas). La cause : le mode "mise à jour" (V0.1.22) ne touchait
délibérément jamais aux radionucléides, par prudence. Étendu : pour une
source explicitement mise à jour dans le même import (et seulement
elle), les radionucléides sont maintenant réconciliés avec le fichier --
ajout de ce qui est nouveau, mise à jour de ce qui a changé, et retrait
de ce qui a disparu du fichier. Testé avec le scénario exact décrit
(retrait de "MELANGE GAMMA", conservation d'un radionucléide inchangé,
ajout d'un nouveau, le tout dans le même réimport) ; sans cette option,
comportement prudent inchangé -- jamais de suppression.

### Réconciliation de la quantité restante avec l'existant, expliquée

Question posée directement : comment déclarer la quantité restante
d'une source utilisée depuis longtemps, sans reconstituer tout
l'historique des prélèvements passés ? Vérifié que le mécanisme de
pesée de contrôle (V0.1.19) gère déjà ce cas -- y compris quand la
valeur déclarée est *inférieure* à la quantité initiale du certificat,
un scénario que le texte d'aide ne couvrait pas explicitement (il ne
parlait que de la réception d'une nouvelle source). Texte d'aide
complété, et testé de bout en bout via l'API : déclaration directe à
6g sur 10g initiaux, devenue la référence telle quelle, puis un vrai
prélèvement ultérieur qui se comporte normalement à partir de cette
nouvelle base.

### Testé

162 tests automatisés (10 nouveaux). Le mécanisme de réconciliation des
radionucléides et le scénario de réconciliation de quantité restante ont
chacun été vérifiés avec le cas concret exact décrit, pas seulement un
exemple générique.

### Fichiers ajoutés

`app/static/filtrable.js`.

### Fichiers modifiés

`app/templates/base.html` (chargement de filtrable.js), `app/static/style.css`
(style de la recherche libre), `app/templates/{radionuclides,movements,locations,consumptions}.html`
(recherche libre), `app/templates/audit.html` (recherche intégrée au
filtre existant), `app/services/export_inventaire_mn.py` (mise en page
simplifiée), `app/services/inventory_import.py` (détection d'erreur de
formule, réconciliation des radionucléides), `app/routes/import_export.py`
(nouveaux compteurs dans la réponse), `app/templates/import_export.html`
(affichage des radionucléides mis à jour/retirés), `app/templates/consumptions.html`
(texte d'aide complété), `tests/test_inventory_import_robustesse.py`,
`tests/test_consumption_movement.py`.

---

## 32. V0.1.25 (21/07/2026) : mises à jour automatisées, host/port, ménage pydantic v2

### Question posée : automatiser les montées de version

Ta proposition (uvicorn --reload surveillant un dossier géré par git,
`git pull` pour mettre à jour) est la bonne approche -- vérifiée de bout
en bout plutôt que validée en théorie : dépôt distant réel simulé (bare
repo + clone), une "nouvelle version" poussée depuis un autre poste,
`git pull` récupérant bien les changements. Puis un vrai serveur
`uvicorn --reload` lancé, et confirmation par les logs qu'un fichier
"touché" déclenche bien un redémarrage.

**Découverte utile en testant** : les templates HTML et fichiers
statiques (CSS/JS) se rechargent tout seuls à chaque requête, **sans
même redémarrer le processus** -- Jinja2 les relit du disque à chaque
fois par défaut, indépendamment de --reload. Vérifié concrètement :
modifié un bloc réellement rendu d'un template pendant que le serveur
tournait (sans toucher main.py), et la nouvelle version est apparue dans
la requête suivante sans qu'aucun redémarrage n'apparaisse dans les
logs. `--reload` (redémarrage du *processus*) n'est donc utile que pour
un changement de code Python ou une nouvelle migration -- une bonne
nouvelle, la plupart des sessions récentes touchant surtout des
templates.

Nouveau script `python -m app.scripts.mettre_a_jour` : sauvegarde la
base de données (par sécurité, horodatée), `git pull`, puis "touche"
`app/main.py` pour déclencher le rechargement de façon certaine plutôt
que de compter uniquement sur la détection automatique de tous les
fichiers modifiés par le pull.

### Question posée : host/port selon la méthode de lancement

Confirmé précisément : `python app/main.py` exécute un bloc
(`if __name__ == "__main__":`) qui lit `.env` et lance uvicorn avec ces
valeurs ; la commande `uvicorn app.main:app` en ligne de commande
importe simplement le code de l'appli sans jamais exécuter ce bloc --
ses propres options `--host`/`--port` (ou leurs défauts, localhost
uniquement) sont les seules qui comptent alors.

En ajoutant `APP_HOST`/`APP_PORT` à la configuration pour rendre `python
app/main.py` configurable par `.env`, trouvé un bug latent plus large :
`Field(env=...)`, utilisé partout dans `app/config.py`, est un paramètre
pydantic v1 silencieusement ignoré (et déprécié) en pydantic v2 -- il ne
crée pas l'alias attendu. Les réglages existants (DB_HOST, SECRET_KEY...)
fonctionnaient malgré tout, par pure coïncidence de nommage (pydantic-
settings fait correspondre un champ à sa variable d'environnement du
même nom, insensible à la casse, indépendamment de ce paramètre) --
coïncidence qui n'aurait pas joué pour `host`/`port` face à
`APP_HOST`/`APP_PORT`. Corrigé partout avec la syntaxe v2 correcte
(`validation_alias`), et au passage la classe `Config` interne
(également dépréciée) remplacée par `model_config = SettingsConfigDict(...)`.

### Testé

166 tests automatisés (3 nouveaux, pour les parties du script de mise à
jour qui ne dépendent pas d'un dépôt distant réel -- le `git pull`
lui-même a été vérifié manuellement avec un dépôt de test complet,
plutôt que reconstruit à chaque exécution de la suite pour un bénéfice
marginal).

### Fichiers ajoutés

`app/scripts/mettre_a_jour.py`, `tests/test_mettre_a_jour.py`.

### Fichiers modifiés

`app/config.py` (host/port, syntaxe pydantic v2 corrigée), `app/main.py`
(bloc `__main__` lit la configuration), `.env` (nouvelles clés
APP_HOST/APP_PORT), `README.md` (section lancement clarifiée, nouvelle
section mises à jour automatiques).

---

## 33. V0.1.26 (22/07/2026) : le vrai scénario de mise à jour, avec organisation actuelle

### Le malentendu

`mettre_a_jour.py` (session précédente) suppose une organisation
particulière : UN dossier stable, géré par git, mis à jour par
`git pull`. Or l'organisation réelle est différente : un nouveau dossier
`V0.1.XX` à chaque version reçue par archive, sans dépôt git. Lancer
`mettre_a_jour.py` depuis un tel dossier fraîchement décompressé
n'aurait rien fait d'utile : ni dépôt git à cet endroit (`git pull`
aurait échoué), ni la vraie base de données (celle livrée dans l'archive
est neuve et vide).

### La solution : un second script, pour le scénario réellement en place

Nouveau `app/scripts/appliquer_version.py` : à exécuter DEPUIS le
dossier fraîchement décompressé, en lui donnant le chemin du dossier
stable (celui d'où le serveur tourne réellement) en argument. Sauvegarde
la base du dossier STABLE (pas celle du dossier fraîchement
décompressé, neuve et sans intérêt), copie le nouveau contenu par-dessus
en épargnant `data/`, `.env` et `.git/`, commite si un dépôt git est
présent (sinon ignore cette étape sans erreur), puis déclenche le
rechargement. `mettre_a_jour.py` reste utile pour un scénario différent
(dépôt git partagé, serveur sur une autre machine) -- les deux sont
maintenant clairement distingués dans le README, avec des exemples
utilisant les chemins réels de l'utilisateur.

### Testé

Vérifié manuellement avec un scénario complet et réaliste (vraie base de
données, vrai `.env`, dépôt git initialisé, vieux fichier disparu de la
nouvelle version) : la base et les secrets survivent intacts, les
nouveaux fichiers arrivent, un commit git est créé, et le vieux fichier
disparu reste présent (une copie n'efface jamais -- limite documentée).
Trois cas limites vérifiés séparément : dossier cible sans git (étape de
commit ignorée proprement), dossier cible inexistant, et dossier cible
qui ne ressemble pas à une installation valide (refus immédiat, rien
copié). 174 tests automatisés au total (8 nouveaux pour ce script).

### Fichiers ajoutés

`app/scripts/appliquer_version.py`, `tests/test_appliquer_version.py`.

### Fichiers modifiés

`README.md` (section 5bis réécrite pour distinguer clairement les deux
scénarios, avec les chemins réels de l'utilisateur en exemple).

---

## 34. V0.1.27 (22/07/2026) : ergonomie de l'emprunt, suppression de source retirée

### Emprunt : même trou que redouté

"Je pensais que c'était fait" -- confirmé, ça ne l'était pas : la
généralisation de la recherche (session précédente) couvrait le tableau
historique des mouvements, mais pas le formulaire de démarrage d'un
emprunt lui-même, resté un menu déroulant classique. Corrigé à
l'identique du patron déjà utilisé pour Consommations : champ texte avec
suggestions (datalist), validation à la soumission, et un bouton
"Emprunter" sur chaque ligne éligible de Sources (calculé côté route :
pas d'emprunt déjà en cours, pas archivée, lieu habituel défini),
ouvrant la pop-up déjà pré-remplie via `?source=XXX` dans l'URL.

En éditant le template, une erreur de structure Jinja m'a échappé un
instant (le bouton "Supprimer" se retrouvait par erreur à l'intérieur de
la nouvelle condition "peut emprunter", donc caché pour toute source non
éligible à l'emprunt) -- repérée et corrigée avant packaging, en
relisant la structure générée plutôt qu'en supposant qu'elle était
correcte.

Vérifié avec un vrai moteur DOM : présélection depuis l'URL, champ texte
(pas un select), rejet d'une saisie invalide sans requête réseau, et
soumission valide avec le bon contenu envoyé.

### Suppression de source : retirée

Question posée directement : pourquoi autoriser la suppression
définitive d'une source, plutôt que la faire persister avec un statut
"détruite" ? Investigation avant de répondre : la route avait déjà un
garde-fou partiel (refusait de supprimer une source avec des
consommations ou mouvements rattachés, avec un message suggérant déjà le
statut "en déchet") -- mais un vrai trou : les radionucléides n'étaient
PAS protégés de la même façon (suppression en cascade), une source sans
consommation/mouvement mais avec des radionucléides pouvait donc être
supprimée avec ses données, sans avertissement. Le statut "détruite"
existait déjà comme alternative traçable.

Conclusion : pas de raison suffisante de garder cette possibilité,
plutôt que de combler ce trou au cas par cas. Route de suppression
retirée entièrement (remplacée par un commentaire expliquant le
raisonnement), bouton et fonction JS associée retirés, méthode du
repository devenue inutilisée retirée également, import désormais
inutile nettoyé au passage.

### Testé

180 tests automatisés (7 nouveaux ou corrigés) : deux tests qui testaient
spécifiquement la suppression retirés (la fonctionnalité n'existe plus),
un nouveau test confirme explicitement que la route répond désormais 405
plutôt que d'accepter la requête, et un test de réimport qui utilisait la
suppression comme étape de préparation adapté pour ne plus en dépendre
(un identifiant jamais créé simule directement le scénario visé, sans
avoir besoin de supprimer quoi que ce soit).

### Fichiers modifiés

`app/routes/sources.py` (route de suppression retirée, import devenu
inutile nettoyé), `app/repositories/source.py` (méthode delete retirée),
`app/templates/sources.html` (bouton Emprunter, bouton Supprimer
retiré), `app/templates/movements.html` (champ texte avec suggestions,
présélection depuis l'URL), `app/main.py` (éligibilité à l'emprunt
calculée pour chaque source), `tests/test_ergonomie_ui.py`,
`tests/test_sources_permissions.py`, `tests/test_inventory_import_robustesse.py`.

---

## 35. V0.1.28 (23/07/2026) : mésaventure git réelle, résolue et testée ; push automatique ; retour en arrière testé

### La mésaventure

Premier essai concret de la mise en place git : un `git init` séparé
dans chaque dossier de version (V0.1.27, et apparemment déjà V0.1.26
avant), sans lien entre eux, plus un dossier "current" possédant lui
aussi son propre historique indépendant. Résultat : rejet du push
("fetch first"), puis "refusing to merge unrelated histories" au
`git pull` depuis "current". Rien d'endommagé, mais une vraie confusion,
exactement le genre de situation où deviner une solution aurait été
risqué.

Diagnostic reconstruit, puis **la solution complète simulée avant
d'être transmise** : dépôt distant bare, dossier avec historique
indépendant ET contenu différent (le cas réel), vraie base de données et
vrai `.env` non suivis. Testé précisément le point de friction (`git
checkout` refuse d'écraser un fichier non suivi qui diffère -- d'où le
besoin du `-f`), et confirmé que la vraie base et le vrai `.env`
ressortent intacts après coup (`git status --ignored` le confirme). Le
nettoyage des branches parasites (`git push origin --delete`) testé
également.

### Push automatique ajouté

Question posée directement : pourquoi le commit n'est-il pas suivi d'un
push automatique ? Bonne question -- ajouté. `appliquer_version.py`
pousse maintenant vers le dépôt distant après chaque commit, s'il y en a
un de configuré. Un échec (pas de réseau, dépôt distant qui a avancé
ailleurs) ne fait jamais échouer la mise à jour : le commit local, lui,
a déjà réussi, et un message clair indique la marche à suivre. Les trois
cas (succès, aucun remote configuré, push refusé) vérifiés avec de vrais
dépôts git, pas seulement supposés -- y compris en reproduisant pour de
vrai un push refusé (un second clone qui pousse une modification
concurrente avant nous).

### "Pas besoin de git pull dans current ?"

Clarifié : dans le scénario où la mise à jour vient d'un fichier reçu
puis appliqué par le script (pas d'un `git pull`), la source de vérité
est directement ce fichier -- rien à récupérer depuis le dépôt distant à
ce moment-là. `git pull`/`mettre_a_jour.py` restent réservés à l'autre
scénario (récupérer un changement fait ailleurs, ex. une seconde
machine).

### Retour en arrière : conçu et testé, pas seulement documenté

Question de sécurité légitime : et si une version posait problème ?
Processus construit et vérifié de bout en bout sur un scénario simulé
complet (V0.1.27 fonctionnelle, V0.1.28 avec un "bug", sauvegarde de
base automatique entre les deux) : `git checkout <commit> -- app/` puis
un nouveau commit restaure le code sans réécrire l'historique (les trois
commits restent visibles, honnêtes) ; copier la sauvegarde horodatée
(déjà créée automatiquement par le script avant chaque mise à jour)
restaure la base. Les deux étapes vérifiées ensemble, dans l'ordre.

### Testé

183 tests automatisés (3 nouveaux, pour le push automatique dans ses
trois cas). Le nom de branche par défaut de l'environnement de test
("master" plutôt que "main") a nécessité un ajustement dans le montage
des tests eux-mêmes (`--initial-branch=main` explicite) -- trouvé en
creusant un échec, pas ignoré.

### Fichiers modifiés

`app/scripts/appliquer_version.py` (push automatique après le commit),
`tests/test_appliquer_version.py` (tests du push, correction du nom de
branche par défaut), `README.md` (section 5bis complétée : push
automatique, clarification git pull, processus de retour en arrière
testé).

---

## 36. V0.1.29 (24/07/2026) : cascade de rechargement sur Windows

### Cas réel rencontré

La procédure de récupération git (session précédente) et
`appliquer_version.py` ont tous les deux fonctionné correctement --
confirmé par le propre journal du script ("Commit git créé", "Poussé
vers le dépôt distant avec succès"). Mais la page web restait affichée
en version antérieure. Le journal du serveur (terminal 1, fourni par
l'utilisateur) montre la cause : neuf vagues successives de
"WatchFiles detected changes... Reloading..." se sont interrompues les
unes les autres (`KeyboardInterrupt` à chaque fois, en pleine
séquence d'import) avant qu'une dixième ne finisse par aboutir. Le
dossier étant sur un lecteur réseau (chemin UNC), la détection de
changements y est probablement moins fiable et plus lente que sur un
disque local, ce qui a dû amplifier le phénomène.

Diagnostic raisonné plutôt que reproduit à l'identique : impossible de
simuler un Windows avec `multiprocessing` en mode "spawn" sur un lecteur
réseau depuis ce bac à sable Linux -- dit explicitement à l'utilisateur,
plutôt que de prétendre à une certitude qui n'existe pas. Le correctif
proposé (avertissement explicite, redémarrage manuel en dernier
recours) reste valable indépendamment du mécanisme exact en cause.

### Corrigé

`appliquer_version.py` affiche maintenant un avertissement explicite
sur Windows après une mise à jour, invitant à vérifier la version
affichée et à redémarrer manuellement en cas de doute plutôt que de
faire confiance aveuglément au rechargement automatique. Absent sur les
autres plateformes (vérifié par test, simulation de `platform.system()`
dans les deux sens).

### Testé

185 tests automatisés (2 nouveaux, pour l'avertissement Windows -- avec
et sans la plateforme simulée).

### Fichiers modifiés

`app/scripts/appliquer_version.py` (avertissement Windows après
rechargement), `tests/test_appliquer_version.py`, `README.md` (section
5bis, nouvelle sous-section E).

---

## 37. V0.1.30 (28/07/2026) : recherche Sources généralisée, lien "gérer tous les lieux" ajouté

### Recherche Sources, mise à niveau

Signalé directement : le champ de recherche de Sources était plus
restrictif que sur les autres pages (ne comparait qu'à l'identifiant),
avec un menu déroulant séparé pour filtrer par radionucléide. Généralisé
pour utiliser la même fonction que Radionucléides/Mouvements/Lieux/
Consommations (`texteCorrespond`, voir filtrable.js) : compare
maintenant le texte tapé à l'identifiant, au(x) radionucléide(s), au
lieu, etc. Le menu déroulant devenu redondant (taper un nom de
radionucléide dans la recherche libre le trouve déjà) a été retiré, côté
template ET côté route (calcul de la liste des radionucléides distincts,
qui ne servait plus qu'à peupler ce menu).

Vérifié avec un vrai moteur DOM : recherche par identifiant, par
radionucléide (impossible avant sans le menu dédié), et par lieu --
chacune isolant correctement les bonnes sources.

### Lien "Gérer tous les lieux" ajouté sur Sources

Le bouton "+ Lieu" existait déjà sur Sources, avec son pendant
radionucléide ("+ Ajouter un radionucléide" + "Gérer tous les
radionucléides →") mais sans lien équivalent vers la page Lieux --
contrairement à Mouvements, qui a déjà les deux. Généralisé : Sources a
maintenant aussi son lien "Gérer tous les lieux →", au même endroit que
celui des radionucléides.

### Testé

186 tests automatisés (un test obsolète adapté pour vérifier le nouveau
comportement plutôt que l'ancien menu déroulant, deux nouveaux pour le
lien lieux et pour l'attribut porté par chaque ligne).

### Fichiers modifiés

`app/templates/sources.html` (recherche généralisée, menu déroulant
retiré, lien lieux ajouté), `app/main.py` (calcul devenu inutile
retiré), `tests/test_ergonomie_ui.py`, `README.md`.

---

## 38. V0.1.31 (28/07/2026) : revue de liens croisés, import de consommations historiques

### Revue de cohérence des liens croisés

Demandé directement, en suite du travail précédent : partout où un
identifiant de source, un nom de radionucléide ou un lieu était affiché
en texte brut sur une page qui n'est pas la sienne, ça devient
maintenant un lien vers la bonne page. Passage systématique par tous
les templates plutôt qu'au cas par cas : identifiant source sur
Radionucléides/Mouvements/Consommations/Audit, lieux sur Mouvements (les
deux colonnes), noms de radionucléides et lieu sur Sources elle-même.

Nécessitait d'abord une brique manquante : un paramètre `?recherche=`
dans l'URL, lu et appliqué au chargement de la page (ajouté à la fois
dans le module générique `rendreFiltrable` et dans la recherche maison
de Sources). Vérifié avec un vrai moteur DOM que cliquer un lien croisé
arrive bien sur la page cible avec la recherche déjà appliquée, pas
seulement préremplie -- sur les deux implémentations (Sources et une
page utilisant le module générique).

### Import de consommations historiques

Nouveau chantier : les consommations étaient jusqu'ici tenues sur des
fiches papier. Flux retenu (proposé par l'utilisateur) : transcription
en tableur Excel (par Claude, à partir de scans à venir), relecture et
correction par l'utilisateur -- la vérification a lieu à CE moment --
puis import volontairement simple ("idiot"), sans bouton dédié dans
l'interface.

Deux points techniques vérifiés avant d'écrire une ligne de code,
plutôt que supposés : `quantite_restante_calculee()` trie déjà
explicitement par date au moment du calcul (jamais par ordre
d'insertion), donc l'ordre des lignes du fichier n'a aucune importance ;
le champ `timestamp` de `ConsumptionDB` accepte une valeur explicite
(pas seulement "maintenant"), donc les dates historiques passent sans
souci en travaillant directement au niveau du modèle plutôt que via le
service habituel (pensé pour la saisie en direct).

Nouveau service (`import_consommations_historiques.py`) : format Excel
simple (ID Source, Date, Masse avant/après, Quantité utilisée,
Commentaire, Utilisateur), génération d'un modèle vide pour cadrer la
transcription, import avec rapport clair (créées / ignorées avec
raison). Point d'entrée en ligne de commande, pas de route HTTP.

Vérifié avec un scénario construit exprès pour mettre à l'épreuve le
point le plus important plutôt que le supposer : trois pesées d'une même
source, saisies **volontairement dans le désordre chronologique** dans
le fichier -- le calcul de quantité restante donne bien le même résultat
qu'un import trié. Vérifié aussi que les dates s'affichent correctement
sur la page Consommations (les dates historiques, pas la date du jour).

### Testé

202 tests automatisés (16 nouveaux : 7 pour les liens croisés, 9 pour
l'import historique). Une nouvelle fixture `db_session` ajoutée à
`conftest.py`, nécessaire pour tester un script autonome qui travaille
directement avec une session de base de données plutôt que par l'API
HTTP habituelle de ce projet.

### Fichiers ajoutés

`app/services/import_consommations_historiques.py`,
`app/scripts/import_consommations_historiques.py`,
`tests/test_import_consommations_historiques.py`,
`tests/test_liens_croises.py`.

### Fichiers modifiés

`app/static/filtrable.js` (préremplissage depuis ?recherche=),
`app/templates/{radionuclides,movements,consumptions,audit,sources}.html`
(liens croisés, préremplissage sur Sources), `tests/conftest.py`
(fixture db_session), `README.md`.

---

## 39. V0.1.32 (30/07/2026) : fiche détaillée par source, réalisée

### La fiche elle-même

Proposition de la session précédente, demandée directement cette fois :
une page par source (`/sources/{id}/fiche`), regroupant informations
générales, radionucléides, mouvements et consommations. Réutilise les
mêmes calculs dérivés que la liste des sources (quantité restante,
activité actuelle par radionucléide, éligibilité à l'emprunt) plutôt que
de les recalculer différemment -- même logique, appliquée à une seule
source. `formater_duree` (déjà utilisée en Python) enregistrée comme
fonction Jinja globale au passage, nécessaire pour afficher la période
radioactive de façon lisible sur cette page (elle ne l'était pas
encore).

Décision prise en construisant : pas de duplication du formulaire de
modification (assez complexe) sur cette nouvelle page. Le bouton
"Modifier" renvoie vers la liste des sources, déjà filtrée sur cette
source précise, où ce formulaire existe déjà et fonctionne -- une seule
version à maintenir plutôt que deux copies à garder synchronisées pour
toujours.

Vérifié avec un vrai serveur et des données complètes (radionucléide,
mouvement en cours, consommation) : quantité restante correctement
calculée, emplacement habituel distingué de l'emplacement actuel (mis à
jour par l'emprunt en cours), bouton "Emprunter" correctement absent
puisqu'un emprunt est déjà en cours, badge "en cours" affiché sur le
mouvement concerné.

### Liens croisés ajustés en conséquence

Les liens croisés de la session précédente (identifiant de source sur
Radionucléides/Mouvements/Consommations/Audit) pointaient vers la liste
des sources filtrée -- ils pointent maintenant vers cette fiche, une
destination plus directe pour "en savoir plus sur cette source
précise". Les liens vers les lieux et les radionucléides (pas liés à une
source unique) restent inchangés, vers la liste filtrée. L'identifiant
lui-même, sur la page Sources, devient aussi cliquable vers sa propre
fiche (il était en texte brut jusqu'ici).

### Testé

211 tests automatisés (16 nouveaux : 9 pour la fiche elle-même,
4 mis à jour pour la nouvelle destination des liens croisés). Contrôle
d'accès vérifié explicitement : une source classée Matière Nucléaire
renvoie 404 (pas 403) à un compte sans accès MN, même logique que
l'API JSON existante.

### Fichiers ajoutés

`app/templates/fiche_source.html`, `tests/test_fiche_source.py`.

### Fichiers modifiés

`app/main.py` (route de la fiche, `formater_duree` enregistrée comme
fonction Jinja globale), `app/static/style.css` (mise en page de la
fiche), `app/templates/{radionuclides,movements,consumptions,audit,sources}.html`
(liens croisés redirigés vers la fiche), `tests/test_liens_croises.py`,
`README.md`.

---

## 40. V0.1.33 (30/07/2026) : dates en français partout

### Le filtre

Demandé directement, sur l'exemple précis de la date de référence d'un
radionucléide. Nouveau filtre Jinja `date_fr` (dans units.py, aux côtés
de `arrondir_scientifique` et `formater_duree`) : JJ/MM/AAAA, avec une
option heure quand pertinent (audit, demandes de rôle), valeur nulle
gérée proprement ("—").

### Recherche systématique plutôt qu'un correctif isolé

Plutôt que de corriger uniquement l'exemple donné, recherche dans tous
les templates. Trouvé et corrigé : Sources, Archive des sources,
Radionucléides, Mouvements (trois dates), Consommations, Audit, la
fiche source (où plusieurs dates étaient déjà en français par
construction précédente, d'autres non -- harmonisées pour utiliser
toutes le même filtre), et une page non anticipée -- la date de demande
de rôle sur la page Utilisateurs, trouvée en élargissant la recherche.
Un cas côté JavaScript (pas un template Jinja) également trouvé et
corrigé : le message affiché après import d'un certificat PDF montrait
une date ISO brute reçue du serveur en JSON.

Point vérifié avec soin, pas supposé : les attributs `data-*` utilisés
en interne pour le tri chronologique des tableaux restent en ISO
(nécessaire pour un tri correct -- JJ/MM/AAAA ne se trie pas
correctement comme texte). Confirmé avec un vrai serveur, sur toutes
les pages, qu'aucune date ISO ne reste visible dans le texte affiché,
uniquement dans ces attributs internes.

### Testé

221 tests automatisés (10 nouveaux). Deux bugs trouvés dans mes propres
tests en les écrivant, pas dans l'application : une assertion trop
stricte ne tenant pas compte d'un champ de saisie caché légitimement en
ISO, et un nom de route mal deviné pour la demande de rôle (corrigé en
retrouvant le vrai nom dans le code plutôt qu'en devinant à nouveau) --
et un piège de fixtures (client et admin_client partagent le même
client de test sous-jacent ; register_and_login sur l'un écrase la
session de l'autre) déjà documenté dans un test existant, dont j'ai
repris exactement le correctif établi.

### Fichiers ajoutés

`tests/test_dates_francaises.py`.

### Fichiers modifiés

`app/services/units.py` (fonction `date_fr`), `app/main.py` (filtre
Jinja enregistré), `app/templates/{sources,sources_archive,radionuclides,consumptions,movements,audit,fiche_source,users}.html`,
`README.md`.

---

## 41. V0.1.34 (30/07/2026) : spectre-type des consommations, généralisé à tous les radionucléides

### La fonctionnalité

Proposée par l'utilisateur : estimer la composition isotopique des
déchets (supposée proportionnelle à l'activité des sources mères
consommées) sur une plage de temps, avec l'activité de chaque
radionucléide amenée par décroissance jusqu'à une date de référence
choisie (aujourd'hui par défaut, n'importe quelle date égale ou
postérieure à la fin de la plage sinon -- une date antérieure est
refusée explicitement, la décroissance n'ayant de sens que vers l'avant
dans le temps).

Vérifié avant d'écrire du code, pas supposé : `DecayService.calculate_activity`
accepte déjà n'importe quelle date de départ et d'arrivée, pas seulement
celle du radionucléide -- directement réutilisable pour amener une
activité calculée à la date d'une consommation jusqu'à la date de
référence souhaitée.

### La question posée en retour, et sa réponse

"Pourquoi ne pas faire le calcul sur tous les rn d'une source ?" --
question légitime, qui méritait d'être creusée plutôt que de reproduire
sans réfléchir la simplification historique ("premier radionucléide
seulement", héritée de `activite_utilisee_bq`). Vérifié précisément :
`_quantite_avant_consommation` (la quantité physique juste avant une
consommation) est une grandeur de la SOURCE dans son ensemble, jamais
spécifique à un radionucléide -- rien à répartir entre plusieurs
radionucléides, la même fraction s'applique identiquement à chacun. Pas
de vraie difficulté mathématique : juste une boucle jamais écrite,
probablement parce que jamais nécessaire en pratique (sources
consommables actuellement toutes mono-élémentaires, confirmé par
l'utilisateur).

Nouvelle fonction `activites_par_radionuclide_bq` (généralisation propre,
pas un correctif ad hoc) : même calcul que l'historique, mais pour
chaque radionucléide de la source. L'ancienne fonction, utilisée ailleurs
pour un affichage à valeur unique (colonne "Activité utilisée" sur
Consommations), n'a volontairement pas été modifiée -- portée limitée au
sujet demandé, pas de changement de comportement en dehors de lui.
Hypothèse d'homogénéité assumée explicitement (un mélange homogène
répartit chaque radionucléide uniformément dans toute la quantité
physique) plutôt que cachée.

### Testé

231 tests automatisés (13 nouveaux). Vérifié avec une vraie source à
deux radionucléides (Co-60 5 Bq/g + Cs-137 15 Bq/g) consommée une seule
fois : les deux contributions apparaissent, correctement et
indépendamment, dans le calcul direct ET sur la page web -- pas
seulement la première comme avant cette généralisation.

### Fichiers ajoutés

`app/services/spectre_consommation.py`, `app/templates/spectre_consommation.html`,
`tests/test_spectre_consommation.py`.

### Fichiers modifiés

`app/services/units.py` (nouvelle fonction `activites_par_radionuclide_bq`),
`app/main.py` (route `/consumptions/spectre`, `formater_activite_bq`
enregistrée comme fonction Jinja globale), `app/templates/consumptions.html`
(lien vers le nouvel outil), `README.md`.

---

## 42. V0.1.35 (31/07/2026) : modifier/supprimer une consommation, harmonisation, doublons, spectre

### Contexte du signalement

Retour direct après un premier essai réel de l'import historique : le
même document importé deux fois par erreur a dupliqué tous les
prélèvements, et une ligne portait la mauvaise année -- sans moyen de
corriger après coup, seule la valeur d'une consommation pouvait être
modifiée, pas sa date, et rien ne pouvait être supprimé.

### Modifier et supprimer une consommation

Date ajoutée à la correction (`ConsumptionUpdate.timestamp`, déjà géré
génériquement par le repository -- aucune logique supplémentaire
nécessaire). Nouvelle route `DELETE /consumptions/{id}` : contrairement
aux sources (jamais supprimables, un objet physique reste toujours
traçable même détruit), une consommation en doublon ne correspond à
AUCUN événement réel -- rien à archiver, la supprimer ne perd aucune
trace d'un fait qui ne s'est jamais produit. La suppression elle-même
reste tracée dans l'audit.

Un vrai bug trouvé en testant avec un moteur DOM plutôt qu'en relisant
le code : le champ date du formulaire de correction restait vide, le
JSON envoyé au frontend n'incluait jamais `timestamp`.

### Harmonisation (question posée en retour : "à réfléchir et harmoniser")

Le même patron (Annuler / Enregistrer / Supprimer, en bas de la pop-up)
étendu à Radionucléides et Lieux -- Supprimer, qui vivait jusqu'ici sur
la ligne du tableau, déplacé dans la pop-up de modification, visible
seulement en édition (pas en création). Sources garde Annuler/Enregistrer
SANS Supprimer, choix déjà établi et volontairement pas remis en
question ici.

### Détection de doublons à l'import historique

Avant chaque création, vérifie si une consommation existe déjà pour la
même source à la même date (déjà en base, ou déjà rencontrée plus tôt
dans le même fichier) -- signalé clairement dans le rapport, jamais
bloquant (reste un import "idiot", deux prélèvements réels le même jour
restant possibles). Vérifié en rejouant exactement le scénario signalé
(même fichier importé deux fois) : les deux lignes correctement
signalées comme doublons potentiels.

### Spectre : message technique retiré, export ajouté

Le message d'avertissement référençant le nom d'une fonction Python
interne ("voir activites_par_radionuclide_bq") retiré, remplacé par une
explication compréhensible. Export Excel du spectre ajouté (deux
feuilles), avec exactement les mêmes paramètres de date que la page.
Logique commune aux deux routes (page + export) extraite dans une
fonction partagée plutôt que dupliquée.

### Testé

247 tests automatisés (23 nouveaux). Plusieurs bugs trouvés dans mes
propres tests en les écrivant (données de test manquantes, fixtures mal
utilisées) -- corrigés en retrouvant la cause exacte plutôt qu'en
contournant l'assertion.

### Fichiers ajoutés

`tests/test_harmonisation_boutons.py`.

### Fichiers modifiés

`app/models/consumption.py` (champ `timestamp` sur `ConsumptionUpdate`),
`app/routes/consumptions.py` (route DELETE, `timestamp` dans l'audit),
`app/repositories/consumption.py` (méthode `delete`),
`app/templates/{consumptions,radionuclides,locations,sources}.html`
(boutons harmonisés), `app/services/import_consommations_historiques.py`
(détection de doublons), `app/scripts/import_consommations_historiques.py`
(affichage des doublons), `app/services/spectre_consommation.py` (message
corrigé, export Excel), `app/main.py` (route d'export, logique partagée),
`app/templates/spectre_consommation.html` (bouton d'export),
`tests/test_consumption_movement.py`,
`tests/test_import_consommations_historiques.py`,
`tests/test_spectre_consommation.py`, `README.md`.

---

## 43. V0.1.36 (31/07/2026) : hauteur des boutons harmonisée, diagnostic 405

### Boutons Annuler/Enregistrer/Supprimer, hauteur incohérente

Signalé directement : la largeur différente entre les trois boutons est
normale (texte de longueur différente), la hauteur ne l'était pas.
`.actions-row` (flex) n'imposait pas d'`align-items` explicite -- ajouté
sur les trois pop-up concernées (Consommations, Radionucléides, Lieux),
sur le conteneur extérieur ET le conteneur imbriqué (Annuler/Enregistrer),
pour une hauteur cohérente entre les trois boutons quelle que soit
l'imbrication.

### DELETE /consumptions/9 → 405 Method Not Allowed, date non prise en compte

Signalé comme un bug, mais non reproductible sur le code de la V0.1.35 :
`DELETE /consumptions/9` renvoie 204 (vérifié avec un vrai serveur, base
neuve, neuf consommations créées puis la neuvième supprimée exactement
comme dans le journal transmis), et la modification de date fonctionne
correctement (vérifié aussi). Un 405 sur cette route précise, combiné à
une date silencieusement ignorée alors que le commentaire et la quantité
passent (exactement ce que donnerait un serveur qui ignore un champ
inconnu), pointe fortement vers une version de l'application antérieure
à la V0.1.35 (celle où le champ `timestamp` et la route DELETE ont été
ajoutés) encore active côté utilisateur -- pas un défaut du code actuel.
À confirmer en vérifiant le numéro de version affiché en bas de la barre
latérale de l'application réellement lancée.

### Testé

244 tests toujours passants (aucun changement fonctionnel, uniquement du
CSS). Comportement DELETE et PATCH (date) revérifiés manuellement avec
un vrai serveur sur une base neuve, en reproduisant exactement le
scénario du journal transmis.

### Fichiers modifiés

`app/templates/{consumptions,locations,radionuclides}.html` (`align-items`
explicite sur les conteneurs de boutons), `README.md`.

---

## 44. V0.1.37 (31/07/2026) : vérification automatique de la version en ligne

### Confirmation du diagnostic

L'utilisateur confirme : la version affichée était bien la V0.1.34, pas
la V0.1.36 -- exactement le même mécanisme que l'incident du 24/07/2026
(cascade de rechargement Windows sur lecteur réseau), déjà documenté et
déjà pourvu d'un avertissement textuel dans `appliquer_version.py`.
Cet avertissement, seul, s'est montré insuffisant en pratique.

### La vraie correction : vérifier plutôt qu'avertir

Plutôt que reformuler l'avertissement une nouvelle fois, `appliquer_version.py`
vérifie maintenant lui-même. Nouvel endpoint `GET /version` (sans
authentification -- ce n'est qu'un numéro de version) ; le script
interroge `http://127.0.0.1:8000/version` une fois la mise à jour
appliquée et compare à la version qui vient d'être déployée, avec un
avertissement impossible à manquer en cas d'écart. Ne bloque jamais si
le serveur n'est pas joignable.

Un vrai bug trouvé en écrivant les tests, pas en écrivant le code :
lire la version attendue via `from app.version import APP_VERSION`
tombait dans le cache d'import Python (`sys.modules`) dès que `app.version`
avait déjà été importé ailleurs dans le même processus -- invisible en
usage réel (le script tourne toujours dans un processus frais), mais
révélé immédiatement par les tests (qui, eux, tournent tous dans le
même processus pytest). Corrigé en lisant et parsant le fichier
`version.py` directement plutôt qu'en l'important, ce qui élimine le
risque plutôt que de le contourner.

Vérifié avec un vrai serveur et un processus isolé, dans les trois cas :
version qui correspond, version qui diverge (le scénario réel rejoué),
serveur injoignable.

### Boutons : hauteur harmonisée

Signalé au passage : la largeur différente entre Annuler/Enregistrer/
Supprimer est normale (texte de longueur différente), la hauteur ne
l'était pas -- `align-items` explicite ajouté sur les conteneurs
concernés.

### Testé

251 tests automatisés (5 nouveaux). Un des nouveaux tests a lui-même
révélé le bug de cache d'import ci-dessus avant d'être corrigé.

### Fichiers modifiés

`app/main.py` (endpoint `/version`), `app/scripts/appliquer_version.py`
(`verifier_version_en_ligne`, lecture directe du fichier plutôt
qu'import), `tests/test_appliquer_version.py`, `README.md`.

---

## 45. V0.1.38 (31/07/2026) : la vraie cause du blocage de version, trouvée et corrigée

### Le correctif précédent ne suffisait pas

Confirmé par l'utilisateur : `--reload` désactivé, serveur arrêté avant
chaque mise à jour, "current" vérifié à jour sur disque (git, contenu
des fichiers) -- et pourtant, toujours V0.1.34 affichée après
redémarrage complet. Un indice décisif dans son message : la hauteur
des boutons (un changement de gabarit HTML) s'était bien mise à jour,
mais pas le numéro de version (lu depuis un module Python). Ce
déséquilibre pointait vers quelque chose de spécifique à l'exécution de
code Python, pas vers les gabarits eux-mêmes.

### Diagnostic : le cache bytecode Python, pas le rechargement

Hypothèse posée, puis vérifiée empiriquement avant d'écrire une seule
ligne de correctif (pas supposée) : quand un fichier `.py` remplacé se
retrouve avec exactement le même (date de modification, taille en
octets) que l'ancien -- possible sur un lecteur réseau, où la
granularité d'horodatage est plus grossière qu'en local -- la
vérification par défaut de Python considère à tort son cache compilé
(`__pycache__`) toujours valide, et continue à exécuter silencieusement
le bytecode de l'ANCIENNE version. Reproduit dans un premier temps de
façon isolée (deux fichiers factices, mtime identique forcé), puis dans
un test automatisé complet simulant tout le scénario réel.

`__pycache__` n'est jamais copié depuis la nouvelle version (déjà
exclu de la copie) -- les anciens dossiers, sur la cible, ne sont donc
jamais remplacés par la copie elle-même. `appliquer_version.py` les
supprime maintenant explicitement à chaque mise à jour, ce qui élimine
le risque à la racine plutôt que de dépendre d'une comparaison
d'horodatage démontrée non fiable dans ce contexte précis.

### Testé

254 tests automatisés (3 nouveaux, dont une reproduction complète du
bug ET de son correctif dans le même test -- vérifié que le problème se
produit bien sans le correctif, avant de vérifier qu'il disparaît avec,
plutôt que de supposer que l'un implique l'autre).

### Fichiers modifiés

`app/scripts/appliquer_version.py` (fonction `nettoyer_cache_bytecode`,
appelée après la copie), `tests/test_appliquer_version.py`, `README.md`.

---

## 46. V0.1.39 (31/07/2026) : trois bugs concrets, passe boutons complète, formulaire du spectre retravaillé

### Trois bugs signalés directement

**Masses sans unité sur la fiche source** : masse avant/après affichaient
juste un nombre, sans "g" ou "mL" -- corrigé sur le même modèle que la
page Consommations (qui l'affichait déjà).

**"Modifier" depuis la fiche source renvoyait à la liste, pas au
formulaire** : fallait recliquer "Modifier" une seconde fois. Ajouté un
paramètre `?modifier=XXX`, même principe que `?source=XXX` sur
Consommations/Mouvements. Un vrai bug d'introduction trouvé et corrigé
en testant avec un moteur DOM : le code vivait dans le premier des deux
blocs `<script>` de `sources.html`, avant que `openEditModal` (défini
dans le second) n'existe encore -- déplacé au bon endroit.

**Pop-up d'emprunt qui se rouvrait après validation** :
`window.location.reload()` gardait `?source=XXX` dans l'URL (arrivée
depuis le bouton "Emprunter" d'une source), ce qui redéclenchait
l'ouverture automatique de cette même pop-up juste après le succès.
Remplacé par une redirection vers une URL propre sur les trois
soumissions de la page Mouvements.

### Passe boutons complète

Demandé directement : "une passe complète et totale de l'ensemble des
boutons pour les aligner, les rendre homogènes." Audit systématique de
TOUTES les pop-up de l'application (13, recensées une à une plutôt
qu'au cas par cas) : bien plus d'incohérences que prévu -- les trois
formulaires de Mouvements, les deux ajouts rapides sur Sources, le
formulaire de l'archive des sources, la création de consommation, et
les deux pop-up globales de `base.html` (mot de passe, demande de rôle)
n'avaient AUCUN bouton "Annuler", juste un bouton d'action seul.

Plutôt que de répéter un style en ligne sur chaque pop-up (source de la
dérive initiale), nouvelle classe CSS dédiée (`.modal-actions`)
centralisant le patron une bonne fois. Vérifié par comptage que chaque
page a désormais une correspondance exacte entre son nombre de boutons
`submit` et son nombre de boutons "Annuler", puis fonctionnellement
avec un moteur DOM sur un échantillon (ouverture, fermeture par
Annuler) plutôt que textuellement seulement.

### Formulaire du spectre-type retravaillé

Trois libellés de longueurs très inégales ("Du", "Au", "Spectre à la
date du") cassaient l'alignement vertical entre les champs. Retravaillé :
la plage de dates (Du/Au) groupée visuellement sous un même intitulé,
séparée par un trait vertical de la date de référence (un concept
différent -- à quelle date calculer la décroissance), plutôt que trois
champs de poids visuel identique sans hiérarchie.

### Testé

263 tests automatisés (17 nouveaux). Plusieurs bugs trouvés dans mes
propres tests en les écrivant (oublis de données préalables pour que
certains formulaires se rendent, page globale non comptée) -- corrigés
en retrouvant la cause exacte.

### Fichiers modifiés

`app/main.py` (unités sur les masses, fiche source), `app/templates/fiche_source.html`
(unités, lien Modifier), `app/templates/sources.html` (`?modifier=`,
placé dans le bon bloc script), `app/templates/movements.html`
(redirection propre, Annuler sur les trois formulaires),
`app/templates/{consumptions,locations,radionuclides,sources,sources_archive,base}.html`
(classe `.modal-actions`, Annuler ajouté où manquant),
`app/templates/spectre_consommation.html` (formulaire retravaillé),
`app/static/style.css` (`.modal-actions`, `.spectre-form`),
`tests/test_fiche_source.py`, `tests/test_consumption_movement.py`,
`tests/test_harmonisation_boutons.py`, `tests/test_spectre_consommation.py`,
`README.md`.

---

## 47. V0.1.40 (31/07/2026) : favicon

### Le signalement

`GET /favicon.ico` journalisé en 404 de façon récurrente par uvicorn --
les navigateurs sondent systématiquement cette adresse à la racine du
site, indépendamment de toute balise dans le `<head>` (qui n'existait
d'ailleurs pas du tout jusqu'ici).

### Réalisé

Repris fidèlement le mark déjà utilisé dans la barre latérale (la même
courbe et le même point, en teal `#4fb8b8`) plutôt qu'inventer un
nouveau symbole, sur un fond reprenant le dégradé sombre de la barre
latérale elle-même -- cohérence visuelle avec l'identité déjà en place.
Vérifié visuellement à 16px et 32px (agrandi en préservant les pixels
exacts pour juger fidèlement du rendu réel, pas d'un aperçu lissé) avant
de valider le choix.

Trois fichiers : `favicon.ico` (multi-résolution 16/32/48, pour la
compatibilité la plus large), `favicon.svg` (net à toute taille sur les
navigateurs récents), `apple-touch-icon.png` (180×180, favoris/écran
d'accueil iOS). Balises `<link>` correspondantes ajoutées dans le
`<head>` de `base.html`, avec le même paramètre de version anti-cache
que les autres ressources statiques. Route dédiée `GET /favicon.ico` à
la racine (en plus de `/static/favicon.ico`) : c'est spécifiquement
cette adresse que les navigateurs sondent d'eux-mêmes, d'où le 404
initial malgré la présence du fichier dans `/static/`.

Vérifié qu'une requête HEAD sur cette nouvelle route renvoie 405 --
mais confirmé qu'il s'agit d'un comportement déjà présent sur toutes
les routes GET existantes de l'application (`/sources`, `/` compris),
pas une régression propre à cette route ; hors sujet, non traité ici.

### Testé

267 tests automatisés (4 nouveaux). Vérifié avec un vrai serveur que
`GET /favicon.ico` renvoie 200, exactement la requête journalisée dans
le signalement initial.

### Fichiers ajoutés

`app/static/favicon.ico`, `app/static/favicon.svg`,
`app/static/apple-touch-icon.png`, `tests/test_favicon.py`.

### Fichiers modifiés

`app/main.py` (route `/favicon.ico`), `app/templates/base.html`
(balises `<link>`), `README.md`.

---

## 48. V0.1.41 (31/08/2026) : "fatal: detected dubious ownership" à la mise à jour

### Le signalement

Journal du script de mise à jour transmis avec un "fatal" : `git add`
puis `git commit` échouaient silencieusement (ou presque -- le message
imprimé pour ce cas, "rien à commiter ou dépôt non configuré", était
trompeur, un troisième cas non anticipé) avec
`fatal: detected dubious ownership in repository at
'//stockagefont/Metiers/.../current'`.

### Ce qu'est réellement ce message

Pas un bug, ni propre à ce dossier : une mesure de sécurité de git
lui-même (depuis la CVE-2022-24765) qui refuse d'opérer sur un dépôt
dont il ne peut pas établir clairement le propriétaire -- déclenchée de
façon quasi systématique sur un chemin réseau (lecteur mappé M:\\... vers
un partage SMB), même quand rien n'est réellement compromis. Un
implication plus large a été vérifiée : le même mécanisme touche
n'importe quelle commande git dans ce dossier, y compris `git pull`
dans `launch.ps1` -- potentiellement un facteur supplémentaire (ou
alternatif) dans le blocage de version déjà résolu par ailleurs
(nettoyage du cache bytecode, V0.1.38).

### Correctif

git indique lui-même, dans son propre message d'erreur, la commande
exacte pour lever ce blocage (`git config --global --add safe.directory
...`) -- reprise telle quelle plutôt que reconstruite (le format exact
attendu, avec le préfixe `%(prefix)///` pour les chemins réseau, dépend
de la version de git et ne vaut pas la peine d'être deviné). `git add`
(jamais vérifié jusqu'ici -- corrigé au passage) et `git commit`
détectent maintenant ce blocage spécifiquement, appliquent le correctif
automatiquement, puis rejouent la commande qui avait échoué.

Reproduit avec un vrai dépôt git (propriétaire changé pour déclencher
réellement la vérification de git, pas seulement un message d'erreur
simulé) avant d'écrire le correctif, puis avec le correctif en place :
le blocage se produit bien sans lui, et le commit aboutit réellement
avec lui (vérifié dans l'historique git, pas seulement par l'absence
d'erreur).

Même correctif appliqué à `git pull` dans `launch.ps1` (PowerShell,
livré séparément du zip applicatif). Faute d'interpréteur PowerShell
disponible pour le tester directement, relu avec soin (équilibre des
accolades/parenthèses vérifié, syntaxe comparée à des patrons
PowerShell déjà utilisés ailleurs dans le même fichier) mais **pas
vérifié empiriquement** comme le reste -- à surveiller au prochain
lancement plutôt qu'à considérer acquis.

### Testé

270 tests automatisés (3 nouveaux, dont une reproduction complète avec
un vrai dépôt git). Ignoré proprement si l'environnement de test ne
permet pas de changer le propriétaire d'un fichier (nécessite les
privilèges root).

### Fichiers modifiés

`app/scripts/appliquer_version.py` (fonction
`_resoudre_dubious_ownership_si_applicable`, `git add` vérifié),
`tests/test_appliquer_version.py`, `README.md`. `launch.ps1` (livré
séparément, hors du zip applicatif comme toujours) mis à jour avec le
même correctif.

---

## 49. V0.1.42 (31/08/2026) : lier les consommations/mouvements/audit à un véritable utilisateur

### La demande

Trois volets, discutés avant modification comme proposé : rattacher le
champ "utilisateur" (jusqu'ici du texte libre) à un compte réel plutôt
qu'un nom sans lien ; une fiche utilisateur, même esprit que la fiche
source ; un contrôle total pour l'administrateur (fusionner, modifier),
avec le principe directeur "jamais d'action sans utilisateur rattaché" --
y compris pour quelqu'un qui a quitté le service depuis longtemps
(l'exemple donné : "Liatimi", partie depuis 15 ans, dont le nom
apparaît sur une fiche papier ancienne).

### Le modèle

`is_active` (déjà présent sur `UserDB`, jamais utilisé jusqu'ici)
distingue un compte réel (peut se connecter) d'un enregistrement
historique (jamais connectable, jamais proposé pour une nouvelle
action, mais garde sa fiche et son historique). Email et mot de passe
assouplis (nullable) pour ces enregistrements. `utilisateur_id`
(clé étrangère vers `users.id`) ajouté sur Consommations, Mouvements et
Audit, à côté du texte déjà présent (conservé tel quel).

Plutôt que de modifier les 15+ points d'appel existants, la
correspondance automatique est centralisée dans les repositories/
services (`AuditRepository.create()`, `ConsumptionService.use_source()`,
`MovementService.demarrer_emprunt()`) : toute nouvelle action réelle
relie désormais automatiquement le bon compte, sans rien à changer
ailleurs.

### Correspondance insensible à la casse

Signalé directement : GDO, BDL et CMO (Grégoire, Bernadette, Céline)
sont de vrais comptes connectés. Une correspondance stricte sur la
casse exacte aurait pu leur créer un doublon historique si le compte
réel est enregistré autrement que l'initiale utilisée sur une fiche
papier. Ajouté `get_by_username_insensible_casse`, utilisée
spécifiquement pour ce rapprochement (get_ou_creer_historique) --
n'affecte ni la connexion ni le reste de l'application, qui continuent
à fonctionner exactement comme avant.

### Migration et rattrapage des données déjà en base

Une vraie découverte en testant plutôt qu'en se fiant au code : sur une
base déjà existante, `Base.metadata.create_all()` ne modifie jamais une
table déjà là -- sans un script de migration dédié
(`migrate_add_utilisateur_id.py`, suivant le patron déjà établi par les
migrations précédentes, appelé automatiquement au démarrage), les
nouvelles colonnes n'apparaîtraient tout simplement pas sur une base
existante. Trouvé en creusant un échec inattendu qui s'est révélé être,
une fois de plus, le cache bytecode Python périmé (le même mécanisme
diagnostiqué pour Windows, cette fois dans le bac à sable de
développement) -- confirmant que ce correctif est généralement utile,
pas seulement pour un lecteur réseau.

Script séparé pour le rattrapage des données (`rattacher_utilisateurs_historiques.py`,
`python -m app.scripts.rattacher_utilisateurs_historiques`) : structure
du schéma et modification des données volontairement distinctes, pour
ne jamais les mélanger. Reproduit et vérifié avec le scénario Liatimi
exact : un nom sans correspondance crée un enregistrement historique ;
le même nom sur plusieurs tables ne crée jamais qu'un seul
enregistrement ; un second passage ne touche plus à ce qui est déjà
rattaché.

### Import historique : même logique désormais

`import_consommations_historiques.py` applique la même correspondance
(compte existant insensible à la casse, sinon enregistrement historique
créé) pour les nouveaux imports. Le rapport affiché en ligne de
commande liste chaque enregistrement historique créé, avec un rappel
d'aller le fusionner depuis sa fiche si le rapprochement automatique a
raté une variante orthographique.

### Fiche utilisateur, fusion, protection contre la suppression

Nouvelle page `/users/{id}/fiche` (réservée aux administrateurs, comme
la liste elle-même) : profil, statut (compte actif ou historique), et
tout ce qui lui est rattaché (consommations, mouvements, audit), chaque
ligne renvoyant vers la fiche de sa source.

Bouton "Fusionner avec..." depuis cette fiche : tout ce qui pointait
vers l'utilisateur source (utilisateur_id ET le texte, repris du nom de
la cible) est réattaché vers la cible choisie avant que la source ne
soit supprimée -- jamais d'action orpheline, même temporairement. La
fusion elle-même reste tracée dans l'audit.

La route de suppression, jusqu'ici sans aucune garde, refuse désormais
un utilisateur qui porte au moins une action tracée (consommation,
mouvement ou audit) -- "fusionner" devient le seul chemin pour faire
disparaître un tel enregistrement, sur le même principe que
l'impossibilité de supprimer une source. Un enregistrement historique
sans rattachement réel (créé par erreur, par exemple) reste, lui,
normalement supprimable.

### Testé

291 tests automatisés (29 nouveaux). Un bug trouvé dans mes propres
tests en les écrivant (le même piège de fixtures déjà documenté :
client et admin_client partagent le même client de test sous-jacent) --
corrigé en reprenant l'ordre déjà établi pour ce cas.

### Fichiers ajoutés

`app/scripts/migrate_add_utilisateur_id.py`,
`app/scripts/rattacher_utilisateurs_historiques.py`,
`app/templates/fiche_utilisateur.html`,
`tests/test_migrate_add_utilisateur_id.py`,
`tests/test_rattacher_utilisateurs_historiques.py`,
`tests/test_fiche_utilisateur_et_fusion.py`.

### Fichiers modifiés

`app/models/{user,consumption,movement,audit}.py`,
`app/repositories/{user,audit}.py`, `app/services/{consumption,movement}.py`,
`app/services/import_consommations_historiques.py`,
`app/scripts/import_consommations_historiques.py`, `app/main.py` (route
fiche utilisateur, migration appelée au démarrage), `app/routes/users.py`
(protection suppression, route fusion), `app/templates/users.html`
(lien vers la fiche, badge historique), `tests/test_import_consommations_historiques.py`.

---

## 50. V0.1.43 (01/09/2026) : exclusion des sources archivées du comptage MN

### La demande

Deux volets. Le second, présenté comme une "nouveauté facile" : ne pas
comptabiliser les déchets/remisées dans l'inventaire des matières
nucléaires, seulement les sources utilisables. Le premier : relier
l'application aux deux dépôts GitHub personnels de l'utilisateur (SI et
nuc) -- traité séparément, voir la réponse donnée directement dans la
conversation plutôt que dans ce rapport technique.

### Ce qui a été trouvé en vérifiant, avant de corriger

`export_inventaire_mn.py` excluait déjà les sources archivées
(`is_archived`, ajoutée le 13/07/2026) -- mais PAS les deux autres
exports concernés par le même comptage réglementaire, `export_annexe1.py`
et `export_tableau1a.py`, qui ne filtraient que sur `matiere_nucleaire`,
sans tenir compte de l'état d'utilisation. Exactement le genre
d'incohérence entre plusieurs endroits équivalents que l'utilisateur a
demandé d'éviter systématiquement (voir la passe boutons, V0.1.39).

Revue exhaustive de tous les usages de `matiere_nucleaire` dans
l'application (20+ occurrences) avant de corriger quoi que ce soit,
pour ne pas se limiter aux deux endroits déjà identifiés : les autres
usages relèvent soit du contrôle d'accès (masquer les sources MN aux
utilisateurs non habilités -- ne doit pas changer), soit de la
détection automatique à la création/import (ne doit pas changer non
plus). Seuls Annexe 1 et Tableau 1a comptent réellement vers un total
réglementaire, comme l'inventaire MN déjà corrigé.

### Correctif

Même filtre qu'`export_inventaire_mn.py` (`and not is_archived(s)`,
fonction déjà existante dans `models/source.py`) appliqué aux deux
exports manquants -- aucune nouvelle logique à écrire, juste étendre ce
qui existait déjà correctement à un seul endroit.

### Testé

293 tests automatisés (2 nouveaux), suivant exactement le même patron
que le test déjà existant pour l'inventaire MN.

### Fichiers modifiés

`app/services/export_annexe1.py`, `app/services/export_tableau1a.py`,
`tests/test_export_formats.py`, `tests/test_tableau1a.py`.

---

## 51. V0.1.44 (01/09/2026) : rafraîchissement du CDC, gestion admin renforcée

### Rafraîchissement d'ANALYSE_CDC_VS_APPLICATION.md

Demandé directement : revoir ce document, vieux de deux mois, en gardant
à l'esprit que plusieurs écarts qu'il liste sont des choix délibérés, pas
des oublis. Chaque section revérifiée directement dans le code de la
V0.1.43 plutôt que recopiée depuis la version précédente. Beaucoup
d'écarts listés en juillet sont en réalité résolus depuis (LaraWeb réel,
recherche/tri/pagination, fiche détaillée, utilisateur sur les
consommations, très largement dépassé) -- signalé clairement plutôt que
de laisser une liste partiellement fausse.

Deux écarts explicitement actés comme délibérés, sur demande directe :
- La relation N:N radioéléments/sources (le plus gros écart structurel
  du CDC) : devenue inutile en pratique, le cache LaraWeb joue déjà le
  rôle de référence partagée pour les données physiques.
- Le seuil d'activité configurable (rôle `user_limited` du CDC) : la
  réglementation impose a priori davantage de secret sur l'emplacement
  d'une source que sur son activité -- cette restriction ne répondrait
  pas au bon besoin. Trace conservée dans le document plutôt que
  silencieusement abandonnée.

Restent ouverts, constatés sans jugement : adresse IP et filtrage par
période sur l'audit, export CSV/JSON, restauration de sauvegarde (la
sauvegarde existe, pas la restauration), livrables formels séparés
(diagramme relationnel, plan de déploiement).

### Gestion admin renforcée des comptes

Demandé directement, sur le modèle de Yunohost ("gestion des users pas
mal", d'après l'expérience de l'utilisateur avec son propre serveur) :
un administrateur peut désormais définir directement le mot de passe
d'un utilisateur (sans connaître l'ancien -- différent de `/me/password`,
self-service, qui l'exige) et révoquer ou réactiver son accès.

La révocation réutilise `is_active`, déjà en place pour les
enregistrements historiques créés à l'import : conceptuellement,
quelqu'un dont l'accès est révoqué devient un enregistrement historique
-- sa fiche et son historique restent intacts, il ne peut simplement
plus se connecter. Aucune nouvelle route de suppression n'était
nécessaire : "fusionner" (V0.1.42) couvre déjà le cas d'un doublon à
faire disparaître.

**Un vrai problème de sécurité trouvé en construisant cette
fonctionnalité, pas en la cherchant** : `is_active` n'était en réalité
jamais vérifié à la connexion. La révocation, sans ce correctif,
n'aurait eu aucun effet réel -- et tenter de se connecter avec le nom
d'un enregistrement historique (sans mot de passe du tout) aurait fait
planter le serveur (`verify_password()` appelée avec un hash `None`)
plutôt que d'échouer proprement. Corrigé : `is_active` vérifié avant
toute tentative de mot de passe dans `authenticate_user()`.

Un bug d'ordre de routes trouvé et corrigé par la suite de tests, pas
par relecture : `/{user_id}/password` (nouvelle route), placée avant
`/me/password` (existante) dans le fichier, interceptait cette dernière
-- une requête vers `/me/password` était prise pour `/{user_id=me}/password`,
et rejetée par la vérification admin avant même que FastAPI tente de
convertir "me" en entier. Déplacé après toutes les routes `/me/...`.

Vérifié avec un vrai moteur DOM (pas seulement les tests automatisés) :
aucune erreur JavaScript au chargement des deux fiches (compte actif et
historique), bouton "Définir un mot de passe" fonctionnel.

### Testé

299 tests automatisés (18 nouveaux), incluant une reproduction complète
du problème de connexion sur un enregistrement historique (vérifié que
ça échoue proprement, pas que ça plante).

### Fichiers modifiés

`app/security/auth.py` (`is_active` vérifié avant le mot de passe),
`app/routes/users.py` (routes `/{id}/password` et `/{id}/acces`, remises
dans le bon ordre), `app/templates/fiche_utilisateur.html` (boutons et
pop-up, conditionnés au statut actif/historique),
`tests/test_fiche_utilisateur_et_fusion.py`,
`ANALYSE_CDC_VS_APPLICATION.md` (réécrit).

---

## 52. V0.1.45 (09/09/2026) : édition du profil, sur le modèle de Yunohost

### La demande

Trois captures d'écran de la gestion des comptes de Yunohost transmises
directement, avec la liste des champs voulus : rien pour la boîte mail
(quota, alias, transfert -- spécifique à Yunohost, sans objet ici), nom
du compte fixe, nom complet et email modifiables, droit (rôle), mot de
passe modifiable et accès révocable -- ces deux derniers déjà construits
en V0.1.44.

### Réalisé

Nouvelle route `PATCH /users/{id}` (nom complet, email, rôle), avec le
même principe de traçage que la modification d'une source : chaque champ
réellement changé (pas juste fourni) tracé séparément dans l'audit.

Le nom du compte n'est structurellement pas dans le modèle d'édition
(`UserUpdate`), pas seulement ignoré par convention : aucune valeur
envoyée pour ce champ ne peut avoir d'effet, vérifié par un test qui
tente explicitement de le modifier.

Deux protections, en plus de celles déjà en place (suppression,
révocation de soi-même) :
- **Email dupliqué refusé** : impossible de définir une adresse déjà
  utilisée par un autre compte.
- **Dernier administrateur protégé** : impossible de retirer les droits
  admin d'un compte si aucun autre administrateur actif ne resterait --
  l'application se retrouverait sans personne capable de gérer les
  comptes. Vérifié dans les deux sens (refusé s'il ne reste personne
  d'autre, autorisé s'il reste un second administrateur actif).

Le rôle n'a pas de sens sur un enregistrement historique (jamais
connectable, donc jamais capable d'exercer quoi que ce soit) : une
tentative de le modifier est ignorée silencieusement plutôt que
rejetée, pour que le même formulaire d'édition (côté interface, le
champ rôle n'apparaît d'ailleurs même pas sur une fiche historique)
puisse être soumis sans traitement particulier.

### Testé

307 tests automatisés (8 nouveaux). Vérifié aussi avec un vrai serveur
et un moteur DOM (pas seulement les tests automatisés) : préremplissage
correct du formulaire, absence du champ rôle sur une fiche historique,
soumission réelle vérifiée directement en base.

### Fichiers modifiés

`app/models/user.py` (`UserUpdate`), `app/repositories/user.py`
(méthode `update`), `app/routes/users.py` (route `PATCH /{id}`),
`app/templates/fiche_utilisateur.html` (bouton et pop-up "Modifier"),
`tests/test_fiche_utilisateur_et_fusion.py`.
