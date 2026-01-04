import 'package:firebase_core/firebase_core.dart';

/// [FirebaseConfig] encapsulates all Firebase environment variables.
class FirebaseConfig {
  static const String apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const String authDomain = String.fromEnvironment('FIREBASE_AUTH_DOMAIN');
  static const String projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
  static const String storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');
  static const String messagingSenderId = String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
  static const String appId = String.fromEnvironment('FIREBASE_APP_ID');

  /// Validates configuration presence.
  static bool get isWebConfigured =>
      apiKey.isNotEmpty &&
      appId.isNotEmpty &&
      projectId.isNotEmpty;

  /// Returns options without using 'const' logic on variable checks.
  static FirebaseOptions? get options {
    if (apiKey == "") return null;
    
    return const FirebaseOptions(
      apiKey: apiKey,
      authDomain: authDomain,
      projectId: projectId,
      storageBucket: storageBucket,
      messagingSenderId: messagingSenderId,
      appId: appId,
    );
  }
}
