import 'dart:io';
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Records a hum to a WAV file. An interface so tests don't need a microphone.
abstract class HumRecorder {
  /// Asks for the microphone if needed. False when the person said no.
  Future<bool> requestPermission();

  Future<void> start();

  /// Stops and returns the WAV file's path, or null if nothing was recorded.
  Future<String?> stop();

  Future<void> dispose();
}

/// Plays a finished song. An interface so tests don't need a speaker.
abstract class SongPlayer {
  /// True while a song is playing, false when it ends or is stopped.
  Stream<bool> get playing;

  /// How far into the song playback is, ticking while it plays.
  Stream<Duration> get position;

  Future<void> playWav(Uint8List bytes);

  Future<void> playUrl(Uri url);

  Future<void> stop();

  Future<void> dispose();
}

class MicRecorder implements HumRecorder {
  final AudioRecorder _recorder = AudioRecorder();

  @override
  Future<bool> requestPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    final folder = await getTemporaryDirectory();
    final path =
        '${folder.path}/hum-${DateTime.now().microsecondsSinceEpoch}.wav';
    // Mono 16-bit PCM is what the backend's note finder reads best, and
    // 22.05 kHz is plenty for a voice and keeps the upload small.
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 22050,
        numChannels: 1,
      ),
      path: path,
    );
  }

  @override
  Future<String?> stop() => _recorder.stop();

  @override
  Future<void> dispose() => _recorder.dispose();
}

class JustAudioSongPlayer implements SongPlayer {
  JustAudioSongPlayer({this.name = 'song'});

  /// Keeps two players' files apart.
  final String name;
  final AudioPlayer _player = AudioPlayer();
  int _songs = 0;

  @override
  Stream<Duration> get position => _player.createPositionStream(
    // Often enough that a note lights up as it starts, not a beat late.
    minPeriod: const Duration(milliseconds: 30),
    maxPeriod: const Duration(milliseconds: 60),
  );

  @override
  Stream<bool> get playing => _player.playerStateStream.map(
    (state) =>
        state.playing && state.processingState != ProcessingState.completed,
  );

  @override
  Future<void> playWav(Uint8List bytes) async {
    // Rotating through a few names, so a new song never reuses the file still playing.
    final folder = await getTemporaryDirectory();
    final file = File('${folder.path}/hum-$name-${_songs++ % 4}.wav');
    await file.writeAsBytes(bytes, flush: true);
    await _player.setFilePath(file.path);
    await _player.play();
  }

  @override
  Future<void> playUrl(Uri url) async {
    await _player.setUrl(url.toString());
    await _player.play();
  }

  @override
  Future<void> stop() => _player.stop();

  @override
  Future<void> dispose() => _player.dispose();
}
