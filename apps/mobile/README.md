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

## Phase 2 — pas commencé

Caller ID en surimpression (`SYSTEM_ALERT_WINDOW`), recherche de contact,
tableau de bord.
