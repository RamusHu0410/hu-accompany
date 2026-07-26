import 'dart:async';

import 'package:nsd/nsd.dart';

/// Finds the Django backend on the LAN via mDNS/Bonjour instead of a
/// hardcoded IP, since dev machines move between networks/DHCP leases.
/// The backend advertises itself under this service type — see
/// backend/api/mdns.py.
///
/// Uses package:nsd (wraps NSNetServiceBrowser on iOS/macOS, NsdManager on
/// Android) rather than a raw-socket mDNS client — iOS's Local Network
/// Privacy restrictions silently drop raw multicast traffic that doesn't
/// go through the native Bonjour APIs, even with the right Info.plist
/// entries, so a pure-Dart UDP implementation (e.g. multicast_dns) is
/// unreliable here.
class ServerDiscovery {
  ServerDiscovery._();

  static const String _serviceType = '_huaccompany._tcp';
  static const Duration _discoveryTimeout = Duration(seconds: 4);

  static String? _cachedBaseUrl;

  /// Returns e.g. "http://172.28.176.117:8000", or null if no backend
  /// answered on the network within the timeout.
  static Future<String?> resolveBaseUrl({bool forceRefresh = false}) async {
    if (!forceRefresh && _cachedBaseUrl != null) {
      return _cachedBaseUrl;
    }

    final completer = Completer<String?>();
    final discovery = await startDiscovery(_serviceType);

    discovery.addServiceListener((service, status) {
      if (status == ServiceStatus.found &&
          service.host != null &&
          service.port != null &&
          !completer.isCompleted) {
        completer.complete('http://${service.host}:${service.port}');
      }
    });

    final result = await completer.future.timeout(
      _discoveryTimeout,
      onTimeout: () => null,
    );
    await stopDiscovery(discovery);

    _cachedBaseUrl = result;
    return result;
  }

  /// Call after a request against the cached URL fails, so the next
  /// resolveBaseUrl() re-discovers instead of retrying a stale address.
  static void invalidateCache() {
    _cachedBaseUrl = null;
  }
}
