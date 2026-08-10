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

  @override
  String get overlaySection => 'Card while ringing';

  @override
  String get overlayTitle => 'Show the CRM card while the phone rings';

  @override
  String get overlayBody =>
      'The customer\'s name, company, stage and latest note appear over the call screen. Without this permission, capture continues normally.';

  @override
  String get overlayAction => 'Allow overlay';

  @override
  String get overlayGranted => 'Overlay allowed';

  @override
  String get navSearch => 'Search';

  @override
  String get searchTitle => 'Find a contact';

  @override
  String get searchHint => 'Number or part of a number';

  @override
  String get searchAction => 'Search';

  @override
  String get searchNotFound => 'No contact matches this number';

  @override
  String get searchPrompt => 'Type at least a few digits to find a contact.';

  @override
  String get searchCompany => 'Company';

  @override
  String get searchStage => 'Stage';

  @override
  String get searchLastNote => 'Latest note';

  @override
  String get screeningTitle => 'Allow reading the incoming number';

  @override
  String get screeningBody =>
      'Without this role, Android does not pass the number to the app and the card cannot be shown. It does NOT make the app your default phone app, and no call is screened or blocked.';

  @override
  String get screeningAction => 'Grant the role';

  @override
  String get screeningGranted => 'Incoming number accessible';

  @override
  String get noticeTitle => 'What this app records';

  @override
  String get noticeIntro =>
      'This phone is a work tool: the app sends your business calls to the company CRM. Here is exactly what, for whom, and for how long.';

  @override
  String get noticeRecordedTitle => 'What is recorded';

  @override
  String get noticeRecordedNumber =>
      'The number you called, or the number calling you.';

  @override
  String get noticeRecordedWhen => 'The date, time and length of the call.';

  @override
  String get noticeRecordedDirection =>
      'The direction: incoming, outgoing or missed.';

  @override
  String get noticeRecordedNote =>
      'The note you write yourself after the call, if you write one.';

  @override
  String get noticeNotRecordedTitle => 'What is not recorded';

  @override
  String get noticeNotRecordedContent =>
      'The content of your conversations. Nothing is listened to, recorded or transcribed — the app has no access to the microphone.';

  @override
  String get noticeNotRecordedPersonal =>
      'Not your messages, not your personal contacts, not your location.';

  @override
  String get noticeNotRecordedHours =>
      'Nothing outside the time range shown in the settings.';

  @override
  String get noticeWhoTitle => 'Who can read them';

  @override
  String get noticeWhoYou => 'You, for your own calls.';

  @override
  String get noticeWhoManager => 'Your manager, for their team\'s calls.';

  @override
  String get noticeWhoAudited =>
      'Every lookup is itself logged, your manager\'s included.';

  @override
  String get noticeHowLongTitle => 'For how long';

  @override
  String noticeRetentionDays(int days) {
    final intl.NumberFormat daysNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String daysString = daysNumberFormat.format(days);

    String _temp0 = intl.Intl.pluralLogic(
      days,
      locale: localeName,
      other: '$daysString days',
      one: 'one day',
    );
    return 'Calls are deleted automatically after $_temp0';
  }

  @override
  String noticeRetentionApprox(int years) {
    final intl.NumberFormat yearsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String yearsString = yearsNumberFormat.format(years);

    String _temp0 = intl.Intl.pluralLogic(
      years,
      locale: localeName,
      other: '$yearsString years',
      one: 'one year',
    );
    return '— about $_temp0.';
  }

  @override
  String get noticeRetentionUnknown =>
      'The duration is set by your employer on the server. It will appear here as soon as the first call is sent.';

  @override
  String get noticeRetentionNone =>
      'No automatic deletion is configured on this server: calls are kept until deleted manually.';

  @override
  String get noticeRightsTitle => 'Your rights';

  @override
  String get noticeRightsBody =>
      'You may ask to see what concerns you, and to have it corrected or erased. Speak to your manager or to the CRM administrator.';

  @override
  String get noticeAcknowledge => 'I have read and understood';

  @override
  String get noticeSection => 'Information';

  @override
  String get noticeReadAgain => 'Privacy notice';

  @override
  String get noticeReadAgainBody =>
      'What the app records, who can read it, and how long it is kept.';

  @override
  String get noticeReadAgainAction => 'Read again';

  @override
  String get searchClear => 'Clear';

  @override
  String searchNotFoundFor(String number) {
    return 'No contact matches $number';
  }

  @override
  String get searchPartialHint =>
      'A fragment is enough — start, middle or end of the number.';

  @override
  String searchTooShort(int min) {
    return 'A little more: $min digits minimum.';
  }

  @override
  String get searchCall => 'Call';
}
