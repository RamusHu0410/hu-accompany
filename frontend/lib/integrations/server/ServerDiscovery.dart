import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:nsd/nsd.dart';

class ServerDiscovery {
  static const String _serviceType = '_huaccompany._tcp';

  static const Duration _discoveryTimeout = Duration(seconds: 5);

  static String? _cachedBaseUrl;

  /// Cleans up the hostname mDNS hands back before it is used in a URL.
  ///
  /// Two things need fixing. A Bonjour hostname is fully qualified and ends
  /// in a trailing dot ("host.local."), which some HTTP clients will not
  /// resolve. And the backend advertises a doubled suffix — mdns.py builds
  /// its `server` field as `socket.gethostname() + ".local."`, but on macOS
  /// gethostname() already returns `<name>.local`, so the record says
  /// `<name>.local.local.` — a name that resolves nowhere. Collapsing
  /// the repeat here fixes discovery from the app side without touching the
  /// backend.
  static String normalizeHost(String host) {
    var cleaned = host;
    while (cleaned.endsWith('.')) {
      cleaned = cleaned.substring(0, cleaned.length - 1);
    }
    while (cleaned.toLowerCase().endsWith('.local.local')) {
      cleaned = cleaned.substring(0, cleaned.length - '.local'.length);
    }
    return cleaned;
  }

  /// Finds the backend server using mDNS/Bonjour.
  ///
  /// If a server was already found, the cached address is returned immediately.
  static Future<String?> resolveBaseUrl({bool forceRefresh = false}) async {
    // Use the previously discovered server when possible.
    if (!forceRefresh && _cachedBaseUrl != null) {
      debugPrint('[Diagnostics] discovery: using cached backend $_cachedBaseUrl');
      return _cachedBaseUrl;
    }

    debugPrint(
      '[Diagnostics] discovery: searching for $_serviceType '
      '(timeout ${_discoveryTimeout.inSeconds}s)...',
    );

    final stopwatch = Stopwatch()..start();
    Discovery? discovery;
    final completer = Completer<String?>();

    try {
      discovery = await startDiscovery(_serviceType);

      discovery.addServiceListener((service, status) {
        debugPrint(
          '[Diagnostics] discovery: event [$status] '
          'host=${service.host} port=${service.port}',
        );

        // Only accept a discovered service with a valid host and port.
        if (status == ServiceStatus.found &&
            service.host != null &&
            service.host!.isNotEmpty &&
            service.port != null &&
            service.port! > 0 &&
            !completer.isCompleted) {
          final host = normalizeHost(service.host!);
          if (host != service.host) {
            debugPrint(
              '[Diagnostics] discovery: normalized advertised host '
              '"${service.host}" -> "$host"',
            );
          }
          final baseUrl = 'http://$host:${service.port}';

          debugPrint(
            '[Diagnostics] discovery: backend FOUND at $baseUrl '
            'in ${stopwatch.elapsedMilliseconds}ms',
          );

          _cachedBaseUrl = baseUrl;
          completer.complete(baseUrl);
        }
      });

      final result = await completer.future.timeout(
        _discoveryTimeout,
        onTimeout: () {
          debugPrint(
            '[Diagnostics] discovery: TIMED OUT after '
            '${stopwatch.elapsedMilliseconds}ms — no backend on this network. '
            'The next request will retry discovery.',
          );
          return null;
        },
      );

      return result;
    } catch (e, stackTrace) {
      debugPrint(
        '[Diagnostics] discovery: FAILED after ${stopwatch.elapsedMilliseconds}ms '
        '— $e. The next request will retry discovery.',
      );
      debugPrintStack(stackTrace: stackTrace);
      return null;
    } finally {
      if (discovery != null) {
        try {
          await stopDiscovery(discovery);
        } catch (e) {
          debugPrint('[Diagnostics] discovery: could not stop cleanly — $e');
        }
      }
    }
  }

  /// Clears the saved backend address.
  ///
  /// Call this when the server changes address or when a request fails.
  /// Clears the saved backend address.
  ///
  /// Call this when the server changes address or when a request fails.
  static void invalidateCache() {
    debugPrint(
      '[Diagnostics] discovery: clearing cached backend $_cachedBaseUrl — '
      'next request will rediscover.',
    );
    _cachedBaseUrl = null;
  }

  /// Alias for invalidateCache().
  ///
  /// Kept so either method name can be used.
  static void clearCache() {
    invalidateCache();
  }
}
