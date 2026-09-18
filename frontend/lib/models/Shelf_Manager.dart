import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// One sheet the user has played, with just enough to render it on the
/// shelf. The record (not a bare id) is what gets stored — nothing in the
/// current backend exposes a "look up a sheet by id" call, so an id-only
/// list would leave the shelf with nothing to display it with.
class ShelfEntry {
  final String id;
  final String title;
  final String composer;
  final DateTime playedAt;

  const ShelfEntry({
    required this.id,
    required this.title,
    required this.composer,
    required this.playedAt,
  });

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'composer': composer,
    'playedAt': playedAt.toIso8601String(),
  };

  factory ShelfEntry.fromJson(Map<String, dynamic> json) => ShelfEntry(
    id: json['id'] as String? ?? '',
    title: json['title'] as String? ?? 'Untitled',
    composer: json['composer'] as String? ?? '',
    playedAt:
        DateTime.tryParse(json['playedAt'] as String? ?? '') ?? DateTime.now(),
  );
}

/// Persists which sheets have been played, on-device, via
/// SharedPreferences. Pure data layer — no widgets, no BuildContext.
class ShelfManager {
  ShelfManager._();

  static const String _prefsKey = 'shelf_played_sheets';
  static const int _maxEntries = 60;

  /// Records a play, moving the sheet to the front if it was already on
  /// the shelf. Call this the moment a sheet is opened for reading.
  static Future<void> recordPlay({
    required String id,
    required String title,
    required String composer,
  }) async {
    if (id.isEmpty) return;

    final prefs = await SharedPreferences.getInstance();
    final entries = await _readAll(prefs);

    entries.removeWhere((e) => e.id == id);
    entries.insert(
      0,
      ShelfEntry(
        id: id,
        title: title,
        composer: composer,
        playedAt: DateTime.now(),
      ),
    );
    if (entries.length > _maxEntries) {
      entries.removeRange(_maxEntries, entries.length);
    }

    await prefs.setString(
      _prefsKey,
      jsonEncode(entries.map((e) => e.toJson()).toList()),
    );
  }

  /// All played sheets, most recently played first.
  static Future<List<ShelfEntry>> loadAll() async {
    final prefs = await SharedPreferences.getInstance();
    return _readAll(prefs);
  }

  static Future<List<ShelfEntry>> _readAll(SharedPreferences prefs) async {
    final raw = prefs.getString(_prefsKey);
    if (raw == null || raw.isEmpty) return [];
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return decoded
          .map((e) => ShelfEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      // Malformed local state (e.g. a schema change) shouldn't crash the
      // shelf — just treat it as empty.
      return [];
    }
  }
}
