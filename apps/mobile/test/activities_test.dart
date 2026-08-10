import 'package:call_tracker/app/theme.dart';
import 'package:call_tracker/features/activities/activities_screen.dart';
import 'package:call_tracker/l10n/app_localizations.dart';
import 'package:call_tracker/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Les appels à passer : l'écran qui rend quelque chose au commercial.
void main() {
  const canal = MethodChannel('com.echango.call_tracker/capture');
  late List<MethodCall> appelsCanal;
  late List<Map<String, Object?>> activites;
  late int recupereeLe;
  late bool clotureAccepte;

  setUp(() {
    appelsCanal = [];
    clotureAccepte = true;
    recupereeLe = DateTime(2026, 8, 10, 9, 12).millisecondsSinceEpoch;
    activites = [
      {
        'id': 1,
        'client': 'Sonatrach Distribution',
        'phone': '+213661445566',
        'deadline': '2026-08-07',
        'state': 'overdue',
        'summary': 'Relancer sur le devis',
        'note': 'Attend une remise',
      },
      {
        'id': 2,
        'client': 'Piste sans numéro',
        'phone': '',
        'deadline': '2026-08-10',
        'state': 'today',
        'summary': 'Trouver le numéro',
        'note': '',
      },
    ];

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (appel) async {
      appelsCanal.add(appel);
      return switch (appel.method) {
        'listActivities' => {
            'fetchedAtMillis': recupereeLe,
            'results': activites,
          },
        'completeActivity' => clotureAccepte,
        _ => null,
      };
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, null);
  });

  Future<void> monter(WidgetTester tester) async {
    tester.view.physicalSize = const Size(420, 1600);
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
          home: const Scaffold(body: ActivitiesScreen()),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('la liste affiche les appels programmés', (tester) async {
    await monter(tester);
    expect(find.text('Sonatrach Distribution'), findsOneWidget);
    expect(find.text('Relancer sur le devis'), findsOneWidget);
    expect(find.text('+213661445566'), findsOneWidget);
  });

  testWidgets('le retard se voit sans lire la date', (tester) async {
    await monter(tester);
    expect(find.text('En retard'), findsOneWidget);
    expect(find.text("Aujourd'hui"), findsOneWidget);
  });

  testWidgets('la fraîcheur du cache est affichée', (tester) async {
    // ⚠️ Le test qui protège la confiance dans l'outil. Une liste périmée qui
    // se présente comme à jour est un mensonge, et le commercial retourne au
    // papier le jour où il s'en aperçoit.
    await monter(tester);
    expect(find.textContaining('Mis à jour'), findsOneWidget);
  });

  testWidgets('jamais synchronisé se dit au lieu de mentir', (tester) async {
    recupereeLe = 0;
    activites = [];
    await monter(tester);
    expect(find.textContaining('Jamais synchronisé'), findsOneWidget);
  });

  testWidgets('une activité sans numéro reste affichée', (tester) async {
    // La masquer ferait perdre une tâche réelle pour un champ manquant.
    await monter(tester);
    expect(find.text('Piste sans numéro'), findsOneWidget);
    expect(find.text('Aucun numéro sur cette fiche'), findsOneWidget);
  });

  testWidgets('le bouton compose le bon numéro', (tester) async {
    await monter(tester);
    await tester.tap(find.byIcon(Icons.call).first);
    await tester.pumpAndSettle();

    final compose = appelsCanal.lastWhere((a) => a.method == 'dial');
    expect(compose.arguments['phoneNumber'], '+213661445566');
  });

  testWidgets('un échec de clôture laisse la tâche en place', (tester) async {
    // ⚠️ Le comportement le plus important de cet écran. Retirer la ligne sans
    // que le serveur ait confirmé ferait disparaître une tâche que personne
    // n'a faite, et le commercial croirait l'avoir cochée.
    clotureAccepte = false;
    await monter(tester);

    await tester.tap(find.widgetWithText(OutlinedButton, 'Fait').first);
    await tester.pumpAndSettle();

    expect(find.text('Sonatrach Distribution'), findsOneWidget);
    expect(find.textContaining('Serveur injoignable'), findsOneWidget);
  });

  testWidgets('l\'écran demande une mise à jour à l\'ouverture', (tester) async {
    await monter(tester);
    final rafraichissements = appelsCanal
        .where((a) => a.method == 'listActivities' && a.arguments['refresh'] == true);
    expect(rafraichissements, isNotEmpty);
  });
}
