# L'API d'AWTRIX NG, mesurée

Relevé pris le **5 octobre 2026** sur une **Ulanzi TC001 réelle**, firmware
**AWTRIX NG 1.1.2**, ESP32, image `usb-awtrix-ng-4mb.bin`.

Ce dossier existe parce que ce projet fait confiance à ce qu'il a mesuré, pas à
ce qu'il a lu. Les `.json` à côté sont les réponses brutes de l'appareil, telles
qu'elles sont sorties. Deux champs ont été masqués — le SSID et l'adresse MAC —
mais la structure est intacte.

Référence amont : <https://blueforcer.github.io/awtrix-ng/>

---

## Ce qui a été vérifié de bout en bout

Une icône LaMetric a été téléchargée par son identifiant, installée sur
l'appareil, référencée dans une app poussée, et le rendu relu depuis le
framebuffer de l'horloge pour vérification. **La chaîne complète fonctionne.**

## Les icônes — la bonne nouvelle

Le travail d'icônes du projet précédent se transfère presque sans retouche.

| | AWTRIX 3 | AWTRIX NG |
|---|---|---|
| lister | `GET /list?dir=/ICONS` | `GET /api/v1/files?dir=/ICONS` |
| installer | `POST /edit`, champ `image`, nom `ICONS/<id>.gif` | `POST /api/v1/files?dir=/ICONS`, champ `file` |
| référencer | `{"icon": "1234"}` | identique |

**L'identifiant reste le nom du fichier sans extension.** GIF animé ou fixe,
jusqu'à 41×8 désormais (contre 32×8) ; JPEG accepté mais déconseillé, flou et
plus lourd à cette taille.

**512 Ko** partagés entre icônes, mélodies, palettes et scripts sur un ESP32
4 Mo.

## Le piège des payloads

`color` n'existe plus. C'est `textColor`.

```
{"color": "#f5a524"}      →  422  unknown key "color"
{"textColor": "#f5a524"}  →  200  {"ok": true}
```

La validation est stricte et **nomme le champ fautif**, ce qui rend le sondage
confortable — là où AWTRIX 3 ignorait silencieusement ce qu'il ne comprenait
pas. 42 clés au total, dont 7 réservées aux notifications.

Autres règles mesurées : `Content-Type: application/json` obligatoire (sinon
415), un corps vide n'est plus une suppression (utiliser `DELETE`), les durées
sont en millisecondes avec le suffixe `Ms`, les énumérations sont des chaînes,
et les apps poussées ne persistent pas au redémarrage.

## Les routes principales

| Route | Ce qu'elle donne |
|---|---|
| `GET /api/v1/device` | état, capteurs, batterie, heap, `resetReason` |
| `GET /api/v1/capabilities` | **effets, transitions, palettes, overlays, règles GPIO** |
| `GET /api/v1/settings` | 42 réglages d'affichage |
| `GET /api/v1/system` | 66 champs réseau, MQTT, NTP, GPIO |
| `GET /api/v1/apps` | inventaire, avec `origin` et `inLoop` |
| `PUT /api/v1/apps/pushed/<nom>` | pousser une app |
| `DELETE /api/v1/apps/<nom>` | la retirer |
| `PUT /api/v1/apps/active` | basculer dessus |
| `POST /api/v1/notifications` | notification |
| `GET /api/v1/display/screen` | **framebuffer 32×8, entiers RGB empaquetés** |
| `GET /api/v1/files?dir=/ICONS` | fichiers embarqués |
| `GET /api/v1/logs` | journal de démarrage, ligne par ligne |

## Ce que NG apporte et qu'AWTRIX 3 ne pouvait pas

- **`GET /api/v1/capabilities`** — l'appareil déclare ce qu'il sait faire :
  19 effets, 22 transitions, 8 palettes, 6 overlays météo. Plus besoin de coder
  ces listes en dur comme le faisait le projet précédent.
- **`overlay`** dans le payload — `rain`, `snow`, `drizzle`, `storm`,
  `thunder`, `frost`, dessinés par le firmware **par-dessus** le texte.
- **`palette`** avec arrêts de couleur — le dégradé de température interpolé à
  la main dans le projet précédent pourrait devenir déclaratif.
- **`barChart`, `lineChart`, `draw`** — graphiques et primitives de dessin
  (pixel, ligne, rectangle, cercle, bitmap).
- **Le son** — `buzzerVolume` et `soundEnabled` sont des réglages ; les
  notifications acceptent `sound`, `soundRtttl`, `soundLoop`, `wakeup`,
  `hold`, `stack`.
- **`GET /api/v1/logs`** — un journal, inexistant avant, précieux pour
  diagnostiquer.

`progress`, `progressColor` et `progressTrackColor` existent toujours : la
barre de progression garde son sens.

## Le GPIO du TC001

Les valeurs par défaut du firmware **sont** celles du TC001, vérifié via
`capabilities` :

```
matrice 32 · buzzer 15 · boutons 26/27/14 · batterie 34 · LDR 35
I2C 21/22 · DFPlayer 23/18 · I2S et ampli désactivés (-1)
```

## Au premier démarrage, si ça se bloque

L'horloge s'est figée buzzer continu après le flash. **Ce n'était pas le
GPIO.** Blueforcer l'explique par un bouton lu comme enfoncé au démarrage
([issue 62](https://github.com/Blueforcer/awtrix-ng/issues/62)).

**Récupération : maintenir le bouton du milieu à la mise sous tension**, une
seconde — l'appareil entre en mode provisionnement et affiche `SETUP`. Variante
pour désactiver les scripts : gauche + droite, trois secondes au démarrage.

**Retour en arrière toujours possible :** `ulanzi_TC001_0.98.bin` reste
téléchargeable depuis la release archivée d'AWTRIX 3. Reflasher ne change pas
l'adresse MAC, donc une réservation DHCP et son nom DNS survivent à l'opération.
