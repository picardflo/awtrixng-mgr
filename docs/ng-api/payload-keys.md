# Les clés de payload, sondées une par une

Relevé pris le **5 octobre 2026** sur une **Ulanzi TC001** en **AWTRIX NG
1.1.2**, en envoyant chaque clé candidate à l'appareil et en lisant sa réponse.

La méthode tient à une propriété du firmware : il **refuse ce qu'il ne connaît
pas, en le nommant**.

```
PUT /api/v1/apps/pushed/probe   {"zzzUnknownKey": 1}
→ 422 {"error":{"code":"validationFailed",
                "message":"unknown key \"zzzUnknownKey\"",
                "field":"zzzUnknownKey"}}
```

C'est l'inverse d'AWTRIX 3, qui ignorait en silence ce qu'il ne comprenait pas
— une faute de frappe dans une clé y produisait un afficheur discrètement faux,
sans rien dire. Ici, l'appareil est sa propre documentation.

---

## Ce que la route des apps accepte

`PUT /api/v1/apps/pushed/<nom>`

| Clé | Forme | Note |
|---|---|---|
| `text` | chaîne | |
| `textCase` | `inherit` \| `upper` \| `asTyped` | énumération nommée dans le 422 |
| `scroll` | objet | `mode`, `direction`, `entry`, `whenFits`, `speed`, `gap`, `holdMs` |
| `textColor` | couleur | **c'est le remplaçant de `color`** |
| `backgroundColor` | couleur | ex-`background` |
| `palette` | nom ou liste de couleurs | les noms connus sont dans `capabilities` |
| `icon` | chaîne | identifiant inchangé depuis AWTRIX 3 |
| `iconMode` | `fixed` \| `pushOnce` \| `push` | ex-`pushIcon`, qui était un entier |
| `effect` | chaîne | validé contre `capabilities.effects` |
| `overlay` | chaîne | validé contre `capabilities.overlays` |
| `barChart` | liste | ex-`bar` |
| `lineChart` | liste | ex-`line` |
| `draw` | liste de commandes | voir plus bas |
| `progress` | entier | |
| `progressColor` | couleur | ex-`progressC` |
| `progressTrackColor` | couleur | ex-`progressBC` |
| `durationMs` | entier | millisecondes, ex-`duration` en secondes |
| `lifetimeMs` | entier | millisecondes, ex-`lifetime` |
| `repeat` | entier | |

## Ce que seule la route des notifications accepte

`POST /api/v1/notifications` — ces six clés répondent `unknown key` sur la
route des apps :

`hold` · `stack` · `wakeup` · `sound` · `soundRtttl` · `soundLoop`

`soundRtttl` est analysé à la volée et dit où il a buté :
`missing ':' after the melody name (at offset 1)`.

## Ce qui n'existe plus du tout

Testées, toutes refusées. Ce sont les clés d'AWTRIX 3 qu'un portage écrit par
réflexe :

`color` · `background` · `duration` · `lifetime` · `pos` · `center` ·
`noScroll` · `scrollSpeed` · `textOffset` · `topText` · `rainbow` ·
`blinkText` · `fadeText` · `bar` · `line` · `gradient` · `pushIcon` · `save`

Et des noms plausibles qui n'ont jamais existé, pour fermer la question :
`position`, `index`, `align`, `textAlign`, `effectSettings`, `iconPosition`,
`autoScale`, `min`, `max`, `unit`, `bitmap`, `image`, `chart`, `rtttl`,
`melody`, `priority`, `dismissable`.

## Les commandes de dessin

`draw` est une liste de **tableaux, le nom d'abord** — un objet est refusé :
« each draw command must be an array, name first ».

Connues : `pixel` · `line` · `rect` · `circle` · `bitmap` · `text`

Inconnues, bien qu'attendues : `fill`, `fillRect`, `fillCircle`.

## Le piège : la validation n'est pas uniforme

C'est le relevé le plus important de la session, et il va contre l'impression
que donne le reste.

Sont **validés** et refusés : `textCase`, `iconMode`, `effect`, `overlay`,
`palette`, `scroll.*`, `draw`, et toute clé inconnue.

Ne sont **pas validés** — l'appareil répond `{"ok": true}` :

```
{"progress": 500}       → ok      alors que l'échelle est 0–100
{"repeat": -5}          → ok
{"barChart": "zz"}      → ok      une chaîne là où une liste est attendue
{"lineChart": {"zz":1}} → ok      un objet là où une liste est attendue
```

**Conséquence pour le code :** les bornes de `app/services/ng/payload.py` sont
les nôtres, pas celles du firmware. Les retirer en se disant que l'appareil
vérifie reviendrait à laisser une valeur aberrante atteindre la matrice.

## Trois règles de transport, mesurées

- **`Content-Type: application/json` est obligatoire.** Sans lui, 415, et la
  requête n'a simplement aucun effet.
- **Un corps vide n'est plus une suppression.** AWTRIX 3 supprimait une app en
  lui postant du vide ; NG a `DELETE`, et l'ambiguïté disparaît avec.
- **La suppression vise le nom exact.** Vérifié en poussant `zz1`, `zz12` et
  `zz1x` puis en supprimant `zz1` : les deux autres sont restées. AWTRIX 3
  supprimait par préfixe, ce qui obligeait le projet précédent à nommer ses
  apps sur une largeur fixe (`ah000123`). **Cette raison-là a disparu.**

## Deux routes dont la forme surprend

```
GET /api/v1/display/screen  → {"width":32,"height":8,"pixels":[...]}
GET /api/v1/logs            → {"next":9,"lines":["[ 0s] boot: AWTRIX NG 1.1.2 …"]}
```

L'écran n'est pas une liste nue comme sur AWTRIX 3, et le journal porte un
curseur : en le repassant en `since`, on ne relit que ce qui est nouveau.

## Refaire le relevé

Tout ceci est vérifié en continu par `backend/tests/test_device.py`, qui tourne
sur demande contre une horloge réelle :

```
cd backend
AWTRIXNG_TEST_HOST=awtrix-cl2.home.lan .venv/bin/python -m pytest -m device
```

Ces tests **écrivent** sur l'afficheur visé. Ils refusent de démarrer sans
hôte explicite, et refusent par leur nom les afficheurs en service.
