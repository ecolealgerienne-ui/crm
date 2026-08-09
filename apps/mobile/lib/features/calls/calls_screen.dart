import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `show DateFormat` et pas un import nu : package:intl exporte lui aussi un
// `TextDirection`, qui masque celui de Material et fait disparaître `.ltr`.
import 'package:intl/intl.dart' show DateFormat;

import '../../app/theme.dart';
import '../../data/capture_models.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';
import 'note_dialog.dart';

class CallsScreen extends ConsumerStatefulWidget {
  const CallsScreen({super.key});

  @override
  ConsumerState<CallsScreen> createState() => _CallsScreenState();
}

class _CallsScreenState extends ConsumerState<CallsScreen>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    // L'observateur sert au retour d'arrière-plan : toucher la notification
    // alors que l'app tourne déjà ne reconstruit pas l'écran, et l'invite ne
    // s'ouvrirait jamais dans ce cas — qui est pourtant le plus fréquent.
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _ouvrirInviteEnAttente());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState etat) {
    if (etat != AppLifecycleState.resumed) return;
    // Recharger la liste, et pas seulement rouvrir l'invite : les appels sont
    // capturés par la couche native alors que l'application est en
    // arrière-plan. Sans cette invalidation, revenir sur l'app montre l'état
    // d'avant — et il faut penser à tirer pour rafraîchir, ce que personne ne
    // fait puisque rien n'indique que la liste est périmée.
    ref.invalidate(appelsProvider);
    _ouvrirInviteEnAttente();
  }

  Future<void> _ouvrirInviteEnAttente() async {
    final id = await ref.read(captureChannelProvider).noteEnAttente();
    if (id == null || !mounted) return;

    final appels = await ref.read(captureChannelProvider).listerAppels();
    final appel = appels.where((a) => a.id == id).firstOrNull;
    if (appel == null || !mounted) return;

    await ouvrirDialogueNote(context, ref, appel);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final appels = ref.watch(appelsProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(appelsProvider),
      child: appels.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Message(
          icone: Icons.error_outline,
          titre: l10n.commonError(e.toString()),
          corps: '',
        ),
        data: (liste) {
          final enAttente =
              liste.where((a) => a.syncStatus != SyncStatus.sent).length;
          return Column(
            children: [
              _BandeauSynchro(enAttente: enAttente),
              Expanded(
                child: liste.isEmpty
                    ? _Message(
                        icone: Icons.call_outlined,
                        titre: l10n.callsEmptyTitle,
                        corps: l10n.callsEmptyBody,
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        itemCount: liste.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, i) => _LigneAppel(
                          appel: liste[i],
                          // Le dialogue est ouvert par l'ÉCRAN, pas par la
                          // ligne : enregistrer la note recharge la liste,
                          // donc la ligne disparaît pendant que le dialogue
                          // vit encore. Le contexte de l'écran, lui, survit.
                          onNote: () => ouvrirDialogueNote(
                            this.context, ref, liste[i],
                          ),
                        ),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _BandeauSynchro extends ConsumerWidget {
  const _BandeauSynchro({required this.enAttente});

  final int enAttente;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final couleurs = Theme.of(context).extension<AppSemanticColors>()!;
    final teinte = enAttente == 0 ? couleurs.synced : couleurs.pending;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
      color: teinte.withValues(alpha: 0.10),
      child: Row(
        children: [
          Icon(
            enAttente == 0 ? Icons.cloud_done_outlined : Icons.cloud_sync_outlined,
            color: teinte,
            size: 20,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              l10n.callsPendingCount(enAttente),
              style: Theme.of(context).textTheme.labelLarge,
            ),
          ),
          if (enAttente > 0)
            TextButton(
              onPressed: () async {
                await ref
                    .read(captureChannelProvider)
                    .synchroniserMaintenant();
                ref.invalidate(appelsProvider);
              },
              child: Text(l10n.callsSyncNow),
            ),
        ],
      ),
    );
  }
}

class _LigneAppel extends StatelessWidget {
  const _LigneAppel({required this.appel, required this.onNote});

  final CallEntry appel;
  final VoidCallback onNote;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final couleurs = Theme.of(context).extension<AppSemanticColors>()!;
    final locale = Localizations.localeOf(context).toLanguageTag();

    final (icone, teinte, libelle) = switch (appel.direction) {
      CallDirection.inbound => (
          Icons.call_received,
          couleurs.inbound,
          l10n.directionInbound
        ),
      CallDirection.outbound => (
          Icons.call_made,
          couleurs.outbound,
          l10n.directionOutbound
        ),
      CallDirection.missed => (
          Icons.call_missed,
          couleurs.missed,
          l10n.directionMissed
        ),
    };

    // `toLocal()` seulement ici : l'horodatage est en UTC du capteur natif
    // jusqu'à Odoo, et n'est converti que pour être lu par un humain.
    final heure = DateFormat.yMMMd(locale)
        .add_Hm()
        .format(appel.startedAt.toLocal());

    final duree = appel.durationSeconds < 60
        ? l10n.durationSeconds(appel.durationSeconds)
        : l10n.durationMinutesSeconds(
            appel.durationSeconds ~/ 60,
            appel.durationSeconds % 60,
          );

    return ListTile(
      leading: CircleAvatar(
        backgroundColor: teinte.withValues(alpha: 0.12),
        foregroundColor: teinte,
        child: Icon(icone, size: 20),
      ),
      title: Text(
        appel.phoneNumber,
        // Un numéro se lit de gauche à droite même en arabe : sans cette
        // contrainte, le « + » de l'indicatif international se retrouve à
        // droite en mise en page RTL.
        textDirection: TextDirection.ltr,
      ),
      subtitle: Text(
        [
          '$libelle · $duree · $heure',
          if (appel.note?.isNotEmpty == true) appel.note!,
        ].join('\n'),
      ),
      isThreeLine: appel.note?.isNotEmpty == true,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Rattrapage manuel : la notification a pu être balayée, ou
          // l'autorisation de notifier refusée. Sans ce bouton, la note
          // deviendrait inaccessible dans les deux cas.
          if (appel.awaitingNote)
            IconButton(
              tooltip: l10n.noteAdd,
              icon: const Icon(Icons.edit_note),
              onPressed: onNote,
            ),
          _PastilleSynchro(appel: appel),
        ],
      ),
    );
  }
}

class _PastilleSynchro extends StatelessWidget {
  const _PastilleSynchro({required this.appel});

  final CallEntry appel;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final couleurs = Theme.of(context).extension<AppSemanticColors>()!;
    final scheme = Theme.of(context).colorScheme;

    final (teinte, texte, infobulle) = switch (appel.syncStatus) {
      SyncStatus.sent => (couleurs.synced, l10n.syncSent, l10n.syncSent),
      SyncStatus.pending => (
          couleurs.pending,
          l10n.syncPending,
          l10n.syncPending
        ),
      SyncStatus.failed => (
          scheme.error,
          l10n.syncFailed,
          l10n.syncFailedWithReason(appel.lastError ?? '—'),
        ),
    };

    return Tooltip(
      message: infobulle,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: teinte.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppRadii.sm),
        ),
        child: Text(
          texte,
          style: Theme.of(context)
              .textTheme
              .labelSmall
              ?.copyWith(color: teinte),
        ),
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({required this.icone, required this.titre, required this.corps});

  final IconData icone;
  final String titre;
  final String corps;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 48),
        Icon(icone, size: 56, color: scheme.onSurfaceVariant),
        const SizedBox(height: 16),
        Text(
          titre,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        if (corps.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            corps,
            textAlign: TextAlign.center,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ],
      ],
    );
  }
}
