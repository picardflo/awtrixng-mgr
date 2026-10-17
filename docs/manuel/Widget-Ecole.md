# Calendrier scolaire

Semaine A ou B, les jours restants, et un décompte qui change de saison.

Les dates viennent des **données ouvertes du Ministère**, pas de dates saisies
à la main : un calendrier tapé une fois est faux l'année suivante. Les jours
fériés, eux, sont calculés — le jeu de données ne les porte pas, et sans eux
« 3 jours restants » est faux le 11 novembre.

## La semaine

L'alternance A/B court **à travers** les vacances plutôt que de s'y
interrompre, ce qui est la règle de l'Éducation nationale. Certains
établissements comptent à l'envers ; une case inverse l'alternance.

La couleur dit la semaine : **cyan pour A, violet pour B**. Deux teintes
franchement différentes, parce qu'à huit pixels et à travers une pièce, deux
nuances voisines sont une seule couleur.

## Le décompte, et sa saison

```
J-{{ countdown }}
```

Un gabarit n'a pas de condition, alors `{{ countdown }}` choisit pour vous :

- **en période scolaire**, il compte jusqu'aux prochaines vacances ;
- **pendant les vacances**, jusqu'au matin de la rentrée.

C'est toujours le nombre qu'on veut voir. Les deux restent disponibles
séparément : `{{ days_to_holiday }}` et `{{ days_to_school }}`.

### L'icône annonce la période comptée

| période | icône | surimpression |
|---|---|---|
| Toussaint | un arbre qui se dépouille | — |
| Noël | le traîneau du père Noël qui traverse | **neige** |
| Hiver | un flocon | **neige** |
| Printemps | un cerisier en fleurs | — |
| Été | une plage | — |

La surimpression est dessinée par le firmware **par-dessus** le texte : il
neige sur votre compteur en décembre, et le chiffre reste lisible dessous.

**L'icône annonce ce qui vient, même en classe.** Le traîneau apparaît neuf
jours avant les vacances de Noël, parce que c'est l'arrivée qu'on décompte.

**La couleur, elle, ne suit la saison que pendant les vacances.** En période
scolaire elle dit la semaine A ou B, qui est la raison d'être de ce widget :
la repeindre aux couleurs de l'automne détruirait la seule information qu'on
lit d'un coup d'œil.

### Les variables

`{{ countdown }}` le bon décompte · `{{ days_to_holiday }}` ·
`{{ days_to_school }}` · `{{ week }}` la lettre · `{{ summary }}` une phrase
toute faite · `{{ days_left }}` jours de classe restants cette semaine ·
`{{ school_days }}` · `{{ holiday }}` · `{{ holiday_name }}` ·
`{{ season }}` la période comptée

## La barre des sept jours

À la place d'une barre de progression, le widget peut dessiner **un segment
par jour de la semaine** — la même forme que l'horloge dessine sous son app
Date. Une barre à 60 % ne dit pas *quels* jours restent ; sept segments si.
