# Steam

Le jeu que vous avez lancé, et où vous en êtes de ses succès.

Deux widgets, qui disparaissent tous les deux de la rotation quand vous ne
jouez pas. L'horloge ne dit rien plutôt que de dire « rien ».

## Le mettre en place

**Services → Steam.** Deux champs :

| | |
|---|---|
| **Profil** | votre SteamID64, ou le nom à la fin de l'URL de votre profil. Coller l'URL entière fonctionne aussi |
| **Clé Web API** | gratuite, sur [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey). Stockée chiffrée |

Le champ **Profil** accepte les trois formes parce que personne ne connaît ses
dix-sept chiffres par cœur :

```
76561197960435530                            l'identifiant
unPseudo                                     le nom d'URL personnalisée
https://steamcommunity.com/id/unPseudo/      l'URL, telle qu'on la copie
```

> **Le piège, et il est silencieux.** Le nom d'URL personnalisée **n'est pas**
> votre nom affiché. Si vous n'avez jamais rempli le champ « URL perso. » de
> votre profil Steam, votre pseudo appartient peut-être à quelqu'un d'autre —
> et Steam répondra `200`, sans la moindre erreur, avec le compte de cet
> inconnu. Le connecteur marchera parfaitement, sur la mauvaise personne.
>
> C'est arrivé pendant l'écriture de cette page : un pseudo tapé tel quel a
> résolu vers le compte d'un inconnu à l'autre bout du monde. Dans le doute, ouvrez votre profil et prenez le
> numéro dans l'adresse — `steamcommunity.com/profiles/`**`76561197960435530`**`/`.
>
> « Tester la connexion » affiche **toujours** l'identifiant résolu à côté du
> nom, précisément pour que vous puissiez les comparer.

### Un réglage à faire côté Steam

Dans **Profil → Modifier le profil → Confidentialité**, les **détails du jeu**
doivent être **publics**. C'est le seul réglage qui compte ici, et sans lui
l'API ne dit jamais à quoi vous jouez — y compris à vous-même.

« Tester la connexion » répond en vous nommant, et en nommant le jeu si vous
êtes en train d'en lancer un. Une clé refusée se dit comme une clé refusée, et
non comme un profil privé : les deux donnent la même réponse chez Steam, et ce
sont deux réglages différents à aller chercher.

## En jeu

Le texte dit le jeu, l'icône dit que c'est Steam. Pas de barre : il n'y a rien
à mesurer dans « être en train de jouer ».

### La longueur des titres, mesurée

Contrairement à Plex, **ce widget garde la durée ordinaire de 8 secondes**, et
c'est une mesure qui le dit. Sur les vingt-quatre jeux les plus joués de
Steam, rendus dans la police de la dalle :

```
"Hades", "Rust", "Dota 2"               ≤ 23 colonnes   fixes, aucun défilement
médiane                                   53 colonnes   5,0 s de défilement
"Red Dead Redemption 2"                   75 colonnes   6,4 s
"The Elder Scrolls V: Skyrim Special…"   149 colonnes  11,3 s
```

Trois titres sur quatre finissent donc dans un passage normal. Le quatrième
est toujours un nom de franchise avec un sous-titre, et c'est à ça que sert
`{{ short }}` :

```
Call of Duty®: Modern Warfare® II   →  Call of Duty          9,3 s → 4,3 s
Tom Clancy's Rainbow Six Siege      →  Rainbow Six Siege     8,3 s → 5,3 s
The Elder Scrolls V: Skyrim Spe…    →  The Elder Scrolls V  11,3 s → 6,1 s
Baldur's Gate 3                     →  Baldur's Gate 3        inchangé
```

La forme courte retire la marque, le sous-titre, et le nom de l'éditeur quand
il est collé devant en deux mots — « Tom Clancy's », « Sid Meier's ». Elle ne
touche pas à « Baldur's Gate 3 » ni à « Garry's Mod », où le possessif **est**
le titre. C'est la seule subtilité de la règle, et elle est volontaire.

### Les variables

`{{ game }}` le titre complet · `{{ short }}` la forme courte ·
`{{ player }}` votre nom affiché · `{{ state }}` votre état ·
`{{ appid }}` l'identifiant du jeu · `{{ server }}` le serveur, le cas échéant

`{{ state }}` vaut `playing`, `online`, `away`, `busy`, `snooze` ou `offline`.
Il reste renseigné même quand vous ne jouez pas — de quoi bâtir un autre
widget si c'est votre présence qui vous intéresse plutôt que le jeu.

## Succès

Le seul widget de ce connecteur qui ait une **barre** qui veuille dire quelque
chose : une fraction d'un total connu, ce pour quoi une barre existe.

```
23/49    ●●●●●●●●●○○○○○○○○○○
```

`23/49` fait 19 colonnes sur les 23 disponibles : **il ne défile pas**. Seul un
jeu à cent succès tous débloqués déborde — `100/100` fait 27 colonnes — et il
défile alors une demi-seconde.

Grande police par défaut, parce qu'il y a une barre : la petite laisserait une
rangée vide juste au-dessus. C'est une règle de tout le projet, et elle est
mesurée.

### Les variables

`{{ unlocked }}` débloqués · `{{ total }}` le total · `{{ remaining }}` ce
qu'il reste · `{{ percent }}` l'achèvement · `{{ game }}` et `{{ short }}`

## Quand le widget ne montre rien

Trois situations, et une seule est un problème :

| Ce qui se passe | Ce que fait le widget |
|---|---|
| Vous ne jouez pas | il quitte la rotation, c'est voulu |
| Le jeu n'a aucun succès | **Succès** quitte la rotation ; beaucoup de jeux n'en ont pas |
| Les détails du jeu sont privés | **Succès** reste vide, et c'est le réglage à corriger |

### Le cas qui n'a aucun symptôme

**« En jeu » marche, « Succès » reste vide pour toujours, et tout a l'air
normal.** La carte du service est verte, le jeu s'affiche sur l'horloge, et
rien ne pointe nulle part.

C'est que **« Détails du jeu » n'est pas sur Public**, dans
*Profil → Modifier le profil → Options de confidentialité*.

Ce qui le rend invisible, c'est une exception de Steam : **une clé liée au
compte qu'on interroge contourne la confidentialité** sur certains appels et
pas sur celui des succès.

```
vos jeux possédés       répond    ← l'exception s'applique
le jeu en cours         répond    ← l'exception s'applique
vos succès              403       ← elle ne s'applique pas
```

Le profil a donc l'air ouvert depuis tous les angles sauf celui qui compte.
**« Tester la connexion » le dit explicitement** quand c'est le cas : c'est le
seul endroit où ce réglage se signale.

Un jeu sans succès n'est pas un jeu dont vous auriez zéro succès : une barre à
zéro toute la soirée serait un mensonge sur un jeu qui n'en propose pas. La
différence est faite, et c'est pour ça que le widget s'efface au lieu
d'afficher `0/0`.

## Ce qui n'y est pas, et ne peut pas y être

**Les messages non lus.** Steam ne publie aucun point d'entrée pour la
messagerie, les notifications ou un compteur de non-lus — ni dans `ISteamUser`,
ni dans `ISteamFriends`. Les seules voies seraient les interfaces internes du
client Steam ou un cookie de session récupéré à la main, et ni l'une ni
l'autre n'a sa place dans un connecteur qui doit encore marcher le mois
prochain.

## Ce que ça coûte à Steam

Deux appels au plus par rafraîchissement, et un seul pour le widget **En
jeu**. Le profil est relu toutes les 60 secondes, les succès toutes les 180 —
ils bougent moins souvent, mais ils bougent **pendant** une partie, et c'est le
seul moment où quelqu'un regarde ce widget.
