import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:hu_accomponist/integrations/server/ServerDiscovery.dart';

/// A request the server answered with an error, or couldn't be reached for.
/// [message] is written for the person using the app.
class ApiException implements Exception {
  final String message;
  final String? code;
  final int? status;

  const ApiException(this.message, {this.code, this.status});

  @override
  String toString() => message;
}

/// Talks to the backend, finding its address over mDNS.
///
/// A network-level failure (not an HTTP error) usually means the cached
/// address went stale, so every call re-discovers and retries once before
/// giving up. Non-2xx answers become an [ApiException] carrying the backend's
/// own `error` text, which is already worded for the user.
class ApiClient {
  const ApiClient({this.timeout = const Duration(seconds: 30)});

  final Duration timeout;

  Future<http.Response> getJson(String path, {Map<String, String>? query}) {
    return _send((baseUrl) {
      final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
      return http.get(uri).timeout(timeout);
    });
  }

  Future<http.Response> postJson(
    String path,
    Map<String, dynamic> body, {
    Duration? timeout,
  }) {
    return _send((baseUrl) {
      return http
          .post(
            Uri.parse('$baseUrl$path'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(timeout ?? this.timeout);
    });
  }

  Future<http.Response> postFile(
    String path, {
    required String field,
    required String filePath,
    Map<String, String> fields = const {},
  }) {
    return _send((baseUrl) async {
      final request = http.MultipartRequest('POST', Uri.parse('$baseUrl$path'))
        ..fields.addAll(fields)
        ..files.add(await http.MultipartFile.fromPath(field, filePath));
      final streamed = await request.send().timeout(timeout);
      return http.Response.fromStream(streamed);
    });
  }

  /// The full URL for [path], for handing to something that fetches it itself
  /// (an audio player streaming a reply).
  Future<Uri> resolve(String path) async {
    final baseUrl = await _baseUrl(forceRefresh: false);
    return Uri.parse('$baseUrl$path');
  }

  /// Returns [response] if the request succeeded, otherwise throws.
  static http.Response ensureOk(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response;
    }
    String message = 'Something went wrong (status ${response.statusCode}).';
    String? code;
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      if (body is Map<String, dynamic>) {
        final error = body['error'];
        if (error is String && error.isNotEmpty) message = error;
        code = body['code'] as String?;
      }
    } on FormatException {
      // Not JSON (a proxy's error page): keep the generic message.
    }
    throw ApiException(message, code: code, status: response.statusCode);
  }

  Future<http.Response> _send(
    Future<http.Response> Function(String baseUrl) request,
  ) async {
    final first = await _attempt(request, forceRefresh: false);
    if (first != null) return first;

    ServerDiscovery.invalidateCache();
    final second = await _attempt(request, forceRefresh: true);
    if (second != null) return second;
    throw const ApiException('Could not reach the accompaniment server.');
  }

  /// Null on a network-level failure, so [_send] can retry.
  Future<http.Response?> _attempt(
    Future<http.Response> Function(String baseUrl) request, {
    required bool forceRefresh,
  }) async {
    final baseUrl = await _baseUrl(forceRefresh: forceRefresh);
    try {
      return await request(baseUrl);
    } on Exception {
      return null;
    }
  }

  Future<String> _baseUrl({required bool forceRefresh}) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl(
      forceRefresh: forceRefresh,
    );
    if (baseUrl == null) {
      throw const ApiException(
        'Could not find the accompaniment server on this network.',
      );
    }
    return baseUrl;
  }
}
