import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';

/// Avis d'information — ce que l'application enregistre, qui le lit, combien
/// de temps.
///
/// **Pourquoi cet écran existe.** Toute la chaîne technique était en place
/// sans lui : les appels sont capturés, transmis, lus par un responsable. Le
/// seul maillon manquant était que la personne enregistrée le sache. C'est
/// aussi le seul point de la chaîne qui soit juridiquement fragile (loi 18-07,
/// information préalable) et, plus concrètement, le plus coûteux à découvrir
/// après coup : un commercial qui apprend par hasard que ses appels remontent
/// depuis des mois n'utilisera plus l'outil de bonne grâce.
///
/// Il sert à deux moments, et le même contenu vaut pour les deux :
///
/// - **en porte** au premier lancement, avec un accusé de lecture ;
/// - **en consultation** depuis les réglages, à tout moment. Un avis qu'on ne
///   peut plus relire n'informe personne — il fait signer.
///
/// ⚠️ **Ce que cet écran ne peut pas garantir.** La capture vit côté natif et
/// ne dépend pas de Flutter : un téléphone configuré par quelqu'un d'autre
/// puis remis en main propre capture dès le premier appel, que le titulaire
/// ait vu cet écran ou non. Aucun code ne peut distinguer qui tient le
/// téléphone. La remise en main propre reste donc une étape humaine, décrite
/// dans `docs/CONFORMITE_DONNEES_APPELS.md`.
class NoticeScreen extends ConsumerWidget {
  const NoticeScreen({super.key, this.enPorte = false});

  /// En porte : accusé de lecture obligatoire, aucun retour possible.
  /// En consultation : simple fermeture.
  final bool enPorte;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final locale = ref.watch(localeProvider);
    final reglages = ref.watch(reglagesProvider);

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: !enPorte,
        title: Text(l10n.noticeTitle),
        actions: [
          // Le sélecteur de langue est ici, et ce n'est pas de la décoration :
          // en porte, c'est le seul écran accessible. Un avis rédigé dans une
          // langue que le lecteur ne pratique pas n'est pas une information,
          // et l'accusé de lecture qui suit ne vaudrait rien.
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
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        children: [
          Text(l10n.noticeIntro, style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: 24),

          _Bloc(
            icone: Icons.fact_check_outlined,
            titre: l10n.noticeRecordedTitle,
            points: [
              l10n.noticeRecordedNumber,
              l10n.noticeRecordedWhen,
              l10n.noticeRecordedDirection,
              l10n.noticeRecordedNote,
            ],
          ),

          // Placé juste après, et pas en fin d'écran : c'est la question que
          // se pose réellement quelqu'un à qui on annonce que ses appels sont
          // suivis. La repousser en bas de page laisse la crainte s'installer
          // pendant toute la lecture.
          _Bloc(
            icone: Icons.mic_off_outlined,
            titre: l10n.noticeNotRecordedTitle,
            points: [
              l10n.noticeNotRecordedContent,
              l10n.noticeNotRecordedPersonal,
              l10n.noticeNotRecordedHours,
            ],
            accent: true,
          ),

          _Bloc(
            icone: Icons.visibility_outlined,
            titre: l10n.noticeWhoTitle,
            points: [
              l10n.noticeWhoYou,
              l10n.noticeWhoManager,
              l10n.noticeWhoAudited,
            ],
          ),

          _Bloc(
            icone: Icons.schedule_outlined,
            titre: l10n.noticeHowLongTitle,
            points: [
              reglages.maybeWhen(
                data: (r) => _dureeConservation(l10n, r.retentionKnown, r.retentionDays),
                // Le canal natif est indisponible en attendant, ou en échec :
                // dire « fixée par votre employeur » reste vrai dans les deux
                // cas, alors qu'avancer un chiffre par défaut serait un
                // engagement que personne n'a pris.
                orElse: () => l10n.noticeRetentionUnknown,
              ),
            ],
          ),

          _Bloc(
            icone: Icons.gavel_outlined,
            titre: l10n.noticeRightsTitle,
            points: [l10n.noticeRightsBody],
          ),

          const SizedBox(height: 16),
          if (enPorte)
            FilledButton(
              onPressed: () => ref.read(avisLuProvider.notifier).accuser(),
              child: Text(l10n.noticeAcknowledge),
            )
          else
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(l10n.commonClose),
            ),
        ],
      ),
    );
  }
}

/// La durée de conservation, dans les trois cas où elle peut se trouver.
///
/// Les distinguer n'est pas une coquetterie : « pas encore connue » et
/// « aucune suppression automatique » se ressemblent dans le code — les deux
/// valent zéro — et disent l'inverse l'un de l'autre au lecteur.
String _dureeConservation(AppLocalizations l10n, bool connue, int jours) {
  if (!connue) return l10n.noticeRetentionUnknown;
  if (jours <= 0) return l10n.noticeRetentionNone;

  final texte = l10n.noticeRetentionDays(jours);
  // Mille quatre-vingt-quinze jours ne dit rien à personne. L'équivalent en
  // années n'est ajouté qu'au-delà d'un an, sinon « environ zéro an ».
  if (jours < 365) return texte;
  return '$texte ${l10n.noticeRetentionApprox((jours / 365).round())}';
}

class _Bloc extends StatelessWidget {
  const _Bloc({
    required this.icone,
    required this.titre,
    required this.points,
    this.accent = false,
  });

  final IconData icone;
  final String titre;
  final List<String> points;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final teinte = accent ? scheme.tertiary : scheme.primary;

    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icone, size: 20, color: teinte),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  titre,
                  style: Theme.of(context)
                      .textTheme
                      .titleMedium
                      ?.copyWith(color: teinte),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          for (final point in points)
            Padding(
              padding: const EdgeInsetsDirectional.only(start: 28, bottom: 6),
              child: Text(point,
                  style: Theme.of(context).textTheme.bodyMedium),
            ),
        ],
      ),
    );
  }
}
