import 'package:freezed_annotation/freezed_annotation.dart';

part 'api_exception.freezed.dart';

@freezed
class ApiException with _$ApiException implements Exception {
  const factory ApiException.network({
    required String message,
    int? statusCode,
  }) = NetworkException;
  
  const factory ApiException.unauthorized({
    @Default('Session expired. Please login again.') String message,
  }) = UnauthorizedException;
  
  const factory ApiException.serverError({
    required String message,
    int? statusCode,
  }) = ServerException;
  
  const factory ApiException.timeout({
    @Default('Request timeout. Check your connection.') String message,
  }) = TimeoutException;
  
  const factory ApiException.unknown({
    required String message,
  }) = UnknownException;
}

extension ApiExceptionX on ApiException {
  String get userMessage => when(
    network: (msg, _) => 'Network error: $msg',
    unauthorized: (msg) => msg,
    serverError: (msg, _) => 'Server error: $msg',
    timeout: (msg) => msg,
    unknown: (msg) => 'Unexpected error: $msg',
  );
}
