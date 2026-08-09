import 'package:flutter/foundation.dart';

/// Sens d'un appel, tel que le remonte `CallLog.Calls.TYPE`.
enum CallDirection { inbound, outbound, missed }

/// État de remise d'un appel vers Odoo.
enum SyncStatus { pending, sent, failed }

@immutable
class CallEntry {
  const CallEntry({
    required this.id,
    required this.clientEventId,
    required this.phoneNumber,
    required this.direction,
    required this.durationSeconds,
    required this.startedAt,
    required this.syncStatus,
    this.lastError,
    this.attempts = 0,
  });

  final int id;

  /// Identifiant généré à la capture, jamais réattribué : c'est lui qui rend
  /// les réessais inoffensifs côté Odoo.
  final String clientEventId;

  final String phoneNumber;
  final CallDirection direction;
  final int durationSeconds;
  final DateTime startedAt;
  final SyncStatus syncStatus;
  final String? lastError;
  final int attempts;

  factory CallEntry.fromMap(Map<dynamic, dynamic> map) {
    return CallEntry(
      id: map['id'] as int,
      clientEventId: map['clientEventId'] as String,
      phoneNumber: map['phoneNumber'] as String,
      direction: CallDirection.values.byName(map['direction'] as String),
      durationSeconds: map['durationSeconds'] as int? ?? 0,
      // Le natif transmet des millisecondes depuis l'époque, en UTC. La
      // conversion en heure locale est faite à l'affichage, jamais ici : le
      // stockage et le transport restent en UTC de bout en bout.
      startedAt: DateTime.fromMillisecondsSinceEpoch(
        map['startedAtMillis'] as int,
        isUtc: true,
      ),
      syncStatus: SyncStatus.values.byName(map['syncStatus'] as String),
      lastError: map['lastError'] as String?,
      attempts: map['attempts'] as int? ?? 0,
    );
  }
}

@immutable
class CaptureSettings {
  const CaptureSettings({
    required this.serverUrl,
    required this.hasToken,
    required this.captureEnabled,
    required this.fromHour,
    required this.toHour,
  });

  final String serverUrl;

  /// Le jeton lui-même ne remonte jamais jusqu'à Dart — seulement le fait
  /// qu'il existe. Il vit dans un `EncryptedSharedPreferences` côté Android,
  /// lu par le worker d'envoi ; le faire transiter par la couche Flutter
  /// l'exposerait aux journaux et aux captures d'écran sans aucun gain.
  final bool hasToken;

  final bool captureEnabled;

  /// Plage horaire de capture, en heures locales pleines (0-24).
  final int fromHour;
  final int toHour;

  static const vide = CaptureSettings(
    serverUrl: '',
    hasToken: false,
    captureEnabled: false,
    fromHour: 8,
    toHour: 19,
  );

  factory CaptureSettings.fromMap(Map<dynamic, dynamic> map) {
    return CaptureSettings(
      serverUrl: map['serverUrl'] as String? ?? '',
      hasToken: map['hasToken'] as bool? ?? false,
      captureEnabled: map['captureEnabled'] as bool? ?? false,
      fromHour: map['fromHour'] as int? ?? 8,
      toHour: map['toHour'] as int? ?? 19,
    );
  }

  CaptureSettings copyWith({
    String? serverUrl,
    bool? hasToken,
    bool? captureEnabled,
    int? fromHour,
    int? toHour,
  }) {
    return CaptureSettings(
      serverUrl: serverUrl ?? this.serverUrl,
      hasToken: hasToken ?? this.hasToken,
      captureEnabled: captureEnabled ?? this.captureEnabled,
      fromHour: fromHour ?? this.fromHour,
      toHour: toHour ?? this.toHour,
    );
  }
}
