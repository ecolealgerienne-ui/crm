import 'package:call_tracker/app/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Tests portant sur la PALETTE, pas sur le `ThemeData` complet.
///
/// Construire `AppTheme.light` passe par `google_fonts`, qui télécharge les
/// polices au premier usage — impossible dans un banc de test, qui n'a pas de
/// réseau. `colorSchemeFor` et `semanticColorsFor` isolent précisément la
/// partie qui porte des invariants vérifiables.
void main() {
  group('Palette', () {
    test('la teinte de surface est neutralisée dans les deux variantes', () {
      // Material 3 teinte toute surface élevée avec `surfaceTint`. Laissée à
      // sa valeur par défaut, elle repeint cartes et feuilles modales dans la
      // couleur principale — c'est exactement le défaut corrigé sur l'app
      // Promo, dont l'interface entière lisait « beige » pour cette raison.
      for (final brightness in Brightness.values) {
        expect(
          AppTheme.colorSchemeFor(brightness).surfaceTint,
          Colors.transparent,
          reason: 'variante $brightness',
        );
      }
    });

    test('les neutres ne sont pas dérivés de la couleur principale', () {
      // Le sens de ce test : un `ColorScheme.fromSeed` produirait des neutres
      // légèrement teintés de bleu. Un gris pur a ses trois composantes
      // égales — la vérifier interdit de revenir à `fromSeed` sans que le banc
      // le signale.
      for (final brightness in Brightness.values) {
        final scheme = AppTheme.colorSchemeFor(brightness);
        for (final (nom, couleur) in [
          ('surfaceContainer', scheme.surfaceContainer),
          ('surfaceContainerHigh', scheme.surfaceContainerHigh),
          ('outlineVariant', scheme.outlineVariant),
        ]) {
          expect(
            couleur.r == couleur.g && couleur.g == couleur.b,
            isTrue,
            reason: '$nom est teinté en $brightness — '
                'un neutre doit avoir ses trois composantes égales',
          );
        }
      }
    });

    test('les deux variantes se distinguent', () {
      expect(
        AppTheme.colorSchemeFor(Brightness.light).surface,
        isNot(AppTheme.colorSchemeFor(Brightness.dark).surface),
      );
    });
  });

  group('Couleurs sémantiques', () {
    test('« en attente » ne réutilise pas la couleur d\'erreur', () {
      // Un appel en attente n'est pas une erreur : c'est le fonctionnement
      // nominal hors réseau. Le peindre comme une erreur ferait croire à une
      // panne à chaque tunnel.
      for (final brightness in Brightness.values) {
        expect(
          AppTheme.semanticColorsFor(brightness).pending,
          isNot(AppTheme.colorSchemeFor(brightness).error),
          reason: 'variante $brightness',
        );
      }
    });

    test('les cinq états se distinguent deux à deux', () {
      for (final brightness in Brightness.values) {
        final c = AppTheme.semanticColorsFor(brightness);
        final couleurs = {c.synced, c.pending, c.inbound, c.outbound, c.missed};
        expect(
          couleurs.length,
          5,
          reason: 'deux états partagent la même couleur en $brightness — '
              'ils deviennent indiscernables dans la liste',
        );
      }
    });

    test('lerp interpole vers la variante cible', () {
      final clair = AppSemanticColors.light;
      final sombre = AppSemanticColors.dark;
      expect(clair.lerp(sombre, 0), clair);
      expect(clair.lerp(sombre, 1).synced, sombre.synced);
    });
  });
}
