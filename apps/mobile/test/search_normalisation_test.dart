import 'package:call_tracker/features/search/search_screen.dart';
import 'package:flutter_test/flutter_test.dart';

/// Normalisation du numéro saisi avant l'appel réseau.
///
/// Un numéro se recopie tel qu'il est écrit — sur une carte de visite, dans un
/// courriel, avec des espaces ou des points. Ce qui part dans l'URL se
/// retrouve tel quel au journal d'audit d'Odoo, seule trace qui dise quel
/// numéro a été consulté ; elle doit rester lisible.
void main() {
  const normaliser = SearchScreenState.normaliser;

  test('un numéro déjà propre ne bouge pas', () {
    expect(normaliser('+213555123456'), '+213555123456');
  });

  test('les séparateurs de lisibilité sont retirés', () {
    for (final saisie in [
      '+213 555 12 34 56',
      '+213.555.12.34.56',
      '+213-555-12-34-56',
      '  +213 555 123 456  ',
    ]) {
      expect(normaliser(saisie), '+213555123456', reason: saisie);
    }
  });

  test('le + de tête est conservé, les autres non', () {
    // Le préfixe international porte du sens ; un + au milieu est une scorie
    // de recopie.
    expect(normaliser('+213+555123456'), '+213555123456');
    expect(normaliser('0555123456'), '0555123456');
  });

  test('le minimum de chiffres est aligné sur le serveur', () {
    // `SearchScreenState.fragmentMin` et `call.tracker.log.FRAGMENT_MIN`
    // doivent rester égaux. Les désaligner ne casse rien bruyamment : l'app
    // laisserait partir des fragments que le serveur refuse par un 400, et
    // l'écran afficherait « aucun contact » là où il devrait dire « trop
    // court ». Ce test ne peut pas lire le Python ; il fige la valeur pour
    // que la modifier ici oblige à aller voir là-bas.
    expect(SearchScreenState.fragmentMin, 4);
  });

  test('une saisie sans aucun chiffre ne déclenche pas de recherche', () {
    // Chaîne vide = pas d'appel réseau, et surtout pas de ligne d'audit
    // inutile côté serveur.
    for (final saisie in ['', '   ', '+', '...', 'abc']) {
      expect(normaliser(saisie), '', reason: saisie);
    }
  });
}
