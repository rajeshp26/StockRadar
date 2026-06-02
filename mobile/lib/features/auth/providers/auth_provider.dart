import 'package:supabase_flutter/supabase_flutter.dart' show Supabase, User, AuthChangeEvent;
import 'package:riverpod_annotation/riverpod_annotation.dart';
import '../../../core/providers/api_provider.dart';
import 'dart:developer' as developer;

part 'auth_provider.g.dart';

@Riverpod(keepAlive: true)
Stream<User?> authState(AuthStateRef ref) {
  return Supabase.instance.client.auth.onAuthStateChange.map(
    (event) => event.session?.user,
  );
}

@Riverpod(keepAlive: true)
class AuthNotifier extends _$AuthNotifier {
  @override
  Future<User?> build() async {
    final user = await ref.watch(authStateProvider.future);

    if (user != null) {
      await _syncWithBackend(user);
    }

    return user;
  }

  Future<void> _syncWithBackend(User user) async {
    final client = ref.read(apiClientProvider);

    try {
      developer.log('AUTH_SYNC: Syncing profile for ${user.email}...');
      await client.post(
        path: '/users/sync',
        data: {
          'email': user.email ?? '',
          'username': user.email?.split('@').first ?? 'User',
        },
        parser: (data) => data,
      );
      developer.log('AUTH_SYNC: Successfully synced profile.');
    } catch (e) {
      developer.log('AUTH_SYNC_ERROR: Failed to sync profile with backend: $e');
    }
  }

  Future<void> signOut() async {
    await Supabase.instance.client.auth.signOut();
  }
}
