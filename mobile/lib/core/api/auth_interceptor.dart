import 'package:dio/dio.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'dart:developer' as developer;

/// [AuthInterceptor] injects the Supabase access token into every request.
class AuthInterceptor extends Interceptor {
  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    try {
      final session = Supabase.instance.client.auth.currentSession;

      if (session != null) {
        options.headers['Authorization'] = 'Bearer ${session.accessToken}';
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
    if (err.response?.statusCode == 401) {
      developer.log('API_AUTH_CRITICAL: Unauthorized (401). Signing out user.');
      Supabase.instance.client.auth.signOut();
    }
    return handler.next(err);
  }
}
