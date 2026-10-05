# awtrixng-mgr

**AWTRIX NG manager** — application web auto-hébergée, déployable sous Docker,
servant de middleware entre des services externes et un ou plusieurs afficheurs
[AWTRIX NG](https://github.com/Blueforcer/awtrix-ng).

> **État : démarrage.** Le dépôt ne contient encore que le relevé de l'API,
> mesuré sur matériel réel. Le code arrive.

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

## Licence

Aucune licence n'est encore choisie. En l'état, tous droits réservés.
