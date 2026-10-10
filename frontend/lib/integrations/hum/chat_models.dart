import 'package:hu_accomponist/integrations/hum/song_project.dart';

/// The answer to one typed or spoken chat message
/// (backend/hum/views_chat.py).
class ChatReply {
  final String heard;

  /// edit, undo, redo, clarify, unsupported, off_topic, unclear, busy or
  /// error.
  final String intent;
  final String reply;

  /// The edited song, or null when nothing changed.
  final SongProject? project;

  /// Tracks whose sound changed (the server renders only these again).
  final List<String> changed;

  /// What changed, for the undo history ("drums quieter").
  final String label;
  final String speechId;
  final String? error;

  const ChatReply({
    required this.heard,
    required this.intent,
    required this.reply,
    this.project,
    this.changed = const [],
    this.label = '',
    this.speechId = '',
    this.error,
  });

  factory ChatReply.fromJson(Map<String, dynamic> json) {
    final project = json['project'] as Map<String, dynamic>?;
    return ChatReply(
      heard: json['heard'] as String? ?? '',
      intent: json['intent'] as String? ?? 'unclear',
      reply: json['reply'] as String? ?? '',
      project: project == null ? null : SongProject.fromJson(project),
      changed: [
        for (final id in json['changed'] as List<dynamic>? ?? const [])
          id as String,
      ],
      label: json['label'] as String? ?? '',
      speechId: json['speech_id'] as String? ?? '',
      error: json['error'] as String?,
    );
  }
}

/// The song after edits made without the chat (POST /api/hum/project/edit).
class EditResult {
  final SongProject project;
  final String label;

  /// Why an edit wasn't made, when one wasn't.
  final List<String> refused;

  const EditResult({
    required this.project,
    this.label = '',
    this.refused = const [],
  });

  bool get changedAnything => label.isNotEmpty;

  factory EditResult.fromJson(Map<String, dynamic> json) => EditResult(
    project: SongProject.fromJson(json['project'] as Map<String, dynamic>),
    label: json['label'] as String? ?? '',
    refused: [
      for (final why in json['refused'] as List<dynamic>? ?? const [])
        why as String,
    ],
  );
}

/// Edits the app's own controls send, in the chat's terms
/// (backend/hum/chat/commands.py).
abstract final class ProjectEdits {
  static Map<String, dynamic> genre(String id) => {
    'action': 'set_genre',
    'genre': id,
  };

  static Map<String, dynamic> mood(String id) => {
    'action': 'set_mood',
    'mood': id,
  };
}
