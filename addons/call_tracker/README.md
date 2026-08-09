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

## Pas encore fait

- **`GET /call_tracker/contact/{numero}`** (Caller ID, spec §3.1) — la route de
  lecture, avec sa liste blanche stricte de champs.
- **Création automatique de piste** quand le numéro est inconnu (spec §10.2) :
  la politique n'est pas tranchée. Aujourd'hui l'appel est journalisé sans
  rattachement, et se retrouve par le filtre *Sans contact rattaché*.
- **Limitation de débit** sur la route d'écriture.
- **Journal d'audit** des accès (spec §7).
