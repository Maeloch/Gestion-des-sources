# Gestion des Sources Radioactives

**Version 0.1.41** — affichée en bas de la barre latérale de l'application. En cas
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

Toujours depuis le dossier du projet, avec l'environnement virtuel activé,
deux façons de lancer l'application, **qui ne se comportent pas tout à
fait pareil** (question posée directement le 21/07/2026) :

```bash
uvicorn app.main:app --reload
```

Accessible uniquement en local (**http://127.0.0.1:8000**) par défaut.
Pour la rendre accessible depuis le réseau (autre appareil sur le même
réseau, par exemple), ajoute explicitement `--host 0.0.0.0` (et
éventuellement `--port` pour changer le port) :

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ou bien :

```bash
python app/main.py
```

Ce deuxième chemin lance l'appli avec les réglages `APP_HOST`/`APP_PORT`
du fichier `.env` (par défaut : `0.0.0.0` et `8000`, donc déjà accessible
depuis le réseau sans rien ajouter) — modifie `.env` si tu veux changer
ça. **Ces deux façons de lancer l'appli sont indépendantes l'une de
l'autre** : `python app/main.py` exécute un bloc de code (`if __name__ ==
"__main__":`) qui lit `.env` et lance uvicorn lui-même avec ces valeurs ;
la commande `uvicorn app.main:app` directe, elle, importe simplement le
code de l'appli sans jamais exécuter ce bloc — ses propres options
`--host`/`--port` (ou leurs valeurs par défaut) sont les seules qui
comptent alors, `.env` n'y change rien.

`--reload` fait redémarrer le serveur automatiquement à chaque
modification du code Python — pratique pendant le développement, et pour
les mises à jour (voir section 5bis). Pour arrêter le serveur : `Ctrl+C`
dans le terminal.

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

## 4bis. Importer des consommations historiques (28/07/2026)

Pour les consommations jusqu'ici tenues sur des fiches papier : pas de
bouton d'import dédié dans l'interface (volontairement), mais un script
en ligne de commande, pensé pour un flux en trois temps -- transcription
(par exemple par Claude, à partir de scans), relecture/correction du
tableur par toi (**c'est là qu'a lieu la vérification**), puis import
"idiot" volontairement peu sophistiqué, le contrôle ayant déjà eu lieu à
l'étape précédente.

Générer un modèle vide pour cadrer la transcription :
```bash
python -m app.scripts.import_consommations_historiques --modele modele.xlsx
```

Colonnes attendues : ID Source, Date, Masse avant (g), Masse après (g),
Quantité utilisée, Commentaire, Utilisateur. Au moins l'un de (Masse
avant, Quantité utilisée) doit être renseigné par ligne. **L'ordre des
lignes n'a aucune importance** (ni entre elles, ni vis-à-vis des
consommations déjà en base) : le calcul de quantité restante trie
toujours par date au moment où il est fait, jamais par ordre
d'insertion -- vérifié directement plutôt que supposé.

Importer le fichier relu :
```bash
python -m app.scripts.import_consommations_historiques mon_fichier.xlsx
```

Un rapport s'affiche : nombre de consommations créées, et le détail de
chaque ligne ignorée avec sa raison (source introuvable, date illisible,
aucune quantité renseignée).

## 5. Sauvegarder ta base de données

`data/database.sqlite` contient toutes tes données. C'est un fichier unique :
pour la sauvegarder, il suffit de le copier ailleurs (clé USB, cloud...)
régulièrement, surtout avant tout essai un peu risqué.

## 5bis. Mises à jour automatiques (21/07/2026, précisé le 22/07/2026)

Deux scénarios bien différents, à ne pas confondre :

### A. Ton organisation actuelle (un nouveau dossier par version reçue)

Si tu continues comme aujourd'hui — un dossier `V0.1.XX` différent à
chaque version que tu télécharges et décompresses — utilise
**`appliquer_version.py`**, pas `mettre_a_jour.py` (voir plus bas). Ce
script s'exécute DEPUIS le nouveau dossier fraîchement décompressé, et
prend en argument le chemin d'un dossier **stable** (celui d'où tourne
réellement ton serveur, quel que soit son nom) :

```bash
cd ~/Python/Venv/BDD_sources/V0.1.25   # le nouveau dossier, tout juste décompressé
python -m app.scripts.appliquer_version ~/Python/Venv/BDD_sources/V0.1.21   # ou quel que soit ton dossier stable
```

Ce script (1) sauvegarde `data/database.sqlite` **du dossier stable**
(horodatée), (2) copie tout le contenu du nouveau dossier vers le stable
— SAUF `data/`, `.env`, `.git/` et les dossiers techniques (venv,
`__pycache__`...), qui restent ceux du dossier stable, jamais écrasés —
(3) si le dossier stable est suivi par git, enregistre un commit puis le
pousse automatiquement vers le dépôt distant s'il y en a un de
configuré (sinon saute ces deux étapes sans erreur, git n'est pas
obligatoire), (4) "touche" `app/main.py` du dossier stable pour
déclencher le rechargement d'un serveur déjà lancé avec `--reload`
depuis ce dossier.

Le push automatique (ajouté le 23/07/2026, question posée directement)
échoue proprement s'il n'y a pas de réseau, ou si le dépôt distant a
avancé ailleurs entre-temps (ex: mise à jour faite depuis un autre
poste) : le commit **local**, lui, a déjà réussi dans tous les cas — un
échec du push ne fait jamais échouer la mise à jour elle-même, juste sa
synchronisation vers GitHub. Le message d'erreur affiché indique quoi
faire (généralement : `git pull` puis relancer `git push` à la main).

**Limite à connaître** : une copie n'efface jamais un fichier qui
n'existe plus dans la nouvelle version (elle ajoute/remplace, elle ne
retire rien). Sans conséquence pratique la plupart du temps (un vieux
fichier Python inutilisé reste juste inerte), mais à savoir.

Concrètement, avec ton organisation (`~/Python/Venv/BDD_sources/`), le
plus simple est de désigner UN dossier comme "le vrai", stable, celui
d'où le serveur tourne en continu (peu importe qu'il s'appelle encore
`V0.1.21` ou autre chose) — plutôt que de changer de dossier à chaque
version. `appliquer_version.py` copie alors CHAQUE nouvelle version
reçue par-dessus ce même dossier stable, sans jamais avoir à relancer le
serveur depuis un nouvel emplacement.

### B. Si le code est géré par git ET que le serveur tourne sur une AUTRE machine

Ce scénario est différent : le dossier stable est un clone d'un dépôt
git (GitHub par exemple), et une mise à jour arrive par `git push` fait
ailleurs (sur un autre poste, ou par un dépôt que tu maintiens toi-même),
suivi d'un `git pull` sur la machine qui fait tourner le serveur. C'est
ce que fait **`mettre_a_jour.py`** :

```bash
python -m app.scripts.mettre_a_jour
```

Ce script (1) sauvegarde `data/database.sqlite`, (2) `git pull`, (3)
touche `app/main.py`. Il suppose que le dossier où il tourne est déjà un
dépôt git configuré avec un `remote` accessible (`git pull` échoue
proprement sinon, sans rien changer). Utile si tu passes un jour par un
dépôt GitHub partagé entre plusieurs machines ; **pas ce qu'il te faut
tant que tu reçois une archive à chaque fois sur une seule machine** —
dans ce cas-là, c'est le scénario A ci-dessus qui s'applique.

Dans les deux cas, quelques précisions utiles, vérifiées concrètement
(pas seulement supposées) :

- **Les templates (pages HTML) et les fichiers statiques (CSS/JS) se
  mettent à jour sans même redémarrer le serveur** : ils sont relus
  depuis le disque à chaque requête. Une mise à jour qui ne change QUE
  ces fichiers-là (le cas le plus fréquent) est donc déjà prise en
  compte à la requête suivante, avant même qu'un rechargement de
  processus n'entre en jeu.
- `--reload` (redémarrage du *processus*) n'est nécessaire que pour un
  changement de code Python (routes, services, modèles) — ou pour une
  nouvelle migration de schéma (voir section 4), qui s'exécute
  automatiquement à chaque démarrage du processus, redémarrage inclus.
- Si le serveur ne tourne pas avec `--reload`, ces scripts préparent la
  mise à jour (code + sauvegarde) mais ne redémarrent rien tout seuls :
  relance-le manuellement après coup.

À noter : `--reload` est pensé par ses auteurs pour le développement, pas
pour un service critique nécessitant une disponibilité 24h/24 sans
interruption — dans ton cas (usage interne, pas un service public à
haute disponibilité), c'est un compromis raisonnable pour la simplicité
que ça apporte. Si un jour la robustesse prime sur la simplicité (panne
réseau en plein transfert, notamment), une piste plus solide serait de
préparer la nouvelle version dans un dossier séparé, vérifier qu'elle
démarre correctement, puis ne basculer qu'ensuite — un chantier
distinct, à ouvrir si le besoin s'en fait sentir.

### C. Pourquoi pas de `git pull` dans le dossier stable (scénario A) ?

Question posée directement le 23/07/2026 : dans le scénario A (ton
organisation actuelle), le dossier stable n'a jamais besoin d'un
`git pull`, et ce n'est pas un oubli. La source de la mise à jour, dans
ce scénario, c'est le fichier que tu télécharges et décompresses — le
script copie ses fichiers DIRECTEMENT dans le dossier stable, puis
enregistre ça comme un commit. Rien ne vient du dépôt distant à ce
moment-là : `git pull` n'aurait donc rien à récupérer. Le `git push`
(désormais automatique) sert seulement à ENVOYER ce commit vers GitHub
pour y garder une trace/sauvegarde — pas à en RECEVOIR quoi que ce soit.

`git pull` (et le script `mettre_a_jour.py`, scénario B) ne redevient
utile que si le dossier stable doit un jour récupérer un changement fait
AILLEURS que par ce chemin habituel — par exemple si tu modifies un
fichier directement sur GitHub, ou si tu fais tourner l'appli sur une
seconde machine qui doit se synchroniser avec les commits poussés depuis
la première.

### D. En cas de souci : revenir à une version antérieure

Testé de bout en bout avant d'être écrit ici (pas seulement en théorie).
Le code et la base de données se traitent séparément :

**Le code**, via git — l'historique n'est jamais perdu, chaque mise à
jour est son propre commit :

```bash
cd ~/Python/Venv/BDD_sources/current   # ton dossier stable
git log --oneline                       # repère le commit de la version qui marchait
git checkout <hash-du-commit> -- app/   # restaure UNIQUEMENT le code de cette version-là
git commit -m "Retour arrière vers V0.1.27"
git push
```

Ceci ne réécrit rien : `git log` montrera ensuite les trois commits
(l'ancienne version, la nouvelle qui posait problème, et ce retour en
arrière) — un historique honnête plutôt qu'un maquillage, et sans les
risques d'un `git reset --hard` (qui, lui, réécrit l'historique et peut
recréer le genre de conflit rencontré récemment s'il est ensuite poussé).

**La base de données**, depuis la sauvegarde automatique : chaque
exécution d'`appliquer_version.py` en crée une, horodatée, dans
`data/backups/`, AVANT toute modification — donc une sauvegarde du
"juste avant que ça ne casse" existe déjà, sans action supplémentaire de
ta part.

```bash
# server arrêté ou --reload actif (voir plus haut, se recharge tout seul)
cp data/backups/database-avant-maj-<horodatage-le-plus-recent>.sqlite data/database.sqlite
```

Si la version problématique avait ajouté une migration de schéma (une
nouvelle colonne, par exemple), revenir en arrière côté code n'y changera
rien tout seul — c'est justement pour ça que restaurer la sauvegarde de
base ci-dessus, qui correspond exactement à l'état d'avant cette
migration, est la partie qui compte le plus dans ce scénario-là.

### E. Sur Windows : le rechargement automatique peut mal réagir à une grosse mise à jour

Rencontré concrètement le 24/07/2026 (journal de serveur réel à
l'appui) : `appliquer_version.py` modifie une centaine de fichiers d'un
coup. Sur Windows, avec `--reload` actif, WatchFiles peut détecter ces
changements en plusieurs vagues rapprochées plutôt qu'en une seule fois
— et chaque nouvelle vague interrompt la tentative de rechargement
précédente avant qu'elle n'ait fini de redémarrer le serveur (visible
dans le journal : plusieurs `WatchFiles detected changes...` suivis
d'un `KeyboardInterrupt`, en cascade). Plus probable encore si le
dossier est sur un lecteur réseau (chemins UNC du type
`\\serveur\partage\...`), la détection de changements y étant moins
fiable que sur un disque local. Le script affiche maintenant un
avertissement explicite à ce sujet sur Windows.

En général, une des tentatives finit par aboutir sans intervention. Mais
si la page web n'affiche toujours pas la nouvelle version en bas à
droite après une mise à jour : arrête complètement le serveur (`Ctrl+C`
dans son terminal — au besoin plusieurs fois si la cascade l'a laissé
dans un état confus) et relance-le proprement, plutôt que d'insister sur
le rechargement automatique pour cette fois-là. Une piste plus radicale
si le problème se répète souvent : arrêter le serveur AVANT de lancer
`appliquer_version.py`, puis le relancer une fois le script terminé —
qui évite complètement le risque, au prix d'une brève coupure du
service pendant la mise à jour.

**Vérification automatique ajoutée (31/07/2026)** : l'avertissement
seul s'est montré insuffisant en pratique (une version est restée
active plusieurs mises à jour après son remplacement sur disque, sans
que ça se voie autrement qu'en relisant soi-même le numéro affiché).
`appliquer_version.py` interroge maintenant lui-même le serveur déjà
lancé (`http://127.0.0.1:8000/version`, nouvel endpoint sans
authentification) une fois la mise à jour terminée, et affiche un
avertissement impossible à manquer si la version répondue ne correspond
pas à celle qui vient d'être déployée. Ne bloque jamais si le serveur
n'est pas joignable (pas encore lancé, port différent...) : c'est une
vérification de confort, pas une étape obligatoire.

### F. La vraie cause, trouvée le 31/07/2026 : le cache bytecode Python, pas le rechargement

La vérification ci-dessus (section E) a eu le mérite de confirmer que
le problème n'était PAS le rechargement automatique : le même symptôme
persistait avec `--reload` désactivé et un arrêt/relance complets du
serveur avant chaque mise à jour. La vraie cause, reproduite
empiriquement (pas seulement supposée) : quand un fichier `.py` est
remplacé et se retrouve, par coïncidence, avec exactement la même (date
de modification, taille en octets) que l'ancien qu'il remplace — plus
probable sur un lecteur réseau, où la granularité d'horodatage est plus
grossière que sur un disque local — Python considère à tort son cache
compilé (`__pycache__`) comme toujours valide, et continue à exécuter
silencieusement le bytecode de l'ANCIENNE version, même après un
redémarrage complet et avec un fichier source parfaitement à jour sur
disque. Explique aussi pourquoi les fichiers non-Python (gabarits HTML,
CSS) se mettaient à jour normalement pendant que le numéro de version
(lu depuis un module Python) restait bloqué, et pourquoi ce problème
n'est jamais apparu sur Hyperion (disque local, pas de lecteur réseau).

`appliquer_version.py` supprime maintenant systématiquement tous les
dossiers `__pycache__` de l'installation cible à chaque mise à jour
(jamais copiés depuis la nouvelle version, donc jamais remplacés par la
copie elle-même) : Python les régénère automatiquement depuis le code
source actuel dès le prochain import, sans dépendre d'une comparaison
d'horodatage qui a démontré ne pas être fiable dans ce contexte précis.

### G. "fatal: detected dubious ownership" (31/08/2026)

Message affiché par git lui-même, pas une erreur du script : une mesure
de sécurité de git (depuis la CVE-2022-24765) qui refuse d'opérer sur
un dépôt dont il ne peut pas établir clairement le propriétaire —
quasi systématique sur un chemin réseau (lecteur mappé type `M:\...`
vers un partage SMB), même quand rien n'est réellement compromis.
Touche n'importe quelle commande git dans ce dossier, pas seulement
celle qui a échoué en premier — y compris `git pull` dans `launch.ps1`,
un facteur à ne pas exclure dans d'éventuels blocages de mise à jour
passés.

`appliquer_version.py` (`git add`, `git commit`) et `launch.ps1`
(`git pull`) détectent maintenant ce blocage spécifiquement et le lèvent
automatiquement, en reprenant la commande que git suggère lui-même dans
son propre message d'erreur (`git config --global --add safe.directory
...`) plutôt qu'en reconstruisant le chemin à deviner. Rien à faire de
ton côté la prochaine fois que ça se présente : le script s'en charge et
journalise ce qu'il a fait.

## 5ter. Dates affichées en français (30/07/2026)

Toutes les dates affichées en lecture seule (tableaux, fiche source,
audit...) sont au format JJ/MM/AAAA plutôt que AAAA-MM-JJ — par
préférence assumée. Les champs de saisie (`<input type="date">`) et les
attributs internes utilisés pour le tri chronologique des tableaux
restent en format ISO : le premier parce que le navigateur l'exige, le
second parce qu'un tri correct par date en dépend (AAAA-MM-JJ se trie
correctement comme texte, JJ/MM/AAAA non).

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
éclatée, renommer un lieu vers un nom déjà utilisé par un autre lieu
propose directement de les fusionner (toutes les sources et tous les
mouvements du premier sont réaffectés au second, avec confirmation,
avant que le premier ne soit supprimé). Un bouton "Fusionner" dédié a
existé un temps en plus de ce renommage, mais s'est révélé sans effet ;
retiré le 14/07/2026 plutôt que corrigé, le renommage restant l'unique
chemin.

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

**Source déjà utilisée depuis longtemps, jamais pesée dans l'appli ?**
(demandé le 14/07/2026) La même pesée de contrôle sert à réconcilier la
base avec la réalité, sans reconstituer l'historique des prélèvements
passés : indique directement ta meilleure estimation de ce qu'il reste
en "Masse pesée" (masse avant), laisse "Masse après" vide. Cette
déclaration devient directement la nouvelle référence — y compris si
elle est *inférieure* à la quantité initiale du certificat (le calcul de
masse de récipient, pertinent pour une réception avec pesée du contenant
complet, ne s'applique pas ici : rien à déduire d'une simple déclaration
directe de quantité de liquide). Les prélèvements suivants se comportent
ensuite normalement à partir de cette nouvelle référence.

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

## 7ter. Fiche détaillée par source (28/07/2026)

Cliquer sur l'identifiant d'une source — sur la page Sources elle-même,
ou partout où il apparaît ailleurs (Radionucléides, Mouvements,
Consommations, Audit) — amène sur une fiche regroupant tout ce qui la
concerne sur une seule page : ses informations générales, ses
radionucléides, son historique de mouvements et de consommations, et
(si présent) son historique d'audit. Les mêmes calculs que sur la liste
des sources s'y appliquent (quantité restante, activité actuelle,
éligibilité à l'emprunt).

Le bouton "Modifier" y renvoie vers la liste des sources, déjà filtrée
sur cette source précise, et ouvre directement le formulaire de
modification (31/07/2026 : fallait auparavant recliquer "Modifier" une
seconde fois une fois sur la liste) : le formulaire, assez complexe,
n'est pas dupliqué sur cette nouvelle page, pour n'avoir qu'une seule
version à maintenir.

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

**Aucune source ne peut être supprimée définitivement** (retiré le
22/07/2026) : dans un contexte de traçabilité réglementaire, une source
doit toujours rester consultable, même détruite ou obsolète — passer son
état d'utilisation à l'un des quatre ci-dessus (page Archives, bouton
"Corriger") est l'unique façon de la sortir de la liste active.

## 8bis. Tri, pagination et activité utilisée

Chaque tableau (Sources, Radionucléides, Consommations, Mouvements,
Lieux, Audit) se trie en cliquant sur un en-tête de colonne (flèche
↑/↓, un second clic inverse le sens) et se pagine — un menu déroulant
choisit le nombre de lignes par page (10/20/50/100/Tout), avec une
navigation page précédente/suivante et le total de lignes affiché.
Le tri et la pagination fonctionnent ensemble et, sur Sources et Audit,
avec les filtres déjà en place (onglets, cases à cocher) : la pagination
s'applique toujours au résultat déjà filtré, jamais avant.

Sur **Sources**, la recherche libre (généralisée le 28/07/2026, elle
était jusque-là plus restrictive qu'ailleurs) compare le texte tapé à
l'identifiant, au(x) radionucléide(s), au lieu, etc. — comme sur les
autres pages (voir plus bas) plutôt que la seule colonne identifiant.
Le menu déroulant dédié au filtre par radionucléide, devenu redondant,
a été retiré : taper un nom de radionucléide dans la recherche libre
suffit désormais. Se combine avec les filtres déjà en place (onglet,
statut).

Une recherche libre du même esprit existe aussi sur **Radionucléides,
Mouvements, Lieux, Consommations et Audit** (14/07/2026) : elle compare
le texte tapé à toutes les colonnes visibles de chaque ligne (nom de
radionucléide, source, lieu, commentaire, utilisateur...), sans liste de
colonnes à choisir. Sur Audit, elle se combine avec les filtres déjà en
place (cases à cocher, dates).

**Liens croisés entre pages** (28/07/2026) : partout où un identifiant de
source, un nom de radionucléide ou un lieu apparaît sur une page qui
n'est pas la sienne (colonne "Source" sur Radionucléides/Mouvements/
Consommations/Audit, colonnes radionucléides/lieu sur Sources elle-même),
c'est maintenant un lien qui amène directement sur la bonne page, avec la
recherche déjà appliquée sur ce texte précis — plus besoin de retaper.

Pour consommer une source gaz/liquide, un bouton **"Consommer"**
directement sur sa ligne (page Sources) ouvre la pop-up de consommation
déjà pré-remplie sur cette source — plus besoin de la rechercher dans la
liste de la page Consommations. Sur cette dernière page, le choix de la
source (si on y arrive directement, sans passer par ce bouton) se fait
maintenant par un champ texte avec suggestions au clavier plutôt qu'un
menu déroulant classique, plus pratique dès qu'il y a beaucoup de
sources consommables.

De la même façon (22/07/2026), un bouton **"Emprunter"** apparaît sur
chaque ligne de source éligible à un nouvel emprunt (pas déjà empruntée,
pas archivée, lieu habituel défini) : ouvre la pop-up de démarrage
d'emprunt (page Mouvements) déjà pré-remplie. Le choix de la source dans
ce formulaire est lui aussi un champ texte avec suggestions, plus le
menu déroulant classique d'auparavant.

Sur la page **Consommations**, une colonne **Activité utilisée** affiche
l'activité (Bq) correspondant à la quantité consommée, calculée à la
date de CETTE consommation précise (décroissance radioactive appliquée
depuis la date de référence du radionucléide) — purement pour
l'affichage, aucune valeur n'est stockée en base.

## 8ter. Spectre-type des consommations (30/07/2026)

Depuis **Consommations**, "Calculer le spectre-type des déchets sur une
plage de temps →" : estime la composition isotopique des déchets sur une
période choisie, à partir des sources consommées (supposée
proportionnelle à leur activité). Trois dates : le début et la fin de la
plage à examiner, et la date à laquelle calculer le spectre (aujourd'hui
par défaut, mais n'importe quelle date égale ou postérieure à la fin de
la plage — la décroissance n'a de sens que vers l'avant dans le temps,
une date antérieure est refusée avec un message clair plutôt que de
produire un résultat sans signification physique).

Pour une source à plusieurs radionucléides, chacun est compté
individuellement (pas seulement le premier, contrairement à la colonne
"Activité utilisée" ci-dessus, pensée pour un affichage simple ligne par
ligne) : la même fraction de la quantité physique consommée s'applique à
chacun, une hypothèse d'homogénéité assumée explicitement (vraie pour un
mélange de calibration homogène, à garder en tête sinon). Toute
consommation ignorée (source sans radionucléide exploitable) ou tout
radionucléide sans période radioactive connue (donc sans décroissance
calculable) est signalé, jamais silencieux.

Bouton **"Exporter (Excel)"** (31/07/2026) : télécharge exactement le
spectre affiché à l'écran (mêmes dates), sur deux feuilles -- le spectre
lui-même, et le détail des consommations qui le composent.

## 8quater. Modifier et supprimer (31/07/2026)

Les pop-ups de modification (Consommations, Radionucléides, Lieux)
suivent maintenant le même patron : **Annuler**, **Enregistrer**, et
pour Consommations/Radionucléides/Lieux, **Supprimer** (avec
confirmation), tous en bas de la pop-up plutôt qu'éparpillés. Sources
garde volontairement Annuler/Enregistrer sans Supprimer — une source
reste un objet physique qui doit toujours pouvoir être tracé, même
détruite (archivage, pas suppression, voir plus haut).

Sur **Consommations** spécifiquement : la date d'une consommation est
désormais modifiable (elle ne l'était pas jusqu'ici, seule la valeur
l'était), et une consommation peut être supprimée -- utile en particulier
pour corriger un import historique dupliqué par erreur. Contrairement à
une source, une consommation en doublon ne correspond à aucun événement
réel : la supprimer ne perd aucune trace d'un fait qui ne s'est jamais
produit. La suppression reste tracée dans l'audit.

L'import de consommations historiques (voir section 4bis) détecte
maintenant les doublons potentiels (même source, même date qu'une
consommation déjà connue, en base ou dans le même fichier) -- signalé
clairement dans le rapport, sans jamais bloquer l'import.

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
  même façon). Par défaut, une source déjà présente (même identifiant) est
  ignorée, jamais écrasée — l'import peut être relancé sans risque de
  doublon ou de perte de corrections déjà faites à la main. Cocher
  **"Mettre à jour les sources déjà présentes"** change ce comportement :
  utile pour corriger une erreur trouvée après coup (exporter les
  sources, corriger le fichier obtenu à la main, réimporter avec cette
  case cochée) — sans elle, une telle correction serait silencieusement
  ignorée, ce qui n'était pas prévu à l'origine (demandé le 14/07/2026).

  Pour une source ainsi mise à jour (et seulement celle-là), ses
  radionucléides sont désormais réconciliés avec le fichier, pas
  seulement ses propres champs (14/07/2026, cas réel : une entrée
  erronée type "MELANGE GAMMA", qui n'est pas un vrai radionucléide,
  supprimée dans le fichier puis réimportée ne se répercutait pas) :
  un radionucléide présent dans le fichier mais absent en base est
  ajouté, un radionucléide dont les valeurs diffèrent est mis à jour, et
  un radionucléide absent du fichier mais présent en base est **retiré**.
  Pour toute autre source (nouvellement créée dans le même import, ou
  non concernée par cette option), le comportement reste inchangé :
  ajout seul, jamais de suppression ni de modification. Le rapport
  d'import détaille les radionucléides créés, mis à jour et retirés.

  Si une colonne comme "Période (années)" ou "Lien LaraWeb" contient une
  formule (macro VBA personnalisée ou autre) qu'Excel n'a jamais
  recalculée avant l'enregistrement du fichier (macros désactivées,
  calcul manuel, réseau indisponible au moment du calcul), la cellule ne
  contient alors aucune valeur exploitable, parfois un code d'erreur brut
  (#NAME?, #REF!...) — l'import le détecte et le signale clairement dans
  le rapport plutôt que de l'ignorer silencieusement ou de l'importer
  tel quel ; recalcule le fichier (Ctrl+Alt+F9 dans Excel, macros
  activées) puis réimporte, ou renseigne la valeur à la main.

  Une ligne sans identifiant
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
  L'emplacement affiché (colonnes "Emplacement habituel"/"actuel") reflète
  toujours l'état actuel des lieux ; l'ancienne colonne "Lieu de stockage"
  (un texte figé au moment de l'import, jamais mis à jour depuis) a été
  retirée le 14/07/2026, car redondante et parfois incohérente avec les
  emplacements corrigés depuis.
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
  confirmer la présence physique. Un bloc de signatures unique en bas du
  document (simplifié le 14/07/2026 : deux signatures par ligne rendait
  le tableau inutilement large, une seule paire pour tout le document
  suffit — une personne vérifie l'ensemble, pas une source à la fois). À
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
