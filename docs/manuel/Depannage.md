# Dépannage

Diagnostic approfondi. Pour une intervention immédiate, voir le
[Maintenance](Maintenance.md).

Chaque cas suit la même trame :

```text
Symptôme → Causes probables → Diagnostic → Correction → Validation
```

---

## L'interface répond « injoignable », mais tout a l'air sain

Symptôme : la page se charge, et **tout `/api/` répond 502**.

```
docker compose ps
  awtrixng-mgr-backend    Up About a minute   (healthy)
  awtrixng-mgr-frontend   Up About an hour    (healthy)
```

Les deux conteneurs sont sains, et le journal du backend montre
`GET /api/health 200`. Rien ne désigne la panne — sauf **les durées** : le
backend vient d'être recréé, le frontend non.

**Correction immédiate :**

```bash
docker compose restart awtrixng-mgr-frontend
```

**Cause** : jusqu'à la 0.15.1, le frontend résolvait l'adresse du backend une
seule fois, à son démarrage. Recréer le seul backend lui donnait une adresse
neuve sur le réseau Docker, et le frontend continuait d'écrire à l'ancienne.

Depuis la 0.15.1 l'adresse est résolue à chaque requête : la panne ne peut
plus se produire. Si vous la voyez encore, c'est que le frontend tourne sur
une image antérieure — `docker compose up -d --build` le reconstruira.

## L'interface ne répond pas

**Causes probables** — conteneur arrêté, backend malsain, Caddy, DNS.

**Diagnostic**

```bash
cd /chemin/vers/awtrixng-mgr
docker compose ps
docker compose logs --tail 50 awtrixng-mgr-backend
docker inspect --format '{{.State.Health.Status}}' awtrixng-mgr-backend
```

Le frontend attend que le backend soit `healthy`. Un frontend qui ne démarre
pas est donc presque toujours un **symptôme**, pas la cause.

Si les conteneurs vont bien, le problème est en amont :

```bash
docker network inspect home.docker | grep -A3 awtrixng-mgr
curl -k https://awtrixng-mgr.lan/api/health
```

awtrixng-mgr **ne publie aucun port sur l'hôte** : on y accède uniquement par
Caddy. Un `curl localhost:8000` depuis l'hôte échouera, et c'est normal.

**Correction** — `docker compose up -d`. Si le backend refuse de démarrer, la
cause est dans ses journaux, en une ligne lisible plutôt qu'une trace.

**Validation** — `curl -s https://awtrixng-mgr.lan/api/health` renvoie un
statut et une version.

---

## `unable to open database file`

**Cause** — les droits sur `./data`. Le conteneur tourne sous un utilisateur
non privilégié ; un volume créé par `root` lui est inaccessible.

**Diagnostic**

```bash
ls -ld /chemin/vers/awtrixng-mgr/data
docker compose logs awtrixng-mgr-backend | grep -i "database\|permission"
```

**Correction** — le point d'entrée du conteneur corrige les droits tout seul au
démarrage. S'il n'y arrive pas :

```bash
docker compose down
sudo chown -R 10001:10001 /chemin/vers/awtrixng-mgr/data
docker compose up -d
```

**Validation** — `/data/awtrixng.db` existe et le conteneur est `healthy`.

---

## Un afficheur reste en erreur

**Causes probables** — horloge éteinte, IP changée, authentification activée
sur le firmware, matrice sur un autre VLAN.

**Diagnostic** — depuis l'hôte Docker, pas depuis votre poste :

```bash
docker compose exec awtrixng-mgr-backend \
  python -c "import urllib.request;print(urllib.request.urlopen('http://IP_DE_L_HORLOGE/api/v1/device',timeout=4).read()[:200])"
```

Une réponse ici mais une erreur dans l'interface pointe vers les identifiants.
Aucune réponse : c'est le réseau.

**Correction** — corrigez l'hôte dans **Afficheurs → Modifier**. Si le firmware
demande une authentification, renseignez identifiant et mot de passe.

**Validation** — **Tester la connexion** affiche les capteurs.

---

## Un widget affiche une valeur figée

C'est **le comportement prévu** quand le service amont ne répond plus :
awtrixng-mgr garde la dernière valeur connue plutôt que d'éteindre l'app.

**Diagnostic** — le badge du widget dit la vérité, même quand la matrice
affiche encore l'ancienne valeur.

```bash
docker compose logs --since 30m awtrixng-mgr-backend | grep -i "widget\|collect"
```

**Correction** — **Rafraîchir** force une collecte. Pour la météo, rappelez-vous
que la réponse est **mise en cache 10 minutes** et partagée entre tous les
widgets du même lieu : deux rafraîchissements rapprochés renverront la même
chose.

**Validation** — le badge repasse **En ligne** et l'horodatage par afficheur
avance.

---

## Un widget n'apparaît jamais sur la matrice

**Causes probables** — widget désactivé, aucun afficheur coché, masqué faute de
données, ou l'app existe mais passe trop vite.

**Diagnostic** — dans l'interface, la ligne du widget indique `n / n
afficheurs`. `0 / 0` veut dire qu'il ne vise plus personne.

Puis regardez ce que l'horloge a vraiment :

```bash
curl -s http://IP_DE_L_HORLOGE/api/v1/apps
```

Vos widgets y apparaissent sous la forme `ah000001`, `ah000002`…

**Correction**

| Constat | Geste |
|---|---|
| `0 / 0 afficheurs` | Cochez une horloge dans **Modifier** |
| Absent de `/api/v1/apps` | Attendez 2 min (réconciliation) ou **Rafraîchir** |
| Présent mais invisible | L'option **Masquer en l'absence de données** est active et le service ne renvoie rien |

**Validation** — l'app est dans `/api/v1/apps` et défile sur la matrice.

---

## L'aperçu ne ressemble pas au résultat

**Causes probables** — presque aucune, désormais.

La police de l'aperçu a été **lue sur une horloge réelle**, caractère par
caractère, dans les deux tailles. L'aperçu et la matrice produisent les mêmes
pixels, vérifié sur huit cas.

Restent trois écarts légitimes :

| Ce que vous voyez | Pourquoi |
|---|---|
| La surimpression météo n'est pas dessinée | le firmware la dessine, l'aperçu ne la simule pas |
| Les effets ne bougent pas | idem |
| L'icône est la vraie, l'aperçu montre sa première image | un GIF animé commence souvent sur une image noire |

**Si le texte diffère vraiment**, c'est le gabarit qui est en cause, pas
l'aperçu : regardez les variables listées sous lui. Une variable mal
orthographiée rend une chaîne vide, en silence.


## L'ordre de la rotation ne change pas

**Cause** — l'AWTRIX garde chaque app **là où elle est apparue la première
fois**. Sa clé `pos` est inopérante en v0.98, c'est mesuré, pas supposé.

**Correction** — **Réorganiser** sur la page Afficheurs : awtrixng-mgr supprime
toutes les apps qu'il gère et les republie dans l'ordre voulu.

**Validation** — `curl -s http://IP_DE_L_HORLOGE/api/v1/apps` liste les `ng…` dans
l'ordre de l'interface.

> Pendant l'opération, la matrice ne montre que ses apps natives pendant
> quelques secondes. C'est inévitable, et c'est pourquoi le réordonnancement
> est une action explicite.

---

## L'interface propose quelque chose qui ne fait rien

**Deux images, deux versions possibles.** Le frontend et le backend se
construisent séparément : `docker compose build` peut en reconstruire un et
servir l'autre depuis son cache. L'interface affiche alors un réglage que le
moteur ne connaît pas, et il ne se passe rien — sans message, puisque de son
point de vue tout va bien.

C'est arrivé avec la langue des horloges : le sélecteur affichait « Français »
et la matrice continuait d'écrire `MODERATE`.

**Comment le vérifier.** `/api/health` est la seule route qui répond sans mot
de passe, et elle donne la version du **backend** :

```
curl -s http://votre-awtrixng-mgr/api/health
{"status":"ok","version":"0.11.1","clock_language":"fr"}
```

Comparez avec le numéro affiché en haut à droite de l'interface, qui vient du
**frontend**. S'ils diffèrent, une image est en retard.

**Comment le corriger.**

```
docker compose build --no-cache
docker compose up -d
```

> `clock_language` dans la même réponse dit ce que le backend croit, et non ce
> qu'un formulaire affiche d'une valeur tenue dans un autre processus. C'est la
> différence entre diagnostiquer et deviner.

## L'horloge est noire, et rien ne dit pourquoi

**Cause probable** — le panneau est coupé.

AWTRIX NG a un interrupteur de matrice qu'AWTRIX 3 n'avait pas, et **rien n'est
écrit au journal quand il s'actionne**. Une horloge trouvée noire ne laisse donc
aucune trace.

**Diagnostic** — le framebuffer continue d'être dessiné derrière des LED
éteintes, donc les pixels ne disent rien. Seul `power` répond :

```bash
curl -s http://IP_DE_L_HORLOGE/api/v1/display
{"power":false,"brightness":10,...}
```

La carte de l'afficheur l'affiche aussi, en rouge : **« Matrice éteinte »**.

**Correction**

```bash
curl -s -X PATCH http://IP_DE_L_HORLOGE/api/v1/display \
  -H 'Content-Type: application/json' -d '{"power":true}'
```

Ou maintenez le bouton du milieu à la mise sous tension, si elle ne répond plus
du tout.

**Validation** — `power` est à `true` et la matrice affiche.

> Un rappel rallume le panneau de lui-même avant de sonner : la clé `wakeup`
> des notifications est acceptée par le firmware et sans effet, mesuré.

---

## L'horloge répond 404 à tout

**Cause** — elle est restée en **AWTRIX 3**.

awtrixng-mgr parle `/api/v1/`, que le firmware 0.98 ne connaît pas.

**Diagnostic**

```bash
curl -s http://IP_DE_L_HORLOGE/api/v1/device     # 404 sur AWTRIX 3
curl -s http://IP_DE_L_HORLOGE/api/stats          # répond sur AWTRIX 3
```

**Correction** — flashez-la en AWTRIX NG, ou pilotez-la depuis
Le projet précédent, qui reste en service pour
ça.

> Elle ne risque rien en attendant : une requête `/api/v1/` sur un firmware
> 0.98 répond 404 sans rien modifier. C'est un garde-fou heureux, pas une
> garantie.

---

## Tout est à 401 après avoir mis un mot de passe

**Causes probables** — cookie `Secure` sans HTTPS, ou mot de passe qui ne
correspond pas.

**Diagnostic**

```bash
curl -s https://awtrixng-mgr.lan/api/auth/status
```

`{"required":true,"authenticated":false}` : le mot de passe est bien actif, la
session n'est pas établie.

**Correction** — en HTTP direct, sans TLS, le navigateur **jette** un cookie
marqué `Secure` et la connexion échoue sans message :

```bash
# dans .env
AWTRIXNG_SECURE_COOKIE=false
```

Derrière Caddy, laissez `true`.

**Validation** — après connexion, `/api/auth/status` renvoie
`"authenticated":true`.
