# awtrixng-mgr

**AWTRIX NG manager** — application web auto-hébergée, déployable sous Docker,
servant de middleware entre des services externes et un ou plusieurs afficheurs
[AWTRIX NG](https://github.com/Blueforcer/awtrix-ng).

> **État : socle.** Version 0.2.0 — le client AWTRIX NG est écrit, vérifié
> sur une horloge réelle, et pilotable en ligne de commande. Il n'y a encore ni
> API REST, ni interface web, ni planificateur. Voir le
> [CHANGELOG](CHANGELOG.md).

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

## Développer

```bash
cd backend
python3 -m venv --without-pip .venv            # pas de python3-venv ici
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest                     # la suite, sans matériel
```

Les tests qui parlent à une horloge réelle sont désélectionnés par défaut. Ils
**écrivent** sur l'afficheur visé, refusent de démarrer sans hôte explicite, et
refusent par leur nom les afficheurs en service :

```bash
AWTRIXNG_TEST_HOST=mon-horloge.local .venv/bin/python -m pytest -m device
```

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
