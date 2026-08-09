# Déploiement d'EchangoCrm sur le VPS

Procédure pour faire tourner Odoo 19 dans `/opt/echangocrm`, derrière le
Traefik déjà en place pour `echango.com`. Pas d'automatisation GitHub côté
déploiement : `git pull` manuel sur le VPS, ce document reste la référence des
commandes.

Adresse publique : **https://echangocrm.echango.com**

---

## 1. Prérequis

### Le réseau Docker partagé

```bash
docker network inspect echango_network
```

S'il n'existe pas, c'est que la stack principale (Traefik / Vendure) n'a jamais
démarré. La lancer d'abord : ce dépôt déclare `echango_network` comme réseau
**externe**, Compose refuse de le créer lui-même et échoue au `up`.

### Le DNS et le certificat

`*.echango.com` existe déjà chez OVH, et le Traefik de la stack principale
détient un certificat wildcard `*.echango.com` (résolveur `letsencrypt`, DNS
challenge OVH). `echangocrm.echango.com` étant un label unique, il est
**couvert par ce certificat sans aucune action** — ni enregistrement DNS
supplémentaire, ni configuration ACME.

Vérifier quand même que la résolution atteint bien le VPS :

```bash
dig +short echangocrm.echango.com
```

### Ce qu'il n'y a PAS à faire

Aucune modification dans le dépôt `vendure`. Son routeur catch-all
`storefront-vendor` capture `*.echango.com` à la priorité 5 ; les routeurs de
ce dépôt sont à 20 et 25, ils passent donc devant. L'exclusion explicite
`!Host(...)` ajoutée jadis pour `promo.echango.com` n'est pas nécessaire ici.

---

## 2. Premier déploiement

```bash
sudo mkdir -p /opt/echangocrm
cd /opt/echangocrm
git clone https://github.com/ecolealgerienne-ui/crm.git .

cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Trois valeurs à renseigner impérativement — les autres ont un défaut correct :

| Variable | Comment la produire |
|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` — **alphanumérique uniquement**, voir l'avertissement dans le fichier |
| `ODOO_ADMIN_PASSWD` | `openssl rand -hex 24` — mot de passe **maître** (création/suppression de bases), à ranger dans le gestionnaire de mots de passe |
| `BASE_DOMAIN` | `echango.com` |

Puis construire et démarrer Postgres seul, la base applicative n'existant pas
encore :

```bash
docker compose --env-file .env.production -f docker-compose.crm.yml build
docker compose --env-file .env.production -f docker-compose.crm.yml up -d postgres_crm
```

---

## 3. Créer la base et installer le CRM

Odoo ne crée **pas** la base tout seul : `list_db = False` ferme le
gestionnaire de bases web, ce qui est voulu. La création se fait en ligne de
commande, une seule fois.

```bash
cd /opt/echangocrm
docker compose --env-file .env.production -f docker-compose.crm.yml run --rm odoo \
  odoo -d echango_crm -i base,crm,contacts,calendar --stop-after-init
```

`-i` crée la base si elle n'existe pas, puis installe les modules. Compter
quelques minutes. Aucune donnée de démonstration n'est chargée
(`without_demo = all` dans la configuration).

### Changer le mot de passe `admin` — AVANT d'exposer le service

⚠️ **Odoo crée l'utilisateur `admin` avec le mot de passe `admin`.** Tant que
ce n'est pas corrigé, quiconque atteint l'URL est administrateur du CRM. Le
faire **maintenant**, pendant que rien n'est encore routé par Traefik :

```bash
read -rsp 'Nouveau mot de passe admin : ' MDP; echo

docker compose --env-file .env.production -f docker-compose.crm.yml \
  run --rm -T -e NOUVEAU_MDP="$MDP" odoo \
  odoo shell -d echango_crm --no-http <<'PY'
import os
env.ref('base.user_admin').write({'password': os.environ['NOUVEAU_MDP']})
env.cr.commit()
PY

unset MDP
```

`read -rsp` évite que le mot de passe atterrisse dans l'historique du shell, et
il transite par une variable d'environnement plutôt que par le corps du script
Python, pour qu'aucune apostrophe ou guillemet ne puisse casser la commande.
`env.cr.commit()` est indispensable : `odoo shell` ne valide pas la
transaction en sortant.

### Démarrer

```bash
docker compose --env-file .env.production -f docker-compose.crm.yml up -d
docker compose --env-file .env.production -f docker-compose.crm.yml logs -f odoo
```

Le CRM répond alors sur https://echangocrm.echango.com.

---

## 4. Redéploiement (mise à jour du dépôt)

```bash
cd /opt/echangocrm
git pull origin main
docker compose --env-file .env.production -f docker-compose.crm.yml up -d --build odoo
```

Si le `git pull` a apporté des addons dans `addons/`, il faut en plus les faire
prendre en compte par la base :

```bash
docker compose --env-file .env.production -f docker-compose.crm.yml \
  exec odoo odoo -d echango_crm -u nom_du_module --stop-after-init
```

ou, dans l'interface : *Applications > Mettre à jour la liste des
applications*.

---

## 5. Routage Traefik — ce qui est en place

Tout est déclaré en labels dans `docker-compose.crm.yml`. Les points qui ne se
devinent pas :

**Deux routeurs, deux ports.** Odoo écoute sur `8069` (HTTP) et `8072`
(gevent : websocket, donc chat, notifications, activités du CRM). Le routeur
`echangocrm-ws` capte `PathPrefix(/websocket)` vers `8072` à la priorité 25,
devant le routeur principal (priorité 20) dont la règle `Host(...)` couvre
aussi ce chemin.

**`workers >= 2` est une dépendance de ce routage.** Avec `workers = 0` Odoo
passe en mode threadé et **rien n'écoute sur 8072** : le routeur websocket
répond 502 et le temps réel tombe en panne, sans que le reste du CRM ait l'air
cassé.

**Middlewares définis localement, pas empruntés.** Ce dépôt ne référence aucun
middleware `@file` de la stack Vendure — d'abord pour rester autonome, ensuite
parce que leur `security-headers@file` impose `X-Frame-Options: DENY`, ce qui
casserait l'éditeur de site et les vues incorporées d'Odoo. Le middleware local
`echangocrm-headers` pose `SAMEORIGIN`, plus HSTS et
`X-Robots-Tag: noindex` (un CRM interne n'a rien à faire dans un index).

**`traefik.docker.network=echango_network` est obligatoire ici.** Le conteneur
`odoo` est sur deux réseaux ; sans cette ligne, Traefik peut retenir son IP sur
le réseau `internal`, qu'il n'atteint pas — le routeur apparaît alors dans le
tableau de bord mais répond 502.

**Postgres n'est sur aucun réseau partagé.** Il vit sur le réseau `internal` de
cette stack, sans port publié.

---

## 6. Le piège du nom `postgres` — à connaître avant de déboguer

Le service Postgres s'appelle `postgres_crm`, et pas `postgres`. Ce n'est pas
cosmétique.

La stack Vendure a **elle aussi** un service nommé `postgres`, attaché au même
réseau externe `echango_network`. Un conteneur attaché aux deux réseaux résout
le nom générique `postgres` vers **leur** conteneur. C'est arrivé au premier
déploiement d'echango Promo : le backend recevait
`password authentication failed for user "..."` alors que le mot de passe était
rigoureusement identique des deux côtés — il parlait simplement à la mauvaise
base.

Devant tout symptôme d'authentification Postgres inexpliqué sur ce VPS,
vérifier d'abord vers quoi le nom se résout :

```bash
docker compose --env-file .env.production -f docker-compose.crm.yml \
  exec odoo getent hosts postgres_crm
```

L'IP doit être celle du conteneur `echangocrm-postgres_crm-1`.

---

## 7. Sauvegardes

> ⚠️ **Rien n'est automatisé à ce jour.** Le script de sauvegarde chiffrée du
> dépôt `echangopromo` (`scripts/backup-db.sh`, dumps GPG vers S3 OVH,
> vérification par restauration réelle, rétention 7 quotidiennes + 8
> hebdomadaires) **n'a pas été porté ici**. Tant que ce n'est pas fait, il n'y
> a **aucune sauvegarde de ce CRM**.

**Deux choses sont à sauvegarder, pas une.** Une sauvegarde SQL seule restaure
un CRM dont toutes les pièces jointes sont cassées :

| Quoi | Où | Contenu |
|---|---|---|
| La base | Postgres `echango_crm` | enregistrements, configuration, utilisateurs |
| Le filestore | volume `echangocrm_odoo_data` (`/var/lib/odoo`) | pièces jointes, images, documents, sessions |

Procédure manuelle, en attendant :

```bash
cd /opt/echangocrm
horodatage=$(date +%Y%m%d-%H%M%S)

# Base
docker compose --env-file .env.production -f docker-compose.crm.yml \
  exec -T postgres_crm pg_dump -U odoo -Fc echango_crm \
  > /var/backups/echangocrm/echango_crm-$horodatage.dump

# Filestore
docker run --rm \
  -v echangocrm_odoo_data:/data:ro \
  -v /var/backups/echangocrm:/sortie \
  alpine tar czf /sortie/filestore-$horodatage.tar.gz -C /data .
```

Les deux doivent être pris **au même moment** : un filestore plus récent que la
base laisse des fichiers orphelins, l'inverse laisse des pièces jointes
manquantes.

### Restaurer

Restaurer **à côté** d'abord, jamais par-dessus la base vivante — une
restauration par-dessus détruit l'état actuel, y compris ce qu'on aurait voulu
garder :

```bash
docker compose --env-file .env.production -f docker-compose.crm.yml \
  exec postgres_crm createdb -U odoo echango_crm_restaure
docker compose --env-file .env.production -f docker-compose.crm.yml \
  exec -T postgres_crm pg_restore -U odoo -d echango_crm_restaure --no-owner \
  < /var/backups/echangocrm/echango_crm-<horodatage>.dump
```

---

## 8. Montée de version d'Odoo

`ODOO_IMAGE_TAG` dans `.env.production` fixe la version majeure.

⚠️ **Changer ce numéro ne suffit pas et n'est pas réversible.** Une majeure
d'Odoo migre le schéma de la base ; l'édition Community ne fournit pas les
scripts de migration (c'est un service payant d'Odoo SA, ou OpenUpgrade). Une
montée de version se prépare sur une **copie** de la base, jamais en place, et
commence par une sauvegarde vérifiée des deux éléments de la section 7.

Les mises à jour de correctifs à l'intérieur d'une majeure (`odoo:19` suit la
branche 19) s'appliquent, elles, par un simple :

```bash
docker compose --env-file .env.production -f docker-compose.crm.yml build --pull odoo
docker compose --env-file .env.production -f docker-compose.crm.yml up -d odoo
```

---

## 9. Différence avec `docker-compose.yml` (développement local)

`docker-compose.yml` à la racine ne sert qu'au poste de développement : ports
`8069`, `8072` et `5434` publiés sur l'hôte, secrets en clair et sans valeur,
pas de Traefik ni de réseau externe. Les deux stacks partagent la **même
image** (`docker/odoo/`), donc le même Odoo et la même configuration rendue.
Leurs noms de projet Compose sont distincts (`echangocrm` / `echangocrm-dev`)
pour qu'elles ne puissent jamais partager un volume Postgres.
