import 'package:call_tracker/app/home_shell.dart';
import 'package:call_tracker/app/theme.dart';
import 'package:call_tracker/features/notice/notice_screen.dart';
import 'package:call_tracker/l10n/app_localizations.dart';
import 'package:call_tracker/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// L'avis d'information : la porte, et ce qu'elle dit.
///
/// Ces tests protègent une propriété qui n'a rien de technique — que personne
/// ne soit enregistré sans le savoir. Le défaut, s'il revenait, serait
/// parfaitement silencieux : l'application marcherait, les appels
/// remonteraient, et rien ne signalerait que l'écran a disparu.
void main() {
  const canal = MethodChannel('com.echango.call_tracker/capture');

  /// Réglages renvoyés par le faux canal natif, ajustables par test.
  late Map<String, Object?> reglagesNatifs;

  setUp(() {
    reglagesNatifs = {
      'serverUrl': 'https://exemple.test',
      'hasToken': true,
      'captureEnabled': true,
      'fromHour': 8,
      'toHour': 19,
      'retentionDays': 0,
      'retentionKnown': false,
    };
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, (appel) async {
      // Les tests de la porte vont jusqu'aux onglets : le faux canal doit
      // répondre à tout ce que l'écran des appels interroge, avec le bon type.
      // Un `null` là où un `int` est attendu casse l'écran sur une erreur de
      // type qui n'a rien à voir avec l'avis.
      return switch (appel.method) {
        'getSettings' => reglagesNatifs,
        'listCalls' => <Map<String, dynamic>>[],
        'pendingCount' => 0,
        'consumePendingNoteCallId' => null,
        'hasCallScreeningRole' || 'canDrawOverlay' => true,
        'isBatteryOptimised' => false,
        _ => null,
      };
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canal, null);
  });

  Future<ProviderContainer> monter(
    WidgetTester tester, {
    Map<String, Object> prefs = const {},
    Widget? ecran,
    String langue = 'fr',
    bool vueHaute = false,
  }) async {
    // L'avis est long : sur les 800×600 par défaut d'un banc de test, tout ce
    // qui suit le premier bloc n'est jamais construit — un `ListView` ne monte
    // pas ses enfants hors écran — et les recherches de texte échouent sans
    // rapport avec ce qui est vérifié. Les tests de contenu demandent donc une
    // hauteur qui contient l'écran entier ; sur un vrai téléphone, il se fait
    // défiler.
    //
    // Réservé à ces tests-là : une vue de 2 600 px fait déborder l'état vide
    // de l'écran des appels, ce qui n'a aucun sens sur un téléphone et
    // masquerait le vrai résultat des tests qui vont jusqu'aux onglets.
    if (vueHaute) {
      tester.view.physicalSize = const Size(420, 2600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
    }

    SharedPreferences.setMockInitialValues({'ui.locale': langue, ...prefs});
    final preferences = await SharedPreferences.getInstance();
    final container = ProviderContainer(
      overrides: [sharedPreferencesProvider.overrideWithValue(preferences)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: Consumer(
          builder: (context, ref, _) => MaterialApp(
            // Suit le provider, comme la vraie application : sans cela, le
            // sélecteur de langue de l'avis n'aurait aucun effet visible et
            // le test qui l'exerce ne vérifierait rien.
            locale: ref.watch(localeProvider),
            // Les couleurs sémantiques, et rien d'autre du thème : le bandeau
            // de synchronisation les lit avec un `!`, et sans elles il lève
            // au lieu de s'afficher. Passer par `AppTheme.light` entier
            // ferait télécharger les polices à google_fonts, ce qu'un banc de
            // test sans réseau ne peut pas faire.
            theme: ThemeData(
              extensions: [AppTheme.semanticColorsFor(Brightness.light)],
            ),
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: supportedAppLocales,
            home: ecran ??
                (ref.watch(avisLuProvider)
                    ? const HomeShell()
                    : const NoticeScreen(enPorte: true)),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return container;
  }

  group('La porte', () {
    testWidgets("s'ouvre sur l'avis au premier lancement", (tester) async {
      await monter(tester);

      expect(find.byType(NoticeScreen), findsOneWidget);
      expect(find.byType(HomeShell), findsNothing,
          reason: "les onglets ne doivent pas etre atteignables avant lecture");
    });

    testWidgets('laisse passer une fois l\'avis accusé', (tester) async {
      await monter(tester, prefs: {'notice.acknowledgedVersion': noticeVersion});

      expect(find.byType(HomeShell), findsOneWidget);
      expect(find.byType(NoticeScreen), findsNothing);
    });

    testWidgets('le bouton mène aux onglets et retient le choix',
        (tester) async {
      final container = await monter(tester, vueHaute: true);

      await tester.tap(find.text('J\'ai lu et compris'));
      await tester.pumpAndSettle();

      expect(find.byType(HomeShell), findsOneWidget);
      expect(
        container.read(sharedPreferencesProvider).getInt('notice.acknowledgedVersion'),
        noticeVersion,
        reason: "sans persistance, l'avis reviendrait a chaque ouverture",
      );
    });

    testWidgets('se rouvre quand la version de l\'avis a changé',
        (tester) async {
      // LE test de ce fichier. Le jour où l'entreprise se met à capturer
      // autre chose, l'accusé de lecture précédent ne porte plus sur le texte
      // affiché : il doit être redemandé. Avec un booléen « déjà vu » à la
      // place du numéro de version, ce test échoue — et c'est exactement le
      // défaut qu'il interdit.
      await monter(tester, prefs: {'notice.acknowledgedVersion': noticeVersion - 1});

      expect(find.byType(NoticeScreen), findsOneWidget);
    });
  });

  group('Le contenu', () {
    testWidgets('dit que les conversations ne sont pas écoutées',
        (tester) async {
      await monter(tester, vueHaute: true);

      // La seule phrase que tout le monde cherche. La perdre dans une
      // réécriture viderait l'écran de son effet.
      expect(
        find.textContaining("n'accède pas au microphone"),
        findsOneWidget,
      );
    });

    testWidgets('annonce que les consultations sont journalisées',
        (tester) async {
      await monter(tester, vueHaute: true);
      expect(find.textContaining('journalisée'), findsOneWidget);
    });

    testWidgets('reste lisible en arabe', (tester) async {
      await monter(tester, langue: 'ar', vueHaute: true);

      expect(find.text('قرأتُ وفهمت'), findsOneWidget);
      expect(
        Directionality.of(tester.element(find.byType(NoticeScreen))),
        TextDirection.rtl,
      );
    });

    testWidgets('permet de changer de langue avant d\'accuser réception',
        (tester) async {
      // Un avis rédigé dans une langue que le lecteur ne pratique pas n'est
      // pas une information, et l'accusé de lecture qui suit ne vaut rien.
      // En porte, cet écran est le seul accessible : le sélecteur doit y être.
      await monter(tester, vueHaute: true);

      await tester.tap(find.byIcon(Icons.translate));
      await tester.pumpAndSettle();
      await tester.tap(find.text('العربية'));
      await tester.pumpAndSettle();

      expect(find.text('قرأتُ وفهمت'), findsOneWidget);
    });
  });

  group('La durée de conservation', () {
    testWidgets('affiche le chiffre annoncé par le serveur', (tester) async {
      reglagesNatifs['retentionDays'] = 1095;
      reglagesNatifs['retentionKnown'] = true;
      await monter(tester, vueHaute: true);

      // Pas de comparaison sur la chaîne entière : en français le séparateur
      // de milliers est une espace insécable étroite, pas une espace
      // ordinaire, et le test échouerait sur un caractère invisible.
      expect(find.textContaining('095'), findsOneWidget);
      expect(find.textContaining('3 ans'), findsOneWidget,
          reason: '1095 jours ne dit rien a personne');
    });

    testWidgets('n\'invente aucun chiffre tant que le serveur s\'est tu',
        (tester) async {
      // `retentionKnown` faux : aucun appel n'a encore été accepté. Afficher
      // une valeur par défaut serait un engagement que personne n'a pris.
      await monter(tester, vueHaute: true);

      expect(find.textContaining('fixée par votre employeur'), findsOneWidget);
      expect(find.textContaining('jours'), findsNothing);
    });

    testWidgets('distingue « aucune purge » de « pas encore connue »',
        (tester) async {
      // Les deux valent zéro dans le code et disent l'inverse au lecteur.
      reglagesNatifs['retentionDays'] = 0;
      reglagesNatifs['retentionKnown'] = true;
      await monter(tester, vueHaute: true);

      expect(find.textContaining('Aucune suppression automatique'),
          findsOneWidget);
    });
  });

  group('En consultation', () {
    testWidgets('se referme sans rien accuser', (tester) async {
      final container = await monter(
        tester,
        prefs: {'notice.acknowledgedVersion': noticeVersion},
        ecran: const NoticeScreen(),
        vueHaute: true,
      );

      expect(find.text('J\'ai lu et compris'), findsNothing,
          reason: 'relire un avis deja accuse ne redemande pas de signature');

      await tester.tap(find.text('Fermer'));
      await tester.pumpAndSettle();

      expect(
        container.read(sharedPreferencesProvider).getInt('notice.acknowledgedVersion'),
        noticeVersion,
      );
    });
  });
}
