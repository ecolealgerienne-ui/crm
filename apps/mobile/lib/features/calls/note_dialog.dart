import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/capture_models.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';

/// Saisie de la note qui suit un appel.
///
/// Deux issues explicites, et pas de croix de fermeture : « Enregistrer » et
/// « Sans note » libèrent toutes deux l'appel, qui part alors sans attendre son
/// échéance. Une fermeture silencieuse laisserait l'appel retenu deux minutes
/// pour rien, et le commercial ne saurait pas pourquoi il ne remonte pas.
Future<void> ouvrirDialogueNote(
  BuildContext context,
  WidgetRef ref,
  CallEntry appel,
) async {
  final l10n = AppLocalizations.of(context)!;
  final controleur = TextEditingController(text: appel.note ?? '');

  final enregistree = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (context) => AlertDialog(
      title: Text(l10n.noteDialogTitle),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            appel.phoneNumber,
            textDirection: TextDirection.ltr,
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: controleur,
            autofocus: true,
            maxLines: 4,
            // Même plafond que le serveur, qui refuse au-delà. Le faire
            // respecter ici évite une saisie perdue à l'envoi.
            maxLength: 1000,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(hintText: l10n.noteDialogHint),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: Text(l10n.noteSkip),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(l10n.noteSave),
        ),
      ],
    ),
  );

  final canal = ref.read(captureChannelProvider);
  final texte = controleur.text.trim();
  controleur.dispose();

  if (enregistree == true && texte.isNotEmpty) {
    await canal.enregistrerNote(appel.id, texte);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l10n.noteSaved)),
      );
    }
  } else {
    await canal.ignorerNote(appel.id);
  }

  ref.invalidate(appelsProvider);
}
