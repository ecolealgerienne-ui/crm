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
    this.note,
    this.awaitingNote = false,
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

  /// Note prise après l'appel, si le commercial en a saisi une.
  final String? note;

  /// L'appel est retenu, le temps que la note soit saisie. Il ne partira pas
  /// tant que ce drapeau est levé — ou que l'échéance native n'est pas passée.
  final bool awaitingNote;

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
      note: map['note'] as String?,
      awaitingNote: map['awaitingNote'] as bool? ?? false,
    );
  }
}

/// Urgence d'un appel programmé, telle qu'Odoo la calcule.
///
/// Reprise du serveur et jamais recalculée ici : Odoo décide dans le fuseau de
/// l'utilisateur, et un second calcul côté téléphone donnerait deux vérités
/// pour la même échéance — qui divergeraient au passage de minuit.
enum EtatActivite { overdue, today, planned }

@immutable
class ActiviteAppel {
  const ActiviteAppel({
    required this.id,
    required this.client,
    required this.phone,
    required this.deadline,
    required this.etat,
    required this.summary,
    required this.note,
  });

  final int id;
  final String client;
  final String phone;
  final String deadline;
  final EtatActivite etat;
  final String summary;
  final String note;

  factory ActiviteAppel.fromMap(Map<dynamic, dynamic> map) {
    return ActiviteAppel(
      id: (map['id'] as num?)?.toInt() ?? 0,
      client: (map['client'] ?? '').toString(),
      phone: (map['phone'] ?? '').toString(),
      deadline: (map['deadline'] ?? '').toString(),
      // Un état inconnu retombe sur `planned` : une échéance mal comprise ne
      // doit pas faire clignoter une tâche en rouge sans raison.
      etat: EtatActivite.values.firstWhere(
        (e) => e.name == map['state'],
        orElse: () => EtatActivite.planned,
      ),
      summary: (map['summary'] ?? '').toString(),
      note: (map['note'] ?? '').toString(),
    );
  }
}

/// La liste, et la date à laquelle elle a été récupérée.
///
/// Les deux voyagent ensemble et s'affichent ensemble : une liste sans sa date
/// de fraîcheur laisse croire qu'elle est à jour, et c'est précisément faux au
/// moment où ça compte — hors réseau.
@immutable
class ListeActivites {
  const ListeActivites({required this.activites, required this.recupereeLe});

  final List<ActiviteAppel> activites;

  /// `null` si aucune récupération n'a jamais abouti.
  final DateTime? recupereeLe;

  static const vide = ListeActivites(activites: [], recupereeLe: null);

  factory ListeActivites.fromMap(Map<dynamic, dynamic> map) {
    final millis = (map['fetchedAtMillis'] as num?)?.toInt() ?? 0;
    final brut = (map['results'] as List?) ?? const [];
    return ListeActivites(
      activites: brut
          .map((e) => ActiviteAppel.fromMap(e as Map<dynamic, dynamic>))
          .toList(growable: false),
      recupereeLe:
          millis > 0 ? DateTime.fromMillisecondsSinceEpoch(millis) : null,
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
    this.retentionDays = 0,
    this.retentionKnown = false,
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

  /// Durée de conservation des appels côté Odoo, annoncée par le serveur à
  /// chaque envoi accepté.
  ///
  /// Elle n'est pas codée en dur dans l'application : elle est fixée par le
  /// `.env` du serveur, et une valeur recopiée ici finirait par mentir à
  /// l'écran d'information le jour où l'exploitant la change. `0` avec
  /// [retentionKnown] à vrai signifie « aucune purge configurée » — ce qui se
  /// dit, et se dit différemment de « pas encore connue ».
  final int retentionDays;

  /// Le serveur a-t-il déjà annoncé sa politique ? Faux tant qu'aucun appel
  /// n'a été accepté.
  final bool retentionKnown;

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
      retentionDays: map['retentionDays'] as int? ?? 0,
      retentionKnown: map['retentionKnown'] as bool? ?? false,
    );
  }

  CaptureSettings copyWith({
    String? serverUrl,
    bool? hasToken,
    bool? captureEnabled,
    int? fromHour,
    int? toHour,
    int? retentionDays,
    bool? retentionKnown,
  }) {
    return CaptureSettings(
      serverUrl: serverUrl ?? this.serverUrl,
      hasToken: hasToken ?? this.hasToken,
      captureEnabled: captureEnabled ?? this.captureEnabled,
      fromHour: fromHour ?? this.fromHour,
      toHour: toHour ?? this.toHour,
      retentionDays: retentionDays ?? this.retentionDays,
      retentionKnown: retentionKnown ?? this.retentionKnown,
    );
  }
}
