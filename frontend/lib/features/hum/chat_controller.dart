import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/integrations/hum/chat_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/hum/song_project.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

/// What the chat needs from the page that owns the song.
abstract class ChatHost {
  /// The song to edit, switching to the band engine first if needed (the
  /// host says so in the chat). Null when there's no hum yet or the song
  /// is still being made; [notReadyReason] says which.
  Future<SongProject?> projectForChat();
  String get notReadyReason;
  bool get canUndo;
  bool get canRedo;

  /// Makes the edited song and keeps it in the history, without playing it.
  Future<void> applyChatEdit(SongProject project, String label);

  /// Step back or forward through the song's versions, without playing.
  Future<bool> undoEdit();
  Future<bool> redoEdit();
  Future<void> playSong();
  Future<void> stopSong();
}

enum ChatVoice { idle, listening, thinking, speaking }

enum ChatSpeaker { user, assistant, notice }

class ChatEntry {
  final ChatSpeaker speaker;
  final String text;
  const ChatEntry(this.speaker, this.text);
}

/// The chat: typed or spoken messages that edit the song, replies shown and
/// (for spoken messages, or when [speakReplies] is on) spoken. The widget
/// only draws this.
class ChatController extends ChangeNotifier {
  ChatController({
    required HumRepository repository,
    required ChatHost host,
    HumRecorder? recorder,
    SongPlayer? voice,
    this.maxListen = const Duration(seconds: 12),
  }) : _repository = repository,
       _host = host,
       _recorder = recorder ?? MicRecorder(),
       _voice = voice ?? JustAudioSongPlayer(name: 'voice') {
    _voiceSub = _voice.playing.listen(_onVoicePlaying);
  }

  final HumRepository _repository;
  final ChatHost _host;
  final HumRecorder _recorder;
  final SongPlayer _voice;
  final Duration maxListen;

  final List<ChatEntry> entries = [];
  ChatVoice state = ChatVoice.idle;

  /// Speak replies to typed messages too (spoken ones are always spoken).
  bool speakReplies = false;

  StreamSubscription<bool>? _voiceSub;
  Timer? _listenTimer;
  bool _voiceStarted = false;
  bool _playSongAfterVoice = false;
  int _turn = 0;
  bool _disposed = false;

  bool get busy => state == ChatVoice.thinking;

  /// A line from the app itself, e.g. that it switched engines.
  void addNotice(String text) {
    entries.add(ChatEntry(ChatSpeaker.notice, text));
    _changed();
  }

  void toggleSpeakReplies() {
    speakReplies = !speakReplies;
    _changed();
  }

  // ── Typing ───────────────────────────────────────────────────────────

  Future<void> send(String text) async {
    final words = text.trim();
    if (words.isEmpty || busy || state == ChatVoice.listening) return;
    await _stopSpeaking();
    entries.add(ChatEntry(ChatSpeaker.user, words));
    await _ask(
      (project) => _repository.chat(
        words,
        project,
        canUndo: _host.canUndo,
        canRedo: _host.canRedo,
      ),
      spoken: false,
    );
  }

  // ── Speaking ─────────────────────────────────────────────────────────

  /// Tap the mic: start listening (cutting off a reply being spoken), or,
  /// while listening, stop and send what was said.
  Future<void> tapMic() async {
    if (state == ChatVoice.listening) return stopListening();
    if (busy) return;
    await _stopSpeaking();
    try {
      if (!await _recorder.requestPermission()) {
        return _say(
          "The microphone is off for this app, so type instead. You can turn it on in Settings.",
        );
      }
      await _host.stopSong(); // or the song ends up in the recording
      await _recorder.start();
    } on Exception catch (e) {
      return _say("I couldn't start listening ($e). Type it instead.");
    }
    state = ChatVoice.listening;
    _listenTimer = Timer(maxListen, stopListening);
    _changed();
  }

  Future<void> stopListening() async {
    if (state != ChatVoice.listening) return;
    _listenTimer?.cancel();
    String? path;
    try {
      path = await _recorder.stop();
    } on Exception {
      path = null;
    }
    if (path == null) {
      state = ChatVoice.idle;
      return _say("I didn't catch that. Try again, or type it.");
    }
    await _ask(
      (project) => _repository.chatVoice(
        path!,
        project,
        canUndo: _host.canUndo,
        canRedo: _host.canRedo,
      ),
      spoken: true,
    );
  }

  /// Stops a reply being spoken.
  Future<void> interrupt() => _stopSpeaking();

  // ── A turn ───────────────────────────────────────────────────────────

  Future<void> _ask(
    Future<ChatReply> Function(SongProject project) request, {
    required bool spoken,
  }) async {
    final turn = ++_turn;
    state = ChatVoice.thinking;
    _changed();
    final project = await _host.projectForChat();
    if (project == null) {
      state = ChatVoice.idle;
      return _say(_host.notReadyReason);
    }
    ChatReply reply;
    try {
      reply = await request(project);
    } on ApiException catch (e) {
      state = ChatVoice.idle;
      return _say(e.message);
    } on Exception {
      state = ChatVoice.idle;
      return _say(
        "I couldn't reach the server. Check it's running and try again.",
      );
    }
    if (turn != _turn || _disposed) return;
    if (spoken && reply.heard.isNotEmpty) {
      entries.add(ChatEntry(ChatSpeaker.user, reply.heard));
    }
    final songChanged = await _carryOut(reply);
    entries.add(ChatEntry(ChatSpeaker.assistant, reply.reply));
    state = ChatVoice.idle;
    _changed();
    final speak = (spoken || speakReplies) && reply.speechId.isNotEmpty;
    if (speak) {
      _playSongAfterVoice = songChanged;
      await _speak(reply.speechId);
    } else if (songChanged) {
      await _host.playSong();
    }
  }

  /// Applies the reply to the song. True when the song changed.
  Future<bool> _carryOut(ChatReply reply) async {
    try {
      switch (reply.intent) {
        case 'edit' when reply.project != null:
          await _host.applyChatEdit(reply.project!, reply.label);
          return true;
        case 'undo':
          return _host.undoEdit();
        case 'redo':
          return _host.redoEdit();
      }
    } on Exception catch (e) {
      entries.add(
        ChatEntry(ChatSpeaker.notice, "That change didn't go through ($e)."),
      );
    }
    return false;
  }

  Future<void> _speak(String speechId) async {
    try {
      final url = await _repository.chatSpeechUrl(speechId);
      _voiceStarted = false;
      state = ChatVoice.speaking;
      _changed();
      await _voice.playUrl(url);
    } on Exception {
      // the text is already on screen: voice is a bonus, not a requirement
      state = ChatVoice.idle;
      entries.add(
        const ChatEntry(
          ChatSpeaker.notice,
          "Voice replies aren't available right now, so I'll answer in text.",
        ),
      );
      _changed();
      await _afterVoice();
    }
  }

  void _onVoicePlaying(bool playing) {
    if (playing) {
      _voiceStarted = true;
    } else if (_voiceStarted && state == ChatVoice.speaking) {
      _voiceStarted = false; // finished on its own
      state = ChatVoice.idle;
      _changed();
      unawaited(_afterVoice());
    }
  }

  Future<void> _afterVoice() async {
    if (!_playSongAfterVoice) return;
    _playSongAfterVoice = false;
    await _host.playSong();
  }

  Future<void> _stopSpeaking() async {
    if (state != ChatVoice.speaking) return;
    state = ChatVoice.idle;
    _voiceStarted = false;
    _playSongAfterVoice =
        false; // interrupted: the listener wants to say something else
    _changed();
    await _voice.stop();
  }

  void _say(String text) {
    entries.add(ChatEntry(ChatSpeaker.assistant, text));
    _changed();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _listenTimer?.cancel();
    _voiceSub?.cancel();
    _recorder.dispose();
    _voice.dispose();
    super.dispose();
  }
}
