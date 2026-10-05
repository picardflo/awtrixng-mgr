# Journal des versions

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et la
numérotation la règle décrite dans le [README](README.md#versions).

## [Non publié]

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
