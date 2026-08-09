import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/capture_channel.dart';
import '../data/capture_models.dart';

/// Fourni par une surcharge au démarrage (voir `main.dart`) : lire les
/// préférences est asynchrone, et un provider asynchrone ici obligerait chaque
/// écran à gérer un état de chargement pour un choix de langue.
final sharedPreferencesProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError('surchargé dans main()');
});

final captureChannelProvider = Provider<CaptureChannel>(
  (ref) => const CaptureChannel(),
);

// ─────────────────────────────────────────────────────────────────────────────
// Langue et thème — pilotés par l'utilisateur, pas par le réglage du système.
//
// Même choix que Promo, et pour la même raison côté thème : le thème clair est
// l'identité de l'app, et `ThemeMode.system` la fait disparaître pour quiconque
// a son téléphone en sombre. Côté langue, `null` signifierait « suivre le
// système », ce qui donne de l'anglais à un commercial francophone dont le
// téléphone est en anglais.
// ─────────────────────────────────────────────────────────────────────────────

const supportedAppLocales = [Locale('fr'), Locale('en'), Locale('ar')];

const _cleLangue = 'ui.locale';
const _cleTheme = 'ui.themeMode';

class LocaleNotifier extends StateNotifier<Locale> {
  LocaleNotifier(this._prefs)
      : super(Locale(_prefs.getString(_cleLangue) ?? 'fr'));

  final SharedPreferences _prefs;

  void definir(Locale locale) {
    state = locale;
    _prefs.setString(_cleLangue, locale.languageCode);
  }
}

final localeProvider = StateNotifierProvider<LocaleNotifier, Locale>(
  (ref) => LocaleNotifier(ref.watch(sharedPreferencesProvider)),
);

class ThemeModeNotifier extends StateNotifier<ThemeMode> {
  ThemeModeNotifier(this._prefs)
      : super(_prefs.getString(_cleTheme) == 'dark'
            ? ThemeMode.dark
            : ThemeMode.light);

  final SharedPreferences _prefs;

  void basculer() {
    state = state == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
    _prefs.setString(_cleTheme, state == ThemeMode.dark ? 'dark' : 'light');
  }
}

final themeModeProvider = StateNotifierProvider<ThemeModeNotifier, ThemeMode>(
  (ref) => ThemeModeNotifier(ref.watch(sharedPreferencesProvider)),
);

// ─────────────────────────────────────────────────────────────────────────────
// État lu depuis la couche native
// ─────────────────────────────────────────────────────────────────────────────

final reglagesProvider = FutureProvider<CaptureSettings>(
  (ref) => ref.watch(captureChannelProvider).lireReglages(),
);

final appelsProvider = FutureProvider<List<CallEntry>>(
  (ref) => ref.watch(captureChannelProvider).listerAppels(),
);

final batterieOptimiseeProvider = FutureProvider<bool>(
  (ref) => ref.watch(captureChannelProvider).batterieOptimisee(),
);
