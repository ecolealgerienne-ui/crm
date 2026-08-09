import 'package:call_tracker/data/capture_models.dart';
import 'package:call_tracker/features/calls/note_dialog.dart';
import 'package:call_tracker/l10n/app_localizations.dart';
import 'package:call_tracker/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Non-régression sur le dialogue de note.
///
/// Le défaut qu'ils gardent fermé : le contrôleur de saisie était détruit par
/// la fonction appelante juste après `showDialog`, qui rend la main AVANT la
/// fin de l'animation de fermeture. Le champ était donc encore monté, sa
/// propre destruction échouait, la désactivation du sous-arbre s'interrompait,
/// et Flutter échouait sur « _dependents.isEmpty: is not true » — en
/// remplaçant TOUTE l'application par l'écran d'erreur rouge.
///
/// `pumpAndSettle` va jusqu'au bout de l'animation de fermeture : c'est là que
/// le défaut se manifestait, et c'est pour cela que ces tests le rattrapent.
void main() {
  const canal = MethodChannel('com.echango.call_tracker/capture');
  late List<MethodCall> appelsCanal;

  setUp(() {
    appelsCanal = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (appel) async {
      appelsCanal.add(appel);
      // `listCalls` doit rendre une liste, les autres méthodes ne rendent rien.
      return appel.method == 'listCalls' ? <Map<String, dynamic>>[] : null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, null);
  });

  final appel = CallEntry(
    id: 42,
    clientEventId: 'evt-test',
    phoneNumber: '+213555000000',
    direction: CallDirection.inbound,
    durationSeconds: 30,
    startedAt: DateTime.utc(2026, 8, 9, 14, 32),
    syncStatus: SyncStatus.pending,
  );

  /// Monte une app minimale et ouvre le dialogue sur l'appel donné.
  Future<void> ouvrir(WidgetTester tester, [CallEntry? cible]) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          // Les quatre délégués de la vraie application. En omettre un fait
          // échouer le test sur un avertissement de locale non couverte, ce
          // qui n'a rien à voir avec ce qu'on vérifie ici.
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: supportedAppLocales,
          locale: const Locale('fr'),
          home: Consumer(
            builder: (context, ref, _) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () =>
                      ouvrirDialogueNote(context, ref, cible ?? appel),
                  child: const Text('ouvrir'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('ouvrir'));
    await tester.pumpAndSettle();
  }

  testWidgets('enregistrer une note ne casse pas l\'arbre de widgets',
      (tester) async {
    await ouvrir(tester);

    await tester.enterText(find.byType(TextField), 'Rappeler vendredi');
    await tester.tap(find.text('Enregistrer la note'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);

    final saveNote = appelsCanal.firstWhere((a) => a.method == 'saveNote');
    expect(saveNote.arguments['id'], 42);
    expect(saveNote.arguments['note'], 'Rappeler vendredi');
  });

  testWidgets('« Sans note » libère l\'appel sans casser l\'arbre',
      (tester) async {
    await ouvrir(tester);

    await tester.tap(find.text('Sans note'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(appelsCanal.map((a) => a.method), contains('skipNote'));
    expect(appelsCanal.map((a) => a.method), isNot(contains('saveNote')));
  });

  testWidgets('valider un champ vide équivaut à renoncer', (tester) async {
    // Sinon on écrirait une note vide dans le CRM, qui remonterait ensuite
    // comme « dernière note » du contact et masquerait la précédente.
    await ouvrir(tester);

    await tester.tap(find.text('Enregistrer la note'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(appelsCanal.map((a) => a.method), contains('skipNote'));
  });

  testWidgets('la note existante est proposée à la réouverture',
      (tester) async {
    await ouvrir(
      tester,
      CallEntry(
        id: 43,
        clientEventId: 'evt-2',
        phoneNumber: '+213555000001',
        direction: CallDirection.outbound,
        durationSeconds: 10,
        startedAt: DateTime.utc(2026, 8, 9),
        syncStatus: SyncStatus.pending,
        note: 'Déjà écrite',
      ),
    );

    expect(find.text('Déjà écrite'), findsOneWidget);
  });
}
