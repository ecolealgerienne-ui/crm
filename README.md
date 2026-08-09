# EchangoCrm

Instance Odoo 19 (CRM) de la suite echango, publiée sur
**https://echangocrm.echango.com**.

Ce dépôt ne contient que de l'infrastructure : deux fichiers Compose et un
petit addon d'amorçage. **Aucune image n'est construite** — l'image officielle
`odoo:19` est utilisée telle quelle, il n'y a pas de Dockerfile à maintenir et
pas d'étape `--build`.

## Démarrage

Une seule commande crée la base, installe le CRM et met le service en ligne.
Il n'y a aucune étape manuelle après.

```bash
# Production (VPS, /opt/echangocrm)
cp .env.production.example .env.production   # renseigner les 2 secrets
docker compose --env-file .env.production -f docker-compose.crm.yml up -d

# Développement local  →  http://localhost:8069  (admin / admin)
docker compose up -d
```

Le service `odoo-init` fait le travail au premier lancement puis s'arrête ;
« Exited (0) » est son résultat normal, pas une panne.

## Autonomie vis-à-vis des autres projets

La stack est indépendante des autres dépôts du VPS (`vendure`,
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
docker-compose.crm.yml           stack de PRODUCTION (VPS, /opt/echangocrm)
docker-compose.yml               stack de DÉVELOPPEMENT local
.env.production.example          modèle du fichier de secrets du VPS
addons/echangocrm_bootstrap/     applique le mot de passe admin à la création
docs/DEPLOIEMENT_VPS.md          procédure complète de déploiement
```

## Configuration

Tous les réglages Odoo sont des drapeaux de ligne de commande, dans la clé
`command:` des fichiers Compose — il n'y a délibérément **pas** d'`odoo.conf`
dans ce dépôt. Les secrets passent par `.env.production` (gitignoré) et par les
variables d'environnement du conteneur.

Le seul réglage d'Odoo qui ne peut vivre que dans un fichier de configuration
est `admin_passwd`, le mot de passe maître. Il n'est pas configuré ici, et
c'est sans conséquence : `--no-database-list` bloque toutes les opérations
qu'il protège, et un routeur Traefik rend `/web/database` inatteignable de
l'extérieur (§5 du document de déploiement).

## Points de vigilance

- **`ODOO_WORKERS >= 2`** — sinon le port gevent `8072` n'est pas servi et le
  websocket (chat, notifications, activités) tombe en panne silencieuse.
- **`ODOO_ADMIN_PASSWORD` n'est lu qu'une fois**, à la création de la base. Il
  se change ensuite dans l'interface, pas dans le fichier.
- **Sauvegardes : base *et* filestore.** Un dump SQL seul restaure un CRM aux
  pièces jointes cassées. Rien n'est automatisé à ce jour — cf. §7 du document
  de déploiement.
