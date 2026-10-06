# Widgets

Un widget, c'est un service + un gabarit de texte + des options d'affichage.

![Liste des widgets](../screenshots/widgets-liste.png)

## Le gabarit

Le champ texte accepte `{{ variable }}`. Les variables disponibles sont
listées sous l'aperçu, et dépendent du widget choisi.

Des filtres existent : `{{ temp | round }}`, `{{ uv | int }}`,
`{{ nom | upper }}`, `{{ texte | truncate(8) }}`, `{{ x | default(0) }}`,
`{{ secondes | duration }}`.

**Il n'y a ni condition ni comparaison.** Pas de `if`, pas de `==`. Un
gabarit affiche, il ne décide pas. Ce qui dépend de la valeur — la couleur,
l'icône — est décidé par le service, et vous pouvez l'imposer si son choix ne
vous convient pas.

## La place, qui est la vraie contrainte

Trente-deux colonnes, et **une icône en prend neuf**. L'aperçu vous dit si le
texte tiendra, et il ne ment pas : la police a été lue sur une vraie horloge.

| | tient | défile |
|---|---|---|
| avec icône | environ 5 caractères | au-delà |
| sans icône | environ 8 caractères | au-delà |

Un texte qui défile n'est pas une faute — c'est lisible, mais il faut attendre.
Pour une valeur qu'on consulte d'un coup d'œil en partant, c'est un vrai coût.

## Les options d'affichage

**Icône.** Vide = celle que le service propose, qui suit souvent la donnée (le
ciel qu'il fait, la phase de la lune). Un identifiant LaMetric l'impose. Elle
s'installe toute seule sur l'horloge au premier affichage.

**Couleur.** Vide = celle que le service propose, qui dépend souvent de la
valeur : la température, la qualité de l'air, l'âge d'un prix de carburant.

**Police.** `Normale` tient sur cinq rangées et se centre ; `Grande` en
occupe sept — exactement celles du dessus de la barre. **La grande va donc de
pair avec une barre**, et paraît une rangée trop haute sans.

Les deux ont la **même largeur de caractère**, mais la grande n'accepte pas
plus de texte pour autant : à côté d'une icône, il reste vingt-quatre colonnes,
et au-delà le texte défile. Quand un gabarit comporte un mot — `AIR 41` — la
normale est parfois le bon choix malgré la barre : le texte reste sur les
rangées 1 à 5, la rangée 6 reste vide, et rien ne défile.

**Défilement.** Ce que fait un texte trop long : enchaîné, aller-retour, fixe
(texte coupé), en boucle. Et « quand le texte tient » : immobile, ou défile
quand même.

**Surimpression météo.** Pluie, neige, bruine, orage, tonnerre, givre, dessinés
par le firmware **par-dessus** le texte. Propre à AWTRIX NG. Vide = au choix du
service, ce qui veut dire que la météo la met toute seule quand il pleut
vraiment.

**Barre de progression.** Grisée quand le service n'a pas de proportion à
montrer.

**Barre des jours.** Sept segments, un par jour de la semaine — la même barre
que l'horloge dessine sous ses apps Heure et Date, aux mêmes colonnes. Elle
remplace la barre de progression : les deux partagent la rangée du bas.

**Masquer si vide.** Un service peut n'avoir rien à dire. Coché, le widget
disparaît de la rotation plutôt que de laisser une valeur périmée.

## L'ordre de la rotation

Les flèches à gauche de chaque widget. L'ordre n'est appliqué qu'au moment où
vous cliquez **Appliquer l'ordre** : l'horloge garde une app là où elle est
arrivée, donc les réordonner veut dire toutes les retirer et les republier. La
matrice ne montre que ses apps natives pendant quelques secondes.

## Dupliquer

Pratique pour un même widget sur deux horloges avec des réglages différents,
ou pour deux carburants. Le nom reçoit « (copie) ».
