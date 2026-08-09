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
}
