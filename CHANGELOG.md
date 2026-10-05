# Journal des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et la
numérotation la règle décrite dans le [README](README.md#versions).

## [Non publié]

## [0.3.2]

La carte d'un afficheur ne montrait **rien** : batterie, wifi, température,
humidité, luminosité et uptime, tous à `—`, alors que l'horloge répondait
parfaitement. Vu par Florian sur son déploiement.

### Corrigé
- **La carte lisait les noms d'AWTRIX 3.** `bat`, `temp`, `hum`,
  `wifi_signal`, `lux`, `bri`, `uptime` — le backend envoie désormais
  `battery_percent`, `temperature`, `humidity`, `wifi_rssi`, `light_level`,
  `brightness`, `uptime_seconds`. Le code compilait, les tests passaient, et
  chaque tuile affichait un tiret.
- **« AWTRIX 3 v1.1.2 »** sous le nom de l'afficheur. C'est NG.

### Changé — aligné sur l'interface de l'horloge
Les six tuiles sont désormais celles que montre l'afficheur lui-même, dans le
même ordre, avec la même seconde ligne sous chacune : batterie `93 %` / `4.14
V`, wifi `-59 dBm` / `bon`, luminosité `3.2 %` / `133 brut`, température,
humidité, images/s. Et la ligne de pied : uptime, RAM libre, app en cours — et
**« matrice éteinte »** quand le panneau est coupé, que le framebuffer seul ne
dirait pas.

Comparer les deux pages ne demande plus de traduire quoi que ce soit.

### Ajouté
- `ldr_raw` et `battery_pin_millivolts` au modèle, que l'interface de l'horloge
  montre et que le nôtre ignorait.
- **`tests/test_frontend_contract.py`** — le seul joint qu'aucun compilateur ne
  surveille. L'interface TypeScript *décrit* le JSON du backend sans en
  dériver : TypeScript la vérifie contre elle-même et se déclare satisfait, les
  tests Python vérifient Python contre Python, et entre les deux, rien. Le test
  lit les noms de champs dans le TypeScript et les compare au modèle Pydantic.
  Vérifié en réintroduisant la panne : il la nomme.

## [0.3.1]

Deux restes de l'ancien nom, vus sur le déploiement de Florian avant de l'être
ici. Le portage les avait laissés parce qu'ils sont du **texte**, pas des
identifiants : rien ne casse quand ils sont faux.

### Corrigé
- **Le bandeau du tableau de bord** affichait `AWTRIXHUB READY`. Il fait 58
  colonnes sur un panneau de 32, donc il défilait, et une capture d'écran le
  prenait en plein milieu : `AWTRIXHI`, un bandeau qui a l'air cassé.
  Remplacé par `AWTRIXNG`, **31 colonnes sur 32** — il tient, donc il se lit à
  tout instant.
- **Le cookie de session** s'appelait encore `awtrixhub_session`. Ce n'est pas
  cosmétique : les deux applications peuvent tourner derrière le même Caddy, et
  un nom partagé ferait que se connecter à l'une déconnecte de l'autre — avec
  un symptôme qui ne désigne rien.

### Ajouté
- `tests/test_no_leftovers.py`, qui balaie le code du backend et du frontend à
  la recherche de l'ancien nom. Les trois casses sont vérifiées, et le
  répertoire des migrations est exclu : sa documentation parle d'awtrixhub
  volontairement.

## [0.3.0]

**L'application entière, portée sur AWTRIX NG.** Backend, planificateur,
connecteurs, API REST et interface React viennent d'awtrixhub ; tout ce qui
parle au firmware a été réécrit, et **chaque option a été essayée sur une
horloge réelle** plutôt que traduite sur le papier.

### Ajouté
- Le modèle de données, les migrations, le planificateur, les six connecteurs
  (météo, qualité de l'air, UV, pollens, carburants, vacances scolaires,
  lune), l'API REST, l'interface React et ses tests.
- **`overlay`** dans les options d'affichage — pluie, neige, bruine, orage,
  tonnerre, givre, dessinés par le firmware par-dessus le texte. Propre à NG.
- **L'interrupteur de matrice** : `GET /api/v1/display` et
  `PATCH /api/v1/display {"power": …}`, exposés par `/api/devices/{id}/power`.
  AWTRIX 3 n'avait que `/api/sleep`, une veille minutée.
- `GET /api/devices/{id}/apps` remplace `/loop` et donne l'**origine** de
  chaque app.
- **964 tests** : 871 backend, 93 frontend, plus 22 qui tournent contre une
  horloge réelle — dont un par type de widget.

### Retiré, parce que le matériel dit que ça ne fait rien
- **`center`** — NG n'a aucune clé de centrage. Mesuré : il centre **lui-même**
  tout texte qui tient. « A » tombe colonnes 14-16, « ABC » colonnes 10-20,
  exactement où un centrage les mettrait. L'aperçu suit désormais le firmware
  au lieu d'offrir un interrupteur sans effet.
- **`rainbow`** — `palette` colore les *effets*, pas le texte. Poussé
  `{"text":"ARC","palette":"Rainbow"}`, relu l'écran : une seule couleur.
- **`lifetimeMode`** — n'existe plus. Le marquage « périmé » d'AWTRIX 3
  disparaît : une app qui cesse d'être rafraîchie s'efface.
- **Le panneau des apps natives** — NG n'offre aucun moyen de les désactiver.
  `DELETE /api/v1/apps/Battery` répond `{"ok":true}` et ne fait rien, et aucun
  des 42 réglages ne les gouverne. Un panneau qui ne peut rien est pire
  qu'absent.
- Les treize migrations héritées, remplacées par une seule. L'une d'elles
  ajoutait précisément `center` et `rainbow`.

### Changé
- `no_scroll` devient **`scroll_mode`** (`wrap`, `bounce`, `static`, `loop`),
  `push_icon` devient **`icon_mode`** (`fixed`, `pushOnce`, `push`), et
  `text_case` passe d'un entier à `inherit` / `upper` / `asTyped`. Les trois
  listes viennent du 422 de l'appareil, pas de la documentation.
- Les formats de date et d'heure, qui étaient des chaînes `strftime`, sont
  devenus des choix structurés — `dateOrder`, `dateSeparator`, `dateYearMode`,
  `timeSeparatorMode`.
- Le mode chambre écrit `brightness`/`autoBrightness`/`soundEnabled`. **ADR-022
  rejugée et maintenue** : sondé `/schedules`, `/automations`, `/timers`,
  `/alarms`, `/cron`, `/dnd` — tous 404, le firmware n'a aucune planification.
- `DisplayOptions` refuse désormais une clé inconnue. Un `center=True` oublié
  dans le connecteur scolaire avait survécu au portage parce que Pydantic les
  ignore en silence — le défaut même qu'on reprochait à AWTRIX 3.
- Le gabarit par défaut du widget scolaire passe de `{{ summary }}` à
  `Sem. {{ week }}` : « Semaine A » fait 35 colonnes là où l'icône en laisse
  23, donc il défilait. Un coup d'œil à une horloge ne devrait pas attendre
  que le texte revienne.
- La barre de séries n'est plus coupée à 11 ou 16 valeurs : mesuré, NG en
  dessine les 15 dernières et ignore le reste — la même queue que le découpage
  gardait.

### Déploiement
- `backend/docker-entrypoint.py` manquait au premier jet du portage : le
  `Dockerfile` le copie, donc le build aurait échoué sur la VM. Trouvé en
  relisant chaque chemin copié par les deux `Dockerfile` — ni Docker ni
  `docker compose` ne sont installés sur la machine de développement, donc
  **le build n'a pas pu être vérifié ici.**

### Mesuré, et qui reste à surveiller
- **`PUT /api/v1/apps/order` est cassée** en 1.1.2 : seule méthode autorisée,
  et *tout* corps JSON — `{}` compris — répond `invalidJson`. Donc pas de
  réordonnancement natif ; on garde la méthode d'awtrixhub, supprimer puis
  republier dans l'ordre.
- **Panneau éteint, le framebuffer continue d'être dessiné.** Un aperçu bâti
  sur `/display/screen` montrerait l'heure sur une horloge noire. Se fier à
  `power`.
- **`PATCH /api/v1/display` ne valide presque rien** : `{"zz":"ZZZ"}` répond
  `{"ok":true}`. Comme `progress` et `barChart`, l'appareil ne rattrape pas.
- Pousser une app nommée comme une native la **masque** — `Battery` devient
  `origin: "pushed"`. Nos noms sont préfixés, donc hors d'atteinte, mais c'est
  une raison de plus de l'être.

## [0.2.0]

Une **ligne de commande**, parce que 0.1.0 n'était testable que par `pytest` ou
par le REPL. Elle n'est pas le produit : elle existe pour que les versions 0.x
soient essayables avant l'API REST et l'interface, et elle restera utile
ensuite pour la même raison qu'un shell de base de données reste utile.

### Ajouté
- **`python -m app.cli`** — `info`, `apps`, `screen`, `push`, `delete`,
  `notify`, `icon`, `logs`, `settings`, `capabilities`.
- **`screen` dessine la matrice dans le terminal**, en couleurs vraies, lue
  depuis `GET /display/screen`. Deux rangées de pixels par ligne de texte via
  le demi-bloc haut, sinon l'horloge sortirait deux fois trop haute.
  `--watch` rafraîchit sur place.
- **`app/core/protected.py`** — la liste des afficheurs auxquels cette
  installation ne doit jamais écrire. Le Salon (`awtrix-cl1`) y est par défaut ;
  `AWTRIXNG_PROTECTED_HOSTS` la remplace, et la vider désactive le garde-fou.
- 23 tests de plus : **82 sans matériel**, 9 contre une horloge réelle.

### Changé
- `tests/test_device.py` utilise désormais le garde-fou partagé au lieu de sa
  propre liste. Une seule liste à tenir, un seul endroit où se tromper.

### Pourquoi le garde-fou est du code et pas une note
Sur le projet précédent, une seconde instance pointée sur un afficheur en
service a supprimé ses apps **deux fois** — la seconde *après* que le risque
eut été consigné dans un ADR. Une mise en garde qu'il faut se rappeler n'est
pas un garde-fou. Lire un afficheur protégé reste permis : c'est écrire qui est
refusé, avant qu'une seule requête ne quitte la machine.

### Mesuré au passage
- **L'écran se lit tel quel, transition comprise.** Une capture prise pendant
  la transition « Rain » rend une image brouillée qui n'est pas un défaut : le
  firmware dessine, on lit. Attendre une seconde après un `push --switch` avant
  de lire.

## [0.1.0]

Premier code du dépôt : le socle backend et le **client AWTRIX NG**, c'est-à-dire
la seule couche qui parle au firmware. Rien de visible encore — pas d'API REST,
pas d'interface, pas de planificateur. C'est la pièce dont tout le reste dépend,
et la seule qui soit vraiment nouvelle : le reste se reprend d'awtrixhub.

### Ajouté
- **`app/services/ng/`** — transport HTTP, modèle de payload, client, icônes.
  Toutes les routes `/api/v1/` dont le projet aura besoin : état, capacités,
  réglages, apps, notifications, fichiers, écran, journal.
- **`app/core/`** — erreurs, configuration, garde-fous d'URL sortante, journal
  qui masque les secrets. Repris d'awtrixhub, préfixe d'environnement
  `AWTRIXNG_`.
- **65 tests**, dont **9 qui tournent contre une horloge réelle**
  (`pytest -m device`, désélectionnés par défaut).
- **`docs/ng-api/payload-keys.md`** — le relevé des clés, sondées une par une
  sur le matériel.

### Mesuré sur matériel, et qui change le code
- **La validation de NG n'est pas uniforme.** `textCase`, `iconMode`, `effect`,
  `overlay`, `palette`, `scroll.*` et `draw` sont refusés quand ils sont faux ;
  `progress`, `repeat`, `barChart` et `lineChart` **ne le sont pas** —
  l'appareil répond `{"ok": true}` à `{"progress": 500}`. Les bornes du modèle
  sont donc les nôtres, et les retirer laisserait une valeur aberrante
  atteindre la matrice.
- **NG supprime une app par son nom exact**, pas par préfixe. Vérifié en
  poussant `zz1`, `zz12` et `zz1x` puis en supprimant `zz1` : les deux autres
  sont restées. C'était la raison d'être du nommage sur largeur fixe
  d'awtrixhub (`ah000123`) — voir ADR-001.
- **Le champ `origin` des apps** distingue `builtin` de `pushed`. Une app du
  firmware ne peut plus être prise pour une orpheline, ce qui est la panne qui
  a vidé une horloge en service deux fois sur le projet précédent.
- **Sept clés n'existent pas** là où un portage les écrirait par réflexe :
  `center`, `noScroll`, `scrollSpeed`, `textOffset`, `topText`, `rainbow`,
  `background`. Le défilement est passé dans un objet `scroll`.
- `GET /display/screen` répond `{width, height, pixels}` et non une liste nue ;
  `GET /logs` porte un curseur `next` qui permet de ne relire que le nouveau.

### Décidé
- Cinq ADR, dans [`docs/architecture.md`](docs/architecture.md).

### À faire ensuite
- Le modèle de données et les migrations, puis le planificateur, puis l'API
  REST, puis l'interface. Les connecteurs (météo, air, carburants, vacances,
  lune) se reprennent d'awtrixhub avec leurs tests.
