import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'ServerDiscovery.dart';

/// Models + fetch logic for backend/feedback_generator's two endpoints:
///   - POST /api/feedback/phrase  -> PhraseReport (see Phrase_Send2_Server.dart,
///     which sends the request; this file just owns the response shape)
///   - POST /api/feedback/summary -> the phase-2, whole-session summary
///     (the real "pull back" in this pair, since it's a separate request
///     from sending any individual phrase)

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

  Map<String, dynamic> toJson() => {
    'title': title,
    'composer': composer,
    'composed_date': composedDate,
  };
}

/// 0-100 category scores for a phrase. Any category can come back null —
/// per the README, a null score means that judge had nothing to measure
/// and it drops out of `overall` rather than counting as zero.
/// `dynamics` and `pedaling` are always null (no loudness/pedal data
/// upstream).
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

/// Pixel rectangle for one bar on the rendered score page, so the app can
/// mark the spot instead of making the player count bars. Null whenever
/// `bar_boxes` wasn't supplied on the request (see Phrase_Send2_Server.dart).
/// [pageSize] is the [width, height] of the PNG page these pixels were
/// measured on — a client rendering the PDF at another resolution needs
/// to scale by its own width/height against this.
class FeedbackBox {
  final int page;
  final double x;
  final double y;
  final double w;
  final double h;
  final List<int> pageSize;

  const FeedbackBox({
    required this.page,
    required this.x,
    required this.y,
    required this.w,
    required this.h,
    required this.pageSize,
  });

  static FeedbackBox? fromJsonNullable(Map<String, dynamic>? json) {
    if (json == null) return null;
    return FeedbackBox(
      page: json['page'] as int? ?? 0,
      x: (json['x'] as num?)?.toDouble() ?? 0,
      y: (json['y'] as num?)?.toDouble() ?? 0,
      w: (json['w'] as num?)?.toDouble() ?? 0,
      h: (json['h'] as num?)?.toDouble() ?? 0,
      pageSize: (json['page_size'] as List<dynamic>? ?? const [])
          .map((e) => e as int)
          .toList(),
    );
  }
}

/// One issue found in the phrase (e.g. a wrong note, a late onset).
///
/// [details] is left as a raw map rather than a strongly-typed class
/// because its shape varies by [category] (pitch feedback carries
/// expected/user Hz and cents, rhythm carries ms offsets, etc.) — read
/// what you need by key rather than assuming a fixed shape. Every finding
/// also carries a `suggestion` inside [details] per the README.
class PhraseFeedbackItem {
  final int bars;
  final FeedbackBox? box;
  final String category;
  final String severity; // "minor" | "major"
  final double confidence; // 0.5 (borderline) .. 1.0 (unmistakable)
  final String message;
  final Map<String, dynamic> details;

  const PhraseFeedbackItem({
    required this.bars,
    required this.box,
    required this.category,
    required this.severity,
    required this.confidence,
    required this.message,
    required this.details,
  });

  factory PhraseFeedbackItem.fromJson(Map<String, dynamic> json) =>
      PhraseFeedbackItem(
        bars: json['bars'] as int? ?? 0,
        box: FeedbackBox.fromJsonNullable(
          json['box'] as Map<String, dynamic>?,
        ),
        category: json['category'] as String? ?? '',
        severity: json['severity'] as String? ?? '',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
        message: json['message'] as String? ?? '',
        details: (json['details'] as Map<String, dynamic>?) ?? const {},
      );
}

/// The full phase-1 report for one phrase, as returned directly by the
/// POST /api/feedback/phrase response.
class PhraseReport {
  final PieceInfo piece;
  final DateTime recordedAt;
  final int phrase;
  final double bpm;
  final String timeSignature;
  final List<int> bars;
  final PhraseScores scores;
  final List<PhraseFeedbackItem> feedback;

  /// Server-assigned session id, formatted "<date>-<piece title>" (e.g.
  /// "2026-09-07-Prelude_in_C") unless an explicit session_id was sent.
  /// Capture this from phrase 1's response and pass it back in on every
  /// later phrase in the same recording (see Phrase_Send2_Server.dart) —
  /// don't invent a client-side session id, the server owns this.
  final String sessionId;
  final String storedAt;

  const PhraseReport({
    required this.piece,
    required this.recordedAt,
    required this.phrase,
    required this.bpm,
    required this.timeSignature,
    required this.bars,
    required this.scores,
    required this.feedback,
    required this.sessionId,
    required this.storedAt,
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
      bpm: (json['bpm'] as num?)?.toDouble() ?? 0,
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
      sessionId: json['session_id'] as String? ?? '',
      storedAt: json['stored_at'] as String? ?? '',
    );
  }
}

/// Fetches the phase-2, whole-session summary once every phrase for a
/// session has been sent.
///
/// TODO: Summary.json's exact shape isn't pinned down in the README
/// (described only as "piece-wide scores, top 3 recurring problems, what
/// went well, one-line summary" — and judges/phase2/era.py is explicitly
/// unfinished, so Era.json's `feedback` always comes back empty for now).
/// fetchSummary() below returns the raw decoded JSON rather than guessing
/// a typed model that might not match. Once you've got a real
/// Phase2/Summary.json sample, this is the place to add a typed
/// SessionSummary class the same way PhraseReport is typed above.
class SessionSummaryService {
  SessionSummaryService._();

  static const String _summaryPath = '/api/feedback/summary';
  static const Duration _fetchTimeout = Duration(seconds: 30);

  static Future<Map<String, dynamic>?> fetchSummary(String sessionId) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      debugPrint('[SessionSummary] No backend found on network.');
      return null;
    }

    var response = await _post(baseUrl, sessionId);

    if (response == null) {
      ServerDiscovery.invalidateCache();
      final freshBaseUrl = await ServerDiscovery.resolveBaseUrl(
        forceRefresh: true,
      );
      if (freshBaseUrl == null) {
        debugPrint('[SessionSummary] Backend unreachable after retry.');
        return null;
      }
      response = await _post(freshBaseUrl, sessionId);
    }

    if (response == null) {
      debugPrint('[SessionSummary] Fetch failed (network error).');
      return null;
    }

    // 404 = no phase-1 phrases stored yet for this session — not really
    // an error, just nothing to summarize.
    if (response.statusCode == 404) {
      debugPrint('[SessionSummary] No phrases stored yet for $sessionId.');
      return null;
    }

    if (response.statusCode != 200) {
      debugPrint(
        '[SessionSummary] Rejected: ${response.statusCode} — ${response.body}',
      );
      return null;
    }

    try {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } catch (error) {
      debugPrint('[SessionSummary] Could not parse response: $error');
      return null;
    }
  }

  static Future<http.Response?> _post(String baseUrl, String sessionId) async {
    final uri = Uri.parse('$baseUrl$_summaryPath');
    try {
      return await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'session_id': sessionId}),
          )
          .timeout(_fetchTimeout);
    } on Exception catch (error) {
      debugPrint('[SessionSummary] Request failed: $error');
      return null;
    }
  }
}