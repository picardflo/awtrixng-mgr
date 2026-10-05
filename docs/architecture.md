# Architecture et décisions

Ce document ne décrit pas le code — le code se lit. Il garde **pourquoi** il est
comme il est, parce que c'est la seule chose qu'on ne peut pas retrouver en le
relisant six mois plus tard.

Chaque décision porte sa raison et, quand il y en a eu une, la panne qui l'a
provoquée.

---

## État

Le dépôt en est au socle : `app/core/` et `app/services/ng/`. Les ADR ci-dessous
sont celles que ce code tranche. Les suivantes viendront avec le modèle de
données, le planificateur et l'interface.

L'ancêtre, **awtrixhub**, porte 23 ADR dans son propre `docs/architecture.md`.
La plupart tiennent et seront reprises telles quelles le jour où le code
correspondant arrivera. Celles que l'arrivée de NG oblige à rejuger sont listées
en fin de page.

---

## ADR-001 — Les noms d'apps gardent leur largeur fixe, pour une autre raison

**Décision.** Une app poussée s'appelle `ng000123` : un préfixe et six chiffres.

**Ce qui a changé.** awtrixhub faisait de même (`ah000123`) pour une raison
précise : **AWTRIX 3 supprimait par préfixe**, donc supprimer `ah1` emportait
`ah12`. La largeur fixe garantissait qu'aucun nom ne puisse être le préfixe d'un
autre.

Mesuré sur NG 1.1.2, ce danger n'existe plus. En poussant `zz1`, `zz12` et
`zz1x` puis en supprimant `zz1`, les deux autres sont restées.

**Pourquoi on garde quand même la largeur fixe.** Elle sert maintenant à autre
chose : parmi les apps dont `origin` vaut `pushed`, c'est elle qui distingue les
nôtres de celles qu'un script Berry ou un autre outil a posées. `is_managed()`
reste une question à réponse nette.

**La conséquence à retenir :** la raison écrite dans awtrixhub est périmée. Qui
lit ce nommage et croit protéger une suppression par préfixe se trompe sur ce
que fait le firmware.

Vérifié par `test_deleting_one_app_leaves_a_longer_name_alone`, qui tourne sur
matériel : le jour où le firmware reviendrait en arrière, c'est un test qui le
dit, pas une horloge qui perd ses widgets.

## ADR-002 — Un 422 est une réponse, pas une panne

**Décision.** `DeviceRejectedError`, distincte de `DeviceUnreachableError`, et
qui porte le **nom du champ** refusé.

**Pourquoi.** C'est le gain ergonomique principal de la migration. AWTRIX 3
ignorait en silence ce qu'il ne comprenait pas : une faute de frappe dans une
clé produisait un afficheur discrètement faux, sans rien dire, et il fallait
comparer au pixel pour s'en apercevoir. NG répond :

```
422 {"error":{"code":"validationFailed",
              "message":"unknown key \"color\"",
              "field":"color"}}
```

Aplatir ça en « l'afficheur ne répond pas » jetterait la seule chose vraiment
utile, et enverrait celui qui lit le journal chercher du côté du réseau alors
que la requête est arrivée et a été comprise.

**Corollaire :** un 422 dont le corps n'a pas la forme attendue reste un refus.
La requête est arrivée ; c'est ce qui compte pour qui diagnostique.

## ADR-003 — Les capacités se lisent, elles ne se codent pas

**Décision.** Effets, transitions, palettes, overlays et présence d'un buzzer
viennent de `GET /api/v1/capabilities`. Rien de tout cela n'est écrit en dur.

**Pourquoi.** awtrixhub n'avait pas le choix : AWTRIX 3 donnait `/api/effects`
et `/api/transitions`, mais rien sur l'audio ni sur les overlays, qui se
devinaient donc. Résultat : une liste codée en dur dans l'application, qui
ment dès que le firmware évolue — dans un sens comme dans l'autre.

Ici l'appareil déclare ses 19 effets, 22 transitions, 8 palettes, 6 overlays et
`{"buzzer": true, "mp3": false, …}`. Une horloge qui gagne un effet par mise à
jour l'offre **sans release de ce projet**.

**Conséquence :** une liste d'effets codée en dur, ici, est un défaut à corriger,
pas un raccourci.

## ADR-004 — Les bornes du payload sont les nôtres

**Décision.** `progress` est borné 0–100, `repeat` et les durées sont positifs,
`barChart` et `lineChart` sont typés en listes — côté application.

**Pourquoi.** On pourrait croire, vu la rigueur du reste, que le firmware
vérifie tout. Il ne le fait pas, et c'est le relevé le plus contre-intuitif de
la session :

```
{"progress": 500}        → {"ok": true}
{"repeat": -5}           → {"ok": true}
{"barChart": "zz"}       → {"ok": true}
{"lineChart": {"zz": 1}} → {"ok": true}
```

Là où `textCase`, `iconMode`, `effect`, `overlay`, `palette`, `scroll.*` et
`draw` sont refusés nommément.

**Conséquence :** retirer ces bornes en se disant « l'appareil validera »
laisserait une valeur aberrante atteindre la matrice. Le détail est dans
[`ng-api/payload-keys.md`](ng-api/payload-keys.md).

## ADR-005 — Les tests qui écrivent refusent les afficheurs en service

**Décision.** `backend/tests/test_device.py` exige un hôte explicite par
`AWTRIXNG_TEST_HOST`, et **échoue** — sans faire la moindre requête — si cet
hôte figure dans `FORBIDDEN_HOSTS`.

**Pourquoi.** Sur le projet précédent, une seconde instance pointée sur une
horloge en service a **supprimé ses apps, deux fois**. La seconde fois est
survenue *après* que le risque eut été consigné dans un ADR.

C'est la leçon : **une note écrite n'a pas suffi.** La règle est donc dans le
code, où elle s'exécute.

**Ce sur quoi il ne faut pas compter.** Ces tests parlent `/api/v1/`, qu'un
firmware 0.98 ne connaît pas : une requête égarée y répondrait 404 plutôt que
d'y faire des dégâts. C'est un garde-fou heureux, pas une permission — il
disparaît sans prévenir le jour où l'horloge en question passe en NG.

---

## Les ADR d'awtrixhub à rejuger

NG retire l'argument qui fondait celles-ci. Elles seront tranchées quand le code
correspondant arrivera, pas avant — les inscrire ici évite de les reprendre par
inertie.

| ADR d'awtrixhub | Pourquoi la rejuger |
|---|---|
| **ADR-004** — nommage des apps sur largeur fixe | **Tranchée**, voir ADR-001 : la raison a changé, la décision tient. |
| **ADR-022** — la plage horaire du mode chambre vit dans l'application | Elle y était placée *parce que le firmware n'en avait pas*. À revoir au regard de ce que NG sait faire seul. |
| **ADR-007** — installation automatique des icônes | Le mécanisme survit presque tel quel, mais `files` donne désormais l'espace restant : l'échec « plus de place » devient prévisible au lieu d'être subi. |
| ADR sur les dégradés de température interpolés à la main | `palette` accepte des arrêts de couleur : le dégradé pourrait devenir déclaratif. |
| ADR sur les listes d'effets et de transitions | **Tranchée**, voir ADR-003. |

Deux apports de NG n'ont pas d'équivalent à rejuger, mais ouvrent des
possibilités qu'awtrixhub ne pouvait pas offrir : les **overlays météo** dessinés
par le firmware par-dessus le texte, et les **scripts Berry** embarqués sur
l'appareil.
