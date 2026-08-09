import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/notice/notice_screen.dart';
import '../l10n/app_localizations.dart';
import '../providers/core_providers.dart';
import 'home_shell.dart';
import 'theme.dart';

class CallTrackerApp extends ConsumerWidget {
  const CallTrackerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final locale = ref.watch(localeProvider);
    final themeMode = ref.watch(themeModeProvider);
    final avisLu = ref.watch(avisLuProvider);

    return MaterialApp(
      onGenerateTitle: (context) => AppLocalizations.of(context)!.appTitle,
      debugShowCheckedModeBanner: false,
      locale: locale,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: supportedAppLocales,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: themeMode,
      // L'avis d'information passe devant tout le reste, tant qu'il n'a pas
      // été accusé pour la version courante. Une porte, pas une route : rien
      // à empiler, rien d'où revenir, et aucun chemin détourné vers les
      // onglets tant que l'écran n'est pas lu.
      home: avisLu ? const HomeShell() : const NoticeScreen(enPorte: true),
    );
  }
}
