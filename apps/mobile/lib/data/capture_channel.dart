import 'package:flutter/services.dart';

import 'capture_models.dart';

/// Passerelle vers la couche de capture Android.
///
/// **Tout le métier est de l'autre côté de ce canal**, et ce n'est pas un
/// détail d'implémentation : la capture d'appels, la file locale et l'envoi
/// vers Odoo doivent fonctionner alors que l'application est fermée et que le
/// moteur Flutter n'existe pas. Un appel entrant ne réveille pas Dart. Cette
/// classe ne fait donc que lire un état et régler des préférences — elle n'est
/// jamais sur le chemin d'un appel capturé.
class CaptureChannel {
  const CaptureChannel();

  static const _canal = MethodChannel('com.echango.call_tracker/capture');

  Future<CaptureSettings> lireReglages() async {
    final map = await _canal.invokeMapMethod<String, dynamic>('getSettings');
    return map == null ? CaptureSettings.vide : CaptureSettings.fromMap(map);
  }

  /// Enregistre les réglages. `token` à `null` laisse le jeton existant
  /// intact — c'est ce qui permet à l'écran de réglages de ne jamais avoir à
  /// relire un jeton qu'il n'a pas le droit de connaître.
  Future<void> ecrireReglages({
    required String serverUrl,
    String? token,
    required bool captureEnabled,
    required int fromHour,
    required int toHour,
  }) {
    return _canal.invokeMethod<void>('saveSettings', {
      'serverUrl': serverUrl,
      if (token != null) 'token': token,
      'captureEnabled': captureEnabled,
      'fromHour': fromHour,
      'toHour': toHour,
    });
  }

  Future<List<CallEntry>> listerAppels({int limite = 200}) async {
    final liste = await _canal.invokeListMethod<Map<dynamic, dynamic>>(
      'listCalls',
      {'limit': limite},
    );
    return (liste ?? const []).map(CallEntry.fromMap).toList(growable: false);
  }

  Future<int> compterEnAttente() async {
    return await _canal.invokeMethod<int>('pendingCount') ?? 0;
  }

  /// Demande une tentative d'envoi immédiate. Ne renvoie pas le résultat :
  /// l'envoi est confié à WorkManager, qui décide du moment réel et gère les
  /// reprises. L'interface se met à jour en relisant la liste.
  Future<void> synchroniserMaintenant() {
    return _canal.invokeMethod<void>('syncNow');
  }

  /// Attache la note et libère l'appel : il part à la prochaine occasion.
  Future<void> enregistrerNote(int id, String note) {
    return _canal.invokeMethod<void>('saveNote', {'id': id, 'note': note});
  }

  /// Renonce à la note : l'appel part tel quel, sans attendre l'échéance.
  Future<void> ignorerNote(int id) {
    return _canal.invokeMethod<void>('skipNote', {'id': id});
  }

  /// Appel dont la notification vient d'être touchée, ou `null`.
  ///
  /// La lecture est destructrice côté natif : sans cela, chaque retour sur
  /// l'application rouvrirait la même invite de note.
  Future<int?> noteEnAttente() {
    return _canal.invokeMethod<int>('consumePendingNoteCallId');
  }

  /// Le rôle de filtrage d'appels est-il accordé ?
  ///
  /// C'est LUI qui donne accès au numéro entrant, pas la surimpression. Les
  /// deux sont nécessaires pour que la fiche s'affiche à la sonnerie, et ils
  /// s'accordent séparément.
  Future<bool> roleFiltrageAccorde() async {
    return await _canal.invokeMethod<bool>('hasCallScreeningRole') ?? false;
  }

  Future<void> demanderRoleFiltrage() {
    return _canal.invokeMethod<void>('requestCallScreeningRole');
  }

  /// La surimpression de fiche CRM est-elle autorisée ?
  Future<bool> surimpressionAutorisee() async {
    return await _canal.invokeMethod<bool>('canDrawOverlay') ?? false;
  }

  /// Ouvre l'écran système d'autorisation de surimpression.
  ///
  /// Aucune boîte de dialogue n'est possible pour cette permission
  /// « spéciale » : elle ne s'accorde que là.
  Future<void> demanderSurimpression() {
    return _canal.invokeMethod<void>('requestOverlayPermission');
  }

  /// Fiche CRM d'un numéro, pour la recherche dans l'application.
  Future<Map<String, String>?> chercherContact(String numero) async {
    final fiche = await _canal.invokeMapMethod<String, dynamic>(
      'lookupContact', {'phoneNumber': numero},
    );
    if (fiche == null) return null;
    return fiche.map((cle, valeur) => MapEntry(cle, (valeur ?? '').toString()));
  }

  Future<bool> batterieOptimisee() async {
    return await _canal.invokeMethod<bool>('isBatteryOptimised') ?? true;
  }

  Future<void> demanderExclusionBatterie() {
    return _canal.invokeMethod<void>('requestIgnoreBatteryOptimisations');
  }
}
