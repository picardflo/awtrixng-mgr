# Plex, par Tautulli

Ce qui passe en ce moment sur votre Plex, et combien de personnes regardent.

Le connecteur parle à **[Tautulli](https://tautulli.com)**, le compagnon de
statistiques de Plex — pas à Plex directement. Tautulli expose une API simple
et un seul appel suffit.

## Le mettre en place

**Services → Tautulli (Plex).** Trois champs :

| | |
|---|---|
| **Adresse** | celle que vous ouvrez dans un navigateur, sans `/home` |
| **Clé d'API** | Tautulli → Réglages → Interface web → API. Stockée chiffrée |
| **Vérifier le certificat** | à décocher si votre Tautulli est en HTTPS avec un certificat auto-signé, ce qui est le cas courant sur un réseau domestique |

« Tester la connexion » répond en nommant ce qu'il trouve : le nombre de flux,
ou la raison précise du refus — une clé rejetée, un serveur injoignable et un
certificat refusé sont trois pannes différentes et se disent différemment.

## Lecture en cours

L'icône dit l'**état**, la barre dit la **progression**, le texte dit le reste.

- ▶ en lecture, ⏸ en pause, ⏹ en mise en mémoire tampon
- la barre, c'est où vous en êtes dans le film ou l'épisode

### Le piège des titres

Un titre d'épisode réel, mesuré sur une dalle :

```
"Une série - Le pilote qui n'en finit pas"
  →  185 colonnes pour les 23 disponibles à côté de l'icône
  →  11 secondes pour défiler une fois
```

**La durée par défaut d'un widget est de 7 à 8 secondes.** Le titre complet
n'aurait donc jamais le temps de finir : l'app passe la main au milieu d'un
mot. C'est pourquoi ce widget-là, et lui seul, démarre à **14 secondes**.

Si le défilement vous gêne, le gabarit `{{ label }}` donne la forme courte —
`S03E16` pour un épisode, l'année pour un film. Elle est **fixe**, lue d'un
coup d'œil, et c'est le seul texte qui tienne sans bouger.

### Les variables

`{{ title }}` le titre complet · `{{ label }}` la forme courte ·
`{{ show }}` la série ou le film · `{{ episode }}` le titre de l'épisode ·
`{{ season }}` `{{ number }}` `{{ year }}` ·
`{{ percent }}` la progression · `{{ state }}` ·
`{{ user }}` qui regarde · `{{ player }}` sur quoi · `{{ streams }}` le total

## Plusieurs personnes à la fois

Le widget **passe d'un flux à l'autre** à chaque rafraîchissement. Il ne garde
rien en mémoire : le choix se déduit de l'heure, ce qui veut dire que le même
widget sur deux horloges affiche le même flux au même moment.

Pour en suivre un en particulier, créez plutôt un second widget.

## Flux actifs

Un compteur, avec le détail en variables : `{{ streams }}`,
`{{ transcoding }}`, `{{ direct }}`, `{{ bandwidth }}`.

**C'est le transcodage qui compte.** Un flux lu directement ne coûte presque
rien à votre serveur ; un flux transcodé lui fait recalculer chaque image. Si
votre Plex rame un soir, c'est ce nombre qu'il faut regarder.

## Quand personne ne regarde

Les deux widgets **disparaissent de la rotation**. C'est l'option « masquer en
l'absence de données », cochée par défaut ici : une horloge qui affiche `0`
toute la soirée est pire qu'une horloge qui n'affiche rien.
