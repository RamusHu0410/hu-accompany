import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter_rust_bridge/flutter_rust_bridge_for_generated.dart'
    show ExternalLibrary;

import 'package:hu_accomponist/src/rust/frb_generated.dart';

/// Single place that brings up the flutter_rust_bridge runtime.
///
/// Exists because how the Rust library is loaded differs by platform, and
/// two call sites need to agree about it.
///
/// On iOS the Rust code is linked **statically** into the Runner executable
/// (`ios/libnative_ffi_sim.a`, via the Frameworks build phase), so its
/// symbols are already in the running process. The generated default loader
/// instead tries to `dlopen` a dynamic `native_ffi.framework`, which does
/// not exist in that build and fails with "Failed to load dynamic library".
/// `ExternalLibrary.process()` looks the symbols up in the current process,
/// which is the correct strategy for static linking.
///
/// Other platforms keep the generated default. Note that macOS does not link
/// the Rust library at all — its Xcode project has no reference to any of the
/// `libnative_ffi*.a` files — so initialization is expected to fail there and
/// anything Rust-backed is unavailable on that target.
abstract final class RustBridge {
  static bool _initialized = false;
  static bool _available = false;

  /// True once initialization has succeeded. False means the Rust side is
  /// not reachable in this build, and callers should degrade rather than
  /// assume a stream will ever produce anything.
  static bool get isAvailable => _available;

  /// Safe to call repeatedly; the work happens once.
  static Future<void> ensureInitialized() async {
    if (_initialized) return;
    _initialized = true;

    try {
      if (Platform.isIOS) {
        await RustLib.init(
          externalLibrary: ExternalLibrary.process(iKnowHowToUseIt: true),
        );
      } else {
        await RustLib.init();
      }
      _available = true;
      debugPrint('[Diagnostics] rust: bridge initialized.');
    } catch (e) {
      _available = false;
      debugPrint('[Diagnostics] rust: bridge unavailable — $e');
    }
  }
}
