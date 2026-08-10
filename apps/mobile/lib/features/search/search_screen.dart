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
  ConsumerState<SearchScreen> createState() => SearchScreenState();
}

/// Publique pour une seule raison : [SearchScreenState.normaliser] porte un
/// invariant vérifiable au banc, et l'enfermer dans un `State` privé le
/// rendrait intestable sans monter toute une application.
class SearchScreenState extends ConsumerState<SearchScreen> {
  final _controleur = TextEditingController();
  bool _enCours = false;
  bool _cherche = false;
  String _interroge = '';
  List<Map<String, String>> _resultats = const [];

  @override
  void initState() {
    super.initState();
    // Redessine à chaque frappe, pour faire apparaître et disparaître le
    // bouton d'effacement. Sans cela il resterait figé dans son état initial.
    _controleur.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _controleur.dispose();
    super.dispose();
  }

  /// Minimum de chiffres avant d'interroger le serveur.
  ///
  /// Doit rester aligné sur `call.tracker.log.FRAGMENT_MIN` côté Odoo. Le
  /// contrôle est fait **des deux côtés** et ce n'est pas une redondance
  /// inutile : ici pour dire pourquoi rien ne part, là-bas parce que le
  /// serveur ne peut faire confiance à aucun client.
  static const fragmentMin = 4;

  /// Ne garde que ce qui fait un numéro : les chiffres et le `+` de tête.
  ///
  /// Un numéro se recopie avec des espaces, des points ou des tirets — c'est
  /// même la forme sous laquelle il est écrit sur une carte de visite. Le
  /// serveur les tolère, mais ils partent alors dans l'URL et se retrouvent
  /// tels quels au journal d'audit, où ils rendent illisible la seule trace
  /// qui dise quel numéro a été consulté.
  static String normaliser(String saisie) {
    final brut = saisie.trim();
    final chiffres = brut.replaceAll(RegExp(r'[^0-9]'), '');
    if (chiffres.isEmpty) return '';
    return brut.startsWith('+') ? '+$chiffres' : chiffres;
  }

  /// Nombre de chiffres saisis, mise en forme retirée.
  int get _chiffresSaisis =>
      _controleur.text.replaceAll(RegExp(r'[^0-9]'), '').length;

  Future<void> _chercher() async {
    final fragment = normaliser(_controleur.text);
    if (_chiffresSaisis < fragmentMin) return;

    setState(() {
      _enCours = true;
      _cherche = true;
      // Mémorisé pour l'afficher avec le résultat : « rien pour CE numéro-là »
      // vaut mieux que « rien », qui laisse croire à une panne quand c'est une
      // faute de frappe.
      _interroge = fragment;
    });
    final resultats =
        await ref.read(captureChannelProvider).rechercherContacts(fragment);
    if (!mounted) return;
    setState(() {
      _resultats = resultats;
      _enCours = false;
    });
  }

  void _effacer() {
    _controleur.clear();
    setState(() {
      _cherche = false;
      _resultats = const [];
      _interroge = '';
    });
  }

  Future<void> _appeler(String numero) {
    return ref.read(captureChannelProvider).composer(numero);
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
            // Deux boutons, et celui d'effacement compte autant que l'autre :
            // le champ garde sa saisie entre deux recherches, et une frappe
            // interrompue y restait sans qu'on la remarque. Toutes les
            // recherches suivantes repartaient alors du même texte tronqué —
            // une faute de frappe se lisait comme « la recherche ne marche
            // pas ». Constaté sur téléphone le 2026-08-10.
            suffixIcon: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_controleur.text.isNotEmpty)
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: _enCours ? null : _effacer,
                    tooltip: l10n.searchClear,
                  ),
                IconButton(
                  icon: const Icon(Icons.arrow_forward),
                  // Grisé tant que le fragment est trop court : un bouton qui
                  // ne fait rien quand on appuie dessus se lit comme une
                  // panne. L'aide sous le champ dit alors ce qui manque.
                  onPressed: (_enCours || _chiffresSaisis < fragmentMin)
                      ? null
                      : _chercher,
                  tooltip: l10n.searchAction,
                ),
              ],
            ),
            helperText: _controleur.text.isNotEmpty &&
                    _chiffresSaisis < fragmentMin
                ? l10n.searchTooShort(fragmentMin)
                : l10n.searchPartialHint,
          ),
        ),
        const SizedBox(height: 24),
        if (_enCours)
          const Center(child: CircularProgressIndicator())
        else if (!_cherche)
          _Vide(icone: Icons.contact_phone_outlined, texte: l10n.searchPrompt)
        else if (_resultats.isEmpty)
          _Vide(
            icone: Icons.person_off_outlined,
            texte: l10n.searchNotFoundFor(_interroge),
          )
        else
          for (final fiche in _resultats)
            _Fiche(fiche: fiche, onAppeler: _appeler),
      ],
    );
  }
}

class _Fiche extends StatelessWidget {
  const _Fiche({required this.fiche, required this.onAppeler});

  final Map<String, String> fiche;
  final Future<void> Function(String numero) onAppeler;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final scheme = Theme.of(context).colorScheme;

    final numero = fiche['phone'] ?? '';

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
            if (numero.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                numero,
                // Un numéro se lit de gauche à droite, même en arabe.
                textDirection: TextDirection.ltr,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ],
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
            if (numero.isNotEmpty) ...[
              const SizedBox(height: 12),
              // Pleine largeur : c'est l'action de l'écran. On cherche un
              // numéro pour l'appeler, pas pour le lire.
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: () => onAppeler(numero),
                  icon: const Icon(Icons.call),
                  label: Text(l10n.searchCall),
                ),
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
