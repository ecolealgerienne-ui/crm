// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppLocalizationsAr extends AppLocalizations {
  AppLocalizationsAr([String locale = 'ar']) : super(locale);

  @override
  String get appTitle => 'متتبّع المكالمات';

  @override
  String get commonCancel => 'إلغاء';

  @override
  String get commonSave => 'حفظ';

  @override
  String get commonRetry => 'إعادة المحاولة';

  @override
  String get commonClose => 'إغلاق';

  @override
  String commonError(String error) {
    return 'خطأ: $error';
  }

  @override
  String get languageSwitchTooltip => 'تغيير اللغة';

  @override
  String get languageFrench => 'Français';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageArabic => 'العربية';

  @override
  String get themeSwitchTooltip => 'تغيير المظهر';

  @override
  String get themeLight => 'فاتح';

  @override
  String get themeDark => 'داكن';

  @override
  String get navCalls => 'المكالمات';

  @override
  String get navSettings => 'الإعدادات';

  @override
  String get callsTitle => 'المكالمات المسجَّلة';

  @override
  String get callsEmptyTitle => 'لا توجد مكالمات مسجَّلة';

  @override
  String get callsEmptyBody =>
      'ستظهر المكالمات هنا تلقائيًا بمجرّد إجراء مكالمة أو استقبالها.';

  @override
  String callsPendingCount(int count) {
    final intl.NumberFormat countNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String countString = countNumberFormat.format(count);

    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$countString مكالمة في الانتظار',
      many: '$countString مكالمة في الانتظار',
      few: '$countString مكالمات في الانتظار',
      two: 'مكالمتان في الانتظار',
      one: 'مكالمة واحدة في الانتظار',
      zero: 'تمت المزامنة بالكامل',
    );
    return '$_temp0';
  }

  @override
  String get callsSyncNow => 'المزامنة الآن';

  @override
  String get directionInbound => 'واردة';

  @override
  String get directionOutbound => 'صادرة';

  @override
  String get directionMissed => 'فائتة';

  @override
  String get syncPending => 'في الانتظار';

  @override
  String get syncSent => 'تمت المزامنة';

  @override
  String get syncFailed => 'فشل';

  @override
  String syncFailedWithReason(String reason) {
    return 'فشل: $reason';
  }

  @override
  String durationSeconds(int seconds) {
    final intl.NumberFormat secondsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String secondsString = secondsNumberFormat.format(seconds);

    return '$secondsString ث';
  }

  @override
  String durationMinutesSeconds(int minutes, int seconds) {
    final intl.NumberFormat minutesNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String minutesString = minutesNumberFormat.format(minutes);
    final intl.NumberFormat secondsNumberFormat =
        intl.NumberFormat.decimalPattern(localeName);
    final String secondsString = secondsNumberFormat.format(seconds);

    return '$minutesString د $secondsString ث';
  }

  @override
  String get settingsTitle => 'الإعدادات';

  @override
  String get settingsConnectionSection => 'الاتصال بأودو';

  @override
  String get settingsServerUrl => 'عنوان الخادم';

  @override
  String get settingsServerUrlHint => 'https://echangocrm.echango.com';

  @override
  String get settingsServerUrlInvalid =>
      'عنوان غير صالح — يجب أن يبدأ بـ https://';

  @override
  String get settingsToken => 'رمز الجهاز';

  @override
  String get settingsTokenHint => 'الصق الرمز الذي أنشأته في أودو';

  @override
  String get settingsTokenSet => 'تم حفظ الرمز';

  @override
  String get settingsTokenMissing => 'لا يوجد رمز — لن تُرسَل المكالمات';

  @override
  String get settingsTokenHelp =>
      'يُنشَأ الرمز في أودو ضمن إدارة العلاقات ثم متتبّع المكالمات ثم الأجهزة. ويُعرض مرة واحدة فقط.';

  @override
  String get settingsCaptureSection => 'التسجيل';

  @override
  String get settingsCaptureEnabled => 'تسجيل المكالمات';

  @override
  String get settingsCaptureEnabledHelp =>
      'إيقاف هذا الخيار يوقف كل تسجيل، دون حذف ما هو في الانتظار.';

  @override
  String get settingsHoursTitle => 'النطاق الزمني';

  @override
  String get settingsHoursHelp => 'خارج هذا النطاق، لا تُسجَّل المكالمات.';

  @override
  String get settingsHoursFrom => 'من';

  @override
  String get settingsHoursTo => 'إلى';

  @override
  String settingsHoursRange(String from, String to) {
    return 'من $from إلى $to';
  }

  @override
  String get permissionsSection => 'الأذونات';

  @override
  String get permissionsMissingTitle => 'أذونات ناقصة';

  @override
  String get permissionsMissingBody =>
      'بدون الوصول إلى سجلّ المكالمات وحالة الهاتف، لا يمكن تسجيل أي مكالمة.';

  @override
  String get permissionsGrant => 'منح';

  @override
  String get permissionsGranted => 'ممنوحة';

  @override
  String get permissionsOpenSettings => 'فتح إعدادات النظام';

  @override
  String get permissionsPermanentlyDenied =>
      'مرفوضة نهائيًا — أعِد تفعيلها من إعدادات النظام.';

  @override
  String get batteryWarningTitle => 'موفّر البطارية';

  @override
  String get batteryWarningBody =>
      'قد يوقف النظام التسجيل في الخلفية. استثناء التطبيق من تحسين البطارية يجعل التتبّع أكثر موثوقية.';

  @override
  String get batteryWarningAction => 'استثناء التطبيق';

  @override
  String get noteDialogTitle => 'ملاحظة بعد المكالمة';

  @override
  String get noteDialogHint => 'ما قيل، في جملة واحدة';

  @override
  String get noteSave => 'حفظ الملاحظة';

  @override
  String get noteSkip => 'بدون ملاحظة';

  @override
  String get noteAdd => 'إضافة ملاحظة';

  @override
  String get noteSaved => 'تم حفظ الملاحظة';

  @override
  String get noteAwaiting => 'بانتظار ملاحظة';

  @override
  String get permissionsNotifications => 'الإشعارات';

  @override
  String get permissionsNotificationsBody =>
      'بدون إذن الإشعارات، لا يمكن للتطبيق أن يقترح كتابة ملاحظة بعد المكالمة. أما التسجيل فيستمر.';
}
