# Le portage, option par option

Ce document existe parce que la règle du projet est de **mesurer, pas de
traduire**. Chaque ligne ci-dessous a été vérifiée sur une **Ulanzi TC001
réelle en AWTRIX NG 1.1.2** : payload poussé, matrice relue.

La méthode : pousser une référence, pousser une variante, comparer les
framebuffers. Deux pièges l'ont faite mentir la première fois, et les deux
valent d'être connus.

1. **La transition dure une seconde.** Capturer avant sa fin compare du bruit,
   et *tout* paraît agir — y compris `iconMode` sur une app sans icône.
2. **Un texte court tient dans la matrice**, donc toutes les options de
   défilement paraissent inertes. Il faut un texte qui déborde.

On caractérise donc par l'ensemble des images distinctes vues sur quelques
secondes, ce qui distingue « fixe », « animé » et « animé autrement ».

---

## Ce qui a été retiré

| Option | Ce que la mesure a donné |
|---|---|
| `center` | **Aucune clé de centrage dans NG.** Et il n'en faut pas : le firmware centre seul tout texte qui tient. `"A"` tombe colonnes 14-16, `"ABC"` colonnes 10-20, `"ABCDEFGH"` colonnes 0-30 — chaque fois là où un centrage les mettrait. |
| `rainbow` | `palette` colore les **effets**, pas le texte. Poussé `{"text":"ARC","palette":"Rainbow"}`, relu l'écran : **une seule couleur allumée**. |
| `lifetimeMode` | `unknown key`. Le marquage « périmé » d'AWTRIX 3 — contour rouge plutôt que suppression — n'a pas d'équivalent. |
| Apps natives | **NG n'offre aucun moyen de les désactiver.** `DELETE /api/v1/apps/Battery` répond `{"ok":true}` et ne change rien ; aucun des 42 réglages ne les gouverne ; `/apps/<nom>` n'accepte que DELETE. Le panneau du projet précédent, qui redémarrait l'horloge pour ça, n'a plus d'objet. |
| Découpage des séries | Inutile. Mesuré : 40 valeurs envoyées, le firmware en dessine **les 15 dernières** — la même queue que le découpage manuel gardait. |

## Ce qui a changé de nom ou de forme

| AWTRIX 3 | AWTRIX NG | Note |
|---|---|---|
| `color` | `textColor` | l'erreur de portage la plus probable |
| `background` | `backgroundColor` | |
| `duration` (s) | `durationMs` | l'interface garde les secondes |
| `lifetime` (s) | `lifetimeMs` | |
| `pushIcon` 0/1/2 | `iconMode` `fixed`/`pushOnce`/`push` | |
| `textCase` 0/1/2 | `textCase` `inherit`/`upper`/`asTyped` | |
| `noScroll` | `scroll.mode: "static"` | |
| `scrollSpeed` | `scroll.speed` | tout le défilement est passé dans un objet |
| `bar` / `line` | `barChart` / `lineChart` | |
| `progressC` / `progressBC` | `progressColor` / `progressTrackColor` | |
| `TFORMAT` / `DFORMAT` (`strftime`) | `dateOrder`, `dateSeparator`, `dateYearMode`, `time24h`… | des choix, plus des incantations |
| `BRI` / `ABRI` / `VOL` | `brightness` / `autoBrightness` / `buzzerVolume` | et `soundEnabled`, qui n'existait pas |
| `POST /api/settings` | `PATCH /api/v1/settings` | PUT et POST répondent 405 |

## Ce que NG apporte

- **`overlay`** — pluie, neige, bruine, orage, tonnerre, givre, dessinés
  par-dessus le texte. Vérifié : la matrice s'anime.
- **L'interrupteur de matrice.** `PATCH /api/v1/display {"power": false}`
  éteint le panneau pour de bon, `true` le rallume. AWTRIX 3 n'avait que
  `/api/sleep`, une veille minutée.
- **`origin` sur chaque app** — `builtin`, `pushed`. C'est ce qui rend la
  réconciliation sûre : une app du firmware ne peut plus être prise pour une
  orpheline.
- **`GET /api/v1/capabilities`** — 19 effets, 22 transitions, 8 palettes,
  6 overlays, et la présence d'un buzzer, déclarés par l'appareil. Plus de
  liste codée en dur.
- **`GET /api/v1/logs`** avec un curseur `next`, inexistant avant.
- **`/api/v1/system`** — 66 champs : réglage fin du capteur de luminosité
  (`minBrightness`, `ldrGamma`, `brightnessSmoothing`), fuseau horaire,
  découverte Home Assistant, MQTT, géométrie des panneaux. Se met à jour en
  **PUT**, là où `/settings` et `/display` veulent **PATCH**.

## Les pièges, à relire avant de déboguer

**La validation n'est pas uniforme.** Sont refusés nommément : `textCase`,
`iconMode`, `effect`, `overlay`, `palette`, `scroll.*`, `draw`, et toute clé
inconnue d'un payload. Ne le sont **pas** :

```
{"progress": 500}        → {"ok": true}
{"repeat": -5}           → {"ok": true}
{"barChart": "zz"}       → {"ok": true}
PATCH /display {"zz":1}  → {"ok": true}
```

Les bornes du modèle sont donc les nôtres. Les retirer en se disant que
l'appareil vérifie laisserait une valeur aberrante atteindre la matrice.

**Panneau éteint, le framebuffer continue d'être dessiné.** `/display/screen`
rend des pixels sur une horloge noire. Un aperçu en direct bâti dessus mentirait
précisément au moment où on le consulte pour comprendre. Se fier à `power`.

**Pousser une app nommée comme une native la masque.** `PUT
/api/v1/apps/pushed/Battery` fait passer `Battery` en `origin: "pushed"`. Nos
noms sont préfixés et sur largeur fixe, donc hors d'atteinte — c'est une raison
de plus de le rester.

**`PUT /api/v1/apps/order` est cassée** en 1.1.2. Seule méthode autorisée, et
*tout* corps JSON — `{}`, `[]`, `{"order":[…]}` — répond
`{"error":{"code":"invalidJson"}}`. Pas de réordonnancement natif : on garde la
méthode du projet précédent, supprimer puis republier dans l'ordre. **À resonder à
chaque version du firmware.**

**Rien n'est journalisé quand le panneau s'éteint.** Une horloge trouvée noire
ne laisse aucune trace dans `/api/v1/logs`.

## Refaire ces mesures

```bash
cd backend
AWTRIXNG_TEST_HOST=awtrix-cl2.home.lan .venv/bin/python -m pytest -m device
```

22 tests, dont un par type de widget : chacun est rendu depuis ses données
d'exemple, poussé, et la matrice relue. Ils **écrivent** sur l'afficheur visé,
refusent de démarrer sans hôte explicite, et refusent par leur nom les
afficheurs en service.
