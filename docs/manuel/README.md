# awtrixng-mgr

Manuel d'utilisation et d'exploitation. L'installation est dans le
[README du dépôt](../../README.md) ; ce wiki commence
une fois qu'awtrixng-mgr tourne.

![Tableau de bord](../screenshots/dashboard.png)

## Par où commencer

| Page | Quand l'ouvrir |
|---|---|
| [Démarrage](Demarrage.md) | Première configuration, de zéro à un widget affiché |
| [Afficheurs](Afficheurs.md) | Ajouter une horloge, la régler, les heures calmes |
| [Widgets](Widgets.md) | Créer et régler ce que l'horloge affiche |
| [Widget Météo](Widget-Meteo.md) | Météo, pluie, humidité, soleil, air, UV |
| [Widget Carburants](Widget-Carburants.md) | Le prix le plus bas près de chez vous |
| [Rappels](Rappels.md) | Un message à une heure fixe, qui interrompt la rotation |
| [Ce que NG change](AWTRIX-NG.md) | Pour qui vient d'AWTRIX 3 |
| [Maintenance](Maintenance.md) | Mise à jour, sauvegarde, journaux |
| [Dépannage](Depannage.md) | Quand quelque chose ne marche pas |
| [Sécurité](Securite.md) | Mot de passe, `.env`, secrets exposés |

## Ce qu'il fait, en une phrase

Il interroge des services, met en forme le résultat pour une matrice 32×8, et
le pousse sur une ou plusieurs horloges **AWTRIX NG** — en boucle, sans que
vous ayez à y revenir.

## Ce qu'il ne fait pas

- Il ne remplace pas l'interface de l'horloge pour le Wi-Fi, le MQTT ou les
  scripts Berry. Il règle en revanche l'affichage, le son et la luminosité :
  voir [Afficheurs](Afficheurs.md).
- Il ne sait **pas** masquer les apps natives (Heure, Date, Température…).
  AWTRIX NG n'offre aucun moyen de le faire — mesuré, pas supposé. Voir
  [Ce que NG change](AWTRIX-NG.md).
- Il n'a **qu'un mot de passe**, pas de comptes utilisateurs. Voir
  [Sécurité](Securite.md).

## Il parle AWTRIX NG, et seulement lui

Les routes sont en `/api/v1/`, que le firmware AWTRIX 3 ne connaît pas. Une
horloge restée en 0.98 répondra donc 404 et sera signalée injoignable — elle ne
risque rien, mais elle ne marchera pas. Pour celles-là, l'ancêtre
Le projet précédent reste en service.
