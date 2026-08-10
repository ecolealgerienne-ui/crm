# Call Tracker — spécification de l'implémentation V1

**Statut** : livré et déployé — rédigé le 2026-08-10 d'après le code existant
**Périmètre** : usage interne echango
**Auteur de la spec d'origine** : Amar — ce document décrit ce qui a été construit

---

## 0. Ce que ce document est, et ce qu'il n'est pas

Il décrit **l'implémentation V1**, telle qu'elle tourne aujourd'hui.

[`call_tracker_odoo_spec.md`](call_tracker_odoo_spec.md) reste le document
d'origine et **l'architecture cible** : plateforme d'ingestion multi-locataire,
file Redis, connecteur, revente B2B. Il n'est pas périmé — il décrit la V2.

V1 s'en écarte sur un point structurant, et c'est délibéré : **il n'y a pas de
plateforme au milieu.** Le §11 dit ce que V2 apporterait et pourquoi V1 ne le
fait pas.

Les **principes directeurs** de la spec d'origine, eux, sont intacts : moindre
privilège, aucun accès à l'API générique d'Odoo, addon dédié exposant des
routes restreintes, distribution interne. Ils ont tenu sans exception.

---

## 1. Architecture réelle

```
┌─ Téléphone Android ──────────────────────┐
│  Flutter (lib/)      → écrans, i18n      │
│      ▲ canal de plateforme               │
│  Kotlin (android/)   → capture, file,    │      HTTPS
│      CallScreeningService, CallLog,      │  ─────────────▶  Odoo 19
│      SQLite, WorkManager                 │   Bearer jeton    addon call_tracker
└──────────────────────────────────────────┘   d'appareil      (controllers/main.py)
```

**App → Odoo, directement.** Rien entre les deux. La décision date du
2026-08-09 : valider la faisabilité de la chaîne avant d'industrialiser, et ne
pas construire une plateforme pour un seul locataire qui est nous-mêmes.

**Flutter ne voit jamais passer un appel.** La capture, la file locale et
l'envoi vivent entièrement en Kotlin, parce qu'un appel arrive presque toujours
alors que l'application est fermée et que le moteur Flutter n'existe pas. Une
file écrite en Dart ne serait jamais alimentée — c'est-à-dire jamais dans le
cas normal. Le canal de plateforme ne transporte que de la lecture d'état et
des réglages.

La spec d'origine écartait les frameworks cross-platform pour cette raison
exacte. Elle avait raison sur la capture ; l'interface, elle, n'a pas ce
problème. D'où le partage.

**Ce que la disparition de la plateforme a coûté** : les fonctions qu'elle
portait ont été réparties.

| Fonction plateforme (spec d'origine) | Où elle vit en V1 |
|---|---|
| File + retry (Redis Streams) | File SQLite locale sur le téléphone, WorkManager pour les reprises |
| Idempotence | `client_event_id` + index unique côté Odoo |
| Cache contacts (Redis, TTL court) | `ContactCache` local, 30 min (2 min pour les inconnus) |
| Historique de synchronisation | `call.tracker.audit` dans Odoo |
| Credentials chiffrés | `EncryptedSharedPreferences` côté téléphone, **empreinte seule** côté Odoo |

---

## 2. Le contrat d'API — cinq routes

Toutes en `Authorization: Bearer <jeton d'appareil>`, `auth='public'` côté
Odoo, accès base en `sudo()`. **Le jeton ne porte aucun droit Odoo** : il
désigne un appareil, et le contrôleur décide seul de ce qui est écrit et de ce
qui est renvoyé.

| Route | Méthode | Rôle |
|---|---|---|
| `/call_tracker/log_call` | POST | Journaliser un appel |
| `/call_tracker/contact/<numero>` | GET | Fiche d'un numéro complet — Caller ID |
| `/call_tracker/contacts/<fragment>` | GET | Recherche par fragment — liste |
| `/call_tracker/activities` | GET | Les appels programmés dans le CRM |
| `/call_tracker/activity/<id>/done` | POST | Clôturer une activité |

Le détail de chaque contrat, ses bornes et ses pièges : [`addons/call_tracker/README.md`](../addons/call_tracker/README.md).

### Deux écarts au contrat d'origine, tous deux volontaires

**`rep_external_id` a disparu de la charge utile.** La spec faisait envoyer par
l'app l'identifiant du commercial. Le jeton d'appareil le porte désormais :
`user_id` est déduit de `appareil.user_id`, côté serveur. **Une application ne
peut donc pas se déclarer être quelqu'un d'autre**, ce que le champ d'origine
permettait.

**Un jeton par appareil, pas un par installation du module.** La spec prévoyait
un jeton unique généré à l'installation, rangé dans `res.config.settings`. Il
en faut un par téléphone : c'est lui qui identifie le commercial, et il doit
être révocable individuellement — un appareil perdu ne doit pas obliger à
reconfigurer toute l'équipe. Odoo n'en stocke que l'**empreinte SHA-256** ; le
jeton en clair n'est affiché qu'une fois.

---

## 3. Modèle de données — dans Odoo, pas dans une base tierce

Il n'y a pas de Postgres de plateforme. Les tables `tenants`, `reps`,
`call_events` et `sync_failures` de la spec d'origine n'existent pas : leur
contenu vit dans Odoo ou sur le téléphone.

| Modèle | Rôle |
|---|---|
| `call.tracker.log` | L'appel : numéro, sens, durée, début, note, rattachement, champs dérivés |
| `call.tracker.device` | L'appareil et son commercial ; empreinte du jeton |
| `call.tracker.audit` | Toute lecture et toute écriture, y compris refusées, avec l'IP |
| `call.tracker.coverage` | Vue SQL — couverture du portefeuille |
| `call.tracker.lead.activity` | Vue SQL — relance des affaires |
| `call.tracker.note.wizard` | Compléter une note depuis le CRM |
| `call.tracker.token.wizard` | Afficher un jeton une seule fois |

Plus deux extensions : `res.partner` et `crm.lead` (compteurs d'appels et de
notes, accès aux listes).

**Modèle dédié, pas activité sur `crm.lead`** — recommandation de la spec
d'origine §3.3, suivie. Les appels ne polluent pas le pipeline, et les vues
liées sont accessibles depuis la fiche client et depuis la piste.

---

## 4. L'application mobile

Quatre onglets, dans cet ordre :

| Onglet | Contenu |
|---|---|
| **À appeler** | Les activités de type appel programmées dans le CRM, retard en tête |
| Appels | Ce qui a été capturé, et l'état de la file |
| Recherche | Par fragment de numéro → liste → fiche client → appeler |
| Réglages | Serveur, jeton, capture, plage horaire, autorisations, avis d'information |

**« À appeler » est en premier délibérément.** C'est le seul écran qui rende
quelque chose au commercial ; tout le reste capture, transmet et rapporte à un
responsable. Et ce n'est pas qu'une question d'adoption : on a mesuré sur un
OnePlus que la surcouche constructeur gèle l'application écran éteint, et que
la tâche d'envoi ne tourne qu'au réveil. **Une application qu'on n'ouvre jamais
est une application dont la file d'envoi ne se vide pas.**

Détail des écrans et de leurs choix : [`apps/mobile/README.md`](../apps/mobile/README.md).

### Ce qui a changé par rapport à la spec §4

| Spec d'origine | V1 |
|---|---|
| Marquage « appel privé » | **Abandonné** (2026-08-09) — la ligne est professionnelle, tous les appels qui y transitent le sont |
| Kotlin natif intégral | Flutter pour l'interface, Kotlin pour la capture |
| Prompt de note post-appel | Livré, avec retenue bornée à 2 min et rattrapage depuis la liste |
| Caller ID, recherche contact | Livrés |
| Dashboard dans une WebView | Livré **dans Odoo**, pas dans l'app : pivot et graphe natifs, là où le manager travaille |

---

## 5. Sécurité et conformité — état

| Exigence spec §7 | État |
|---|---|
| Jeton jamais un login Odoo | ✅ Jeton propre, révocable, empreinte seule en base |
| Secrets chiffrés au repos | ✅ `EncryptedSharedPreferences`, repli documenté si le Keystore est défaillant |
| HTTPS uniquement | ✅ Trafic en clair interdit dans le manifeste de release |
| Journal d'audit | ✅ `call.tracker.audit` — **lectures comprises**, c'est le point |
| Rétention à définir | ✅ 1095 jours, `CALL_TRACKER_RETENTION_DAYS`, purge quotidienne |
| Statut 18-07 | ✅ [`CONFORMITE_DONNEES_APPELS.md`](CONFORMITE_DONNEES_APPELS.md) |

**Deux propriétés ajoutées, absentes de la spec d'origine :**

**L'historique n'est jamais collecté.** Le suivi démarre à l'activation de la
capture ; le journal d'appels antérieur reste sur l'appareil. Sans cette règle,
la première activation versait dans le CRM des années d'appels privés —
mesuré sur le premier téléphone réel branché : 3000 appels.

**Les commerciaux sont informés.** Un écran barre l'accès aux onglets au
premier lancement : ce qui est enregistré, ce qui ne l'est pas, qui peut le
lire, combien de temps. L'accusé de lecture porte un **numéro de version**,
pour que l'avis soit redemandé le jour où le fond change.

---

## 6. Les décisions prises

Les questions ouvertes de la spec (§3.3 et §10), tranchées.

| Question | Décision | Quand |
|---|---|---|
| Numéro inconnu | **Qualification manuelle.** Un bouton, mais un clic humain — une création automatique remplit le pipeline de taxis et de faux numéros | 2026-08-09 (revient sur un premier choix inverse) |
| Modèle du log | `call.tracker.log` dédié | 2026-08-09 |
| Multi-numéros par contact | Rapprochement sur les **9 derniers chiffres**, sur `phone_sanitized`, `phone` et `mobile` quand il existe | 2026-08-09 |
| Identification du commercial | **Un appareil, un commercial.** Pas de multi-compte — voir §10 | 2026-08-09 |
| Rétention | 1095 jours, réglable dans le `.env` | 2026-08-09 |
| Marquage « appel privé » | Abandonné | 2026-08-09 |
| Version d'Odoo | **19 uniquement.** Pas de compatibilité 16-18 : elle coûterait des détours sur des champs disparus (`mobile`) et des vues qui ont changé de grammaire | 2026-08-09 |
| Périmètre de la recherche de contacts | **Ouvert** (`all`), réglable par `CALL_TRACKER_SEARCH_SCOPE` — l'équipe est petite et chacun couvre les autres | 2026-08-10 |
| Pointage des activités | **Manuel.** Un appel de 4 s tombé sur la messagerie cocherait sinon une vraie tâche | 2026-08-10 |

---

## 7. Livré au-delà de la spec

Rien de tout cela n'était demandé ; tout est né d'un besoin constaté en route.

**Reporting dans Odoo** — cloisonnement par commercial, champs dérivés
(`outcome`, `hour_of_day`, `delivery_lag_minutes`), couverture du portefeuille,
relance des affaires. Le raisonnement, y compris ce qui est **refusé** — pas de
taux de conversion, il serait lu comme causal — est dans
[`REPORTING_KPI.md`](REPORTING_KPI.md).

**Le délai de remise** (`delivery_lag_minutes`) est la mesure qui doit précéder
tout classement entre commerciaux. Sans elle, on compare des réglages de
batterie.

**Les appels à passer** — les activités du CRM rendues au téléphone. La seule
fonction qui donne au lieu de prendre.

**Enrichissement depuis le CRM** — l'appel reste figé, le fil du client
s'enrichit, et ce qu'on y écrit revient au téléphone à la sonnerie suivante.

**L'historique des notes rassemblé sur le compte** — une note vit sur la piste
quand il y en a une, sinon sur le contact ; sept notes sur huit étaient donc
invisibles depuis la fiche client.

---

## 8. Ce qui est éprouvé, et comment

197 tests Odoo, 44 tests Flutter, 0 échec.

Chaîne validée de bout en bout sur émulateur **et sur un téléphone réel**
(OnePlus 7 Pro, Android 12, 2026-08-10) : appel → capture → file → Wi-Fi →
Odoo → rattachement au bon contact → note → retour au Caller ID.

**Ce qu'aucun banc ne dira** : la survie en arrière-plan sur plusieurs jours.
On sait déjà qu'OxygenOS gèle l'application écran éteint — observé douze
secondes après l'installation. Le design se rattrape au réveil, donc le risque
est le **retard**, pas la perte. L'ampleur de ce retard reste à mesurer.

---

## 9. Déploiement

| | |
|---|---|
| Production | `https://echangocrm.echango.com`, `/opt/echangocrm` |
| Module | `call_tracker`, installé, nommé dans l'amorçage |
| Variables | `CALL_TRACKER_RETENTION_DAYS=1095`, `CALL_TRACKER_SEARCH_SCOPE=all` |
| Développement | `http://localhost:8169`, Postgres 5436 |

Procédure : [`DEPLOIEMENT_VPS.md`](DEPLOIEMENT_VPS.md).

⚠️ `docker compose` exige `--env-file .env.production`, et **`restart` ne
prend pas les variables** — il faut `up -d`, qui recrée le conteneur.

---

## 10. Ce que V1 ne fait pas

**Un appareil, un commercial.** Pas de bascule de compte, et ce n'est pas
qu'une fonction manquante : l'attribution se fait **à la réception**, et la
file locale ne porte aucun commercial. Des appels en attente au moment d'une
bascule arriveraient au nom du suivant. Plus profondément, un téléphone partagé
partage sa ligne SIM — Android ne sait pas qui tient l'appareil. Le modèle
honnête pour un poste partagé serait un appareil rattaché à une **équipe**, en
renonçant au classement nominatif sur cette ligne.

**Pas de création ni de replanification d'activité depuis le téléphone.**
Programmer un appel est un acte de bureau ; l'ajouter reviendrait à commencer
un Odoo mobile.

**Pas d'enregistrement audio, pas d'iOS, pas de multi-CRM** — hors périmètre
de la spec d'origine §4.3, et toujours.

**L'APK n'est pas encore signé par une clé de production.** La configuration
Gradle est en place et vérifiée ; il manque la clé elle-même, que seul
l'exploitant peut créer — une clé dont le mot de passe aurait circulé serait
compromise dès sa naissance. Sans `android/key.properties`, le build de release
retombe sur la clé de débogage et l'annonce. Procédure dans
[`apps/mobile/README.md`](../apps/mobile/README.md), section Signature.

⚠️ **Perdre cette clé interdit définitivement toute mise à jour de
l'application** : Android refuse une mise à jour signée autrement, et il
n'existe aucun recours hors Play App Signing.

---

## 11. Ce que V2 apporterait

L'architecture cible de [`call_tracker_odoo_spec.md`](call_tracker_odoo_spec.md)
n'a de sens qu'au moment de **vendre à des tiers**. Ce qu'elle ajoute :

- **Multi-locataire** : plusieurs Odoo clients, chacun avec son adresse et son
  jeton. En V1, l'app connaît une seule instance.
- **Découplage** : la file Redis absorbe une indisponibilité de l'Odoo client
  sans que le téléphone ait à réessayer pendant des heures.
- **Onboarding self-service** du module chez le client.
- **Position de sous-traitant** au sens de la 18-07 — qui change tout le cadre
  juridique, et qui est le vrai chantier, pas la technique.

**Rien de cela n'est utile tant que le seul locataire, c'est nous.** V1 doit
d'abord prouver deux choses sur le terrain : que la capture tient sur des
téléphones réels pendant des semaines, et que les commerciaux ouvrent
l'application. La seconde décide de la première.
