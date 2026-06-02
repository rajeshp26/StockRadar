import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;

enum Environment { development, staging, production }

class EnvironmentConfig {
  static const Environment current = kDebugMode ? Environment.development : Environment.production;

  static bool get isDevelopment => current == Environment.development;

  static String get apiBaseUrl {
    if (kIsWeb) {
      return 'https://8001-stockerpro.cluster-joak5ukfbnbyqspg4tewa33d24.cloudworkstations.dev';
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
