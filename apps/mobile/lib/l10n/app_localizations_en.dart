// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Call Tracker';

  @override
  String get commonCancel => 'Cancel';

  @override
  String get commonSave => 'Save';

  @override
  String get commonRetry => 'Retry';

  @override
  String get commonClose => 'Close';

  @override
  String commonError(String error) {
    return 'Error: $error';
  }

  @override
  String get languageSwitchTooltip => 'Change language';

  @override
  String get languageFrench => 'Français';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageArabic => 'العربية';

  @override
  String get themeSwitchTooltip => 'Change theme';

  @override
  String get themeLight => 'Light';

  @override
  String get themeDark => 'Dark';

  @override
  String get navCalls => 'Calls';

  @override
  String get navSettings => 'Settings';

  @override
  String get callsTitle => 'Captured calls';

  @override
  String get callsEmptyTitle => 'No calls captured yet';

  @override
  String get callsEmptyBody =>
      'Calls will appear here automatically, as soon as one is made or received.';

  @override
  String callsPendingCount(int count) {
    final intl.NumberFormat countNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String countString = countNumberFormat.format(count);

    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$countString calls pending',
      one: '1 call pending',
      zero: 'Everything is synced',
    );
    return '$_temp0';
  }

  @override
  String get callsSyncNow => 'Sync now';

  @override
  String get directionInbound => 'Incoming';

  @override
  String get directionOutbound => 'Outgoing';

  @override
  String get directionMissed => 'Missed';

  @override
  String get syncPending => 'Pending';

  @override
  String get syncSent => 'Synced';

  @override
  String get syncFailed => 'Failed';

  @override
  String syncFailedWithReason(String reason) {
    return 'Failed: $reason';
  }

  @override
  String durationSeconds(int seconds) {
    final intl.NumberFormat secondsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String secondsString = secondsNumberFormat.format(seconds);

    return '${secondsString}s';
  }

  @override
  String durationMinutesSeconds(int minutes, int seconds) {
    final intl.NumberFormat minutesNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String minutesString = minutesNumberFormat.format(minutes);
    final intl.NumberFormat secondsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String secondsString = secondsNumberFormat.format(seconds);

    return '${minutesString}m ${secondsString}s';
  }

  @override
  String get settingsTitle => 'Settings';

  @override
  String get settingsConnectionSection => 'Odoo connection';

  @override
  String get settingsServerUrl => 'Server address';

  @override
  String get settingsServerUrlHint => 'https://echangocrm.echango.com';

  @override
  String get settingsServerUrlInvalid =>
      'Invalid address — it must start with https://';

  @override
  String get settingsToken => 'Device token';

  @override
  String get settingsTokenHint => 'Paste the token generated in Odoo';

  @override
  String get settingsTokenSet => 'Token saved';

  @override
  String get settingsTokenMissing => 'No token — calls will not be sent';

  @override
  String get settingsTokenHelp =>
      'Generate the token in Odoo, under CRM then Call Tracker then Devices. It is shown only once.';

  @override
  String get settingsCaptureSection => 'Capture';

  @override
  String get settingsCaptureEnabled => 'Capture calls';

  @override
  String get settingsCaptureEnabledHelp =>
      'Turning this off suspends all capture, without clearing what is already pending.';

  @override
  String get settingsHoursTitle => 'Time range';

  @override
  String get settingsHoursHelp => 'Outside this range, calls are not captured.';

  @override
  String get settingsHoursFrom => 'From';

  @override
  String get settingsHoursTo => 'To';

  @override
  String settingsHoursRange(String from, String to) {
    return 'From $from to $to';
  }

  @override
  String get permissionsSection => 'Permissions';

  @override
  String get permissionsMissingTitle => 'Missing permissions';

  @override
  String get permissionsMissingBody =>
      'Without access to the call log and the phone state, no call can be captured.';

  @override
  String get permissionsGrant => 'Grant';

  @override
  String get permissionsGranted => 'Granted';

  @override
  String get permissionsOpenSettings => 'Open system settings';

  @override
  String get permissionsPermanentlyDenied =>
      'Permanently denied — re-enable them in the system settings.';

  @override
  String get batteryWarningTitle => 'Battery saver';

  @override
  String get batteryWarningBody =>
      'The system may stop background capture. Excluding the app from battery optimisation makes tracking more reliable.';

  @override
  String get batteryWarningAction => 'Exclude the app';

  @override
  String get noteDialogTitle => 'Post-call note';

  @override
  String get noteDialogHint => 'What was said, in one sentence';

  @override
  String get noteSave => 'Save note';

  @override
  String get noteSkip => 'No note';

  @override
  String get noteAdd => 'Add a note';

  @override
  String get noteSaved => 'Note saved';

  @override
  String get noteAwaiting => 'Awaiting note';

  @override
  String get permissionsNotifications => 'Notifications';

  @override
  String get permissionsNotificationsBody =>
      'Without notification permission, the app cannot offer to write a note after a call. Capture itself continues.';
}
