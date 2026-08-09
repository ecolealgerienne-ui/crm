# EchangoCrm

Instance Odoo 19 (CRM) de la suite echango, publiée sur
**https://echangocrm.echango.com**.

Ce dépôt ne contient que de l'infrastructure : les deux fichiers Compose,
l'image Odoo et ses addons custom. Aucun code applicatif Odoo n'est modifié —
on part de l'image officielle.

## Autonomie vis-à-vis des autres projets

La stack est volontairement indépendante des autres dépôts du VPS (`vendure`,
`echangopromo`). Elle ne partage avec eux que :

- le réseau Docker externe `echango_network` ;
- le conteneur Traefik qui y est attaché, et son certificat wildcard
  `*.echango.com`.

Pas de base commune, pas d'image commune, pas de code commun, et **aucun
middleware Traefik emprunté** — ils sont redéfinis en labels dans
`docker-compose.crm.yml`. Déployer ce CRM ne demande de modifier aucun autre
dépôt.

## Arborescence

```
docker-compose.crm.yml   stack de PRODUCTION (VPS, /opt/echangocrm)
docker-compose.yml       stack de DÉVELOPPEMENT local
.env.production.example  modèle du fichier de secrets du VPS
docker/odoo/             image Odoo (Dockerfile, entrypoint, odoo.conf.template)
addons/                  addons Odoo custom, montés en /mnt/extra-addons
docs/DEPLOIEMENT_VPS.md  procédure complète de déploiement
```

## Développement local

```bash
docker compose up -d --build

# Créer la base (une seule fois) — Odoo ne la crée pas seul, list_db = False
docker compose run --rm odoo \
  odoo -d echango_crm -i base,crm,contacts,calendar --stop-after-init
```

→ http://localhost:8069 — identifiants `admin` / `admin` (valeurs de
développement, sans valeur ailleurs).

## Production

Voir **[docs/DEPLOIEMENT_VPS.md](docs/DEPLOIEMENT_VPS.md)**. En résumé :

```bash
cd /opt/echangocrm
cp .env.production.example .env.production   # puis renseigner les secrets
docker compose --env-file .env.production -f docker-compose.crm.yml up -d --build
```

Le `--env-file` n'est pas optionnel : le même fichier alimente la substitution
`${...}` du fichier Compose **et** l'environnement du conteneur Odoo.

## Points de vigilance

- **`ODOO_WORKERS >= 2`** — sinon le port gevent `8072` n'est pas servi et le
  websocket (chat, notifications, activités) tombe en panne silencieuse.
- **`POSTGRES_PASSWORD` alphanumérique uniquement** — l'entrypoint Odoo amont
  relit la valeur avec `cut -d " " -f3`.
- **Sauvegardes : base *et* filestore.** Un dump SQL seul restaure un CRM aux
  pièces jointes cassées. Rien n'est automatisé à ce jour — cf. §7 du document
  de déploiement.
