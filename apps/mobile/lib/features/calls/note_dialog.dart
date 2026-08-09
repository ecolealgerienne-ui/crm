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
  // Capturés AVANT l'attente : `AppLocalizations.of` et `ScaffoldMessenger.of`
  // s'abonnent à un widget hérité, et les appeler après coup inscrirait cet
  // abonnement sur un élément peut-être déjà en train de disparaître.
  final l10n = AppLocalizations.of(context)!;
  final messager = ScaffoldMessenger.of(context);
  final canal = ref.read(captureChannelProvider);

  final texte = await showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (context) => _DialogueNote(appel: appel),
  );

  // `null` = « Sans note ». Une chaîne vide aussi, si l'utilisateur a validé
  // sans rien écrire : dans les deux cas l'appel part tel quel.
  if (texte != null && texte.isNotEmpty) {
    await canal.enregistrerNote(appel.id, texte);
    messager.showSnackBar(SnackBar(content: Text(l10n.noteSaved)));
  } else {
    await canal.ignorerNote(appel.id);
  }

  ref.invalidate(appelsProvider);
}

/// Le dialogue possède son contrôleur de saisie, et le détruit lui-même.
///
/// ⚠️ **C'est la raison d'être de ce widget**, pas un souci de style.
/// `showDialog` rend la main dès l'appel à `Navigator.pop`, AVANT que
/// l'animation de fermeture ne soit terminée : le champ de saisie est encore
/// monté à cet instant. Détruire le contrôleur depuis la fonction appelante,
/// juste après l'attente, laissait donc un `TextField` vivant abonné à un
/// contrôleur mort. Sa propre destruction échouait ensuite, la désactivation
/// du sous-arbre s'interrompait à mi-chemin, et des éléments restaient
/// inscrits sur un widget hérité — Flutter échouait alors sur
/// « _dependents.isEmpty: is not true », un message qui ne désigne ni le
/// dialogue ni le contrôleur, et qui remplaçait toute l'application par
/// l'écran d'erreur rouge.
///
/// Un `State` détruit son contrôleur dans son propre `dispose()`, c'est-à-dire
/// quand le champ n'existe plus. L'ordre est garanti par le framework.
class _DialogueNote extends StatefulWidget {
  const _DialogueNote({required this.appel});

  final CallEntry appel;

  @override
  State<_DialogueNote> createState() => _DialogueNoteState();
}

class _DialogueNoteState extends State<_DialogueNote> {
  late final TextEditingController _controleur =
      TextEditingController(text: widget.appel.note ?? '');

  @override
  void dispose() {
    _controleur.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    return AlertDialog(
      title: Text(l10n.noteDialogTitle),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            widget.appel.phoneNumber,
            textDirection: TextDirection.ltr,
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _controleur,
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
          onPressed: () => Navigator.of(context).pop(),
          child: Text(l10n.noteSkip),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_controleur.text.trim()),
          child: Text(l10n.noteSave),
        ),
      ],
    );
  }
}
