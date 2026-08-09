import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';

/// Recherche d'un contact par numéro.
///
/// Consomme la même route que la surimpression, et passe par le même cache :
/// chercher un numéro qu'on vient de voir sonner ne doit pas provoquer un
/// second appel à l'Odoo du client.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _controleur = TextEditingController();
  bool _enCours = false;
  bool _cherche = false;
  Map<String, String>? _fiche;

  @override
  void dispose() {
    _controleur.dispose();
    super.dispose();
  }

  Future<void> _chercher() async {
    final numero = _controleur.text.trim();
    if (numero.isEmpty) return;

    setState(() {
      _enCours = true;
      _cherche = true;
    });
    final fiche = await ref.read(captureChannelProvider).chercherContact(numero);
    if (!mounted) return;
    setState(() {
      _fiche = fiche;
      _enCours = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        TextField(
          controller: _controleur,
          keyboardType: TextInputType.phone,
          // Un numéro se lit de gauche à droite même en arabe.
          textDirection: TextDirection.ltr,
          onSubmitted: (_) => _chercher(),
          decoration: InputDecoration(
            labelText: l10n.searchHint,
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(
              icon: const Icon(Icons.arrow_forward),
              onPressed: _enCours ? null : _chercher,
              tooltip: l10n.searchAction,
            ),
          ),
        ),
        const SizedBox(height: 24),
        if (_enCours)
          const Center(child: CircularProgressIndicator())
        else if (!_cherche)
          _Vide(icone: Icons.contact_phone_outlined, texte: l10n.searchPrompt)
        else if (_fiche == null)
          _Vide(icone: Icons.person_off_outlined, texte: l10n.searchNotFound)
        else
          _Fiche(fiche: _fiche!),
      ],
    );
  }
}

class _Fiche extends StatelessWidget {
  const _Fiche({required this.fiche});

  final Map<String, String> fiche;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              fiche['name'] ?? '',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            if ((fiche['company'] ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              _Ligne(etiquette: l10n.searchCompany, valeur: fiche['company']!),
            ],
            if ((fiche['crm_stage'] ?? '').isNotEmpty) ...[
              const SizedBox(height: 12),
              Chip(
                label: Text(fiche['crm_stage']!),
                backgroundColor: scheme.primaryContainer,
                side: BorderSide.none,
              ),
            ],
            if ((fiche['last_notes'] ?? '').isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(
                l10n.searchLastNote,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              ),
              const SizedBox(height: 4),
              Text(
                fiche['last_notes']!,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Ligne extends StatelessWidget {
  const _Ligne({required this.etiquette, required this.valeur});

  final String etiquette;
  final String valeur;

  @override
  Widget build(BuildContext context) {
    return Text(
      '$etiquette · $valeur',
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
    );
  }
}

class _Vide extends StatelessWidget {
  const _Vide({required this.icone, required this.texte});

  final IconData icone;
  final String texte;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Column(
        children: [
          Icon(icone, size: 48, color: scheme.onSurfaceVariant),
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
