# Call Tracker — addon Odoo

Reçoit les appels capturés par l'application mobile et les journalise dans
`call.tracker.log`, rattachés au contact ou à la piste correspondant au numéro.

## Pourquoi un module, et pas l'API générique d'Odoo

Une clé API Odoo hérite des **droits complets** de l'utilisateur associé : il
n'existe aucun moyen natif de restreindre un accès externe à « écrire un
journal d'appel et rien d'autre ». Ce module expose ses propres routes, avec
son propre jeton, révocable sans toucher à aucun compte.

Le jeton ne porte **aucun droit Odoo** : il désigne un appareil, rien de plus.
Ce qui est écrit et ce qui est renvoyé est décidé dans `controllers/main.py`,
jamais par les ACL d'un compte.

## Contrat de l'API

### `POST /call_tracker/log_call`

```
Authorization: Bearer <jeton de l'appareil>
Content-Type: application/json
```

```json
{
  "client_event_id": "uuid-genere-par-l-app",
  "phone_number": "+213555000000",
  "direction": "outbound",
  "duration_seconds": 142,
  "started_at": "2026-08-09T14:32:00Z"
}
```

Tous les champs sont obligatoires sauf `duration_seconds` (défaut 0).
**Un champ non listé fait rejeter la requête** — il signale un désaccord de
version entre l'app et le serveur, et l'ignorer ferait journaliser des appels
amputés sans que personne ne le remarque.

`started_at` doit porter un fuseau (`Z` ou `+HH:MM`). Un horodatage nu est
refusé : le téléphone peut être sur n'importe quel fuseau, et le supposer UTC
décalerait les appels de plusieurs heures en silence.

Pas de `rep_external_id`, contrairement à la spec : le jeton identifie
l'appareil, et l'appareil porte le commercial.

| Réponse | Code | Sens |
|---|---|---|
| `{"status":"logged","call_id":1,"linked_record":"crm.lead,26"}` | 201 | appel journalisé |
| `{"status":"duplicate","call_id":1,...}` | 200 | déjà reçu — voir ci-dessous |
| `{"status":"unauthorized"}` | 401 | jeton absent, inconnu ou révoqué |
| `{"status":"invalid","detail":"..."}` | 400 | charge utile refusée |

`linked_record` vaut `null` si le numéro ne correspond à rien.

### `GET /call_tracker/contact/<numero>`

Fiche minimale pour l'affichage à la sonnerie (Caller ID). Même
authentification.

```json
{ "status": "found", "name": "Ahmed Benali", "company": "Marché Central",
  "last_notes": "Relance prévue vendredi", "crm_stage": "Négociation" }
```

`404 {"status":"not_found"}` si le numéro ne correspond à rien — et non un
objet vide : l'app doit distinguer « inconnu au CRM » de « connu mais sans
information », qui s'affichent différemment.

⚠️ **La liste blanche des quatre champs est écrite en dur dans
`models/call_tracker_log.py`, et nulle part ailleurs.** Le contrôleur travaille
en `sudo()` : il a accès à tout le contact. Rien dans les droits d'Odoo
n'empêchera courriel, adresse ou chiffre d'affaires de sortir — c'est ce code
seul qui les retient. Un test vérifie sur la réponse brute qu'aucun d'eux
n'apparaît.

`last_notes` est le dernier message de type `comment` du fil, converti en texte
et tronqué à 200 caractères. Les notifications automatiques (changement
d'étape, courriel envoyé) sont écartées : elles noieraient la vraie note sous
du bruit à chaque sonnerie.

### L'idempotence, et pourquoi elle renvoie 200

L'app garde une file locale persistante et réémet ce qu'elle n'a pas pu
livrer : **les réessais sont certains, pas hypothétiques.** Un
`client_event_id` déjà reçu renvoie donc `200 duplicate` et non une erreur —
un 4xx ferait réessayer l'app indéfiniment dans le seul cas où tout va bien.

Deux garde-fous, parce qu'un seul ne suffit pas : une recherche préalable, et
un index unique SQL qui tranche si deux réessais se croisent.

## Le jeton

Généré depuis *CRM > Call Tracker > Appareils*, bouton **Générer un jeton**.
Affiché **une seule fois** : seule son empreinte SHA-256 est conservée.

Un SHA-256 nu suffit, et ce n'est pas un raccourci — les fonctions lentes
(bcrypt, pbkdf2) servent à rendre coûteuse l'énumération de secrets à faible
entropie, c'est-à-dire de mots de passe humains. Un jeton de 256 bits d'aléa
n'a rien à énumérer.

Régénérer un jeton **révoque l'ancien**. Décocher *Actif* révoque l'appareil
sans toucher au compte du commercial ni aux appels déjà journalisés.

## Rapprochement des numéros

Comparaison sur les **9 derniers chiffres**, parce qu'un mobile algérien
s'écrit indifféremment `0555000000`, `+213555000000` ou `00213555000000`.
Un numéro de moins de 9 chiffres n'est rapproché de rien — mieux vaut aucun
rattachement qu'un rattachement au hasard.

Les colonnes interrogées sont **détectées à l'exécution** et non écrites en
dur : `mobile` a disparu de `res.partner` et de `crm.lead` en Odoo 19, et une
requête sur une colonne absente échoue au lieu de ne rien trouver. Le champ
`phone_sanitized` (normalisation E.164 d'Odoo) est interrogé en plus de
`phone`, car il est NULL quand Odoo n'a pas su déduire le pays.

Aucun index ne couvre cette expression SQL. Sans conséquence sur le carnet
d'adresses d'une PME, mais **c'est le premier endroit à revoir si le
rapprochement ralentit**.

## Éprouver le module

```bash
wsl -e bash -lc "cd /mnt/c/Users/amar/Desktop/shope/echangoCrm && \
  docker compose run --rm -T odoo odoo -d echango_crm -u call_tracker --stop-after-init && \
  docker compose restart odoo"
```

Puis, avec un jeton généré dans l'interface :

```bash
curl -i -X POST http://localhost:8169/call_tracker/log_call \
  -H "Authorization: Bearer <jeton>" -H "Content-Type: application/json" \
  -d '{"client_event_id":"essai-1","phone_number":"+213555000000",
       "direction":"outbound","duration_seconds":42,
       "started_at":"2026-08-09T14:32:00Z"}'
```

## Depuis une fiche client, voir ses appels

Le rattachement `partner_id` / `lead_id` existait depuis le début, mais
seulement en base. Un bouton sur la fiche contact et sur la piste ouvre
désormais la liste de leurs appels.

Sur une **société**, le compteur additionne les appels de ses contacts
rattachés (`child_of`) : les appels sont journalisés au nom de
l'interlocuteur, et un compteur limité à la société elle-même afficherait zéro
là où il y a le plus à voir.

## Note prise après l'appel

Champ `note` facultatif dans la charge utile de `log_call`, plafonné à 1000
caractères. Quand elle est présente et qu'une piste ou un contact est
rattaché, la note est **publiée dans le fil de discussion** — type `comment`,
sous-type `mail.mt_note`, attribuée au commercial.

Ce report n'est pas décoratif, il **referme une boucle** : c'est ce même fil
que lit `fiche_contact` pour alimenter le Caller ID. La note écrite après un
appel s'affiche donc au suivant.

⚠️ Sous-type `mt_note` et non un commentaire public : se tromper ici
enverrait la note au client par courriel.

## Numéro inconnu — création automatique de piste

Décision du 2026-08-09 (spec §10.2). Un appel dont le numéro n'est **ni** un
contact **ni** une piste crée une piste, attribuée au commercial qui a passé ou
reçu l'appel.

Deux garde-fous, et ils comptent autant que la fonctionnalité :

- **Un contact connu sans piste ouverte ne déclenche rien.** Ce n'est pas un
  numéro inconnu ; lui créer une piste rouvrirait une affaire à chaque appel de
  suivi.
- **Le deuxième appel du même inconnu réutilise la piste.** Elle porte le
  numéro, donc `_chercher_piste` la retrouve. Sans cela, chaque rappel d'un
  prospect créerait une affaire de plus.

Le type créé (`lead` ou `opportunity`) suit la configuration CRM du commercial.
Créer un `lead` sur une base où l'étape de qualification est désactivée le
rendrait **invisible** : le menu correspondant est masqué.

## Rétention

`CALL_TRACKER_RETENTION_DAYS`, lue dans l'environnement du serveur (injectée
par docker-compose depuis `.env.production`). Une tâche planifiée quotidienne
purge les appels **et** leurs traces d'audit au-delà.

⚠️ **`0`, absente ou illisible = aucune purge.** Le sens de l'erreur est
choisi : un fichier d'environnement mal renseigné ne doit pas faire disparaître
des données. Mais tant que la valeur vaut 0, il n'y a pas de politique de
rétention — il y a une absence de politique, ce qui ne tient pas au regard de
la loi 18-07.

La limite se compte sur la **date de l'appel**, pas sur celle de son
enregistrement : un appel remonté avec trois semaines de retard, parce que le
téléphone est resté hors réseau, doit être daté de l'appel.

## Journal d'audit

`call.tracker.audit` — *CRM > Call Tracker > Journal d'audit*, réservé aux
administrateurs. Chaque journalisation d'appel **et chaque consultation de
contact** y laisse une ligne, y compris les tentatives refusées, avec l'IP
d'origine.

Les **lectures** sont le vrai sujet. Une écriture laisse une trace visible :
l'appel apparaît dans la liste. Une consultation ne laisse rien — sans ce
journal, un jeton volé pourrait parcourir le carnet d'adresses numéro par
numéro sans qu'il en subsiste la moindre trace. Le filtre *Refusés* fait
apparaître d'un coup d'œil un jeton révoqué resté dans un téléphone, ou
quelqu'un qui tâtonne.

L'écriture d'une trace ne peut jamais faire échouer l'appel qu'elle observe :
un journal d'audit qui casse la fonctionnalité est désactivé au premier
incident, et il n'y en a alors plus du tout.

## Tests

94 tests couvrant le contrat HTTP des deux routes, l'idempotence, la
révocation, le rapprochement téléphonique, la création automatique de piste,
la note post-appel, les liens depuis les fiches CRM, la rétention et le
journal d'audit.

```bash
docker compose run --rm -T odoo odoo \
  --database=call_tracker_test --init=call_tracker \
  --test-enable --test-tags=/call_tracker --stop-after-init \
  --log-level=warn --log-handler=odoo.tests:INFO
```

⚠️ **`--test-tags=/call_tracker` n'est pas optionnel.** Sans lui,
`--test-enable` lance les 2296 tests de tous les modules installés, dont des
parcours navigateur qui échouent dans un conteneur sans `websocket-client` :
on croit alors avoir cassé quelque chose.

⚠️ **`--log-level=warn` seul ne montre RIEN**, pas même le succès : les
résultats sont journalisés en INFO. D'où `--log-handler=odoo.tests:INFO`.

## Limitation de débit

Posée côté Traefik, pas dans l'addon : voir le routeur `echangocrm-api` et le
middleware `echangocrm-api-limite` dans `docker-compose.crm.yml`. Les valeurs
sont hautes délibérément — les opérateurs mobiles algériens font du NAT à
grande échelle, et l'app vide sa file d'un trait au retour du réseau.

## Portée de version

**Odoo 19 uniquement**, décision du 2026-08-09. La spec §3.2 demandait 16 à 19 ;
le module utilise `_read_group(aggregates=…)`, les vues `<list>` et un
`post_init_hook(env)`, tous introduits en Odoo 17. Il tournerait probablement
en 17 et 18, mais ce n'est ni visé ni éprouvé.

## Pas encore fait

- **Documentation loi 18-07** : le mécanisme de rétention existe, la
  qualification de « sous-traitant de données » et la politique écrite qui
  l'accompagne restent à produire.
- **Purge des pistes créées automatiquement** : la rétention supprime les
  appels et les traces, pas les pistes qu'ils ont engendrées. C'est
  volontaire — une piste est une donnée commerciale, pas une trace technique —
  mais cela signifie qu'un numéro appelé une fois laisse une piste
  indéfiniment.
