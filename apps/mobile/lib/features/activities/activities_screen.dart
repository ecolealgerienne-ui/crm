import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../../data/capture_models.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';

/// Les appels programmés dans le CRM — la liste de travail du commercial.
///
/// **Le seul écran qui rende quelque chose au lieu de prendre.** Tout le reste
/// de l'application est rétrospectif : elle capture, elle transmet, elle
/// rapporte à un responsable. Un outil qui ne rend rien ne s'ouvre pas.
///
/// Et ce n'est pas qu'une question d'adoption : on a mesuré sur un OnePlus que
/// la surcouche constructeur gèle l'application écran éteint, et que la tâche
/// d'envoi ne tourne qu'au réveil. **Une application qu'on n'ouvre jamais est
/// une application dont la file d'envoi ne se vide pas.** L'écran qui rend
/// l'app utile est donc aussi celui qui rend la capture fiable.
class ActivitiesScreen extends ConsumerStatefulWidget {
  const ActivitiesScreen({super.key});

  @override
  ConsumerState<ActivitiesScreen> createState() => _ActivitiesScreenState();
}

class _ActivitiesScreenState extends ConsumerState<ActivitiesScreen> {
  bool _enCours = false;

  @override
  void initState() {
    super.initState();
    // Un aller-retour dès l'ouverture, sans bloquer l'affichage : le cache
    // s'affiche tout de suite, la liste fraîche le remplace quand elle arrive.
    WidgetsBinding.instance.addPostFrameCallback((_) => _rafraichir());
  }

  Future<void> _rafraichir() async {
    if (_enCours) return;
    setState(() => _enCours = true);
    await ref.read(captureChannelProvider).listerActivites(rafraichir: true);
    if (!mounted) return;
    ref.invalidate(activitesProvider);
    setState(() => _enCours = false);
  }

  Future<void> _appeler(String numero) {
    return ref.read(captureChannelProvider).composer(numero);
  }

  Future<void> _cloturer(ActiviteAppel activite) async {
    final l10n = AppLocalizations.of(context)!;
    final messager = ScaffoldMessenger.of(context);

    final ok = await ref.read(captureChannelProvider).cloturerActivite(activite.id);
    if (!mounted) return;

    if (ok) {
      ref.invalidate(activitesProvider);
    } else {
      // ⚠️ La ligne RESTE quand le serveur n'a pas confirmé. La retirer
      // ferait disparaître une tâche que personne n'a faite, et le commercial
      // croirait l'avoir cochée. Mieux vaut un bouton qui refuse de marcher
      // qu'une tâche perdue en silence.
      messager.showSnackBar(SnackBar(content: Text(l10n.activitiesDoneFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final liste = ref.watch(activitesProvider);

    return RefreshIndicator(
      onRefresh: _rafraichir,
      child: liste.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Message(texte: l10n.commonError(e.toString())),
        data: (donnees) {
          if (donnees.activites.isEmpty) {
            return ListView(
              children: [
                _BandeauFraicheur(quand: donnees.recupereeLe, enCours: _enCours),
                _Message(texte: l10n.activitiesEmpty),
              ],
            );
          }
          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              _BandeauFraicheur(quand: donnees.recupereeLe, enCours: _enCours),
              for (final activite in donnees.activites)
                _Ligne(
                  activite: activite,
                  onAppeler: _appeler,
                  onFait: () => _cloturer(activite),
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Depuis quand cette liste date.
///
/// ⚠️ Ce bandeau n'est pas décoratif. Le cache n'expire jamais — une liste
/// d'hier vaut infiniment mieux qu'un écran vide pour quelqu'un dans un
/// sous-sol. Mais une liste périmée qui se présente comme à jour est un
/// mensonge, et le commercial retournerait au papier le jour où il s'en
/// apercevrait. La fraîcheur doit donc être lisible, toujours.
class _BandeauFraicheur extends StatelessWidget {
  const _BandeauFraicheur({required this.quand, required this.enCours});

  final DateTime? quand;
  final bool enCours;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;
    final langue = Localizations.localeOf(context).toString();

    final texte = enCours
        ? l10n.activitiesRefreshing
        : quand == null
            ? l10n.activitiesNeverFetched
            : l10n.activitiesFetchedAt(
                DateFormat.yMMMd(langue).add_Hm().format(quand!.toLocal()),
              );

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
      color: scheme.surfaceContainerHigh,
      child: Row(
        children: [
          Icon(enCours ? Icons.sync : Icons.schedule,
              size: 16, color: scheme.onSurfaceVariant),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              texte,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

class _Ligne extends StatelessWidget {
  const _Ligne({
    required this.activite,
    required this.onAppeler,
    required this.onFait,
  });

  final ActiviteAppel activite;
  final Future<void> Function(String numero) onAppeler;
  final VoidCallback onFait;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;

    // Le retard se voit à la couleur, pas seulement à la date : c'est ce qu'on
    // doit repérer sans lire.
    final (teinte, etiquette) = switch (activite.etat) {
      EtatActivite.overdue => (scheme.error, l10n.activitiesOverdue),
      EtatActivite.today => (scheme.primary, l10n.activitiesToday),
      EtatActivite.planned => (scheme.onSurfaceVariant, activite.deadline),
    };

    return Card(
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.event, size: 14, color: teinte),
                const SizedBox(width: 6),
                Text(
                  etiquette,
                  style: Theme.of(context)
                      .textTheme
                      .labelMedium
                      ?.copyWith(color: teinte, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(activite.client,
                style: Theme.of(context).textTheme.titleMedium),
            if (activite.summary.isNotEmpty)
              Text(activite.summary,
                  style: Theme.of(context).textTheme.bodyMedium),
            if (activite.note.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                activite.note,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
            if (activite.phone.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(activite.phone,
                  textDirection: TextDirection.ltr,
                  style: Theme.of(context).textTheme.bodyMedium),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                if (activite.phone.isNotEmpty)
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () => onAppeler(activite.phone),
                      icon: const Icon(Icons.call),
                      label: Text(l10n.searchCall),
                    ),
                  )
                else
                  // Une activité sans numéro reste affichée : la masquer
                  // ferait perdre une tâche réelle pour un champ manquant.
                  Expanded(
                    child: Text(
                      l10n.activitiesNoNumber,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: scheme.error),
                    ),
                  ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: onFait,
                  child: Text(l10n.activitiesDone),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.texte});

  final String texte;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 64),
      child: Column(
        children: [
          Icon(Icons.event_available_outlined,
              size: 48, color: scheme.onSurfaceVariant),
          const SizedBox(height: 12),
          Text(
            texte,
            textAlign: TextAlign.center,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}
