/// The band engine's genres: each is a small band that belongs together.
/// Mirrors backend/hum/song/presets.py.
enum SongGenre {
  pop('pop', 'Pop'),
  lofi('lofi', 'Lo-fi'),
  rock('rock', 'Rock'),
  ballad('ballad', 'Ballad'),
  cinematic('cinematic', 'Cinematic'),
  electronic('electronic', 'Electronic'),
  jazz('jazz', 'Jazz'),
  acoustic('acoustic', 'Acoustic');

  const SongGenre(this.apiName, this.label);

  final String apiName;
  final String label;

  /// The genre a settings style names, or null for any other word.
  static SongGenre? fromStyle(String? style) {
    for (final genre in values) {
      if (genre.apiName == style) return genre;
    }
    return null;
  }
}

/// How the band plays it. No mood means "as hummed".
enum SongMood {
  dark('dark', 'Dark'),
  chill('chill', 'Chill'),
  bright('bright', 'Bright'),
  hype('hype', 'Hype');

  const SongMood(this.apiName, this.label);

  final String apiName;
  final String label;

  static SongMood? fromName(String? name) {
    for (final mood in values) {
      if (mood.apiName == name) return mood;
    }
    return null;
  }
}
