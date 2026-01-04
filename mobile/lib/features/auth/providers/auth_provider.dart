import 'package:firebase_auth/firebase_auth.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../../core/providers/api_provider.dart';
import 'dart:developer' as developer;

part 'auth_provider.g.dart';

@Riverpod(keepAlive: true)
Stream<User?> authState(AuthStateRef ref) {
  return FirebaseAuth.instance.authStateChanges();
}

@Riverpod(keepAlive: true)
class AuthNotifier extends _$AuthNotifier {
  @override
  Future<User?> build() async {
    // Wait for the auth state to be available
    final user = await ref.watch(authStateProvider.future);
    
    if (user != null) {
      // PROACTIVE SYNC: Ensure the backend is in sync with this user
      await _syncWithBackend(user);
    }
    
    return user;
  }

  Future<void> _syncWithBackend(User user) async {
    final client = ref.read(apiClientProvider);
    
    try {
      developer.log('AUTH_SYNC: Syncing profile for ${user.email}...');
      await client.post(
        path: '/users/sync', // Correct: Using named parameter
        data: {
          'email': user.email ?? '',
          'username': user.displayName ?? user.email?.split('@').first ?? 'User',
        },
        parser: (data) => data,
      );
      developer.log('AUTH_SYNC: Successfully synced profile.');
    } catch (e) {
      developer.log('AUTH_SYNC_ERROR: Failed to sync profile with backend: $e');
    }
  }

  Future<void> signOut() async {
    await FirebaseAuth.instance.signOut();
  }
}
