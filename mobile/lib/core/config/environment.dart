import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;

enum Environment { development, staging, production }

class EnvironmentConfig {
  static const Environment current = kDebugMode ? Environment.development : Environment.production;

  static bool get isDevelopment => current == Environment.development;

  static String get apiBaseUrl {
    // CLOUD FIX: When running in the workstation browser, we MUST use the 
    // public domain of the backend (Port 8001), not localhost.
    if (kIsWeb) {
      return 'https://8001-firebase-studio-1766781248288.cluster-joak5ukfbnbyqspg4tewa33d24.cloudworkstations.dev';
    }

    switch (current) {
      case Environment.development:
        return 'http://10.0.2.2:8001';
      case Environment.staging:
        return 'https://api-staging.stockerpro.com';
      case Environment.production:
        return 'https://api.stockerpro.com';
    }
  }
}
