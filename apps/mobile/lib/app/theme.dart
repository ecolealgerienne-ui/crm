import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Rayons de coin, repris tels quels du design system echango Promo :
/// chips 8dp, boutons/champs 16dp, cartes/feuilles modales 24dp.
class AppRadii {
  AppRadii._();

  static const double sm = 8;
  static const double md = 16;
  static const double lg = 24;
  static const double pill = 999;
}

/// Durée de transition unique (≤180ms, easeOut). Pas d'animation
/// spring/physics : coûteuse à interpoler sur les appareils d'entrée de gamme,
/// qui sont précisément ceux que porteront les commerciaux.
const kAppTransitionDuration = Duration(milliseconds: 180);

/// Couleurs sémantiques absentes du `ColorScheme` Material, qui n'a que
/// `error`.
///
/// Le jeu diffère de celui de Promo, parce que ce que cette app doit rendre
/// lisible n'est pas le même : là-bas succès/attention/favori, ici l'état de
/// synchronisation d'un appel et son sens (entrant, sortant, manqué). Une
/// couleur sémantique nomme une intention métier — la recopier d'une app à
/// l'autre par souci d'uniformité produirait des noms qui ne veulent rien
/// dire ici.
@immutable
class AppSemanticColors extends ThemeExtension<AppSemanticColors> {
  const AppSemanticColors({
    required this.synced,
    required this.pending,
    required this.inbound,
    required this.outbound,
    required this.missed,
  });

  /// Appel remis à Odoo.
  final Color synced;

  /// Appel encore dans la file locale.
  ///
  /// ⚠️ Volontairement distincte de `colorScheme.error` : un appel en attente
  /// n'est **pas** une erreur, c'est le fonctionnement nominal hors réseau.
  /// Le peindre en rouge ferait croire à une panne à chaque tunnel.
  final Color pending;

  final Color inbound;
  final Color outbound;

  /// Un appel manqué se distingue d'un échec de synchronisation : c'est un
  /// fait métier, pas un incident technique. D'où une teinte propre, et non
  /// `error` réutilisé.
  final Color missed;

  /// Variantes sombres plus claires et moins saturées : une couleur franche
  /// sur fond sombre « vibre » et attire l'œil plus que l'information ne le
  /// mérite.
  static const light = AppSemanticColors(
    synced: Color(0xFF2F9E62),
    pending: Color(0xFF9A6B00),
    inbound: Color(0xFF2563EB),
    outbound: Color(0xFF0F766E),
    missed: Color(0xFFC2410C),
  );
  static const dark = AppSemanticColors(
    synced: Color(0xFF4ADE80),
    pending: Color(0xFFFBBF24),
    inbound: Color(0xFF7BA9F7),
    outbound: Color(0xFF5EEAD4),
    missed: Color(0xFFFB923C),
  );

  @override
  AppSemanticColors copyWith({
    Color? synced,
    Color? pending,
    Color? inbound,
    Color? outbound,
    Color? missed,
  }) {
    return AppSemanticColors(
      synced: synced ?? this.synced,
      pending: pending ?? this.pending,
      inbound: inbound ?? this.inbound,
      outbound: outbound ?? this.outbound,
      missed: missed ?? this.missed,
    );
  }

  @override
  AppSemanticColors lerp(ThemeExtension<AppSemanticColors>? other, double t) {
    if (other is! AppSemanticColors) return this;
    return AppSemanticColors(
      synced: Color.lerp(synced, other.synced, t)!,
      pending: Color.lerp(pending, other.pending, t)!,
      inbound: Color.lerp(inbound, other.inbound, t)!,
      outbound: Color.lerp(outbound, other.outbound, t)!,
      missed: Color.lerp(missed, other.missed, t)!,
    );
  }

  /// Égalité par valeur, absente de l'implémentation d'origine reprise de
  /// Promo.
  ///
  /// Ce n'est pas cosmétique : Flutter compare les `ThemeExtension` pour
  /// décider s'il doit reconstruire. Sans `==`, deux instances porteuses des
  /// mêmes couleurs sont vues comme différentes, et toute reconstruction du
  /// `ThemeData` — un changement de langue suffit — propage une invalidation
  /// à tout l'arbre alors que rien n'a changé visuellement.
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is AppSemanticColors &&
          other.synced == synced &&
          other.pending == pending &&
          other.inbound == inbound &&
          other.outbound == outbound &&
          other.missed == missed;

  @override
  int get hashCode => Object.hash(synced, pending, inbound, outbound, missed);
}

/// Bleu ardoise en couleur principale, safran en accent.
///
/// **L'identité diffère de Promo, la méthode non.** Promo est en terracotta :
/// c'est une app grand public, tournée vers la découverte de promotions. Le
/// Call Tracker est un outil interne que le commercial ouvre pour vérifier
/// que son suivi remonte — un bleu ardoise sobre y sert mieux qu'un orange
/// qui appelle à l'action toutes les trente secondes. Le safran de Promo est
/// conservé en accent secondaire : c'est le fil visuel qui rattache les deux
/// applications à la même suite.
///
/// ⚠️ **`ColorScheme` construit à la main, pas `ColorScheme.fromSeed`.** La
/// leçon vient de Promo (refonte du 2026-07-29) : `fromSeed` dérive *tous* les
/// tons de la graine, y compris `onSurface`, `outlineVariant`, les fonds de
/// conteneur et `surfaceTint` qui teinte toute surface élevée. Le résultat est
/// une interface entièrement lavée dans la teinte de la graine, alors qu'on ne
/// voulait qu'un accent. Un `fromSeed(...).copyWith(...)` ne suffit pas non
/// plus : il laisse passer tout ton oublié, et il y en a une quinzaine.
class AppTheme {
  AppTheme._();

  static const _ardoise = Color(0xFF1F4E79);
  static const _safran = Color(0xFFF2A93B);

  /// Bleu plus clair sur fond sombre : l'ardoise manque de contraste posée
  /// sur du noir.
  static const _ardoiseDark = Color(0xFF6BA6DC);

  // --- Neutres clairs : gris purs, aucune trace de la graine bleue ---
  static const _white = Color(0xFFFFFFFF);
  static const _ink = Color(0xFF1A1A1A);
  static const _inkMuted = Color(0xFF6B6B6B);
  static const _greyLowest = Color(0xFFFFFFFF);
  static const _greyLow = Color(0xFFFAFAFA);
  static const _grey = Color(0xFFF6F6F6);
  static const _greyHigh = Color(0xFFF1F1F1);
  static const _greyHighest = Color(0xFFEBEBEB);
  static const _outlineLight = Color(0xFFC9C9C9);
  static const _outlineVariantLight = Color(0xFFE6E6E6);

  /// Le seul endroit où une surface est teintée, et volontairement : pastille
  /// d'onglet actif, puce sélectionnée.
  static const _blueTintLight = Color(0xFFE4EDF6);
  static const _onBlueTintLight = Color(0xFF10314D);

  // --- Neutres sombres : gris neutres également ---
  static const _surfaceDark = Color(0xFF141414);
  static const _inkDark = Color(0xFFECECEC);
  static const _inkMutedDark = Color(0xFFA8A8A8);
  static const _greyLowestDark = Color(0xFF0F0F0F);
  static const _greyLowDark = Color(0xFF1A1A1A);
  static const _greyDark = Color(0xFF1F1F1F);
  static const _greyHighDark = Color(0xFF262626);
  static const _greyHighestDark = Color(0xFF2E2E2E);
  static const _outlineDark = Color(0xFF5A5A5A);
  static const _outlineVariantDark = Color(0xFF303030);
  static const _blueTintDark = Color(0xFF12293D);
  static const _onBlueTintDark = Color(0xFFC7DDF0);

  static const _errorLight = Color(0xFFD6303D);
  static const _errorDark = Color(0xFFF87171);

  static ThemeData get light => _build(brightness: Brightness.light);
  static ThemeData get dark => _build(brightness: Brightness.dark);

  /// Couleurs sémantiques de la variante demandée.
  static AppSemanticColors semanticColorsFor(Brightness brightness) =>
      brightness == Brightness.dark
          ? AppSemanticColors.dark
          : AppSemanticColors.light;

  /// Palette seule, sans typographie.
  ///
  /// Extraite de `_build` pour être vérifiable en test : construire un
  /// `ThemeData` complet passe par `google_fonts`, qui télécharge les polices
  /// au premier usage et échoue donc dans un banc de test, où il n'y a pas de
  /// réseau. Les invariants qui comptent — neutres non teintés, `surfaceTint`
  /// neutralisé — vivent ici.
  static ColorScheme colorSchemeFor(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    return isDark
        ? const ColorScheme.dark(
            primary: _ardoiseDark,
            onPrimary: Color(0xFF06263D),
            primaryContainer: _blueTintDark,
            onPrimaryContainer: _onBlueTintDark,
            secondary: _safran,
            onSecondary: Color(0xFF3D2A00),
            secondaryContainer: _blueTintDark,
            onSecondaryContainer: _onBlueTintDark,
            surface: _surfaceDark,
            onSurface: _inkDark,
            onSurfaceVariant: _inkMutedDark,
            surfaceContainerLowest: _greyLowestDark,
            surfaceContainerLow: _greyLowDark,
            surfaceContainer: _greyDark,
            surfaceContainerHigh: _greyHighDark,
            surfaceContainerHighest: _greyHighestDark,
            outline: _outlineDark,
            outlineVariant: _outlineVariantDark,
            error: _errorDark,
            onError: Color(0xFF3D0006),
            // Neutralise la teinte d'élévation Material 3 : sans ça, toute
            // carte ou feuille surélevée reprend un voile bleu.
            surfaceTint: Colors.transparent,
          )
        : const ColorScheme.light(
            primary: _ardoise,
            onPrimary: _white,
            primaryContainer: _blueTintLight,
            onPrimaryContainer: _onBlueTintLight,
            secondary: _safran,
            onSecondary: _ink,
            secondaryContainer: _blueTintLight,
            onSecondaryContainer: _onBlueTintLight,
            surface: _white,
            onSurface: _ink,
            onSurfaceVariant: _inkMuted,
            surfaceContainerLowest: _greyLowest,
            surfaceContainerLow: _greyLow,
            surfaceContainer: _grey,
            surfaceContainerHigh: _greyHigh,
            surfaceContainerHighest: _greyHighest,
            outline: _outlineLight,
            outlineVariant: _outlineVariantLight,
            error: _errorLight,
            onError: _white,
            surfaceTint: Colors.transparent,
          );
  }

  static ThemeData _build({required Brightness brightness}) {
    final colorScheme = colorSchemeFor(brightness);
    final textTheme = _textTheme(colorScheme);
    final outline = colorScheme.outlineVariant;

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: colorScheme.surface,
      textTheme: textTheme,
      extensions: [semanticColorsFor(brightness)],
      appBarTheme: AppBarTheme(
        backgroundColor: colorScheme.surface,
        foregroundColor: colorScheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        titleTextStyle:
            textTheme.titleLarge?.copyWith(color: colorScheme.onSurface),
        iconTheme: IconThemeData(color: colorScheme.primary),
        actionsIconTheme: IconThemeData(color: colorScheme.primary),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: colorScheme.surface,
        indicatorColor: colorScheme.primaryContainer,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
      ),
      dividerTheme: DividerThemeData(color: outline, thickness: 1),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: colorScheme.surface,
        surfaceTintColor: Colors.transparent,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: colorScheme.surface,
        surfaceTintColor: Colors.transparent,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: colorScheme.surface,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.lg),
          side: BorderSide(color: outline),
        ),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: colorScheme.onSurfaceVariant,
        titleTextStyle: textTheme.bodyLarge,
        subtitleTextStyle: textTheme.bodySmall
            ?.copyWith(color: colorScheme.onSurfaceVariant),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        side: BorderSide(color: outline),
        selectedColor: colorScheme.primary,
        backgroundColor: colorScheme.surface,
        labelStyle: textTheme.labelLarge,
        secondaryLabelStyle:
            textTheme.labelLarge?.copyWith(color: colorScheme.onPrimary),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.md),
        ),
        filled: true,
        fillColor: colorScheme.surface,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: colorScheme.primary,
          foregroundColor: colorScheme.onPrimary,
          textStyle: textTheme.labelLarge,
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadii.md),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: colorScheme.onSurface,
          side: BorderSide(color: outline),
          textStyle: textTheme.labelLarge,
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 20),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadii.md),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: colorScheme.primary,
          textStyle: textTheme.labelLarge,
        ),
      ),
    );
  }

  /// Cairo pour les titres, IBM Plex Sans Arabic pour le corps — même couple
  /// que Promo, et pour la même raison : l'arabe est une des trois langues de
  /// l'app, et une police sans jeu arabe complet y affiche des rectangles
  /// vides. L'échelle est reprise à l'identique pour que les deux apps se
  /// lisent pareil.
  static TextTheme _textTheme(ColorScheme colorScheme) {
    TextStyle title(double size, double lineHeight, FontWeight weight) =>
        GoogleFonts.cairo(
          fontSize: size,
          height: lineHeight / size,
          fontWeight: weight,
          color: colorScheme.onSurface,
        );

    TextStyle body(double size, double lineHeight, FontWeight weight) =>
        GoogleFonts.ibmPlexSansArabic(
          fontSize: size,
          height: lineHeight / size,
          fontWeight: weight,
          color: colorScheme.onSurface,
        );

    return TextTheme(
      displayLarge: title(40, 46, FontWeight.w700),
      displayMedium: title(34, 40, FontWeight.w700),
      displaySmall: title(30, 36, FontWeight.w700),
      headlineLarge: title(32, 38, FontWeight.w700),
      headlineMedium: title(28, 34, FontWeight.w700),
      headlineSmall: title(24, 30, FontWeight.w700),
      titleLarge: title(22, 28, FontWeight.w600),
      titleMedium: title(18, 24, FontWeight.w600),
      titleSmall: title(16, 22, FontWeight.w600),
      bodyLarge: body(16, 24, FontWeight.w400),
      bodyMedium: body(15, 22, FontWeight.w400),
      bodySmall: body(12, 16, FontWeight.w400),
      labelLarge: body(14, 20, FontWeight.w500),
      labelMedium: body(12, 16, FontWeight.w500),
      labelSmall: body(11, 14, FontWeight.w500),
    );
  }
}
