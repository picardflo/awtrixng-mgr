# secrets.example.md

Modèle de `secrets.md` (fichier **local uniquement**, exclu de git via `.gitignore`).

Copier ce fichier en `secrets.md` puis renseigner les vraies valeurs :

```bash
cp secrets.example.md secrets.md && chmod 600 secrets.md
```

> Ces identifiants servent **uniquement aux tests manuels contre le lab**.
> La configuration réelle d'awtrixhub se fait via l'interface web et est
> stockée en base, jamais dans un fichier du dépôt.

---

## Zabbix

```text
URL         : https://zabbix.example.lan
Name        : <nom du connecteur>
User        : <utilisateur API>
Auth token  : <token API Zabbix>
Right       : ReadOnly
```

## Tautulli

```text
URL     : http://tautulli.example.lan:8181
API Key : <clé API Tautulli>
```
