import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/activities/activities_screen.dart';
import '../features/calls/calls_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/settings_screen.dart';
import '../l10n/app_localizations.dart';
import '../providers/core_providers.dart';

/// Quatre onglets, un `IndexedStack` : pas de routeur.
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

  /// Change d'onglet, et **relit les appels en revenant sur leur liste**.
  ///
  /// Un `IndexedStack` garde les trois onglets montés : revenir sur les appels
  /// ne reconstruit rien et n'invalide aucun provider. La liste affichait donc
  /// « En attente » sur des appels déjà remis à Odoo, jusqu'au prochain retour
  /// dans l'application ou à un tiré-pour-rafraîchir.
  ///
  /// Le défaut est cosmétique mais il se lit comme une panne : le commercial
  /// voit une file qui ne se vide pas et conclut que rien ne part. Constaté le
  /// 2026-08-10.
  void _allerA(int index) {
    setState(() => _onglet = index);
    if (index == 0) ref.invalidate(activitesProvider);
    if (index == 1) ref.invalidate(appelsProvider);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final themeMode = ref.watch(themeModeProvider);
    final locale = ref.watch(localeProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(
          switch (_onglet) {
            0 => l10n.activitiesTitle,
            1 => l10n.callsTitle,
            2 => l10n.searchTitle,
            _ => l10n.settingsTitle,
          },
        ),
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
        // « À appeler » en PREMIER, et ce n'est pas un détail d'ordre : c'est
        // le seul onglet qui rende quelque chose au commercial. L'ouverture de
        // l'application doit tomber sur ce qu'il a à faire, pas sur ce qu'on a
        // enregistré de lui.
        children: const [
          ActivitiesScreen(),
          CallsScreen(),
          SearchScreen(),
          SettingsScreen(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _onglet,
        onDestinationSelected: _allerA,
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.event_outlined),
            selectedIcon: const Icon(Icons.event),
            label: l10n.navActivities,
          ),
          NavigationDestination(
            icon: const Icon(Icons.call_outlined),
            selectedIcon: const Icon(Icons.call),
            label: l10n.navCalls,
          ),
          NavigationDestination(
            icon: const Icon(Icons.search_outlined),
            selectedIcon: const Icon(Icons.search),
            label: l10n.navSearch,
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
