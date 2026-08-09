# Spec technique — Call Tracker mobile connecté à Odoo CRM

**Statut** : Draft v1 — à affiner avant développement
**Cible** : équipe commerciale interne (MVP), extension possible en produit B2B vendu aux clients Odoo
**Auteur** : Amar — usage prévu : implémentation via Claude Code

---

## 1. Contexte et objectif

Application mobile Android qui capture automatiquement les appels passés/reçus par un commercial (numéro, durée, direction) et les synchronise vers Odoo CRM, sans nécessiter de saisie manuelle. Objectif MVP : couvrir le besoin interne (suivi des appels sur les clients échange/echango/Odoo). Objectif long terme : produit vendable à des entreprises utilisant Odoo, avec un positionnement sécurité différenciant (accès minimal, pas de credentials larges).

### Principes directeurs (non négociables)
- **Moindre privilège** : le système ne doit jamais avoir accès à plus de données Odoo que le strict nécessaire au logging d'appel + affichage minimal de contact.
- **Pas de dépendance à l'API générique Odoo avec un utilisateur à droits larges.** Toute communication avec Odoo passe par un module Odoo dédié (addon) exposant des endpoints restreints.
- **MVP d'abord, généricité ensuite.** Le connecteur est codé spécifiquement pour Odoo. L'architecture doit permettre d'ajouter d'autres CRM plus tard, mais on ne développe pas d'abstraction multi-CRM tant qu'il n'y a pas de demande réelle.
- **Distribution interne d'abord** : pas de publication publique sur Google Play au lancement (voir section 6), pour éviter la contrainte du formulaire de déclaration de permissions et la nécessité de devenir dialer par défaut.

---

## 2. Architecture générale

```
[App mobile Android]
        │  (HTTPS, auth par token tenant)
        ▼
[API d'ingestion]  ──────────────┐
        │                         │ (état, config, credentials chiffrés)
        ▼                         ▼
[Redis Streams: file + retry] [Postgres: tenant, sync history]
        │
        ▼
[Connecteur Odoo (worker)]
        │  (HTTPS, token dédié au module — PAS un compte utilisateur Odoo classique)
        ▼
[Module Odoo dédié (addon), déployé côté client]
        │
        ▼
[Base Odoo du client — crm.lead / modèle custom call.log]
```

### 2.1 Composants à développer

| Composant | Rôle | Techno suggérée |
|---|---|---|
| App mobile Android | Capture des appels, UI Caller ID, recherche contact, notes post-appel | Kotlin natif (accès CallLog/TelephonyManager nécessite API native, pas de framework cross-platform fiable ici) |
| API d'ingestion | Reçoit les événements d'appel de l'app mobile, valide, pousse en file | Node/NestJS ou Python/FastAPI (au choix selon stack existante) |
| File d'attente | Découple ingestion et livraison, gère les retries | Redis Streams |
| Base d'état | Config tenant, credentials chiffrés, historique de sync, cache contacts | PostgreSQL |
| Connecteur Odoo (worker) | Consomme la file, appelle le module Odoo dédié | Même stack que l'API d'ingestion |
| Module Odoo (addon) | Expose les endpoints restreints côté client, écrit/lit dans Odoo | Python (addon Odoo standard, `models.py` + `controllers.py`) |

---

## 3. Module Odoo dédié (addon) — spécification détaillée

C'est la pièce la plus critique côté sécurité : elle remplace l'usage de l'API générique Odoo (XML-RPC/JSON-RPC/REST), qui est structurellement incapable de restreindre l'accès à un champ ou une action précise (les clés API Odoo héritent des droits complets de l'utilisateur associé — il n'y a pas de contrôle fin par endpoint nativement).

### 3.1 Endpoints exposés

**POST `/call_tracker/log_call`** (écriture)
- Auth : token propre au module (généré à l'installation, pas un login Odoo), transmis en `Authorization: Bearer <token>`.
- Payload attendu :
```json
{
  "phone_number": "+213555000000",
  "direction": "outbound",       // "inbound" | "outbound" | "missed"
  "duration_seconds": 142,
  "started_at": "2026-08-09T14:32:00Z",
  "rep_external_id": "amar_001"  // identifiant du commercial côté plateforme, mappé à un user Odoo
}
```
- Comportement interne : valide strictement les champs (rejette tout champ non listé ci-dessus), résout le contact par numéro de téléphone (`res.partner` ou `crm.lead`), crée une activité/log d'appel liée. Utilise `sudo()` en interne pour l'écriture — le token externe n'a jamais de droits Odoo directs.
- Réponse : `{ "status": "logged", "linked_record": "crm.lead,42" }` ou `{ "status": "no_match", "action": "created_lead" }` selon la politique choisie (voir 3.3).

**GET `/call_tracker/contact/{phone_number}`** (lecture, pour Caller ID / recherche in-app)
- Auth : même mécanisme.
- Réponse limitée à des champs whitelistés uniquement :
```json
{
  "name": "Ahmed Market",
  "company": "Marché Central Djelfa",
  "last_notes": "Relance prévue vendredi",
  "crm_stage": "Négociation"
}
```
- **Ne jamais renvoyer** : email, adresse complète, données financières, historique complet — même si le compte Odoo sous-jacent y a accès. Le filtrage est fait explicitement dans le contrôleur, jamais par confiance dans les ACL Odoo.

### 3.2 Installation côté client
- Addon packagé comme un module Odoo standard (`__manifest__.py`, dépendance `crm`), installable depuis Apps → Import Module ou dépôt Git privé.
- À l'installation, génère un token unique affiché une seule fois (pattern "API key à copier immédiatement"), stocké côté client en `res.config.settings` du module.
- Doit fonctionner sur Odoo 16 à 19 (vérifier compat continuellement vu la dépréciation XML-RPC/JSON-RPC annoncée pour Odoo 20/22 — mais comme ce module n'utilise pas ces protocoles, il n'est pas concerné).

### 3.3 Règles métier à définir (décisions à prendre avant dev)
- Que faire si le numéro ne correspond à aucun contact existant ? (créer un lead automatiquement / ignorer / mettre en file d'attente pour validation manuelle)
- Sur quel modèle logger l'appel : `crm.lead` (activité liée) ou un modèle dédié `call.tracker.log` (plus propre, ne pollue pas les leads) ? → **Recommandation : modèle dédié**, avec une vue liée en onglet sur `crm.lead`/`res.partner`.
- Gestion multi-numéros par contact (mobile pro, fixe, etc.).

---

## 4. Application mobile — spécification fonctionnelle

### 4.1 Fonctionnalités MVP (phase 1)
- Capture automatique des appels SIM (entrants, sortants, manqués) via `BroadcastReceiver` sur `PHONE_STATE` + lecture `CallLog.Calls` après raccrochage.
- Envoi asynchrone vers l'API d'ingestion, avec **file locale persistante (SQLite/Room)** pour ne rien perdre en cas de perte réseau — retry côté app avant de compter sur le retry côté plateforme.
- Association appel ↔ commercial (identifiant fixe par device/compte, pas de multi-compte au MVP).
- Marquage "appel privé" (non loggé) — paramètre simple dans l'app.
- Plage horaire de logging configurable (ex: ne logger que 8h-19h).

### 4.2 Fonctionnalités phase 2 (post-validation MVP)
- **Caller ID** : au moment de la sonnerie, requête vers `/call_tracker/contact/{phone}`, affichage d'un overlay avec nom/société/dernière note (nécessite permission `SYSTEM_ALERT_WINDOW` — à vérifier aussi côté Play Store, permission également sensible).
- **Recherche contact in-app** : barre de recherche interrogeant le cache local (synchronisé périodiquement) ou l'endpoint de lecture.
- **Prompt de note post-appel** : à la fin de chaque appel, popup proposant d'ajouter une note texte, envoyée avec le log d'appel.
- **Dashboard simple** : nombre d'appels du jour/semaine, temps total, taux de décroché (peut être une vue web plutôt que native, consommée dans une WebView).

### 4.3 Hors scope (explicitement exclu, sauf demande future)
- Enregistrement audio des appels (implications légales/consentement plus lourdes, à traiter séparément si demandé).
- Support iOS (Apple restreint bien plus l'accès au call log — nécessiterait une approche complètement différente, CallKit/Caller ID extension uniquement, sans accès à l'historique).
- Multi-CRM (Salesforce, HubSpot...) — architecture le permet, pas développé au MVP.

---

## 5. API d'ingestion — contrat

**POST `/api/v1/calls`**
```json
{
  "tenant_id": "uuid",
  "rep_id": "amar_001",
  "phone_number": "+213555000000",
  "direction": "outbound",
  "duration_seconds": 142,
  "started_at": "2026-08-09T14:32:00Z",
  "client_event_id": "uuid-généré-côté-app"  // pour idempotence/dédoublonnage
}
```
- Auth : token API scopé par tenant (pas de compte utilisateur générique).
- Réponse immédiate `202 Accepted` — le traitement réel (résolution du tenant → connecteur Odoo) se fait de manière asynchrone via la file.
- `client_event_id` obligatoire pour permettre le dédoublonnage en cas de retry côté app mobile.

**GET `/api/v1/contacts/{phone_number}?tenant_id=uuid`**
- Proxy vers le module Odoo du tenant concerné, avec cache court (Redis, TTL 5 min) pour limiter la charge sur l'Odoo client.

---

## 6. Contraintes Android / Google Play (rappel des décisions prises)

- `READ_CALL_LOG` est une permission restreinte : Google exige que l'app soit gestionnaire par défaut (Téléphone/SMS/Assistant) pour l'obtenir en publication publique, avec formulaire de déclaration à soumettre et remettre à jour à chaque changement d'usage.
- **Décision MVP : pas de publication Play Store publique.** Distribution en APK signé, installation manuelle ou via Managed Google Play (app privée à l'organisation) sur les appareils de l'équipe commerciale.
- Si publication publique envisagée plus tard : prévoir soit de devenir dialer par défaut (`InCallService`/`CallScreeningService`), soit de constituer un dossier de déclaration solide en amont — ne pas sous-estimer ce chantier.

---

## 7. Sécurité et conformité

- Credentials/tokens du module Odoo chiffrés au repos (pas en clair en base Postgres) — utiliser un KMS ou au minimum un chiffrement applicatif avec clé hors base.
- Toute communication en HTTPS uniquement, certificats valides (déjà en place via Traefik).
- Le token du module Odoo n'est **jamais** un login/mot de passe utilisateur Odoo — uniquement un secret propre au module, révocable indépendamment.
- Documentation claire pour les futurs clients B2B : préciser le statut de "sous-traitant de données" au sens de la loi 18-07 (Algérie), avec politique de rétention des données d'appel à définir (durée de conservation, droit à l'effacement).
- Logs d'audit sur la plateforme : qui a accédé à quoi, quand (utile pour la confiance client et le debug).

---

## 8. Modèle de données (plateforme, Postgres)

**`tenants`** : id, name, odoo_module_token (chiffré), odoo_base_url, created_at, status

**`reps`** : id, tenant_id, external_id, display_name, active

**`call_events`** : id, tenant_id, rep_id, phone_number, direction, duration_seconds, started_at, client_event_id (unique), sync_status (`pending`/`synced`/`failed`), odoo_linked_record, created_at

**`sync_failures`** : id, call_event_id, error_message, retry_count, last_attempt_at

---

## 9. Roadmap proposée

| Phase | Contenu | Sortie |
|---|---|---|
| Phase 1 — MVP | Capture appel mobile + file locale, API ingestion, Redis Streams, module Odoo (log_call uniquement), déploiement sur 3-5 clients Odoo internes | App fonctionnelle en interne |
| Phase 2 — Enrichissement | Caller ID, recherche contact, notes post-appel, endpoint de lecture Odoo | Validation du produit, mesure adoption |
| Phase 3 — Industrialisation | Dashboard analytics, gestion multi-tenant robuste, onboarding self-service du module Odoo | Prêt à vendre en B2B |
| Phase 4 (optionnel) — Multi-CRM | Abstraction connecteur si demande confirmée hors écosystème Odoo | Extension du marché adressable |

---

## 10. Questions ouvertes à trancher avant de lancer le dev

1. Modèle Odoo cible pour le log d'appel : `call.tracker.log` dédié vs activité sur `crm.lead` — confirmer.
2. Politique de création automatique de lead si numéro inconnu : oui/non/validation manuelle.
3. Identification du commercial : mapping fixe device↔rep au MVP, ou gestion de plusieurs commerciaux par device (peu probable au MVP) ?
4. Rétention des données d'appel sur la plateforme : durée avant purge automatique.
5. Nom de l'app et de la marque — éviter toute référence directe à "Odoo" dans le nom pour raisons de marque déposée (voir remarque faite sur le concurrent banasTech).
