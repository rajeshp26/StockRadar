import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'dart:developer' as developer;

/// [AuthInterceptor] ensures that every request is authenticated.
/// Now hardened with force-refresh logic and session expiration handling.
class AuthInterceptor extends Interceptor {
  final FirebaseAuth _auth = FirebaseAuth.instance;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    try {
      final user = _auth.currentUser;

      if (user != null) {
        // PRODUCTION FIX: Force refresh ensures we don't send an expired token
        // to the FastAPI backend, preventing unnecessary 401s.
        final token = await user.getIdToken(true);
        options.headers['Authorization'] = 'Bearer $token';
      }

      handler.next(options);
    } catch (e) {
      developer.log('API_AUTH_ERROR: Failed to inject token: $e');
      handler.reject(
        DioException(
          requestOptions: options,
          error: 'Failed to retrieve auth token',
        ),
      );
    }
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    // 401 Unauthorized means the session is definitively invalid or token verification failed.
    if (err.response?.statusCode == 401) {
      developer.log('API_AUTH_CRITICAL: Unauthorized (401). Signing out user.');
      _auth.signOut();
      // NOTE: In a full app, you would also trigger a navigation event to the login screen.
    }
    return handler.next(err);
  }
}
