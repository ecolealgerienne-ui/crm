import 'package:call_tracker/app/theme.dart';
import 'package:call_tracker/features/search/contact_sheet.dart';
import 'package:call_tracker/features/search/search_screen.dart';
import 'package:call_tracker/l10n/app_localizations.dart';
import 'package:call_tracker/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Chercher, choisir, appeler.
///
/// Le parcours entier tient dans ces tests : un fragment rend une liste, une
/// ligne ouvre une fiche, la fiche compose. Chaque maillon a sa raison d'être
/// et se casse silencieusement — une liste qui ne s'ouvre plus reste une
/// liste, un bouton qui ne compose plus reste un bouton.
void main() {
  const canal = MethodChannel('com.echango.call_tracker/capture');
  late List<MethodCall> appelsCanal;

  setUp(() {
    appelsCanal = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (appel) async {
      appelsCanal.add(appel);
      return switch (appel.method) {
        'searchContacts' => [
            {
              'name': 'Yacine Amrani',
              'company': 'Sonatrach Distribution',
              'phone': '+213661445566',
              'crm_stage': 'Proposition',
            },
            {
              'name': 'Leïla Hamidi',
              'company': '',
              'phone': '+213661445599',
              'crm_stage': '',
            },
          ],
        'lookupContact' => {
            'name': 'Yacine Amrani',
            'company': 'Sonatrach Distribution',
            'last_notes': 'Attend le devis pour lundi',
            'crm_stage': 'Proposition',
          },
        _ => null,
      };
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, null);
  });

  Future<void> monter(WidgetTester tester) async {
    tester.view.physicalSize = const Size(420, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    SharedPreferences.setMockInitialValues({'ui.locale': 'fr'});
    final prefs = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
        child: MaterialApp(
          locale: const Locale('fr'),
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: supportedAppLocales,
          theme: ThemeData(
            extensions: [AppTheme.semanticColorsFor(Brightness.light)],
          ),
          home: const Scaffold(body: SearchScreen()),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> chercher(WidgetTester tester, String fragment) async {
    await tester.enterText(find.byType(TextField), fragment);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.arrow_forward));
    await tester.pumpAndSettle();
  }

  group('La liste', () {
    testWidgets('un fragment rend plusieurs contacts', (tester) async {
      await monter(tester);
      await chercher(tester, '4455');

      expect(find.text('Yacine Amrani'), findsOneWidget);
      expect(find.text('Leïla Hamidi'), findsOneWidget);
      expect(find.text('+213661445566'), findsOneWidget,
          reason: 'sans le numéro on ne sait pas lequel choisir');
    });

    testWidgets('rien ne part en deçà du minimum de chiffres', (tester) async {
      // Le serveur refuserait par un 400 ; l'app doit le dire AVANT, sinon
      // l'écran affiche « aucun contact » là où il faudrait « trop court ».
      await monter(tester);
      await tester.enterText(find.byType(TextField), '555');
      await tester.pumpAndSettle();

      expect(
        tester.widget<IconButton>(
          find.ancestor(
            of: find.byIcon(Icons.arrow_forward),
            matching: find.byType(IconButton),
          ),
        ).onPressed,
        isNull,
        reason: 'un bouton qui ne fait rien se lit comme une panne',
      );
      expect(appelsCanal.where((a) => a.method == 'searchContacts'), isEmpty);
    });

    testWidgets('le bouton d\'appel de la ligne compose le numéro',
        (tester) async {
      await monter(tester);
      await chercher(tester, '4455');

      await tester.tap(find.byIcon(Icons.call).first);
      await tester.pumpAndSettle();

      final compose = appelsCanal.lastWhere((a) => a.method == 'dial');
      expect(compose.arguments['phoneNumber'], '+213661445566');
    });
  });

  group('La fiche', () {
    testWidgets('s\'ouvre en touchant une ligne', (tester) async {
      await monter(tester);
      await chercher(tester, '4455');

      await tester.tap(find.text('Yacine Amrani'));
      await tester.pumpAndSettle();

      expect(find.byType(ContactSheet), findsOneWidget);
    });

    testWidgets('affiche la dernière note, que la liste ne rapporte pas',
        (tester) async {
      // C'est la raison d'être de l'écran : la route de liste ne renvoie pas
      // les notes, pour ne pas en sortir dix quand on en lira une.
      await monter(tester);
      await chercher(tester, '4455');
      await tester.tap(find.text('Yacine Amrani'));
      await tester.pumpAndSettle();

      expect(find.text('Attend le devis pour lundi'), findsOneWidget);
      expect(appelsCanal.where((a) => a.method == 'lookupContact').length, 1);
    });

    testWidgets('reste lisible si la fiche détaillée ne répond pas',
        (tester) async {
      // Le détail COMPLÈTE le résumé, il ne le remplace pas : réseau coupé,
      // l'écran garde ce que la recherche avait déjà rendu au lieu de se
      // vider.
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(canal, (appel) async {
        appelsCanal.add(appel);
        if (appel.method == 'searchContacts') {
          return [
            {
              'name': 'Yacine Amrani',
              'company': 'Sonatrach Distribution',
              'phone': '+213661445566',
              'crm_stage': 'Proposition',
            },
          ];
        }
        return null;
      });

      await monter(tester);
      await chercher(tester, '4455');
      await tester.tap(find.text('Yacine Amrani'));
      await tester.pumpAndSettle();

      expect(find.text('Yacine Amrani'), findsOneWidget);
      expect(find.text('Sonatrach Distribution'), findsOneWidget);
      expect(find.text('Aucune note pour l\'instant.'), findsOneWidget);
    });

    testWidgets('son bouton compose le numéro', (tester) async {
      await monter(tester);
      await chercher(tester, '4455');
      await tester.tap(find.text('Yacine Amrani'));
      await tester.pumpAndSettle();

      // `find.byType(FilledButton)` ne conviendrait pas : `FilledButton.icon`
      // construit une sous-classe privée, et `byType` compare le type exact.
      await tester.tap(find.byIcon(Icons.call));
      await tester.pumpAndSettle();

      final compose = appelsCanal.lastWhere((a) => a.method == 'dial');
      expect(compose.arguments['phoneNumber'], '+213661445566');
    });
  });
}
