import 'Quiz_Question.dart';

/// A generated quiz: the topic it was built for, plus its questions.
///
/// Mirrors the backend's `quiz/models.py` QuizSet. [levelLabel] and
/// [eraSpan] are echoed back by the server rather than re-derived here, so
/// the results screen can title itself the way the student typed the topic.
class QuizSet {
  final String eraKey;
  final String eraName;
  final String eraSpan;
  final String levelLabel;
  final List<QuizQuestion> questions;

  const QuizSet({
    required this.eraKey,
    required this.eraName,
    required this.eraSpan,
    required this.levelLabel,
    required this.questions,
  });

  int get length => questions.length;
  bool get isEmpty => questions.isEmpty;

  /// "The Middle Ages · ad 476 - ad 1450", or just the era when the span is
  /// missing.
  String get subtitle =>
      eraSpan.isEmpty ? eraName : '$eraName · $eraSpan';

  factory QuizSet.fromJson(Map<String, dynamic> json) {
    final topic = json['topic'] as Map<String, dynamic>? ?? const {};
    return QuizSet(
      eraKey: topic['era_key'] as String? ?? '',
      eraName: topic['era_name'] as String? ?? '',
      eraSpan: topic['era_span'] as String? ?? '',
      levelLabel: topic['level'] as String? ?? '',
      questions: (json['questions'] as List<dynamic>? ?? const [])
          .map((q) => QuizQuestion.fromJson(q as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// The outcome of one completed run. Built by the session page and consumed
/// by the results page.
class QuizResult {
  final QuizSet set;
  final List<QuizAnswer> answers;

  const QuizResult({required this.set, required this.answers});

  int get total => answers.length;
  int get correct => answers.where((a) => a.isCorrect).length;
  int get wrong => answers.where((a) => !a.isCorrect && !a.wasSkipped).length;
  int get skipped => answers.where((a) => a.wasSkipped).length;

  List<QuizAnswer> get missed =>
      answers.where((a) => !a.isCorrect).toList(growable: false);

  /// 0-100, rounded. Zero questions scores 0 rather than dividing by zero.
  int get percent => total == 0 ? 0 : ((correct / total) * 100).round();

  /// Per-category tallies, used for the results breakdown.
  Map<String, ({int correct, int total})> get byCategory {
    final tally = <String, ({int correct, int total})>{};
    for (final answer in answers) {
      final key = answer.question.category;
      final current = tally[key] ?? (correct: 0, total: 0);
      tally[key] = (
        correct: current.correct + (answer.isCorrect ? 1 : 0),
        total: current.total + 1,
      );
    }
    return tally;
  }
}
