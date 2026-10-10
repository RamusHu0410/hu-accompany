import 'package:hu_accomponist/integrations/hum/hum_models.dart';

/// What each song maker does, in the listener's words, and what the app
/// says when it changes maker on its own. Shown under the engine picker, in
/// its "Compare" sheet, and in the chat.
extension EngineGuide on HumEngine {
  /// One line under the picker.
  String get summary => switch (this) {
    HumEngine.band =>
      'A band plays your tune in a genre, with an intro, verse, chorus and outro.',
    HumEngine.epic =>
      'A full orchestra arranged around your tune. Biggest sound, best from a clean hum.',
    HumEngine.simple =>
      'Chords in a style under your tune. The steadiest choice for a rough hum.',
  };

  String get howItWorks => switch (this) {
    HumEngine.band =>
      'Each instrument is its own part (melody, chords, bass, pad, drums), built from your hum\'s key and tempo.',
    HumEngine.epic =>
      'An ensemble is arranged around your tune and made in one piece.',
    HumEngine.simple =>
      'Chords are picked to fit your tune and played in a style, made in one piece.',
  };

  String get youCanChange => switch (this) {
    HumEngine.band =>
      'Genre, mood, and anything by chat: one instrument, its volume, the tempo, the key, a section. Every change can be undone.',
    HumEngine.epic || HumEngine.simple =>
      'Mood, speed and pitch with the sliders. Chat edits need Band.',
  };

  bool get editableByChat => this == HumEngine.band;
}

abstract final class EngineNotices {
  static const String switchedForChat =
      'Switched to Band so I can make that change. Band keeps each instrument on '
      'its own part, which is what chat edits need; Epic and Simple make the song '
      'in one piece. Tap Epic or Simple above to go back.';

  static const String switchedForGenre =
      'Switched to Band: genres and moods are Band\'s. Epic and Simple are shaped '
      'with the sliders instead.';

  /// Leaving Band after editing the song there.
  static String leftEditedBand(HumEngine to) =>
      '${to.label} makes its own version of your hum, so your Band edits '
      'aren\'t in it. They\'re kept: switch back to Band to hear them.';
}
