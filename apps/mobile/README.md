# Call Tracker — application mobile Android

Capture automatique des appels d'un commercial (numéro, durée, direction) et
synchronisation vers Odoo CRM, sans saisie manuelle.

**État : rien n'est développé.** Ce dossier est la place réservée à l'app ; la
spécification qui la décrit est [`docs/call_tracker_odoo_spec.md`](../../docs/call_tracker_odoo_spec.md).

## Ce qui est déjà arrêté par la spec

| | |
|---|---|
| Plateforme | Android uniquement — iOS est hors scope (Apple n'expose pas l'historique d'appels) |
| Techno | Kotlin natif : `CallLog` et `TelephonyManager` demandent l'API native, aucun framework multiplateforme ne les couvre de façon fiable |
| Capture | `BroadcastReceiver` sur `PHONE_STATE`, puis lecture de `CallLog.Calls` après raccrochage |
| Résilience | file locale persistante (Room) — l'app réessaie elle-même avant de compter sur un retry côté serveur |
| Distribution | APK signé ou Managed Google Play privé. **Pas de publication publique au MVP** |

## Pourquoi pas le Play Store public

`READ_CALL_LOG` est une permission restreinte. Pour l'obtenir en publication
publique, Google exige que l'app soit gestionnaire par défaut (Téléphone / SMS /
Assistant), avec un formulaire de déclaration à soumettre et à maintenir à
chaque changement d'usage. C'est un chantier à part entière, écarté du MVP.
Revenir dessus supposerait soit de devenir dialer par défaut
(`InCallService` / `CallScreeningService`), soit de monter ce dossier en amont.

## Architecture retenue — écart assumé avec la spec

**Décidé le 2026-08-09 : l'app parle directement à l'addon Odoo.**

```
[App Android]  ──HTTPS + token du module──▶  [Addon Odoo]  ──▶  [Base Odoo]
```

La spec (§2) intercale une API d'ingestion multi-tenant, une file Redis Streams,
un worker et un Postgres d'état. Tout cela est **écarté du premier jet** : on
cherche d'abord à établir la faisabilité, et cette chaîne ne se justifie qu'à
partir du moment où il y a plusieurs tenants à router. La spec reste la cible
d'industrialisation, ce n'est pas un abandon.

Ce que ce raccourci déplace, et qu'il ne faut pas perdre de vue :

- **L'idempotence remonte dans l'addon.** C'est l'API d'ingestion qui portait le
  dédoublonnage par `client_event_id`. Sans elle, c'est l'addon Odoo qui doit
  refuser un `client_event_id` déjà vu — sinon chaque réessai depuis la file
  locale de l'app crée un doublon d'appel. **C'est le point à ne pas oublier :
  la file locale rend les réessais certains, pas hypothétiques.**
- **Le cache de contacts passe côté app.** Le Redis à TTL 5 min qui protégeait
  l'Odoo client disparaît ; c'est l'app qui doit mettre en cache, sous peine
  d'une requête Odoo à chaque sonnerie.
- **L'URL Odoo et le token vivent sur l'appareil**, au lieu d'être une ligne de
  la table `tenants`. À stocker dans le Keystore Android, pas en clair.

## Reste à trancher avant la première ligne de code

- **Identification du commercial** (§10.3) — mapping fixe appareil ↔ commercial
  au MVP, ou plusieurs commerciaux par appareil ? Détermine s'il faut un écran
  de connexion et une notion de session.
- **Modèle Odoo cible** (§10.1) — `call.tracker.log` dédié ou activité sur
  `crm.lead`. La spec recommande le modèle dédié, et le besoin d'idempotence
  ci-dessus va dans le même sens : un modèle propre peut porter une contrainte
  d'unicité sur `client_event_id`, une activité sur `crm.lead` beaucoup moins
  naturellement.

## Le reste du système

L'addon Odoo qui reçoit les appels ira dans [`addons/`](../../addons/), à côté
de `echangocrm_bootstrap`, et se testera contre l'instance Odoo 19 locale
montée par `docker-compose.yml` à la racine.
