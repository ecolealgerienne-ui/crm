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

## À trancher avant la première ligne de code

Ces points de la spec conditionnent la structure de l'app, pas seulement son
comportement :

- **Identification du commercial** (§10.3) — mapping fixe appareil ↔ commercial
  au MVP, ou plusieurs commerciaux par appareil ? Détermine s'il faut un écran
  de connexion et une notion de session.
- **Destination des événements** (§2) — la spec fait passer l'app par une API
  d'ingestion multi-tenant avec file Redis. Pour un MVP à 3-5 clients internes,
  l'app pourrait parler directement à l'addon Odoo, la plateforme n'arrivant
  qu'à l'industrialisation. Ce choix change le contrat réseau de l'app.
- **Modèle Odoo cible** (§10.1) — `call.tracker.log` dédié ou activité sur
  `crm.lead`. La spec recommande le modèle dédié.

## Le reste du système

L'addon Odoo qui reçoit les appels ira dans [`addons/`](../../addons/), à côté
de `echangocrm_bootstrap`, et se testera contre l'instance Odoo 19 locale
montée par `docker-compose.yml` à la racine.
