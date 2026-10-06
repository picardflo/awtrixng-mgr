# Le circuit : développer, publier, déployer

Trois dépôts, une VM, et des pièges qui ne se devinent pas. Cette page est
l'aide-mémoire — elle a été écrite après les avoir tous rencontrés.

```
  poste de travail                 Gogs (privé)            GitHub (public)
  ~/Gogs/awtrixng-mgr   ──push──►  origin        ──push──►  github
          │
          │                                            docker-vm
          └────────────────────────────────────────►  /srv/docker_data/...
                                                       git pull + rebuild
```

## En une ligne

```bash
git push origin master    # Gogs, en continu
git push github master    # GitHub, quand c'est prêt à être vu
```

Puis, **sur la VM** :

```bash
cd /srv/docker_data/awtrixng-mgr
git pull
docker compose up -d --build
```

## L'identité, et pourquoi elle est réglée par dépôt

L'historique public ne doit pas porter l'adresse professionnelle de l'auteur.
Elle est donc remplacée **dans ce dépôt seulement** :

```bash
git config --get user.email          # ici : …@users.noreply.github.com
git config --global --get user.email # ailleurs : l'adresse habituelle
```

`git config` sans `--global` écrit dans `.git/config` du dépôt courant. Les
autres dépôts de la machine n'en savent rien — c'est exactement l'usage prévu
quand on porte plusieurs casquettes.

L'adresse de redirection vient de GitHub, **Settings → Emails → Keep my email
addresses private**. Vaut la peine d'y cocher aussi **Block command line
pushes that expose my email** : c'est la différence entre « j'ai vérifié » et
« c'est vérifié ».

### Le ménage a été fait une fois

Une centaine de commits portaient l'ancienne adresse.
`scripts/prepare-publication.sh` les a réécrits, et l'historique corrigé a été
adopté **partout**, Gogs compris. Les trois dépôts sont donc au même commit,
et il n'y a plus de réécriture à faire.

Le script reste là pour le jour où la même situation se présenterait sur un
autre dépôt. Il travaille sur un clone jetable, jamais sur le dépôt courant.

## Les quatre pièges rencontrés

### « git pull met à jour, donc l'application est à jour »

Non. `git pull` met à jour **les fichiers** ; le conteneur continue d'exécuter
ce qu'il a embarqué au dernier build. D'où un dépôt en 0.16.3 et une
application en 0.16.2, sans que rien ne le signale.

Ce qui tranche :

```bash
curl -sk https://<votre-hôte>/api/health   # la version qui tourne vraiment
```

### « stale info » au push

`--force-with-lease` compare ce qu'on pousse à ce qu'il **croit** savoir du
distant. Un clone qui n'a jamais rien récupéré de ce distant n'a aucun point
de comparaison : ce n'est pas un conflit, c'est une ignorance.

```bash
git fetch origin && git push --force-with-lease origin master
```

### Les deux conteneurs sont sains et l'interface est morte

Corrigé en 0.15.1, mais le symptôme mérite d'être connu : voir
[Dépannage](manuel/Depannage.md). La durée de vie des conteneurs est ce qui
trahit — un backend recréé il y a une minute, un frontend debout depuis une
heure.

### Un garde-fou réglé au mauvais endroit

`AWTRIXNG_PROTECTED_HOSTS` dans le `.env` de la VM protège le conteneur. Les
outils qui écrivent le plus sur une dalle — banc de maquettes, extracteur de
police, tests matériels — tournent sur le **poste de travail**. Depuis la
0.16.1 le réglage est lu des deux côtés, mais il faut un `.env` à la racine de
la copie de travail aussi :

```ini
AWTRIXNG_PROTECTED_HOSTS=awtrix-salon,awtrix-salon.lan
```

## Avant de publier une version

```bash
cd backend  && .venv/bin/ruff check . && .venv/bin/python -m pytest
cd ../frontend && npx tsc --noEmit && npm test -- --run
cd .. && python3 scripts/check-manual.py
./scripts/bump-version.sh <version>      # met les trois fichiers d'accord
./scripts/update-screenshots.sh          # APRÈS le bump : la version est dans les images
```

Les tests matériels, écartés par défaut, demandent une horloge :

```bash
AWTRIXNG_TEST_HOST=awtrix-labo.lan backend/.venv/bin/python -m pytest -m device
```

## La licence

AGPL-3.0, dans [`LICENSE`](../LICENSE). Le texte vient de l'API de GitHub
(`api.github.com/licenses/agpl-3.0`), gnu.org ayant été injoignable le jour
où il a fallu le poser. Il a été vérifié plutôt que cru : 661 lignes, et
surtout la **clause 13, « Remote Network Interaction »**, qui est celle qui
distingue l'AGPL de la GPL. Sans elle, le fichier aurait été une GPL mal
étiquetée.

AWTRIX NG, lui, est sous PolyForm Noncommercial. Ça ne lie pas ce projet, qui
ne contient aucune ligne du firmware et dialogue avec son API HTTP — mais ça a
pesé dans le choix.

## Si quelqu'un contribue un jour

L'historique public a été réécrit une fois. Tant que personne d'autre n'avait
cloné, c'était sans conséquence. **Ça ne l'est plus** dès qu'un fork existe :
un force-push ferait disparaître les commits sur lesquels son travail repose.

D'où le circuit actuel, qui n'en demande plus aucun.
