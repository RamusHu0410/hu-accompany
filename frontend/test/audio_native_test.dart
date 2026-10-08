import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/integrations/audio/Audio_Native.dart';

// Runs on the host VM, where the Rust library is not linked into the process:
// the paths a build without it (macOS, tests) takes. What happens with the
// library linked (codes, messages, permission) needs a device; see
// native_ffi/README.md.
void main() {
  test('starting without the native library says so instead of throwing', () {
    final audio = AudioNative();
    expect(audio.isConnected, isFalse);
    expect(audio.begin(), contains('not available'));
    expect(audio.problem(), isNull);
    expect(audio.end, returnsNormally);
  });

  test('preparing needs nothing off iOS', () async {
    expect(await AudioNative().prepare(), isNull);
  });

  test('only codes below 100 are fatal', () {
    expect(const AudioProblem(4, 'could not open').isFatal, isTrue);
    expect(const AudioProblem(100, 'silent').isFatal, isFalse);
  });
}
