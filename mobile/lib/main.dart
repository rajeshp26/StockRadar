import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:stockerpro/core/config/firebase_config.dart';
import 'package:stockerpro/features/watchlist/presentation/screens/watchlist_screen.dart';

void main() async {
  // ===== CRITICAL: Initialize Flutter Bindings First =====
  WidgetsFlutterBinding.ensureInitialized();
  
  debugPrint('[BOOTSTRAP] WidgetsFlutterBinding initialized');

  // ===== STEP 1: Initialize Firebase Auth Only =====
  try {
    if (kIsWeb) {
      // FAIL-FAST: Ensure environment variables were injected
      if (!FirebaseConfig.isWebConfigured) {
        throw Exception(
          "Firebase Configuration Missing. Please run with --dart-define flags. "
          "Refer to docs/ENVIRONMENT_SETUP_GUIDE.md"
        );
      }
      
      debugPrint('[BOOTSTRAP] Firebase Web Config Found:');
      debugPrint('  - API Key: ${FirebaseConfig.apiKey.substring(0, 10)}...');
      debugPrint('  - Project ID: ${FirebaseConfig.projectId}');
      debugPrint('  - Auth Domain: ${FirebaseConfig.authDomain}');
      
      // Initialize Firebase ONLY for Auth
      try {
        await Firebase.initializeApp(
          options: FirebaseConfig.options!,
        );
        debugPrint('[BOOTSTRAP] ✅ Firebase.initializeApp() COMPLETED');
        
        // Verify Auth is accessible
        final auth = FirebaseAuth.instance;
        debugPrint('[BOOTSTRAP] ✅ FirebaseAuth instance accessible');
        debugPrint('[BOOTSTRAP]    Current user: ${auth.currentUser?.email ?? "None (anonymous)"}');
        
      } catch (e, st) {
        debugPrint('[BOOTSTRAP] ❌ Firebase initialization FAILED:');
        debugPrint('Error: $e');
        debugPrint('StackTrace: $st');
        rethrow;
      }
    } else {
      debugPrint('[BOOTSTRAP] Not running on Web, skipping Firebase init');
      await Firebase.initializeApp();
    }
  } catch (e) {
    debugPrint('[BOOTSTRAP] FATAL: Firebase initialization failed: $e');
    // Show error UI instead of crashing
    runApp(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.error_outline, size: 48, color: Colors.red),
                const SizedBox(height: 16),
                const Text(
                  'Firebase Auth Initialization Failed',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    e.toString(),
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.grey),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    return;
  }

  // ===== STEP 2: Run the app with Riverpod =====
  debugPrint('[BOOTSTRAP] All initialization complete. Launching app...');
  
  runApp(
    const ProviderScope(
      child: StockerProApp(),
    ),
  );
}

class StockerProApp extends StatelessWidget {
  const StockerProApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'StockerPro',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F172A),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        fontFamily: 'Inter',
      ),
      home: const WatchlistScreen(),
    );
  }
}
