# awtrixng-mgr

**AWTRIX NG manager** — application web auto-hébergée, déployable sous Docker,
servant de middleware entre des services externes et un ou plusieurs afficheurs
[AWTRIX NG](https://github.com/Blueforcer/awtrix-ng).

> **État : fonctionnel.** Version 0.3.0 — l'application complète, portée
> d'awtrixhub sur AWTRIX NG : connecteurs, planificateur, API REST, interface
> React. Chaque option d'affichage a été essayée sur une horloge réelle.
> Le `docker compose` n'a pas pu être construit ici (pas de Docker sur la
> machine de dev). Voir le [CHANGELOG](CHANGELOG.md).

---

## Pourquoi un nouveau projet

Ce projet succède à **awtrixhub**, qui pilote des horloges en AWTRIX 3.

[AWTRIX 3 est abandonné](https://github.com/Blueforcer/awtrix3) depuis
septembre 2026 — son dépôt est une archive, sa dernière version est la 0.98 de
janvier 2025. Le successeur, **AWTRIX NG**, est une réécriture complète dont
l'API n'a **aucune compatibilité ascendante** : routes `/api/v1/`, clés en
camelCase, durées en millisecondes, validation stricte.

Faire cohabiter les deux firmwares dans un seul dépôt aurait fait converger le
projet vers le plus petit dénominateur commun, et bridé NG durablement :
scripts embarqués sur l'appareil, overlays météo natifs, palettes, graphiques,
panneaux jusqu'à 128 px. D'où un dépôt séparé.

**awtrixhub n'est pas abandonné pour autant** : il reste en service sur les
horloges encore en AWTRIX 3, figé parce que son firmware l'est.

## Ce qui est repris d'awtrixhub

Tout ce qui ignore le firmware, c'est-à-dire l'essentiel : les connecteurs
(Open-Meteo, qualité de l'air, UV, pollens, prix des carburants, vacances
scolaires, phases de lune), le planificateur, le moteur de gabarits, l'API
REST, l'interface React — et leurs tests, qui portent les leçons apprises à
l'usage.

Ce qui disparaît : la couche qui parlait à AWTRIX 3, remplacée par un client
`/api/v1/`.

## Documentation

- [`docs/ng-api/`](docs/ng-api/) — l'API d'AWTRIX NG **mesurée sur une Ulanzi
  TC001 réelle**, avec les réponses brutes de l'appareil. Routes, payloads,
  mécanisme d'icônes, pièges rencontrés, et la procédure de récupération si
  l'horloge se bloque après un flash.
- [`docs/ng-api/payload-keys.md`](docs/ng-api/payload-keys.md) — chaque clé de
  payload sondée une par une sur le matériel : ce que le firmware accepte, ce
  qu'il refuse en le nommant, et **ce qu'il accepte sans le valider**.
- [`docs/architecture.md`](docs/architecture.md) — les décisions prises, et
  celles héritées d'awtrixhub qui restent à rejuger.
- **[Le wiki](https://gogs.home.lan/fpicard/awtrixng-mgr/wiki)** — le manuel
  d'utilisation : démarrage, widgets, rappels, dépannage. Les captures qu'il
  affiche vivent dans [`docs/screenshots/`](docs/screenshots/).

## La démonstration

```bash
backend/.venv/bin/python scripts/demo/serve.py --port 9000
```

L'application complète contre un faux amont : deux afficheurs AWTRIX NG
inventés, une fausse Open-Meteo, des données fixes. **Elle ne touche aucun
matériel** — c'est ce qui permet de prendre les captures sans risquer qu'un
réconciliateur efface les apps d'une horloge en service.

`./scripts/update-screenshots.sh` la lance, capture les dix-neuf écrans du wiki
et les écrit dans `docs/screenshots/`. Le numéro de version apparaît dans les
images : capturez **avant** de bumper.
- [`docs/ng-vs-awtrix3.md`](docs/ng-vs-awtrix3.md) — ce que le portage a
  retiré, changé et gagné, option par option, avec la mesure qui le justifie.

## Développer

```bash
cd backend
python3 -m venv --without-pip .venv            # pas de python3-venv ici
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest                     # 873 tests, sans matériel

cd ../frontend && npm install && npm run build
npx vitest run                                 # 93 tests
```

Les tests qui parlent à une horloge réelle sont désélectionnés par défaut. Ils
**écrivent** sur l'afficheur visé, refusent de démarrer sans hôte explicite, et
refusent par leur nom les afficheurs en service :

```bash
AWTRIXNG_TEST_HOST=mon-horloge.local .venv/bin/python -m pytest -m device
```

Parmi eux, `tests/test_device_widgets.py` rend **chaque type de widget** à
partir de ses données d'exemple, le pousse, et relit la matrice. C'est ce qui
distingue « le payload est celui qu'on attendait » de « l'afficheur en fait
quelque chose ».

## Parler à une horloge, sans interface

En attendant l'interface web, une ligne de commande permet d'essayer tout ce
que le client sait faire :

```bash
cd backend
export AWTRIXNG_HOST=mon-horloge.local

.venv/bin/python -m app.cli info          # version, capteurs, batterie, capacités
.venv/bin/python -m app.cli apps          # les apps présentes, avec leur origine
.venv/bin/python -m app.cli screen        # la matrice, dessinée dans le terminal
.venv/bin/python -m app.cli screen --watch

.venv/bin/python -m app.cli push "SALUT" --color '#f5a524' --switch
.venv/bin/python -m app.cli push "12 °C" --icon 11949 --overlay rain
.venv/bin/python -m app.cli notify "Minuteur fini" --wakeup --rtttl 'd=4,o=5,b=120:c,e,g'
.venv/bin/python -m app.cli delete cli

.venv/bin/python -m app.cli logs --follow
```

`screen` lit le framebuffer réel : ce que la matrice montre, pas ce qu'on croit
lui avoir envoyé. Une capture prise pendant une transition rend une image en
cours de dessin — c'est normal, attendre une seconde.

**Les commandes qui écrivent refusent les afficheurs en service.** La liste est
dans `app/core/protected.py`, le Salon y est par défaut, et
`AWTRIXNG_PROTECTED_HOSTS` la remplace. Lire reste toujours permis.

<a id="versions"></a>
## Versions

| Niveau | Quand | Conséquence pour l'exploitant |
|---|---|---|
| Correctif `0.1.x` | défaut corrigé, interface ajustée, doc complétée | `git pull && docker compose up -d --build` |
| Mineur `0.x.0` | nouveau widget, nouveau service, migration de base | automatique, mais du neuf apparaît |
| Majeur `x.0.0` | variable obligatoire, format de sauvegarde incompatible | **une action de sa part** |

`./scripts/bump-version.sh <version>` met d'accord les fichiers qui portent le
numéro ; un test échoue s'ils divergent.

## Licence

Aucune licence n'est encore choisie. En l'état, tous droits réservés.
