import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:stockerpro/features/watchlist/presentation/screens/watchlist_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  debugPrint('[BOOTSTRAP] WidgetsFlutterBinding initialized');

  try {
    const supabaseUrl = String.fromEnvironment(
      'SUPABASE_URL',
      defaultValue: 'https://viqdqgxcumcdhqxooplw.supabase.co',
    );
    const supabaseAnonKey = String.fromEnvironment(
      'SUPABASE_ANON_KEY',
      defaultValue: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZpcWRxZ3hjdW1jZGhxeG9vcGx3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYwODI1NDAsImV4cCI6MjA4MTY1ODU0MH0.uQln345Vv9LL1c8BmiBA_kekaiKXntpcclpabfVOreg',
    );

    await Supabase.initialize(
      url: supabaseUrl,
      anonKey: supabaseAnonKey,
    );
    debugPrint('[BOOTSTRAP] ✅ Supabase.initialize() COMPLETED');
  } catch (e) {
    debugPrint('[BOOTSTRAP] FATAL: Supabase initialization failed: $e');
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
                  'Authentication Initialization Failed',
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
