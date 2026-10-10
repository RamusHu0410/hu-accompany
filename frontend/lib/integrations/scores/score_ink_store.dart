import 'package:shared_preferences/shared_preferences.dart';

/// The pen ink drawn on each score, kept on this device so it's still there
/// next time the score is opened. Stored as the score page's own JSON
/// (strokes pinned to bars; see assets/osmd/osmd_viewer.html).
class ScoreInkStore {
  const ScoreInkStore();

  static const String _prefix = 'score_ink_v1_';

  /// The score's strokes, or '[]' when none were drawn.
  Future<String> load(String scoreId) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('$_prefix$scoreId') ?? '[]';
  }

  Future<void> save(String scoreId, String strokesJson) async {
    final prefs = await SharedPreferences.getInstance();
    if (strokesJson == '[]') {
      await prefs.remove('$_prefix$scoreId');
    } else {
      await prefs.setString('$_prefix$scoreId', strokesJson);
    }
  }
}
