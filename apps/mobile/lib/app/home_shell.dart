import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/calls/calls_screen.dart';
import '../features/settings/settings_screen.dart';
import '../l10n/app_localizations.dart';
import '../providers/core_providers.dart';

/// Deux onglets, un `IndexedStack` : pas de routeur.
///
/// Aucun lien profond, aucune redirection conditionnelle — go_router
/// n'apporterait ici qu'une dépendance et une indirection. À reprendre en
/// phase 2, quand la recherche de contact et le détail d'appel arriveront.
class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  int _onglet = 0;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final themeMode = ref.watch(themeModeProvider);
    final locale = ref.watch(localeProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(_onglet == 0 ? l10n.callsTitle : l10n.settingsTitle),
        actions: [
          PopupMenuButton<Locale>(
            icon: const Icon(Icons.translate),
            tooltip: l10n.languageSwitchTooltip,
            initialValue: locale,
            onSelected: ref.read(localeProvider.notifier).definir,
            itemBuilder: (context) => [
              PopupMenuItem(
                value: const Locale('fr'),
                child: Text(l10n.languageFrench),
              ),
              PopupMenuItem(
                value: const Locale('en'),
                child: Text(l10n.languageEnglish),
              ),
              PopupMenuItem(
                value: const Locale('ar'),
                child: Text(l10n.languageArabic),
              ),
            ],
          ),
          IconButton(
            tooltip: l10n.themeSwitchTooltip,
            icon: Icon(themeMode == ThemeMode.dark
                ? Icons.light_mode_outlined
                : Icons.dark_mode_outlined),
            onPressed: ref.read(themeModeProvider.notifier).basculer,
          ),
        ],
      ),
      body: IndexedStack(
        index: _onglet,
        children: const [CallsScreen(), SettingsScreen()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _onglet,
        onDestinationSelected: (i) => setState(() => _onglet = i),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.call_outlined),
            selectedIcon: const Icon(Icons.call),
            label: l10n.navCalls,
          ),
          NavigationDestination(
            icon: const Icon(Icons.settings_outlined),
            selectedIcon: const Icon(Icons.settings),
            label: l10n.navSettings,
          ),
        ],
      ),
    );
  }
}
