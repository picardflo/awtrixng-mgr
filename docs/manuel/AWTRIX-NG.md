# Ce que NG change

Pour qui vient d'AWTRIX 3. Tout ce qui suit a été **mesuré sur une Ulanzi
TC001 en NG 1.1.2**, pas lu dans une documentation.

Le relevé complet est dans le dépôt :
[`docs/ng-vs-awtrix3.md`](../../docs/ng-vs-awtrix3.md).

## Ce qui disparaît de l'interface

| | pourquoi |
|---|---|
| **Apps natives** | NG n'offre aucun moyen de les désactiver. `DELETE /api/v1/apps/Battery` répond `{"ok":true}` et ne change rien, et aucun des 42 réglages ne les gouverne. |
| **Texte centré** | NG n'a aucune clé de centrage — et n'en a pas besoin : il centre seul tout texte qui tient. |
| **Texte arc-en-ciel** | `palette` colore les *effets*, pas le texte. Vérifié à l'écran. |
| **Mode chambre** | Scindé. Voir plus bas. |
| **Pollen, Afficheur** | Retirés pour d'autres raisons — voir [Widget Météo](Widget-Meteo.md). |

## Ce qui apparaît

**La surimpression météo.** Le firmware dessine la pluie, la neige ou l'orage
par-dessus l'app. Six, et l'horloge déclare lesquelles elle sait faire.

**La grande police.** Sept rangées au lieu de cinq, et sans coûter une seule
colonne de plus. AWTRIX 3 avait une police et aucun mot à dire.

**L'interrupteur de matrice.** Le panneau s'éteint et se rallume sans
redémarrage. AWTRIX 3 n'avait qu'une veille minutée.

**Les accents.** NG les dessine tous — `àâéèêëîïôùûç`, les majuscules, `œæ`,
`°€µ`. AWTRIX 3 imprimait un point d'interrogation, et ce projet retirait donc
les accents avant d'envoyer. Plus maintenant.

**La barre des jours.** Sept segments, un par jour — la même que l'horloge
dessine sous ses apps Heure et Date, aux mêmes colonnes.

## Le mode chambre, scindé

Sur AWTRIX 3, la luminosité automatique **planchait à 2** sans qu'on puisse
changer ce plancher — trop clair pour une chambre. D'où un mécanisme entier :
couper le capteur au crépuscule, forcer un niveau plus bas, mémoriser ce qu'on
avait écrasé, le remettre à l'aube.

NG fait de ce plancher **un réglage**. Un réglage remplace l'horaire, l'état
sauvegardé et la restauration — et il lit la pièce plutôt que l'heure, donc il
baisse quand vous vous couchez vraiment.

Ce qui reste s'appelle **[Heures calmes](Afficheurs.md)** : la moitié qu'un
capteur de lumière ne peut pas faire, puisque le silence est une affaire
d'heure.

## Deux pièges à connaître

**Panneau éteint, le framebuffer continue d'être dessiné.** Un aperçu bâti sur
les pixels montrerait l'heure sur une horloge noire. La carte d'un afficheur
dit « Matrice éteinte » parce qu'elle lit `power`, pas les pixels.

**La validation du firmware n'est pas uniforme.** Il refuse `textCase`,
`iconMode`, `effect`, `overlay` et toute clé inconnue, en les nommant. Il
accepte en revanche `{"progress": 500}` sans broncher. Les bornes du
constructeur de widgets sont donc les nôtres, pas les siennes.

## Et les horloges restées en 0.98 ?

awtrixng-mgr parle `/api/v1/`, que le firmware 0.98 ne connaît pas : il
répondra 404 et l'horloge sera signalée injoignable. Elle ne risque rien, mais
elle ne marchera pas.

Pour celles-là, le projet précédent reste en
service, figé en 0.20.0 parce que son firmware l'est.
