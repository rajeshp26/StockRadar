import 'package:dio/dio.dart';
import '../config/environment.dart';
import 'api_exception.dart';
import 'api_result.dart';
import 'auth_interceptor.dart';
import 'dart:developer' as developer;

/// [ApiClient] is the centralized networking engine for StockerPro.
/// It provides robust error handling, automatic authentication relay,
/// and type-safe response parsing.
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;

  late final Dio _dio;

  ApiClient._internal() {
    _dio = Dio(
      BaseOptions(
        baseUrl: EnvironmentConfig.apiBaseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    _setupInterceptors();
  }

  void _setupInterceptors() {
    // SECURITY: The Auth Relay
    _dio.interceptors.add(AuthInterceptor());

    // LOGGING: Only in development
    if (EnvironmentConfig.isDevelopment) {
      _dio.interceptors.add(LogInterceptor(
        requestHeader: true,
        requestBody: true,
        responseHeader: true,
        responseBody: true,
        error: true,
      ));
    }
  }

  /// [request] is a generic wrapper that catches DioExceptions and converts them
  /// into StockerPro's [ApiException] for consistent UI error handling.
  Future<ApiResult<T>> request<T>({
    required String path,
    required String method,
    Map<String, dynamic>? queryParameters,
    dynamic data,
    required T Function(dynamic) parser,
  }) async {
    try {
      final response = await _dio.request(
        path,
        options: Options(method: method),
        queryParameters: queryParameters,
        data: data,
      );

      return ApiResult.success(parser(response.data));
    } on DioException catch (e) {
      developer.log('API_REQUEST_ERROR: ${e.message}');
      return ApiResult.failure(_handleDioException(e));
    } catch (e) {
      developer.log('API_UNKNOWN_ERROR: $e');
      return ApiResult.failure(
        ApiException.unknown(message: e.toString()),
      );
    }
  }

  ApiException _handleDioException(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return const ApiException.timeout();

      case DioExceptionType.badResponse:
        final statusCode = e.response?.statusCode;
        final message = e.response?.data?['detail'] ?? 'Server error';

        if (statusCode == 401) {
          return const ApiException.unauthorized();
        }

        return ApiException.serverError(
          message: message.toString(),
          statusCode: statusCode,
        );

      case DioExceptionType.connectionError:
        return const ApiException.network(
          message: 'No internet connection',
        );

      default:
        return ApiException.unknown(
          message: e.message ?? 'An unexpected error occurred',
        );
    }
  }

  // Convenience Methods
  Future<ApiResult<T>> get<T>({
    required String path,
    Map<String, dynamic>? queryParameters,
    required T Function(dynamic) parser,
  }) =>
      request(
        path: path,
        method: 'GET',
        queryParameters: queryParameters,
        parser: parser,
      );

  Future<ApiResult<T>> post<T>({
    required String path,
    dynamic data,
    required T Function(dynamic) parser,
  }) =>
      request(
        path: path,
        method: 'POST',
        data: data,
        parser: parser,
      );
}
