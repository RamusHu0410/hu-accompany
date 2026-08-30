import 'package:flutter_test/flutter_test.dart';
import 'package:hu_accomponist/main.dart';
import 'package:hu_accomponist/src/rust/frb_generated.dart';
import 'package:integration_test/integration_test.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async => await RustLib.init());

  testWidgets('App boots with RustLib initialized', (WidgetTester tester) async {
    // Smoke test only: confirms RustLib.init() doesn't throw and the app's
    // widget tree builds cleanly end to end (Vinyl_Loading_Screen ->
    // Record_Navigator_Page). There's no Rust API surface to exercise yet
    // (the old greet() demo fn was removed and nothing has replaced it),
    // so this intentionally doesn't assert on any generated-binding output —
    // add that back here once native_ffi exposes real functions to call.
    await tester.pumpWidget(const HuAccumponistApp());
    await tester.pump(const Duration(milliseconds: 950)); // past the loading screen's minDuration
    expect(tester.takeException(), isNull);
  });
}