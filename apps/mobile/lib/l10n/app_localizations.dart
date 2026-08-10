import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_en.dart';
import 'app_localizations_fr.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('fr'),
    Locale('en'),
    Locale('ar')
  ];

  /// No description provided for @appTitle.
  ///
  /// In fr, this message translates to:
  /// **'Call Tracker'**
  String get appTitle;

  /// No description provided for @commonCancel.
  ///
  /// In fr, this message translates to:
  /// **'Annuler'**
  String get commonCancel;

  /// No description provided for @commonSave.
  ///
  /// In fr, this message translates to:
  /// **'Enregistrer'**
  String get commonSave;

  /// No description provided for @commonRetry.
  ///
  /// In fr, this message translates to:
  /// **'Réessayer'**
  String get commonRetry;

  /// No description provided for @commonClose.
  ///
  /// In fr, this message translates to:
  /// **'Fermer'**
  String get commonClose;

  /// No description provided for @commonError.
  ///
  /// In fr, this message translates to:
  /// **'Erreur : {error}'**
  String commonError(String error);

  /// No description provided for @languageSwitchTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Changer de langue'**
  String get languageSwitchTooltip;

  /// No description provided for @languageFrench.
  ///
  /// In fr, this message translates to:
  /// **'Français'**
  String get languageFrench;

  /// No description provided for @languageEnglish.
  ///
  /// In fr, this message translates to:
  /// **'English'**
  String get languageEnglish;

  /// No description provided for @languageArabic.
  ///
  /// In fr, this message translates to:
  /// **'العربية'**
  String get languageArabic;

  /// No description provided for @themeSwitchTooltip.
  ///
  /// In fr, this message translates to:
  /// **'Changer de thème'**
  String get themeSwitchTooltip;

  /// No description provided for @themeLight.
  ///
  /// In fr, this message translates to:
  /// **'Clair'**
  String get themeLight;

  /// No description provided for @themeDark.
  ///
  /// In fr, this message translates to:
  /// **'Sombre'**
  String get themeDark;

  /// No description provided for @navCalls.
  ///
  /// In fr, this message translates to:
  /// **'Appels'**
  String get navCalls;

  /// No description provided for @navSettings.
  ///
  /// In fr, this message translates to:
  /// **'Réglages'**
  String get navSettings;

  /// No description provided for @callsTitle.
  ///
  /// In fr, this message translates to:
  /// **'Appels capturés'**
  String get callsTitle;

  /// No description provided for @callsEmptyTitle.
  ///
  /// In fr, this message translates to:
  /// **'Aucun appel capturé'**
  String get callsEmptyTitle;

  /// No description provided for @callsEmptyBody.
  ///
  /// In fr, this message translates to:
  /// **'Les appels apparaîtront ici automatiquement, dès qu\'un appel sera passé ou reçu.'**
  String get callsEmptyBody;

  /// No description provided for @callsPendingCount.
  ///
  /// In fr, this message translates to:
  /// **'{count, plural, =0{Tout est synchronisé} =1{1 appel en attente} other{{count} appels en attente}}'**
  String callsPendingCount(int count);

  /// No description provided for @callsSyncNow.
  ///
  /// In fr, this message translates to:
  /// **'Synchroniser maintenant'**
  String get callsSyncNow;

  /// No description provided for @directionInbound.
  ///
  /// In fr, this message translates to:
  /// **'Entrant'**
  String get directionInbound;

  /// No description provided for @directionOutbound.
  ///
  /// In fr, this message translates to:
  /// **'Sortant'**
  String get directionOutbound;

  /// No description provided for @directionMissed.
  ///
  /// In fr, this message translates to:
  /// **'Manqué'**
  String get directionMissed;

  /// No description provided for @syncPending.
  ///
  /// In fr, this message translates to:
  /// **'En attente'**
  String get syncPending;

  /// No description provided for @syncSent.
  ///
  /// In fr, this message translates to:
  /// **'Synchronisé'**
  String get syncSent;

  /// No description provided for @syncFailed.
  ///
  /// In fr, this message translates to:
  /// **'Échec'**
  String get syncFailed;

  /// No description provided for @syncFailedWithReason.
  ///
  /// In fr, this message translates to:
  /// **'Échec : {reason}'**
  String syncFailedWithReason(String reason);

  /// ⚠️ `format: decimalPattern` est indispensable, pas décoratif. Sans lui, intl rend l'entier par toString() : l'arabe affiche « 8 ث » en chiffres latins juste à côté d'une date en chiffres arabes (٩ أغسطس ٢٠٢٦), que DateFormat localise, lui. Constaté à l'écran le 2026-08-09.
  ///
  /// In fr, this message translates to:
  /// **'{seconds} s'**
  String durationSeconds(int seconds);

  /// No description provided for @durationMinutesSeconds.
  ///
  /// In fr, this message translates to:
  /// **'{minutes} min {seconds} s'**
  String durationMinutesSeconds(int minutes, int seconds);

  /// No description provided for @settingsTitle.
  ///
  /// In fr, this message translates to:
  /// **'Réglages'**
  String get settingsTitle;

  /// No description provided for @settingsConnectionSection.
  ///
  /// In fr, this message translates to:
  /// **'Connexion à Odoo'**
  String get settingsConnectionSection;

  /// No description provided for @settingsServerUrl.
  ///
  /// In fr, this message translates to:
  /// **'Adresse du serveur'**
  String get settingsServerUrl;

  /// No description provided for @settingsServerUrlHint.
  ///
  /// In fr, this message translates to:
  /// **'https://echangocrm.echango.com'**
  String get settingsServerUrlHint;

  /// No description provided for @settingsServerUrlInvalid.
  ///
  /// In fr, this message translates to:
  /// **'Adresse invalide — elle doit commencer par https://'**
  String get settingsServerUrlInvalid;

  /// No description provided for @settingsToken.
  ///
  /// In fr, this message translates to:
  /// **'Jeton de l\'appareil'**
  String get settingsToken;

  /// No description provided for @settingsTokenHint.
  ///
  /// In fr, this message translates to:
  /// **'Collez le jeton généré dans Odoo'**
  String get settingsTokenHint;

  /// No description provided for @settingsTokenSet.
  ///
  /// In fr, this message translates to:
  /// **'Jeton enregistré'**
  String get settingsTokenSet;

  /// No description provided for @settingsTokenMissing.
  ///
  /// In fr, this message translates to:
  /// **'Aucun jeton — les appels ne seront pas envoyés'**
  String get settingsTokenMissing;

  /// No description provided for @settingsTokenHelp.
  ///
  /// In fr, this message translates to:
  /// **'Le jeton se génère dans Odoo, dans CRM puis Call Tracker puis Appareils. Il n\'est affiché qu\'une seule fois.'**
  String get settingsTokenHelp;

  /// No description provided for @settingsCaptureSection.
  ///
  /// In fr, this message translates to:
  /// **'Capture'**
  String get settingsCaptureSection;

  /// No description provided for @settingsCaptureEnabled.
  ///
  /// In fr, this message translates to:
  /// **'Capturer les appels'**
  String get settingsCaptureEnabled;

  /// No description provided for @settingsCaptureEnabledHelp.
  ///
  /// In fr, this message translates to:
  /// **'Désactiver suspend toute capture, sans effacer ce qui est déjà en attente.'**
  String get settingsCaptureEnabledHelp;

  /// No description provided for @settingsHoursTitle.
  ///
  /// In fr, this message translates to:
  /// **'Plage horaire'**
  String get settingsHoursTitle;

  /// No description provided for @settingsHoursHelp.
  ///
  /// In fr, this message translates to:
  /// **'En dehors de cette plage, les appels ne sont pas capturés.'**
  String get settingsHoursHelp;

  /// No description provided for @settingsHoursFrom.
  ///
  /// In fr, this message translates to:
  /// **'À partir de'**
  String get settingsHoursFrom;

  /// No description provided for @settingsHoursTo.
  ///
  /// In fr, this message translates to:
  /// **'Jusqu\'à'**
  String get settingsHoursTo;

  /// No description provided for @settingsHoursRange.
  ///
  /// In fr, this message translates to:
  /// **'De {from} à {to}'**
  String settingsHoursRange(String from, String to);

  /// No description provided for @permissionsSection.
  ///
  /// In fr, this message translates to:
  /// **'Autorisations'**
  String get permissionsSection;

  /// No description provided for @permissionsMissingTitle.
  ///
  /// In fr, this message translates to:
  /// **'Autorisations manquantes'**
  String get permissionsMissingTitle;

  /// No description provided for @permissionsMissingBody.
  ///
  /// In fr, this message translates to:
  /// **'Sans l\'accès au journal d\'appels et à l\'état du téléphone, aucun appel ne peut être capturé.'**
  String get permissionsMissingBody;

  /// No description provided for @permissionsGrant.
  ///
  /// In fr, this message translates to:
  /// **'Accorder'**
  String get permissionsGrant;

  /// No description provided for @permissionsGranted.
  ///
  /// In fr, this message translates to:
  /// **'Accordées'**
  String get permissionsGranted;

  /// No description provided for @permissionsOpenSettings.
  ///
  /// In fr, this message translates to:
  /// **'Ouvrir les réglages du système'**
  String get permissionsOpenSettings;

  /// No description provided for @permissionsPermanentlyDenied.
  ///
  /// In fr, this message translates to:
  /// **'Refusées définitivement — à réactiver dans les réglages du système.'**
  String get permissionsPermanentlyDenied;

  /// No description provided for @batteryWarningTitle.
  ///
  /// In fr, this message translates to:
  /// **'Économiseur de batterie'**
  String get batteryWarningTitle;

  /// No description provided for @batteryWarningBody.
  ///
  /// In fr, this message translates to:
  /// **'Le système peut arrêter la capture en arrière-plan. Exclure l\'application de l\'optimisation de batterie fiabilise le suivi.'**
  String get batteryWarningBody;

  /// No description provided for @batteryWarningAction.
  ///
  /// In fr, this message translates to:
  /// **'Exclure l\'application'**
  String get batteryWarningAction;

  /// No description provided for @noteDialogTitle.
  ///
  /// In fr, this message translates to:
  /// **'Note après l\'appel'**
  String get noteDialogTitle;

  /// No description provided for @noteDialogHint.
  ///
  /// In fr, this message translates to:
  /// **'Ce qui s\'est dit, en une phrase'**
  String get noteDialogHint;

  /// No description provided for @noteSave.
  ///
  /// In fr, this message translates to:
  /// **'Enregistrer la note'**
  String get noteSave;

  /// No description provided for @noteSkip.
  ///
  /// In fr, this message translates to:
  /// **'Sans note'**
  String get noteSkip;

  /// No description provided for @noteAdd.
  ///
  /// In fr, this message translates to:
  /// **'Ajouter une note'**
  String get noteAdd;

  /// No description provided for @noteSaved.
  ///
  /// In fr, this message translates to:
  /// **'Note enregistrée'**
  String get noteSaved;

  /// No description provided for @noteAwaiting.
  ///
  /// In fr, this message translates to:
  /// **'En attente de note'**
  String get noteAwaiting;

  /// No description provided for @permissionsNotifications.
  ///
  /// In fr, this message translates to:
  /// **'Notifications'**
  String get permissionsNotifications;

  /// No description provided for @permissionsNotificationsBody.
  ///
  /// In fr, this message translates to:
  /// **'Sans autorisation de notifier, l\'application ne peut pas proposer d\'écrire une note après un appel. La capture, elle, continue.'**
  String get permissionsNotificationsBody;

  /// No description provided for @overlaySection.
  ///
  /// In fr, this message translates to:
  /// **'Fiche à la sonnerie'**
  String get overlaySection;

  /// No description provided for @overlayTitle.
  ///
  /// In fr, this message translates to:
  /// **'Afficher la fiche CRM pendant la sonnerie'**
  String get overlayTitle;

  /// No description provided for @overlayBody.
  ///
  /// In fr, this message translates to:
  /// **'Le nom du client, sa société, son étape et sa dernière note s\'affichent par-dessus l\'écran d\'appel. Sans cette autorisation, la capture continue normalement.'**
  String get overlayBody;

  /// No description provided for @overlayAction.
  ///
  /// In fr, this message translates to:
  /// **'Autoriser la surimpression'**
  String get overlayAction;

  /// No description provided for @overlayGranted.
  ///
  /// In fr, this message translates to:
  /// **'Surimpression autorisée'**
  String get overlayGranted;

  /// No description provided for @navSearch.
  ///
  /// In fr, this message translates to:
  /// **'Recherche'**
  String get navSearch;

  /// No description provided for @searchTitle.
  ///
  /// In fr, this message translates to:
  /// **'Rechercher un contact'**
  String get searchTitle;

  /// No description provided for @searchHint.
  ///
  /// In fr, this message translates to:
  /// **'Numéro ou début de numéro'**
  String get searchHint;

  /// No description provided for @searchAction.
  ///
  /// In fr, this message translates to:
  /// **'Rechercher'**
  String get searchAction;

  /// No description provided for @searchNotFound.
  ///
  /// In fr, this message translates to:
  /// **'Aucun contact ne correspond à ce numéro'**
  String get searchNotFound;

  /// No description provided for @searchPrompt.
  ///
  /// In fr, this message translates to:
  /// **'Saisissez au moins quelques chiffres pour retrouver un contact.'**
  String get searchPrompt;

  /// No description provided for @searchCompany.
  ///
  /// In fr, this message translates to:
  /// **'Société'**
  String get searchCompany;

  /// No description provided for @searchStage.
  ///
  /// In fr, this message translates to:
  /// **'Étape'**
  String get searchStage;

  /// No description provided for @searchLastNote.
  ///
  /// In fr, this message translates to:
  /// **'Dernière note'**
  String get searchLastNote;

  /// No description provided for @screeningTitle.
  ///
  /// In fr, this message translates to:
  /// **'Autoriser la lecture du numéro entrant'**
  String get screeningTitle;

  /// No description provided for @screeningBody.
  ///
  /// In fr, this message translates to:
  /// **'Sans ce rôle, Android ne communique pas le numéro à l\'application et la fiche ne peut pas s\'afficher. Il ne fait PAS de l\'application votre téléphone par défaut, et aucun appel n\'est filtré ni bloqué.'**
  String get screeningBody;

  /// No description provided for @screeningAction.
  ///
  /// In fr, this message translates to:
  /// **'Accorder le rôle'**
  String get screeningAction;

  /// No description provided for @screeningGranted.
  ///
  /// In fr, this message translates to:
  /// **'Numéro entrant accessible'**
  String get screeningGranted;

  /// No description provided for @noticeTitle.
  ///
  /// In fr, this message translates to:
  /// **'Ce que cette application enregistre'**
  String get noticeTitle;

  /// No description provided for @noticeIntro.
  ///
  /// In fr, this message translates to:
  /// **'Ce téléphone est un outil de travail : l\'application transmet vos appels professionnels au CRM de l\'entreprise. Voici exactement quoi, pour qui, et pendant combien de temps.'**
  String get noticeIntro;

  /// No description provided for @noticeRecordedTitle.
  ///
  /// In fr, this message translates to:
  /// **'Ce qui est enregistré'**
  String get noticeRecordedTitle;

  /// No description provided for @noticeRecordedNumber.
  ///
  /// In fr, this message translates to:
  /// **'Le numéro appelé, ou celui qui vous appelle.'**
  String get noticeRecordedNumber;

  /// No description provided for @noticeRecordedWhen.
  ///
  /// In fr, this message translates to:
  /// **'La date, l\'heure et la durée de l\'appel.'**
  String get noticeRecordedWhen;

  /// No description provided for @noticeRecordedDirection.
  ///
  /// In fr, this message translates to:
  /// **'Le sens de l\'appel : entrant, sortant ou manqué.'**
  String get noticeRecordedDirection;

  /// No description provided for @noticeRecordedNote.
  ///
  /// In fr, this message translates to:
  /// **'La note que vous écrivez vous-même après l\'appel, si vous en écrivez une.'**
  String get noticeRecordedNote;

  /// No description provided for @noticeNotRecordedTitle.
  ///
  /// In fr, this message translates to:
  /// **'Ce qui n\'est pas enregistré'**
  String get noticeNotRecordedTitle;

  /// No description provided for @noticeNotRecordedContent.
  ///
  /// In fr, this message translates to:
  /// **'Le contenu de vos conversations. Rien n\'est écouté, enregistré ni transcrit — l\'application n\'accède pas au microphone.'**
  String get noticeNotRecordedContent;

  /// No description provided for @noticeNotRecordedPersonal.
  ///
  /// In fr, this message translates to:
  /// **'Ni vos messages, ni vos contacts personnels, ni votre position.'**
  String get noticeNotRecordedPersonal;

  /// No description provided for @noticeNotRecordedHours.
  ///
  /// In fr, this message translates to:
  /// **'Rien en dehors de la plage horaire indiquée dans les réglages.'**
  String get noticeNotRecordedHours;

  /// No description provided for @noticeWhoTitle.
  ///
  /// In fr, this message translates to:
  /// **'Qui peut les lire'**
  String get noticeWhoTitle;

  /// No description provided for @noticeWhoYou.
  ///
  /// In fr, this message translates to:
  /// **'Vous, sur vos propres appels.'**
  String get noticeWhoYou;

  /// No description provided for @noticeWhoManager.
  ///
  /// In fr, this message translates to:
  /// **'Votre responsable, sur ceux de son équipe.'**
  String get noticeWhoManager;

  /// No description provided for @noticeWhoAudited.
  ///
  /// In fr, this message translates to:
  /// **'Chaque consultation est elle-même journalisée, y compris celles de votre responsable.'**
  String get noticeWhoAudited;

  /// No description provided for @noticeHowLongTitle.
  ///
  /// In fr, this message translates to:
  /// **'Combien de temps'**
  String get noticeHowLongTitle;

  /// No description provided for @noticeRetentionDays.
  ///
  /// In fr, this message translates to:
  /// **'Les appels sont effacés automatiquement au bout de {days, plural, =1{un jour} other{{days} jours}}'**
  String noticeRetentionDays(int days);

  /// No description provided for @noticeRetentionApprox.
  ///
  /// In fr, this message translates to:
  /// **'— soit environ {years, plural, =1{un an} other{{years} ans}}.'**
  String noticeRetentionApprox(int years);

  /// No description provided for @noticeRetentionUnknown.
  ///
  /// In fr, this message translates to:
  /// **'La durée est fixée par votre employeur sur le serveur. Elle s\'affichera ici dès le premier appel transmis.'**
  String get noticeRetentionUnknown;

  /// No description provided for @noticeRetentionNone.
  ///
  /// In fr, this message translates to:
  /// **'Aucune suppression automatique n\'est configurée sur ce serveur : les appels sont conservés jusqu\'à suppression manuelle.'**
  String get noticeRetentionNone;

  /// No description provided for @noticeRightsTitle.
  ///
  /// In fr, this message translates to:
  /// **'Vos droits'**
  String get noticeRightsTitle;

  /// No description provided for @noticeRightsBody.
  ///
  /// In fr, this message translates to:
  /// **'Vous pouvez demander à consulter ce qui vous concerne, à le faire corriger ou effacer. Adressez-vous à votre responsable ou à l\'administrateur du CRM.'**
  String get noticeRightsBody;

  /// No description provided for @noticeAcknowledge.
  ///
  /// In fr, this message translates to:
  /// **'J\'ai lu et compris'**
  String get noticeAcknowledge;

  /// No description provided for @noticeSection.
  ///
  /// In fr, this message translates to:
  /// **'Information'**
  String get noticeSection;

  /// No description provided for @noticeReadAgain.
  ///
  /// In fr, this message translates to:
  /// **'Avis d\'information'**
  String get noticeReadAgain;

  /// No description provided for @noticeReadAgainBody.
  ///
  /// In fr, this message translates to:
  /// **'Ce que l\'application enregistre, qui peut le lire, et combien de temps c\'est conservé.'**
  String get noticeReadAgainBody;

  /// No description provided for @noticeReadAgainAction.
  ///
  /// In fr, this message translates to:
  /// **'Relire l\'avis'**
  String get noticeReadAgainAction;

  /// No description provided for @searchClear.
  ///
  /// In fr, this message translates to:
  /// **'Effacer'**
  String get searchClear;

  /// No description provided for @searchNotFoundFor.
  ///
  /// In fr, this message translates to:
  /// **'Aucun contact ne correspond à {number}'**
  String searchNotFoundFor(String number);

  /// No description provided for @searchPartialHint.
  ///
  /// In fr, this message translates to:
  /// **'Un fragment suffit — début, milieu ou fin du numéro.'**
  String get searchPartialHint;

  /// No description provided for @searchTooShort.
  ///
  /// In fr, this message translates to:
  /// **'Encore un peu : {min} chiffres au minimum.'**
  String searchTooShort(int min);

  /// No description provided for @searchCall.
  ///
  /// In fr, this message translates to:
  /// **'Appeler'**
  String get searchCall;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['ar', 'en', 'fr'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return AppLocalizationsAr();
    case 'en':
      return AppLocalizationsEn();
    case 'fr':
      return AppLocalizationsFr();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
