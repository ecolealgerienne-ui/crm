// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get appTitle => 'Call Tracker';

  @override
  String get commonCancel => 'Annuler';

  @override
  String get commonSave => 'Enregistrer';

  @override
  String get commonRetry => 'Réessayer';

  @override
  String get commonClose => 'Fermer';

  @override
  String commonError(String error) {
    return 'Erreur : $error';
  }

  @override
  String get languageSwitchTooltip => 'Changer de langue';

  @override
  String get languageFrench => 'Français';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageArabic => 'العربية';

  @override
  String get themeSwitchTooltip => 'Changer de thème';

  @override
  String get themeLight => 'Clair';

  @override
  String get themeDark => 'Sombre';

  @override
  String get navCalls => 'Appels';

  @override
  String get navSettings => 'Réglages';

  @override
  String get callsTitle => 'Appels capturés';

  @override
  String get callsEmptyTitle => 'Aucun appel capturé';

  @override
  String get callsEmptyBody =>
      'Les appels apparaîtront ici automatiquement, dès qu\'un appel sera passé ou reçu.';

  @override
  String callsPendingCount(int count) {
    final intl.NumberFormat countNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String countString = countNumberFormat.format(count);

    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$countString appels en attente',
      one: '1 appel en attente',
      zero: 'Tout est synchronisé',
    );
    return '$_temp0';
  }

  @override
  String get callsSyncNow => 'Synchroniser maintenant';

  @override
  String get directionInbound => 'Entrant';

  @override
  String get directionOutbound => 'Sortant';

  @override
  String get directionMissed => 'Manqué';

  @override
  String get syncPending => 'En attente';

  @override
  String get syncSent => 'Synchronisé';

  @override
  String get syncFailed => 'Échec';

  @override
  String syncFailedWithReason(String reason) {
    return 'Échec : $reason';
  }

  @override
  String durationSeconds(int seconds) {
    final intl.NumberFormat secondsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String secondsString = secondsNumberFormat.format(seconds);

    return '$secondsString s';
  }

  @override
  String durationMinutesSeconds(int minutes, int seconds) {
    final intl.NumberFormat minutesNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String minutesString = minutesNumberFormat.format(minutes);
    final intl.NumberFormat secondsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String secondsString = secondsNumberFormat.format(seconds);

    return '$minutesString min $secondsString s';
  }

  @override
  String get settingsTitle => 'Réglages';

  @override
  String get settingsConnectionSection => 'Connexion à Odoo';

  @override
  String get settingsServerUrl => 'Adresse du serveur';

  @override
  String get settingsServerUrlHint => 'https://echangocrm.echango.com';

  @override
  String get settingsServerUrlInvalid =>
      'Adresse invalide — elle doit commencer par https://';

  @override
  String get settingsToken => 'Jeton de l\'appareil';

  @override
  String get settingsTokenHint => 'Collez le jeton généré dans Odoo';

  @override
  String get settingsTokenSet => 'Jeton enregistré';

  @override
  String get settingsTokenMissing =>
      'Aucun jeton — les appels ne seront pas envoyés';

  @override
  String get settingsTokenHelp =>
      'Le jeton se génère dans Odoo, dans CRM puis Call Tracker puis Appareils. Il n\'est affiché qu\'une seule fois.';

  @override
  String get settingsCaptureSection => 'Capture';

  @override
  String get settingsCaptureEnabled => 'Capturer les appels';

  @override
  String get settingsCaptureEnabledHelp =>
      'Désactiver suspend toute capture, sans effacer ce qui est déjà en attente.';

  @override
  String get settingsHoursTitle => 'Plage horaire';

  @override
  String get settingsHoursHelp =>
      'En dehors de cette plage, les appels ne sont pas capturés.';

  @override
  String get settingsHoursFrom => 'À partir de';

  @override
  String get settingsHoursTo => 'Jusqu\'à';

  @override
  String settingsHoursRange(String from, String to) {
    return 'De $from à $to';
  }

  @override
  String get permissionsSection => 'Autorisations';

  @override
  String get permissionsMissingTitle => 'Autorisations manquantes';

  @override
  String get permissionsMissingBody =>
      'Sans l\'accès au journal d\'appels et à l\'état du téléphone, aucun appel ne peut être capturé.';

  @override
  String get permissionsGrant => 'Accorder';

  @override
  String get permissionsGranted => 'Accordées';

  @override
  String get permissionsOpenSettings => 'Ouvrir les réglages du système';

  @override
  String get permissionsPermanentlyDenied =>
      'Refusées définitivement — à réactiver dans les réglages du système.';

  @override
  String get batteryWarningTitle => 'Économiseur de batterie';

  @override
  String get batteryWarningBody =>
      'Le système peut arrêter la capture en arrière-plan. Exclure l\'application de l\'optimisation de batterie fiabilise le suivi.';

  @override
  String get batteryWarningAction => 'Exclure l\'application';

  @override
  String get noteDialogTitle => 'Note après l\'appel';

  @override
  String get noteDialogHint => 'Ce qui s\'est dit, en une phrase';

  @override
  String get noteSave => 'Enregistrer la note';

  @override
  String get noteSkip => 'Sans note';

  @override
  String get noteAdd => 'Ajouter une note';

  @override
  String get noteSaved => 'Note enregistrée';

  @override
  String get noteAwaiting => 'En attente de note';

  @override
  String get permissionsNotifications => 'Notifications';

  @override
  String get permissionsNotificationsBody =>
      'Sans autorisation de notifier, l\'application ne peut pas proposer d\'écrire une note après un appel. La capture, elle, continue.';

  @override
  String get overlaySection => 'Fiche à la sonnerie';

  @override
  String get overlayTitle => 'Afficher la fiche CRM pendant la sonnerie';

  @override
  String get overlayBody =>
      'Le nom du client, sa société, son étape et sa dernière note s\'affichent par-dessus l\'écran d\'appel. Sans cette autorisation, la capture continue normalement.';

  @override
  String get overlayAction => 'Autoriser la surimpression';

  @override
  String get overlayGranted => 'Surimpression autorisée';

  @override
  String get navSearch => 'Recherche';

  @override
  String get searchTitle => 'Rechercher un contact';

  @override
  String get searchHint => 'Numéro ou début de numéro';

  @override
  String get searchAction => 'Rechercher';

  @override
  String get searchNotFound => 'Aucun contact ne correspond à ce numéro';

  @override
  String get searchPrompt =>
      'Saisissez au moins quelques chiffres pour retrouver un contact.';

  @override
  String get searchCompany => 'Société';

  @override
  String get searchStage => 'Étape';

  @override
  String get searchLastNote => 'Dernière note';

  @override
  String get screeningTitle => 'Autoriser la lecture du numéro entrant';

  @override
  String get screeningBody =>
      'Sans ce rôle, Android ne communique pas le numéro à l\'application et la fiche ne peut pas s\'afficher. Il ne fait PAS de l\'application votre téléphone par défaut, et aucun appel n\'est filtré ni bloqué.';

  @override
  String get screeningAction => 'Accorder le rôle';

  @override
  String get screeningGranted => 'Numéro entrant accessible';

  @override
  String get noticeTitle => 'Ce que cette application enregistre';

  @override
  String get noticeIntro =>
      'Ce téléphone est un outil de travail : l\'application transmet vos appels professionnels au CRM de l\'entreprise. Voici exactement quoi, pour qui, et pendant combien de temps.';

  @override
  String get noticeRecordedTitle => 'Ce qui est enregistré';

  @override
  String get noticeRecordedNumber =>
      'Le numéro appelé, ou celui qui vous appelle.';

  @override
  String get noticeRecordedWhen => 'La date, l\'heure et la durée de l\'appel.';

  @override
  String get noticeRecordedDirection =>
      'Le sens de l\'appel : entrant, sortant ou manqué.';

  @override
  String get noticeRecordedNote =>
      'La note que vous écrivez vous-même après l\'appel, si vous en écrivez une.';

  @override
  String get noticeNotRecordedTitle => 'Ce qui n\'est pas enregistré';

  @override
  String get noticeNotRecordedContent =>
      'Le contenu de vos conversations. Rien n\'est écouté, enregistré ni transcrit — l\'application n\'accède pas au microphone.';

  @override
  String get noticeNotRecordedPersonal =>
      'Ni vos messages, ni vos contacts personnels, ni votre position.';

  @override
  String get noticeNotRecordedHours =>
      'Rien en dehors de la plage horaire indiquée dans les réglages.';

  @override
  String get noticeWhoTitle => 'Qui peut les lire';

  @override
  String get noticeWhoYou => 'Vous, sur vos propres appels.';

  @override
  String get noticeWhoManager => 'Votre responsable, sur ceux de son équipe.';

  @override
  String get noticeWhoAudited =>
      'Chaque consultation est elle-même journalisée, y compris celles de votre responsable.';

  @override
  String get noticeHowLongTitle => 'Combien de temps';

  @override
  String noticeRetentionDays(int days) {
    final intl.NumberFormat daysNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String daysString = daysNumberFormat.format(days);

    String _temp0 = intl.Intl.pluralLogic(
      days,
      locale: localeName,
      other: '$daysString jours',
      one: 'un jour',
    );
    return 'Les appels sont effacés automatiquement au bout de $_temp0';
  }

  @override
  String noticeRetentionApprox(int years) {
    final intl.NumberFormat yearsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String yearsString = yearsNumberFormat.format(years);

    String _temp0 = intl.Intl.pluralLogic(
      years,
      locale: localeName,
      other: '$yearsString ans',
      one: 'un an',
    );
    return '— soit environ $_temp0.';
  }

  @override
  String get noticeRetentionUnknown =>
      'La durée est fixée par votre employeur sur le serveur. Elle s\'affichera ici dès le premier appel transmis.';

  @override
  String get noticeRetentionNone =>
      'Aucune suppression automatique n\'est configurée sur ce serveur : les appels sont conservés jusqu\'à suppression manuelle.';

  @override
  String get noticeRightsTitle => 'Vos droits';

  @override
  String get noticeRightsBody =>
      'Vous pouvez demander à consulter ce qui vous concerne, à le faire corriger ou effacer. Adressez-vous à votre responsable ou à l\'administrateur du CRM.';

  @override
  String get noticeAcknowledge => 'J\'ai lu et compris';

  @override
  String get noticeSection => 'Information';

  @override
  String get noticeReadAgain => 'Avis d\'information';

  @override
  String get noticeReadAgainBody =>
      'Ce que l\'application enregistre, qui peut le lire, et combien de temps c\'est conservé.';

  @override
  String get noticeReadAgainAction => 'Relire l\'avis';

  @override
  String get searchClear => 'Effacer';

  @override
  String searchNotFoundFor(String number) {
    return 'Aucun contact ne correspond à $number';
  }

  @override
  String get searchPartialHint =>
      'Un fragment suffit — début, milieu ou fin du numéro.';

  @override
  String searchTooShort(int min) {
    return 'Encore un peu : $min chiffres au minimum.';
  }

  @override
  String get searchCall => 'Appeler';

  @override
  String get contactSheetTitle => 'Fiche client';

  @override
  String get contactSheetNoNote => 'Aucune note pour l\'instant.';
}
