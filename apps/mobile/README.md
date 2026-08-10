# Call Tracker — application mobile

Capture automatique des appels d'un commercial et remise à l'addon Odoo
`call_tracker`, sans saisie manuelle.

Spécification : [`docs/call_tracker_odoo_spec.md`](../../docs/call_tracker_odoo_spec.md).
Contrat de l'API : [`addons/call_tracker/README.md`](../../addons/call_tracker/README.md).

## Architecture — et pourquoi le métier est en Kotlin

```
┌─ Flutter (lib/) ─────────────┐   canal   ┌─ Android (android/…/kotlin) ─────┐
│ thème, i18n fr/en/ar,        │◀─────────▶│ CallStateReceiver  → PHONE_STATE │
│ liste des appels, réglages   │  lecture  │ CallLogScanner     → CallLog     │
│                              │  d'état   │ CallStore (SQLite) → file locale │
└──────────────────────────────┘           │ SyncWorker         → POST Odoo   │
                                            └──────────────────────────────────┘
```

**Flutter ne voit jamais passer un appel.** La capture, la file et l'envoi
vivent entièrement côté natif, parce qu'un appel arrive presque toujours alors
que l'application est fermée et que le moteur Flutter n'existe pas. Une file
écrite en Dart ne serait jamais alimentée — c'est-à-dire jamais dans le cas
normal. Le canal de plateforme ne transporte que de la lecture d'état et des
réglages.

C'est aussi pourquoi la configuration (URL, jeton) est rangée en
`EncryptedSharedPreferences` côté Kotlin et non en `flutter_secure_storage` :
c'est le worker qui doit la lire.

## Conventions reprises de l'app echango Promo

| | |
|---|---|
| Socle | Flutter + Riverpod |
| Thème | `ColorScheme` construit **à la main** — jamais `fromSeed`, qui teinte tous les neutres —, `ThemeExtension` pour les couleurs sémantiques, `AppRadii` 8/16/24, transition unique 180 ms |
| Typo | Cairo (titres) + IBM Plex Sans Arabic (corps) : couple choisi pour son jeu arabe complet |
| i18n | `.arb` fr / en / ar, `generate: true` |
| Langue et thème | pilotés par l'utilisateur, **pas** par le réglage système |

Deux écarts assumés :

- **Identité visuelle propre.** Bleu ardoise au lieu du terracotta de Promo :
  celui-ci est une app grand public tournée vers la découverte, celle-ci un
  outil interne qu'on ouvre pour vérifier que son suivi remonte. Le safran de
  Promo est conservé en accent secondaire — c'est le fil qui rattache les deux
  applications à la même suite.
- **Pas de go_router.** Deux écrans, aucun lien profond, aucune redirection
  conditionnelle. À reprendre en phase 2.

## Développer

```bash
flutter pub get
flutter analyze && flutter test
flutter run                       # ou : flutter build apk --debug
```

### Éprouver la capture sur émulateur

Un émulateur sait simuler un appel : `PHONE_STATE` est réellement diffusé et
`CallLog` réellement écrit. Aucun téléphone ni carte SIM n'est nécessaire pour
valider la mécanique.

```bash
adb install -r -g build/app/outputs/flutter-apk/app-debug.apk

# Provisionnement — receveur de DÉBOGAGE uniquement (src/debug/, absent des
# APK de release). Voir DevProvisionReceiver.kt.
adb shell am broadcast -a com.echango.call_tracker.DEV_PROVISION \
  -n com.echango.call_tracker/.DevProvisionReceiver \
  --es url "http://10.0.2.2:8169" --es token "<jeton>" \
  --ez enabled true --ei fromHour 0 --ei toHour 24 --ez resetCursor true

# Appel entrant simulé
adb emu gsm call 6039963829
adb emu gsm accept 6039963829
adb emu gsm cancel 6039963829

adb logcat -s CallTracker
```

`10.0.2.2` est l'hôte vu depuis l'émulateur. Le trafic en clair n'est autorisé
que dans la variante de débogage : un APK de release ne peut pas parler en
`http`, quelle que soit l'adresse saisie.

⚠️ La plage horaire par défaut est 8 h – 19 h. Un essai en soirée ne capture
rien tant qu'on ne l'a pas élargie — d'où `fromHour 0 / toHour 24` ci-dessus.

## Ce qui est éprouvé, et ce qui ne peut pas l'être ici

Validé de bout en bout sur émulateur (Android 16, 2026-08-09) : appel entrant
simulé → `PHONE_STATE` → lecture de `CallLog` → file locale → `POST` vers Odoo
→ enregistrement rattaché au bon contact et à la bonne piste. Interface
vérifiée en français, en mode sombre, et en arabe (mise en page RTL, numéro
maintenu en LTR).

**L'émulateur valide le mécanisme, pas la durabilité.** Il ne dira rien de la
survie du service aux optimisations de batterie des surcouches constructeur
(Samsung, Xiaomi), qui est le mode de défaillance le plus courant de ce type
d'application. C'est la raison de la carte d'avertissement dans les réglages,
et cela reste à éprouver sur un vrai téléphone, sur plusieurs jours.

## La note après l'appel

Une notification propose de noter ce qui vient d'être dit. L'appel est
**retenu deux minutes** dans la file locale, le temps de la saisie, puis part —
avec la note si elle a été écrite, sans elle sinon.

Trois choix qui ne se devinent pas :

- **Une notification, pas un écran qui s'impose.** L'app n'est presque jamais
  au premier plan quand un appel se termine ; surgir par-dessus l'écran
  d'accueil juste après un raccrochage serait une intrusion.
- **La retenue est bornée.** Si le commercial ne répond pas, l'appel part sans
  note. Une fonctionnalité de confort ne doit pas pouvoir retenir la donnée
  principale. Un rendez-vous WorkManager est posé à l'échéance, sinon l'appel
  attendrait le suivant pour remonter.
- **Un bouton de rattrapage dans la liste**, parce que la notification a pu
  être balayée ou l'autorisation de notifier refusée — sans lui la note
  deviendrait inaccessible dans les deux cas.

Côté Odoo, la note est publiée dans le fil de la piste, et **revient au
Caller ID de l'appel suivant**.

## Le suivi commence à l'activation, jamais avant

**L'historique d'appels du téléphone n'est jamais remonté.** Le curseur de
balayage est posé à l'instant où la capture est activée ; tout ce qui précède
reste sur l'appareil.

Deux barrières, volontairement redondantes :

| Où | Quand |
|---|---|
| `MainActivity.saveSettings` | À chaque passage de la capture de désactivé à activé — le repère est posé là |
| `CallLogScanner.balayer` | Filet : un curseur à `0` signifie « jamais posé ». Ce balayage-là ne remonte rien, il pose le repère et sort |

La seconde existe parce que l'invariant doit tenir **là où il est consommé**.
Une restauration de sauvegarde, des préférences recopiées ou un
provisionnement automatisé laisseraient un zéro, et un zéro ici ne fait pas
rien : il verse dans le CRM tout le passé téléphonique du commercial.

⚠️ **Le défaut était invisible en développement** : un émulateur neuf n'a
qu'une poignée d'appels de test. Constaté le 2026-08-10 en branchant un vrai
téléphone — **3000 appels** dans son journal, tous candidats au départ. Il ne
se serait vu que sur le premier téléphone de production, une fois les données
parties.

C'est aussi une exigence de conformité, pas seulement d'hygiène : l'avis
d'information promet que « l'application transmet vos appels professionnels »,
au présent. Une collecte rétroactive de cette ampleur ne serait pas
proportionnée à la finalité (loi 18-07).

Corollaire assumé : couper puis rallumer la capture repose le repère. Les
appels de l'intervalle ne remontent pas — couper est un acte délibéré, le
rallumer ne doit pas rattraper ce qu'on avait choisi de ne pas journaliser.

Le drapeau de débogage `resetCursor` pose `1`, pas `0`, pour rester distinct
du sentinelle et continuer à rejouer tout un journal d'émulateur.

## Rechercher, puis appeler

L'onglet Recherche prend un **fragment** de numéro — début, milieu ou fin — et
rend une liste. Chaque résultat porte un bouton *Appeler*.

- **Minimum 4 chiffres**, aligné sur `FRAGMENT_MIN` côté Odoo. Le contrôle est
  fait des deux côtés : ici pour dire *pourquoi* rien ne part, là-bas parce
  qu'un serveur ne fait confiance à aucun client. Un test fige la valeur.
- **`ACTION_DIAL`, pas `ACTION_CALL`.** Le numéro est composé, l'appel n'est
  pas lancé : c'est le commercial qui appuie sur le vert. `ACTION_CALL`
  exigerait la permission `CALL_PHONE` — une permission dangereuse de plus sur
  une application qui demande déjà `READ_CALL_LOG` et le rôle de filtrage — et
  donnerait à l'app le pouvoir d'appeler toute seule. Sur une vraie ligne
  professionnelle, un bogue y coûterait de l'argent. Un appui de plus, et la
  chaîne de capture prend le relais comme pour n'importe quel appel.
- **Sans cache.** [ContactCache] est indexé par numéro complet ; un fragment
  n'en est pas un, et garder des listes ferait afficher un carnet périmé — un
  contact créé il y a cinq minutes resterait introuvable. Le cache sert la
  sonnerie, où la même fiche revient souvent.

## Le cache des fiches contact

Une fiche trouvée est gardée **30 minutes**, un numéro inconnu **2 minutes
seulement** (`ContactCache.DUREE_INCONNU_MILLIS`). Les deux durées n'ont rien
à voir et il ne faut pas les réunifier.

Constaté le 2026-08-10 : avec 30 minutes pour les deux, un numéro appelé avant
d'être saisi dans le CRM restait « inconnu » à l'écran une demi-heure durant,
alors que la fiche existait depuis cinq minutes. Le Caller ID ne s'affichait
pas et rien ne le signalait — l'application n'appelait même plus le serveur.

Ce n'est pas un cas de laboratoire : la qualification est manuelle côté Odoo,
donc « un inconnu appelle → je crée le client → il rappelle » est la séquence
**normale**. Deux minutes couvrent le rappel immédiat d'un démarcheur, seul
cas que ce cache devait éviter.

## L'avis d'information

Un écran barre l'accès aux onglets au premier lancement : ce qui est
enregistré, ce qui ne l'est pas, qui peut le lire, combien de temps. Il reste
consultable depuis *Réglages > Information*.

Le fond et le raisonnement sont dans `docs/CONFORMITE_DONNEES_APPELS.md` §6.
Côté code, trois points valent d'être connus avant d'y toucher :

- **`noticeVersion` dans `core_providers.dart`.** L'accusé de lecture est un
  entier, pas un booléen. À incrémenter dès que le **fond** change — ce qui
  est capturé, qui le lit, combien de temps — pour que chacun revoie l'avis.
  Une reformulation ou une traduction ne le change pas.
- **La durée de conservation vient du serveur**, jamais d'une constante :
  Odoo renvoie `retention_days` à chaque appel accepté, `SyncWorker` la range
  dans `SecureSettings`. « Pas encore reçue » et « aucune purge » valent zéro
  toutes les deux dans le code et disent l'inverse au lecteur — l'écran les
  distingue, `retentionKnown` sert à cela.
- **Le sélecteur de langue est sur l'écran**, parce qu'en porte c'est le seul
  écran atteignable.

⚠️ La capture est native : un téléphone configuré par un tiers capture avant
que quiconque ait vu cet écran. Aucun code ne peut y remédier — la remise en
main propre reste une étape humaine.

## Phase 2 — pas commencé

Caller ID en surimpression (`SYSTEM_ALERT_WINDOW`), recherche de contact,
tableau de bord.
