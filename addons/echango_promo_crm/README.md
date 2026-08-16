# echango Promo — suivi des commerçants

Reçoit chaque nuit l'instantané des commerçants d'echango Promo et le rend
exploitable par l'équipe commerciale.

> ⚠️ **Le contrat d'échange n'est pas ici.** Il vit dans l'autre dépôt —
> `docs/SPEC_INTEGRATION_ECHANGOCRM.md` d'`echangopromo` — en un seul
> exemplaire. Ne pas le recopier : deux copies d'un contrat divergent au premier
> changement.

---

## ⚠️ Le piège du développement : mettre à jour ne suffit pas

**Un `--update` lancé dans un `docker exec` ne recharge PAS le serveur qui sert
le navigateur.** Ce sont deux processus : le second garde en mémoire le registre
d'avant, donc ses modèles d'avant.

Le symptôme est trompeur — le navigateur affiche une erreur Owl :

```
OwlError: An error occured in the owl lifecycle
Caused by: Error: "echango.promo.suivi"."wilaya" field is undefined.
```

… alors que le champ **existe** en base et dans le code. Vérifié le
2026-08-15 : la vue SQL portait bien ses 17 colonnes, `wilaya` comprise, et
l'écran plantait quand même. *(Le modèle `echango.promo.suivi` a été supprimé
depuis, le 2026-08-16 ; le piège, lui, n'a pas bougé d'un pouce.)*

**Toujours enchaîner les deux :**

```bash
CONT=echangocrm-dev-odoo-1
MDP=$(docker exec "$CONT" printenv PASSWORD)

docker exec "$CONT" odoo --database=echango_crm --db_host=postgres_crm \
  --db_user=odoo --db_password="$MDP" --update=echango_promo_crm \
  --http-port=8079 --gevent-port=8082 --stop-after-init --log-level=warn

docker restart "$CONT"
```

⚠️ **`--http-port=8079`** : sans lui, le processus de mise à jour se heurte au
serveur en cours sur 8069 et sort en `Address already in use` — un message qui
ne parle ni de module ni de mise à jour.

⚠️ **`docker exec -i`** pour `odoo shell` : sans le `-i`, stdin n'est pas
transmis, le script ne s'exécute pas et la commande sort **sans rien dire**.

## Vérifier qu'un écran se charge, sans ouvrir le navigateur

`get_views` est exactement ce que le client web appelle : il lève sur un champ
inconnu, une vue mal formée ou un groupe manquant.

```python
action = env.ref('echango_promo_crm.action_echango_promo_suivi')
env['res.partner'].get_views(action.views)
```

⚠️ **Passer `action.views` et non une liste écrite à la main** : c'est la
résolution de l'action qui a été fausse le 2026-08-16 — les vues existaient et
se chargeaient, mais l'action en ouvrait d'autres. Un `get_views` sur des vues
qu'on a choisies soi-même n'aurait rien vu.

## Les tests

```bash
docker exec "$CONT" odoo --database=echango_crm --db_host=postgres_crm \
  --db_user=odoo --db_password="$MDP" --update=echango_promo_crm \
  --http-port=8079 --gevent-port=8082 \
  --test-enable --test-tags=/echango_promo_crm --stop-after-init --log-level=test
```

⚠️ Une suite ajoutée dans `tests/` **et non importée dans `tests/__init__.py`**
ne s'exécute jamais et ne produit aucune erreur.

⚠️ **Ne pas lancer cette commande depuis Git Bash sous Windows.** Sa conversion
automatique des chemins transforme `--test-tags=/echango_promo_crm` en
`--test-tags=C:/Program Files/Git/echango_promo_crm`. Odoo répond alors :

```
ERROR   odoo.tests.tag_selector: Invalid tag C:/Program Files/Git/echango_promo_crm
WARNING odoo.tests.result: 0 failed, 0 error(s) of 0 tests
```

**« 0 failed » se lit comme un succès** alors qu'aucun test n'a tourné. Lancer
depuis WSL, ou préfixer par `MSYS_NO_PATHCONV=1`. Le seul contrôle qui ne trompe
pas : **le nombre de tests exécutés**, qui doit être non nul.

## Le journal des lots — à quoi il sert, et sa rétention

Il répond à **une seule question**, celle qu'on se pose quand un chiffre
paraît faux : *« qu'est-ce qui est arrivé cette nuit, et qu'est-ce qui a été
refusé ? »*

⚠️ **Un refus qui ne laisse pas de trace est invisible en production.** Un
export silencieusement rejeté ressemble trait pour trait à un export qui n'est
jamais parti. C'est le pendant de la source « silencieuse » : celle-ci dit que
rien n'arrive, celui-là dit ce qui est arrivé.

**Une ligne par LOT, pas par page** (2026-08-15). Une ligne par page rendait le
journal illisible à mesure que le parc grandit : 280 commerçants font 3 pages,
10 000 en font 50 — soit 51 lignes par nuit, près de 19 000 par an. Les pages
sont cumulées ; ce qui garde sa ligne propre, ce sont les **refus**, qui portent
leur message.

En régime normal : **deux lignes par nuit** — le lot et son acquittement.

⚠️ **La purge ne tourne que si `ECHANGO_PROMO_RETENTION_DAYS` est renseignée.**
Son repli est `0`, c'est-à-dire **conservation indéfinie** : un fichier
d'environnement mal renseigné ne doit pas faire disparaître des données. La
tâche le journalise à chaque passage — « aucune retention configuree, rien a
purger » — pour que l'absence de politique ne soit pas indiscernable d'une
purge qui n'a rien trouvé.

## Ce que ce module ne fait pas

- **Il n'écrit jamais vers echango Promo.** Un commerçant bloqué se débloque
  dans Promo : dupliquer ses écrans créerait deux endroits où valider un
  registre.
- **Il ne reçoit aucune donnée de client final.** Ceux-ci sont anonymes par
  conception dans le produit ; seuls des agrégats franchissent la frontière.
- **Il n'archive rien sans acquittement de fin de lot.** Sans lui, « ce
  commerçant n'est plus envoyé » et « l'export s'est arrêté à la page 3 » sont
  indiscernables.
