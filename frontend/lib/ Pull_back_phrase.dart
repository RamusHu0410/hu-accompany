import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'ServerDiscovery.dart';

/// Models + fetch logic for the scored feedback report the Python
/// backend returns for one phrase, after it's had time to analyze the
/// notes sent by PhraseUploadService (Phrase_Send2_Server.dart).
///
/// Intentionally a separate request from the send — the backend needs
/// time to run analysis after a phrase lands, so push and pull are two
/// independent round trips rather than one blocking call.

/// The piece currently being practiced.
class PieceInfo {
  final String title;
  final String composer;
  final String composedDate;

  const PieceInfo({
    required this.title,
    required this.composer,
    required this.composedDate,
  });

  factory PieceInfo.fromJson(Map<String, dynamic> json) => PieceInfo(
    title: json['title'] as String? ?? '',
    composer: json['composer'] as String? ?? '',
    composedDate: json['composed_date'] as String? ?? '',
  );
}

/// 0-100 category scores for a phrase. Any category can come back null —
/// the backend only fills in what it actually scored (e.g. dynamics and
/// pedaling aren't implemented yet as of the sample payload this was
/// built from).
class PhraseScores {
  final int overall;
  final int? pitch;
  final int? rhythm;
  final int? tempo;
  final int? dynamics;
  final int? articulation;
  final int? notes;
  final int? pedaling;

  const PhraseScores({
    required this.overall,
    this.pitch,
    this.rhythm,
    this.tempo,
    this.dynamics,
    this.articulation,
    this.notes,
    this.pedaling,
  });

  factory PhraseScores.fromJson(Map<String, dynamic> json) => PhraseScores(
    overall: json['overall'] as int? ?? 0,
    pitch: json['pitch'] as int?,
    rhythm: json['rhythm'] as int?,
    tempo: json['tempo'] as int?,
    dynamics: json['dynamics'] as int?,
    articulation: json['articulation'] as int?,
    notes: json['notes'] as int?,
    pedaling: json['pedaling'] as int?,
  );
}

/// One issue found in the phrase (e.g. a wrong note, a late onset).
///
/// [details] is left as a raw map rather than a strongly-typed class
/// because its shape varies by [category] — pitch feedback carries
/// expected_hz/user_hz/cents, rhythm feedback carries diff_ms/direction,
/// and future categories will likely bring their own fields. Read what
/// you need by key rather than assuming a fixed shape.
class PhraseFeedbackItem {
  final int bars;
  final String category;
  final String severity;
  final double confidence;
  final String message;
  final Map<String, dynamic> details;

  const PhraseFeedbackItem({
    required this.bars,
    required this.category,
    required this.severity,
    required this.confidence,
    required this.message,
    required this.details,
  });

  factory PhraseFeedbackItem.fromJson(Map<String, dynamic> json) =>
      PhraseFeedbackItem(
        bars: json['bars'] as int? ?? 0,
        category: json['category'] as String? ?? '',
        severity: json['severity'] as String? ?? '',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
        message: json['message'] as String? ?? '',
        details: (json['details'] as Map<String, dynamic>?) ?? const {},
      );
}

/// The full scored report for one phrase, as returned by the backend.
class PhraseReport {
  final PieceInfo piece;
  final DateTime recordedAt;
  final int phrase;
  final int bpm;
  final String timeSignature;
  final List<int> bars;
  final PhraseScores scores;
  final List<PhraseFeedbackItem> feedback;

  const PhraseReport({
    required this.piece,
    required this.recordedAt,
    required this.phrase,
    required this.bpm,
    required this.timeSignature,
    required this.bars,
    required this.scores,
    required this.feedback,
  });

  factory PhraseReport.fromJson(Map<String, dynamic> json) {
    final rawRecordedAt = json['recorded_at'] as String?;
    return PhraseReport(
      piece: PieceInfo.fromJson(
        json['piece'] as Map<String, dynamic>? ?? const {},
      ),
      recordedAt: rawRecordedAt != null
          ? (DateTime.tryParse(rawRecordedAt) ?? DateTime.now())
          : DateTime.now(),
      phrase: json['phrase'] as int? ?? 0,
      bpm: json['bpm'] as int? ?? 0,
      timeSignature: json['time_signature'] as String? ?? '',
      bars: (json['bars'] as List<dynamic>? ?? const [])
          .map((e) => e as int)
          .toList(),
      scores: PhraseScores.fromJson(
        json['scores'] as Map<String, dynamic>? ?? const {},
      ),
      feedback: (json['feedback'] as List<dynamic>? ?? const [])
          .map((e) => PhraseFeedbackItem.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// Fetches the scored feedback report for one phrase.
///
/// Same discovery + retry-once pattern as the app's other backend
/// clients — see ServerDiscovery.dart.
class PhraseFeedbackService {
  PhraseFeedbackService._();

  // PLACEHOLDER — this endpoint does not exist on the backend yet.
  // TODO: confirm the real path (and whether it's a GET with query
  // params like this, or something else — e.g. a path like
  // '/api/practice/phrase/<session_id>/<phrase>') with Ramus.
  static const String _fetchPhrasePath = '/api/practice/phrase';

  static const Duration _fetchTimeout = Duration(seconds: 30);

  static Future<PhraseReport?> fetchPhraseFeedback({
    required String sessionId,
    required int phraseNumber,
  }) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      debugPrint('[PhraseFeedback] No backend found on network.');
      return null;
    }

    var response = await _get(baseUrl, sessionId, phraseNumber);

    if (response == null) {
      ServerDiscovery.invalidateCache();
      final freshBaseUrl = await ServerDiscovery.resolveBaseUrl(
        forceRefresh: true,
      );
      if (freshBaseUrl == null) {
        debugPrint('[PhraseFeedback] Backend unreachable after retry.');
        return null;
      }
      response = await _get(freshBaseUrl, sessionId, phraseNumber);
    }

    if (response == null) {
      debugPrint(
        '[PhraseFeedback] Fetch failed for phrase $phraseNumber (network error).',
      );
      return null;
    }

    if (response.statusCode != 200) {
      debugPrint(
        '[PhraseFeedback] Phrase $phraseNumber rejected: '
        '${response.statusCode} — ${response.body}',
      );
      return null;
    }

    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      return PhraseReport.fromJson(decoded);
    } catch (error) {
      debugPrint('[PhraseFeedback] Could not parse response: $error');
      return null;
    }
  }

  static Future<http.Response?> _get(
    String baseUrl,
    String sessionId,
    int phraseNumber,
  ) async {
    final uri = Uri.parse('$baseUrl$_fetchPhrasePath').replace(
      queryParameters: {'session_id': sessionId, 'phrase': '$phraseNumber'},
    );
    try {
      return await http.get(uri).timeout(_fetchTimeout);
    } on Exception catch (error) {
      debugPrint('[PhraseFeedback] Fetch failed: $error');
      return null;
    }
  }
}