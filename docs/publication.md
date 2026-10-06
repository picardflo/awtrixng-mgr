# Publier ce dépôt

Ce qu'il reste à faire à la main, et pourquoi chaque point ne peut pas être
fait d'avance.

## 1. La licence — fait

**AGPL-3.0**, dans [`LICENSE`](../LICENSE).

Le texte vient de l'API de GitHub (`api.github.com/licenses/agpl-3.0`) et non
de gnu.org, injoignable depuis les deux machines le jour où il a fallu le
poser. Un texte de licence se copie **à l'octet près**, donc il a été vérifié
plutôt que cru :

```
661 lignes
« GNU AFFERO GENERAL PUBLIC LICENSE »
« Version 3, 19 November 2007 »
« 13. Remote Network Interaction »   <- la clause propre à l'AGPL
« Copyright (C) 2007 Free Software Foundation »
```

La clause 13 est celle qui distingue l'AGPL de la GPL : sans elle, le fichier
aurait été une GPL mal étiquetée.

### Pourquoi celle-ci

AWTRIX NG est sous **PolyForm Noncommercial**, qui exclut l'usage commercial.
Ça ne nous lie pas : ce projet ne contient aucune ligne du firmware, il parle
à son API HTTP, et utiliser une API ne crée pas d'œuvre dérivée.

L'AGPL a été choisie pour ce qu'elle empêche : quiconque en fait un service
accessible par le réseau doit en publier les modifications. Ces outils
existent parce que leurs équivalents commerciaux sont hors de prix ; l'AGPL
est la licence qui empêche d'en refaire un produit fermé, tout en restant une
vraie licence open source — donc packageable, forkable, contribuable.

## 2. L'adresse des commits

L'historique porte une adresse **professionnelle** dans une centaine de
commits. Publiée, elle est indéfiniment moissonnable et archivée dans chaque
miroir.

```bash
./scripts/prepare-publication.sh 12345678+monpseudo@users.noreply.github.com
```

L'adresse se trouve dans GitHub, **Settings → Emails → Keep my email
addresses private**. Elle redirige sans exposer.

Le script travaille sur un **clone jetable**, jamais sur ce dépôt : réécrire
l'historique change chaque empreinte de commit, et le `git pull` de la machine
de déploiement tomberait en rejet.

## 3. Ce qui a déjà été fait

- **Le manuel est dans `docs/manuel/`** et ne dépend plus d'un serveur privé :
  onze pages, images relatives, vérifiées par `./scripts/check-manual.py`.
- **Les exemples sont anonymisés.** Les relevés météo, air et carburants
  portaient le village de l'auteur ; ils portent une ville voisine, à
  géométrie équivalente — les distances et les prix restent cohérents.
- **Le garde-fou est vide par défaut.** `AWTRIXNG_PROTECTED_HOSTS` nommait
  l'horloge du salon de l'auteur. Une liste pleine des noms de quelqu'un
  d'autre ne protège personne tout en ayant l'air de protéger.
- **Les scripts matériels demandent l'afficheur** (`AWTRIXNG_PANEL`) au lieu
  d'en supposer un.
- **Plus aucun renvoi vers le dépôt privé** ni vers `gogs.home.lan`.

## 4. À décider avant le premier push

- **Le nom du dépôt** — `awtrixng-mgr` était libre sur GitHub, PyPI, npm et
  Docker Hub au 5 octobre 2026. À revérifier le jour venu.
- **Les captures d'écran** montrent des widgets réels : une ville, des prix de
  carburant, des noms de rappels. Elles ont été refaites depuis la
  démonstration (`scripts/demo/`), qui ne contient aucune donnée personnelle —
  mais un coup d'œil avant publication ne coûte rien.
- **Signaler quelque chose en amont ?** Plusieurs mesures faites ici
  intéresseraient l'auteur du firmware — `wakeup` accepté sans effet sur les
  notifications, par exemple. Si c'est fait, l'écrire soi-même : sur
  l'issue 62 d'awtrix-ng, il a explicitement demandé à ses rapporteurs de ne
  pas lui écrire via une IA.
