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

| Route | Méthode | Rôle | Périmètre des données rendues |
|---|---|---|---|
| `/call_tracker/log_call` | POST | Journaliser un appel | écrit seulement ; attribué au commercial de l'appareil |
| `/call_tracker/contact/<numero>` | GET | Fiche d'un numéro complet — Caller ID | **tout le carnet**, toujours |
| `/call_tracker/contacts/<fragment>` | GET | Recherche par fragment — liste | selon `CALL_TRACKER_SEARCH_SCOPE` |
| `/call_tracker/activities` | GET | Les appels programmés dans le CRM | **le commercial de l'appareil, toujours** |
| `/call_tracker/activity/<id>/done` | POST | Clôturer une activité | ses activités à lui, vérifié au serveur |

Le détail de chaque contrat, ses bornes et ses pièges : [`addons/call_tracker/README.md`](../addons/call_tracker/README.md).

### 2.1 Où s'applique `CALL_TRACKER_SEARCH_SCOPE`, et où il ne s'applique pas

**Une seule route le consulte : la recherche par fragment.** Les quatre autres
ne l'appellent jamais, et ce n'est pas un oubli — chacune a sa propre raison.

**`/contacts/<fragment>` — réglable.** C'est la seule route qui parcourt le
carnet d'adresses à partir d'un bout de numéro, donc la seule où le périmètre
soit une question ouverte. `all` par défaut, `own` pour restreindre aux clients
du commercial. Voir §6.

**`/activities` — cloisonné par la donnée, sans réglage possible.** Une
activité *est* assignée à un utilisateur ; le jeton désigne l'appareil, donc le
commercial. La requête filtre `user_id = <commercial de l'appareil>` et il n'y
a rien à choisir. Un réglage ici n'aurait aucun sens : il ne pourrait
qu'*élargir* le périmètre au-delà de ce que le CRM a assigné.

**`/contact/<numero>` — délibérément ouverte, quel que soit le réglage.** Quand
le téléphone sonne, il faut savoir qui appelle, même si la fiche appartient à
un collègue en congé. Afficher « inconnu » ferait décrocher à l'aveugle, ce qui
est pire que de ne rien afficher. Elle exige un numéro **complet** : on ne
parcourt rien, on identifie un correspondant qui est déjà en train d'appeler.

**`/log_call` — n'a pas de périmètre de lecture.** Elle écrit, et n'accuse
réception qu'avec `call_id`, `linked_record` et `retention_days`. Aucun nom, ni
libellé de piste : une route d'écriture n'a pas à devenir une fuite de lecture.

### 2.2 Ce que l'application déclare ne fait jamais autorité

Trois mécanismes distincts, un seul principe : **le serveur ne croit pas
l'app**. C'est le pendant concret du « moindre privilège » de la spec
d'origine, et c'est ce qui rend acceptable qu'un jeton d'appareil circule sur
des téléphones qu'on ne maîtrise pas.

**L'identité du commercial n'est pas envoyée.** La spec d'origine faisait
transmettre par l'app un `rep_external_id`. Il a disparu de la charge utile :
`user_id` est déduit de `appareil.user_id`, côté serveur. **Une application ne
peut donc pas se déclarer être quelqu'un d'autre**, ce que le champ d'origine
permettait — un jeton volé aurait pu attribuer des appels à n'importe qui.

**La propriété d'une activité est revérifiée à chaque clôture.** L'app envoie
un identifiant ; rien n'empêche un jeton volé d'en envoyer d'autres, au hasard.
Le contrôleur ne se contente donc pas de clôturer ce qu'on lui désigne :

```python
activite = self.env['mail.activity'].sudo().browse(identifiant)
if not activite.exists() or activite.user_id != commercial:
    return False          # -> HTTP 404
```

**Le même 404 dans les deux cas**, et c'est le point : distinguer
« inexistante » de « pas la vôtre » renseignerait sur le portefeuille des
collègues, un identifiant à la fois. Sans ce contrôle, un appareil clôturerait
les tâches de n'importe qui — et une tâche qui disparaît de la liste d'un
collègue ne se remarque pas, elle s'oublie. Deux tests le couvrent, dont un
qui vérifie qu'une activité étrangère **survit** à la tentative.

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
| Collision entre pays | **Refusée** quand les deux numéros portent un indicatif différent — `+971555123456` ne désigne plus le client `+213555123456`. Un numéro national ne déclenche rien : on ignore son pays | 2026-08-10 |
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

287 tests Odoo, 44 tests Flutter, **29 tests Kotlin**, 0 échec. Les trois
suites tournent à chaque poussée (`.github/workflows/tests.yml`).

Chaîne validée de bout en bout sur émulateur **et sur un téléphone réel**
(OnePlus 7 Pro, Android 12, 2026-08-10) : appel → capture → file → Wi-Fi →
Odoo → rattachement au bon contact → note → retour au Caller ID.

### Le déséquilibre corrigé le 2026-08-10

Jusqu'à cette date, **la couche Kotlin n'avait aucun test** : 2 084 lignes,
dont la file, le curseur de balayage, la classification des erreurs et le
stockage du jeton. Les tests Dart s'arrêtaient au `MethodChannel`, qu'ils
remplacent par un mock.

Ce n'était pas une lacune répartie au hasard. Les 262 tests existants
couvraient la moitié du système qui échoue **bruyamment** — codes HTTP,
contraintes, droits — et zéro couvrait celle qui échoue **en silence**. Une
revue en six volets a trouvé quatre défauts critiques ; les quatre étaient
côté Kotlin, aucun n'était visible à l'écran, et chacun aurait été pris par un
test unitaire pur :

| Défaut | Ce que voyait l'utilisateur |
|---|---|
| Le balayage héritait de la contrainte réseau du worker d'envoi | Hors réseau, rien n'était capturé — alors que la file locale est présentée comme le rempart |
| Le rendez-vous d'envoi différé était jeté par `KEEP` | Le dernier appel de la journée dormait jusqu'au lendemain |
| Le curseur avançait jusqu'au présent | Un appel long apparu derrière un appel court n'était jamais lu |
| Un curseur parti dans le futur ne redescendait jamais | Capture morte définitivement, « Tout est synchronisé » à l'écran |

**Ce qu'aucun banc ne dira** : la survie en arrière-plan sur plusieurs jours.
On sait déjà qu'OxygenOS gèle l'application écran éteint — observé douze
secondes après l'installation. Le balayage périodique de quinze minutes et la
relance à l'ouverture sont les deux filets posés depuis ; leur efficacité
réelle reste à mesurer sur le terrain.

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
