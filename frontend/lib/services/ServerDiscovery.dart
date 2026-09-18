import 'dart:async';

import 'package:nsd/nsd.dart';

class ServerDiscovery {
  static const String _serviceType = '_huaccompany._tcp';

  static const Duration _discoveryTimeout = Duration(seconds: 5);

  static String? _cachedBaseUrl;

  /// Finds the backend server using mDNS/Bonjour.
  ///
  /// If a server was already found, the cached address is returned immediately.
  static Future<String?> resolveBaseUrl({bool forceRefresh = false}) async {
    // Use the previously discovered server when possible.
    if (!forceRefresh && _cachedBaseUrl != null) {
      print(
        'ServerDiscovery: using cached backend URL: '
        '$_cachedBaseUrl',
      );
      return _cachedBaseUrl;
    }

    print(
      'ServerDiscovery: searching for backend service '
      '$_serviceType...',
    );

    Discovery? discovery;
    final completer = Completer<String?>();

    try {
      discovery = await startDiscovery(_serviceType);

      discovery.addServiceListener((service, status) {
        print(
          'ServerDiscovery: service event '
          '[$status] '
          'host=${service.host}, '
          'port=${service.port}',
        );

        // Only accept a discovered service with a valid host and port.
        if (status == ServiceStatus.found &&
            service.host != null &&
            service.host!.isNotEmpty &&
            service.port != null &&
            service.port! > 0 &&
            !completer.isCompleted) {
          final baseUrl = 'http://${service.host}:${service.port}';

          print('ServerDiscovery: backend found at $baseUrl');

          _cachedBaseUrl = baseUrl;
          completer.complete(baseUrl);
        }
      });

      final result = await completer.future.timeout(
        _discoveryTimeout,
        onTimeout: () {
          print(
            'ServerDiscovery: discovery timed out after '
            '${_discoveryTimeout.inSeconds} seconds.',
          );

          return null;
        },
      );

      if (result == null) {
        print('ServerDiscovery: no backend server was found.');
      }

      return result;
    } catch (e, stackTrace) {
      print('ServerDiscovery: discovery failed: $e');
      print(stackTrace);

      return null;
    } finally {
      if (discovery != null) {
        try {
          await stopDiscovery(discovery);
          print('ServerDiscovery: discovery stopped.');
        } catch (e) {
          print('ServerDiscovery: could not stop discovery: $e');
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
    print(
      'ServerDiscovery: clearing cached backend URL: '
      '$_cachedBaseUrl',
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
