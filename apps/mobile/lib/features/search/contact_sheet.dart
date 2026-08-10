import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';

/// Fiche complète d'un contact, ouverte depuis un résultat de recherche.
///
/// **Pourquoi un second aller-retour alors qu'on vient d'obtenir une liste.**
/// Les deux routes ne rendent pas la même chose, et c'est délibéré :
///
/// - `/call_tracker/contacts/<fragment>` rend une liste, donc le strict
///   nécessaire pour choisir — nom, numéro, société, étape. Elle peut toucher
///   tout le carnet d'adresses ; plus elle en dit par résultat, plus un jeton
///   volé récolte à chaque requête.
/// - `/call_tracker/contact/<numero>` rend UNE fiche, avec la dernière note.
///   Elle exige un numéro complet : on ne la déclenche que pour un contact
///   qu'on a déjà identifié.
///
/// Charger la note pour dix résultats dont on en ouvrira un seul coûterait dix
/// fois plus au serveur et sortirait neuf notes que personne ne lira.
///
/// Le second appel passe par le cache local (30 minutes) : ouvrir puis
/// refermer une fiche ne rappelle pas le serveur.
class ContactSheet extends ConsumerStatefulWidget {
  const ContactSheet({super.key, required this.resume});

  /// Ce que la recherche a rendu : `name`, `phone`, `company`, `crm_stage`.
  ///
  /// Affiché immédiatement, sans attendre le réseau. L'écran s'ouvre donc
  /// rempli ; seule la note arrive après.
  final Map<String, String> resume;

  @override
  ConsumerState<ContactSheet> createState() => _ContactSheetState();
}

class _ContactSheetState extends ConsumerState<ContactSheet> {
  Map<String, String>? _detail;
  bool _enCours = true;

  String get _numero => widget.resume['phone'] ?? '';

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    if (_numero.isEmpty) {
      setState(() => _enCours = false);
      return;
    }
    final fiche = await ref.read(captureChannelProvider).chercherContact(_numero);
    if (!mounted) return;
    setState(() {
      _detail = fiche;
      _enCours = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;

    // Le détail complète le résumé, il ne le remplace pas : si la route de
    // fiche est injoignable, la fiche reste lisible avec ce que la recherche
    // avait déjà rendu, au lieu de se vider.
    final nom = _detail?['name']?.isNotEmpty == true
        ? _detail!['name']!
        : widget.resume['name'] ?? '';
    final societe = _detail?['company']?.isNotEmpty == true
        ? _detail!['company']!
        : widget.resume['company'] ?? '';
    final etape = _detail?['crm_stage']?.isNotEmpty == true
        ? _detail!['crm_stage']!
        : widget.resume['crm_stage'] ?? '';
    final note = _detail?['last_notes'] ?? '';

    return Scaffold(
      appBar: AppBar(title: Text(l10n.contactSheetTitle)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
        children: [
          Text(nom, style: Theme.of(context).textTheme.headlineSmall),
          if (societe.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              societe,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
          ],
          if (etape.isNotEmpty) ...[
            const SizedBox(height: 12),
            Align(
              alignment: AlignmentDirectional.centerStart,
              child: Chip(
                label: Text(etape),
                backgroundColor: scheme.primaryContainer,
                side: BorderSide.none,
              ),
            ),
          ],
          if (_numero.isNotEmpty) ...[
            const SizedBox(height: 20),
            // `searchHint` decrit le CHAMP DE RECHERCHE (« Numéro ou début
            // de numéro ») : le reutiliser ici affichait cette invite comme
            // etiquette du numero d'un client, ce qui n'a aucun sens sur une
            // fiche. Vu sur une capture d'ecran, jamais dans un test — aucune
            // assertion ne portait sur ce libelle.
            _Champ(etiquette: l10n.contactSheetPhone, valeur: _numero, ltr: true),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () =>
                    ref.read(captureChannelProvider).composer(_numero),
                icon: const Icon(Icons.call),
                label: Text(l10n.searchCall),
              ),
            ),
          ],
          const SizedBox(height: 28),
          Text(
            l10n.searchLastNote,
            style: Theme.of(context)
                .textTheme
                .labelLarge
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 6),
          if (_enCours)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: LinearProgressIndicator(),
            )
          else
            Text(
              // Une note absente se dit, elle ne se laisse pas deviner par un
              // blanc : « pas encore de note » et « la fiche n'a pas chargé »
              // se ressemblent à l'écran et disent l'inverse.
              note.isEmpty ? l10n.contactSheetNoNote : note,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: note.isEmpty ? scheme.onSurfaceVariant : null,
                    fontStyle: note.isEmpty ? FontStyle.italic : null,
                  ),
            ),
        ],
      ),
    );
  }
}

class _Champ extends StatelessWidget {
  const _Champ({required this.etiquette, required this.valeur, this.ltr = false});

  final String etiquette;
  final String valeur;
  final bool ltr;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          etiquette,
          style: Theme.of(context)
              .textTheme
              .labelLarge
              ?.copyWith(color: scheme.onSurfaceVariant),
        ),
        const SizedBox(height: 4),
        Text(
          valeur,
          // Un numéro se lit de gauche à droite, même en arabe.
          textDirection: ltr ? TextDirection.ltr : null,
          style: Theme.of(context).textTheme.titleMedium,
        ),
      ],
    );
  }
}
