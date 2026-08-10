import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../data/capture_models.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/core_providers.dart';
import '../notice/notice_screen.dart';

/// Permissions sans lesquelles rien ne peut être capturé.
///
/// `READ_CALL_LOG` est une permission **restreinte** par Google : elle est
/// accordable sur un APK installé manuellement ou distribué par Managed Google
/// Play, mais une publication publique exigerait que l'app soit gestionnaire
/// d'appels par défaut. C'est la raison de la distribution interne.
const _permissionsRequises = [Permission.phone];

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _urlCtrl = TextEditingController();
  final _tokenCtrl = TextEditingController();
  bool _initialise = false;
  bool _captureActive = false;
  int _de = 8;
  int _a = 19;
  String? _erreurUrl;

  @override
  void dispose() {
    _urlCtrl.dispose();
    _tokenCtrl.dispose();
    super.dispose();
  }

  void _amorcer(CaptureSettings reglages) {
    if (_initialise) return;
    _initialise = true;
    _urlCtrl.text = reglages.serverUrl;
    _captureActive = reglages.captureEnabled;
    _de = reglages.fromHour;
    _a = reglages.toHour;
  }

  Future<void> _enregistrer() async {
    final url = _urlCtrl.text.trim();
    final l10n = AppLocalizations.of(context)!;

    // Refus de tout ce qui n'est pas https : le jeton part dans un en-tête
    // Authorization, et l'accepter en clair sur http en ferait un secret
    // lisible par n'importe quel réseau wifi traversé.
    //
    // `http` toléré en débogage uniquement, pour viser l'instance Odoo locale
    // (http://10.0.2.2:8169 depuis l'émulateur). Ce n'est pas qu'une
    // permissivité d'interface : le manifeste de production interdit le trafic
    // en clair, un APK de release ne pourrait donc pas l'utiliser même si ce
    // contrôle laissait passer.
    final uri = Uri.tryParse(url);
    final schemasAcceptes = kDebugMode ? {'https', 'http'} : {'https'};
    if (url.isEmpty ||
        uri == null ||
        !schemasAcceptes.contains(uri.scheme) ||
        uri.host.isEmpty) {
      setState(() => _erreurUrl = l10n.settingsServerUrlInvalid);
      return;
    }
    setState(() => _erreurUrl = null);

    final jetonSaisi = _tokenCtrl.text.trim();
    await ref.read(captureChannelProvider).ecrireReglages(
          serverUrl: url,
          token: jetonSaisi.isEmpty ? null : jetonSaisi,
          captureEnabled: _captureActive,
          fromHour: _de,
          toHour: _a,
        );
    _tokenCtrl.clear();
    ref.invalidate(reglagesProvider);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(l10n.settingsTokenSet)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final reglages = ref.watch(reglagesProvider);

    return reglages.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(l10n.commonError(e.toString()))),
      data: (r) {
        _amorcer(r);
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            _Section(titre: l10n.settingsConnectionSection),
            TextField(
              controller: _urlCtrl,
              keyboardType: TextInputType.url,
              autocorrect: false,
              decoration: InputDecoration(
                labelText: l10n.settingsServerUrl,
                hintText: l10n.settingsServerUrlHint,
                errorText: _erreurUrl,
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _tokenCtrl,
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: l10n.settingsToken,
                hintText: l10n.settingsTokenHint,
                helperText:
                    r.hasToken ? l10n.settingsTokenSet : l10n.settingsTokenMissing,
                helperStyle: r.hasToken
                    ? null
                    : TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
            const SizedBox(height: 8),
            _Aide(l10n.settingsTokenHelp),
            const SizedBox(height: 24),

            _Section(titre: l10n.settingsCaptureSection),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _captureActive,
              onChanged: (v) => setState(() => _captureActive = v),
              title: Text(l10n.settingsCaptureEnabled),
              subtitle: Text(l10n.settingsCaptureEnabledHelp),
            ),
            const SizedBox(height: 8),
            Text(l10n.settingsHoursTitle,
                style: Theme.of(context).textTheme.titleSmall),
            _Aide(l10n.settingsHoursHelp),
            // Les menus deroulants portent une etiquette flottante posee SUR
            // leur bordure. Sans cet espace, elle vient toucher la ligne
            // d'aide au-dessus, et les deux se lisent comme un seul bloc
            // brouille. Vu sur une capture d'ecran.
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _ChoixHeure(
                    label: l10n.settingsHoursFrom,
                    valeur: _de,
                    onChanged: (v) => setState(() => _de = v),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _ChoixHeure(
                    label: l10n.settingsHoursTo,
                    valeur: _a,
                    onChanged: (v) => setState(() => _a = v),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),

            _Section(titre: l10n.permissionsSection),
            const _BlocPermissions(),
            const SizedBox(height: 12),
            const _BlocRoleFiltrage(),
            const SizedBox(height: 12),
            const _BlocSurimpression(),
            const SizedBox(height: 12),
            const _BlocBatterie(),
            const SizedBox(height: 24),

            _Section(titre: l10n.noticeSection),
            const _BlocAvis(),
            const SizedBox(height: 32),

            FilledButton(
              onPressed: _enregistrer,
              child: Text(l10n.commonSave),
            ),
          ],
        );
      },
    );
  }
}

class _ChoixHeure extends StatelessWidget {
  const _ChoixHeure({
    required this.label,
    required this.valeur,
    required this.onChanged,
  });

  final String label;
  final int valeur;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<int>(
      initialValue: valeur,
      decoration: InputDecoration(labelText: label),
      items: [
        for (var h = 0; h <= 24; h++)
          DropdownMenuItem(
            value: h,
            child: Text('${h.toString().padLeft(2, '0')}:00',
                textDirection: TextDirection.ltr),
          ),
      ],
      onChanged: (v) => v == null ? null : onChanged(v),
    );
  }
}

class _BlocPermissions extends StatefulWidget {
  const _BlocPermissions();

  @override
  State<_BlocPermissions> createState() => _BlocPermissionsState();
}

class _BlocPermissionsState extends State<_BlocPermissions> {
  bool? _accordees;
  bool _refuseDefinitivement = false;

  @override
  void initState() {
    super.initState();
    _rafraichir();
  }

  Future<void> _rafraichir() async {
    var toutes = true;
    var definitif = false;
    for (final p in _permissionsRequises) {
      final statut = await p.status;
      toutes = toutes && statut.isGranted;
      definitif = definitif || statut.isPermanentlyDenied;
    }
    if (mounted) {
      setState(() {
        _accordees = toutes;
        _refuseDefinitivement = definitif;
      });
    }
  }

  Future<void> _demander() async {
    await _permissionsRequises.request();
    await _rafraichir();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    if (_accordees == null) return const SizedBox.shrink();
    if (_accordees!) {
      return _Encart(
        icone: Icons.verified_user_outlined,
        titre: l10n.permissionsGranted,
        corps: '',
      );
    }
    return _Encart(
      icone: Icons.gpp_maybe_outlined,
      titre: l10n.permissionsMissingTitle,
      corps: _refuseDefinitivement
          ? l10n.permissionsPermanentlyDenied
          : l10n.permissionsMissingBody,
      action: _refuseDefinitivement ? l10n.permissionsOpenSettings : l10n.permissionsGrant,
      onAction: _refuseDefinitivement ? openAppSettings : _demander,
      alerte: true,
    );
  }
}

/// Le rôle de filtrage : c'est LUI qui donne accès au numéro entrant.
///
/// Présenté avant la surimpression parce qu'il vient en premier dans la
/// chaîne — autoriser à dessiner par-dessus l'écran ne sert à rien tant qu'on
/// ne sait pas QUI appelle.
class _BlocRoleFiltrage extends ConsumerWidget {
  const _BlocRoleFiltrage();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final accorde = ref.watch(roleFiltrageProvider);

    return accorde.maybeWhen(
      data: (oui) => oui
          ? _Encart(
              icone: Icons.ring_volume_outlined,
              titre: l10n.screeningGranted,
              corps: '',
            )
          : _Encart(
              icone: Icons.ring_volume_outlined,
              titre: l10n.screeningTitle,
              corps: l10n.screeningBody,
              action: l10n.screeningAction,
              onAction: () async {
                await ref.read(captureChannelProvider).demanderRoleFiltrage();
              },
            ),
      orElse: () => const SizedBox.shrink(),
    );
  }
}

class _BlocSurimpression extends ConsumerWidget {
  const _BlocSurimpression();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final autorisee = ref.watch(surimpressionProvider);

    return autorisee.maybeWhen(
      data: (accordee) => accordee
          ? _Encart(
              icone: Icons.picture_in_picture_alt_outlined,
              titre: l10n.overlayGranted,
              corps: '',
            )
          : _Encart(
              icone: Icons.picture_in_picture_alt_outlined,
              titre: l10n.overlayTitle,
              corps: l10n.overlayBody,
              action: l10n.overlayAction,
              onAction: () async {
                await ref.read(captureChannelProvider).demanderSurimpression();
                // La permission s'accorde dans un écran du système : à ce
                // stade elle n'est pas encore prise. On invalide au retour,
                // pas ici.
              },
            ),
      orElse: () => const SizedBox.shrink(),
    );
  }
}

class _BlocBatterie extends ConsumerWidget {
  const _BlocBatterie();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = AppLocalizations.of(context)!;
    final optimisee = ref.watch(batterieOptimiseeProvider);

    return optimisee.maybeWhen(
      data: (estOptimisee) => estOptimisee
          ? _Encart(
              icone: Icons.battery_alert_outlined,
              titre: l10n.batteryWarningTitle,
              corps: l10n.batteryWarningBody,
              action: l10n.batteryWarningAction,
              onAction: () async {
                await ref
                    .read(captureChannelProvider)
                    .demanderExclusionBatterie();
                ref.invalidate(batterieOptimiseeProvider);
              },
              alerte: true,
            )
          : const SizedBox.shrink(),
      orElse: () => const SizedBox.shrink(),
    );
  }
}

/// Accès permanent à l'avis d'information.
///
/// Un avis qu'on ne peut plus relire après le premier lancement n'informe
/// personne — il fait signer. Celui qui veut vérifier six mois plus tard ce
/// qui remonte de son téléphone doit pouvoir le retrouver sans demander à
/// quiconque.
class _BlocAvis extends StatelessWidget {
  const _BlocAvis();

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return _Encart(
      icone: Icons.privacy_tip_outlined,
      titre: l10n.noticeReadAgain,
      corps: l10n.noticeReadAgainBody,
      action: l10n.noticeReadAgainAction,
      onAction: () => Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => const NoticeScreen()),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.titre});

  final String titre;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Text(
        titre,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: Theme.of(context).colorScheme.primary,
            ),
      ),
    );
  }
}

class _Aide extends StatelessWidget {
  const _Aide(this.texte);

  final String texte;

  @override
  Widget build(BuildContext context) {
    return Text(
      texte,
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
    );
  }
}

class _Encart extends StatelessWidget {
  const _Encart({
    required this.icone,
    required this.titre,
    required this.corps,
    this.action,
    this.onAction,
    this.alerte = false,
  });

  final IconData icone;
  final String titre;
  final String corps;
  final String? action;
  final VoidCallback? onAction;
  final bool alerte;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final teinte = alerte ? scheme.error : scheme.primary;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icone, color: teinte),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(titre,
                      style: Theme.of(context).textTheme.titleSmall),
                  if (corps.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      corps,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                    ),
                  ],
                  if (action != null) ...[
                    const SizedBox(height: 8),
                    OutlinedButton(onPressed: onAction, child: Text(action!)),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
