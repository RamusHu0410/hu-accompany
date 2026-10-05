import AVFoundation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)

    // The Rust audio engine (cpal) opens the microphone itself and never
    // touches AVAudioSession, so the permission and the session have to be
    // arranged here, before it starts (lib/integrations/audio/Audio_Native.dart).
    let channel = FlutterMethodChannel(
      name: "hu_accomponist/audio_session",
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "prepare":
        AppDelegate.prepareAudioSession(result)
      case "release":
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  /// Asks for microphone permission (the system prompt appears only the first
  /// time), then makes the session one that records. Answers "granted",
  /// "denied", or a FlutterError when the session could not be set up.
  private static func prepareAudioSession(_ result: @escaping FlutterResult) {
    let answer: (Bool) -> Void = { granted in
      DispatchQueue.main.async {
        guard granted else {
          result("denied")
          return
        }
        let session = AVAudioSession.sharedInstance()
        do {
          // Recording needs a record-capable category: the default (ambient)
          // one delivers silence. .measurement turns off the system's gain
          // control and filtering, which would reshape the sound the pitch
          // network listens to. No .allowBluetooth: a Bluetooth headset mic
          // is 8-16 kHz mono.
          try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker])
          try session.setActive(true)
          result("granted")
        } catch {
          result(FlutterError(code: "audio_session", message: error.localizedDescription, details: nil))
        }
      }
    }
    if #available(iOS 17.0, *) {
      AVAudioApplication.requestRecordPermission(completionHandler: answer)
    } else {
      AVAudioSession.sharedInstance().requestRecordPermission(answer)
    }
  }
}
