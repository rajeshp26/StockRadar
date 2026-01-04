import 'package:freezed_annotation/freezed_annotation.dart';
import 'api_exception.dart';

part 'api_result.freezed.dart';

@freezed
class ApiResult<T> with _$ApiResult<T> {
  const factory ApiResult.success(T data) = Success<T>;
  const factory ApiResult.failure(ApiException exception) = Failure<T>;
}

extension ApiResultX<T> on ApiResult<T> {
  T? get dataOrNull => when(
    success: (data) => data,
    failure: (_) => null,
  );
  
  ApiException? get errorOrNull => when(
    success: (_) => null,
    failure: (error) => error,
  );
}
