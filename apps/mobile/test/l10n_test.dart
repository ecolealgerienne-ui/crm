import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Les trois traductions doivent déclarer exactement les mêmes clés.
///
/// C'est le test qui rattrape le défaut le plus banal d'une app multilingue :
/// une chaîne ajoutée en français, oubliée en arabe. Rien ne le signale au
/// build — `flutter gen-l10n` se contente d'un avertissement, et l'app affiche
/// le texte français au milieu d'une interface arabe. Ici, il échoue.
void main() {
  final langues = ['fr', 'en', 'ar'];

  Map<String, dynamic> lire(String langue) {
    final fichier = File('lib/l10n/app_$langue.arb');
    expect(fichier.existsSync(), isTrue, reason: '${fichier.path} est absent');
    return jsonDecode(fichier.readAsStringSync()) as Map<String, dynamic>;
  }

  /// Les clés commençant par `@` sont des métadonnées (placeholders,
  /// descriptions) et n'ont pas à être répétées dans chaque traduction.
  Set<String> clesDe(Map<String, dynamic> arb) =>
      arb.keys.where((k) => !k.startsWith('@')).toSet();

  test('les trois traductions couvrent les mêmes clés', () {
    final reference = clesDe(lire('fr'));
    expect(reference, isNotEmpty);

    for (final langue in langues.where((l) => l != 'fr')) {
      final clesTraduites = clesDe(lire(langue));

      final manquantes = reference.difference(clesTraduites);
      expect(
        manquantes,
        isEmpty,
        reason: 'app_$langue.arb : ${manquantes.length} clé(s) non traduite(s)',
      );

      final superflues = clesTraduites.difference(reference);
      expect(
        superflues,
        isEmpty,
        reason: 'app_$langue.arb : clé(s) absente(s) du modèle français, '
            'donc jamais affichée(s) — ${superflues.join(', ')}',
      );
    }
  });

  test('aucune traduction vide', () {
    for (final langue in langues) {
      final arb = lire(langue);
      for (final entree in arb.entries) {
        if (entree.key.startsWith('@')) continue;
        expect(
          (entree.value as String).trim(),
          isNotEmpty,
          reason: 'app_$langue.arb : la clé « ${entree.key} » est vide',
        );
      }
    }
  });
}
