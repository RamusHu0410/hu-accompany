/// One question in a generated quiz set.
///
/// Mirrors the backend's `quiz/models.py` Question dataclass field for
/// field. Grading lives here rather than on a screen because both the
/// session page (to mark an answer as it is given) and the results page (to
/// list what went wrong) need the same verdict, and they must not be able
/// to disagree about it.
library;

enum QuizKind { multipleChoice, fillBlank }

class QuizQuestion {
  final String id;
  final QuizKind kind;

  /// One of composers / forms / terminology / context — shown as a small
  /// label so the student can see what a wrong answer was testing.
  final String category;

  final String prompt;

  /// Empty for a fill-in-the-blank.
  final List<String> choices;

  /// The canonical answer, shown on the results screen.
  final String answer;

  /// Every spelling the backend will accept, already lowercased. Includes
  /// [answer]. Used only for [QuizKind.fillBlank].
  final List<String> accepted;

  final String explanation;

  /// "core" or "arct" — ARCT questions only appear when the topic asked
  /// for them.
  final String level;

  const QuizQuestion({
    required this.id,
    required this.kind,
    required this.category,
    required this.prompt,
    required this.choices,
    required this.answer,
    required this.accepted,
    required this.explanation,
    required this.level,
  });

  bool get isAdvanced => level == 'arct';

  /// True when [response] should be marked correct.
  ///
  /// Multiple choice compares exactly, since the text came from [choices].
  /// Fill-in-the-blank is matched case- and whitespace-insensitively
  /// against [accepted], which is why the backend sends the alternates
  /// rather than the app trying to guess at them.
  bool isCorrect(String? response) {
    if (response == null) return false;
    final normalized = response.trim().toLowerCase();
    if (normalized.isEmpty) return false;
    if (kind == QuizKind.multipleChoice) {
      return normalized == answer.trim().toLowerCase();
    }
    return accepted.contains(normalized);
  }

  factory QuizQuestion.fromJson(Map<String, dynamic> json) {
    return QuizQuestion(
      id: json['id'] as String? ?? '',
      kind: (json['kind'] as String? ?? '') == 'fill_blank'
          ? QuizKind.fillBlank
          : QuizKind.multipleChoice,
      category: json['category'] as String? ?? '',
      prompt: json['prompt'] as String? ?? '',
      choices: (json['choices'] as List<dynamic>? ?? const [])
          .map((c) => c.toString())
          .toList(),
      answer: json['answer'] as String? ?? '',
      accepted: (json['accepted'] as List<dynamic>? ?? const [])
          .map((a) => a.toString().toLowerCase())
          .toList(),
      explanation: json['explanation'] as String? ?? '',
      level: json['level'] as String? ?? 'core',
    );
  }
}

/// A question paired with what the student actually answered. Built as the
/// session runs and handed to the results page, so the review list does not
/// have to reconstruct anything.
class QuizAnswer {
  final QuizQuestion question;

  /// Null when the question was skipped.
  final String? response;

  const QuizAnswer({required this.question, required this.response});

  bool get isCorrect => question.isCorrect(response);
  bool get wasSkipped => response == null || response!.trim().isEmpty;
}
