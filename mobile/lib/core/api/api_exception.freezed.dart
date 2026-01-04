// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'api_exception.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

/// @nodoc
mixin _$ApiException {
  String get message => throw _privateConstructorUsedError;
  @optionalTypeArgs
  TResult when<TResult extends Object?>({
    required TResult Function(String message, int? statusCode) network,
    required TResult Function(String message) unauthorized,
    required TResult Function(String message, int? statusCode) serverError,
    required TResult Function(String message) timeout,
    required TResult Function(String message) unknown,
  }) =>
      throw _privateConstructorUsedError;
  @optionalTypeArgs
  TResult? whenOrNull<TResult extends Object?>({
    TResult? Function(String message, int? statusCode)? network,
    TResult? Function(String message)? unauthorized,
    TResult? Function(String message, int? statusCode)? serverError,
    TResult? Function(String message)? timeout,
    TResult? Function(String message)? unknown,
  }) =>
      throw _privateConstructorUsedError;
  @optionalTypeArgs
  TResult maybeWhen<TResult extends Object?>({
    TResult Function(String message, int? statusCode)? network,
    TResult Function(String message)? unauthorized,
    TResult Function(String message, int? statusCode)? serverError,
    TResult Function(String message)? timeout,
    TResult Function(String message)? unknown,
    required TResult orElse(),
  }) =>
      throw _privateConstructorUsedError;
  @optionalTypeArgs
  TResult map<TResult extends Object?>({
    required TResult Function(NetworkException value) network,
    required TResult Function(UnauthorizedException value) unauthorized,
    required TResult Function(ServerException value) serverError,
    required TResult Function(TimeoutException value) timeout,
    required TResult Function(UnknownException value) unknown,
  }) =>
      throw _privateConstructorUsedError;
  @optionalTypeArgs
  TResult? mapOrNull<TResult extends Object?>({
    TResult? Function(NetworkException value)? network,
    TResult? Function(UnauthorizedException value)? unauthorized,
    TResult? Function(ServerException value)? serverError,
    TResult? Function(TimeoutException value)? timeout,
    TResult? Function(UnknownException value)? unknown,
  }) =>
      throw _privateConstructorUsedError;
  @optionalTypeArgs
  TResult maybeMap<TResult extends Object?>({
    TResult Function(NetworkException value)? network,
    TResult Function(UnauthorizedException value)? unauthorized,
    TResult Function(ServerException value)? serverError,
    TResult Function(TimeoutException value)? timeout,
    TResult Function(UnknownException value)? unknown,
    required TResult orElse(),
  }) =>
      throw _privateConstructorUsedError;

  @JsonKey(ignore: true)
  $ApiExceptionCopyWith<ApiException> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ApiExceptionCopyWith<$Res> {
  factory $ApiExceptionCopyWith(
          ApiException value, $Res Function(ApiException) then) =
      _$ApiExceptionCopyWithImpl<$Res, ApiException>;
  @useResult
  $Res call({String message});
}

/// @nodoc
class _$ApiExceptionCopyWithImpl<$Res, $Val extends ApiException>
    implements $ApiExceptionCopyWith<$Res> {
  _$ApiExceptionCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? message = null,
  }) {
    return _then(_value.copyWith(
      message: null == message
          ? _value.message
          : message // ignore: cast_nullable_to_non_nullable
              as String,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$NetworkExceptionImplCopyWith<$Res>
    implements $ApiExceptionCopyWith<$Res> {
  factory _$$NetworkExceptionImplCopyWith(_$NetworkExceptionImpl value,
          $Res Function(_$NetworkExceptionImpl) then) =
      __$$NetworkExceptionImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String message, int? statusCode});
}

/// @nodoc
class __$$NetworkExceptionImplCopyWithImpl<$Res>
    extends _$ApiExceptionCopyWithImpl<$Res, _$NetworkExceptionImpl>
    implements _$$NetworkExceptionImplCopyWith<$Res> {
  __$$NetworkExceptionImplCopyWithImpl(_$NetworkExceptionImpl _value,
      $Res Function(_$NetworkExceptionImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? message = null,
    Object? statusCode = freezed,
  }) {
    return _then(_$NetworkExceptionImpl(
      message: null == message
          ? _value.message
          : message // ignore: cast_nullable_to_non_nullable
              as String,
      statusCode: freezed == statusCode
          ? _value.statusCode
          : statusCode // ignore: cast_nullable_to_non_nullable
              as int?,
    ));
  }
}

/// @nodoc

class _$NetworkExceptionImpl implements NetworkException {
  const _$NetworkExceptionImpl({required this.message, this.statusCode});

  @override
  final String message;
  @override
  final int? statusCode;

  @override
  String toString() {
    return 'ApiException.network(message: $message, statusCode: $statusCode)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$NetworkExceptionImpl &&
            (identical(other.message, message) || other.message == message) &&
            (identical(other.statusCode, statusCode) ||
                other.statusCode == statusCode));
  }

  @override
  int get hashCode => Object.hash(runtimeType, message, statusCode);

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$NetworkExceptionImplCopyWith<_$NetworkExceptionImpl> get copyWith =>
      __$$NetworkExceptionImplCopyWithImpl<_$NetworkExceptionImpl>(
          this, _$identity);

  @override
  @optionalTypeArgs
  TResult when<TResult extends Object?>({
    required TResult Function(String message, int? statusCode) network,
    required TResult Function(String message) unauthorized,
    required TResult Function(String message, int? statusCode) serverError,
    required TResult Function(String message) timeout,
    required TResult Function(String message) unknown,
  }) {
    return network(message, statusCode);
  }

  @override
  @optionalTypeArgs
  TResult? whenOrNull<TResult extends Object?>({
    TResult? Function(String message, int? statusCode)? network,
    TResult? Function(String message)? unauthorized,
    TResult? Function(String message, int? statusCode)? serverError,
    TResult? Function(String message)? timeout,
    TResult? Function(String message)? unknown,
  }) {
    return network?.call(message, statusCode);
  }

  @override
  @optionalTypeArgs
  TResult maybeWhen<TResult extends Object?>({
    TResult Function(String message, int? statusCode)? network,
    TResult Function(String message)? unauthorized,
    TResult Function(String message, int? statusCode)? serverError,
    TResult Function(String message)? timeout,
    TResult Function(String message)? unknown,
    required TResult orElse(),
  }) {
    if (network != null) {
      return network(message, statusCode);
    }
    return orElse();
  }

  @override
  @optionalTypeArgs
  TResult map<TResult extends Object?>({
    required TResult Function(NetworkException value) network,
    required TResult Function(UnauthorizedException value) unauthorized,
    required TResult Function(ServerException value) serverError,
    required TResult Function(TimeoutException value) timeout,
    required TResult Function(UnknownException value) unknown,
  }) {
    return network(this);
  }

  @override
  @optionalTypeArgs
  TResult? mapOrNull<TResult extends Object?>({
    TResult? Function(NetworkException value)? network,
    TResult? Function(UnauthorizedException value)? unauthorized,
    TResult? Function(ServerException value)? serverError,
    TResult? Function(TimeoutException value)? timeout,
    TResult? Function(UnknownException value)? unknown,
  }) {
    return network?.call(this);
  }

  @override
  @optionalTypeArgs
  TResult maybeMap<TResult extends Object?>({
    TResult Function(NetworkException value)? network,
    TResult Function(UnauthorizedException value)? unauthorized,
    TResult Function(ServerException value)? serverError,
    TResult Function(TimeoutException value)? timeout,
    TResult Function(UnknownException value)? unknown,
    required TResult orElse(),
  }) {
    if (network != null) {
      return network(this);
    }
    return orElse();
  }
}

abstract class NetworkException implements ApiException {
  const factory NetworkException(
      {required final String message,
      final int? statusCode}) = _$NetworkExceptionImpl;

  @override
  String get message;
  int? get statusCode;
  @override
  @JsonKey(ignore: true)
  _$$NetworkExceptionImplCopyWith<_$NetworkExceptionImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class _$$UnauthorizedExceptionImplCopyWith<$Res>
    implements $ApiExceptionCopyWith<$Res> {
  factory _$$UnauthorizedExceptionImplCopyWith(
          _$UnauthorizedExceptionImpl value,
          $Res Function(_$UnauthorizedExceptionImpl) then) =
      __$$UnauthorizedExceptionImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String message});
}

/// @nodoc
class __$$UnauthorizedExceptionImplCopyWithImpl<$Res>
    extends _$ApiExceptionCopyWithImpl<$Res, _$UnauthorizedExceptionImpl>
    implements _$$UnauthorizedExceptionImplCopyWith<$Res> {
  __$$UnauthorizedExceptionImplCopyWithImpl(_$UnauthorizedExceptionImpl _value,
      $Res Function(_$UnauthorizedExceptionImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? message = null,
  }) {
    return _then(_$UnauthorizedExceptionImpl(
      message: null == message
          ? _value.message
          : message // ignore: cast_nullable_to_non_nullable
              as String,
    ));
  }
}

/// @nodoc

class _$UnauthorizedExceptionImpl implements UnauthorizedException {
  const _$UnauthorizedExceptionImpl(
      {this.message = 'Session expired. Please login again.'});

  @override
  @JsonKey()
  final String message;

  @override
  String toString() {
    return 'ApiException.unauthorized(message: $message)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$UnauthorizedExceptionImpl &&
            (identical(other.message, message) || other.message == message));
  }

  @override
  int get hashCode => Object.hash(runtimeType, message);

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$UnauthorizedExceptionImplCopyWith<_$UnauthorizedExceptionImpl>
      get copyWith => __$$UnauthorizedExceptionImplCopyWithImpl<
          _$UnauthorizedExceptionImpl>(this, _$identity);

  @override
  @optionalTypeArgs
  TResult when<TResult extends Object?>({
    required TResult Function(String message, int? statusCode) network,
    required TResult Function(String message) unauthorized,
    required TResult Function(String message, int? statusCode) serverError,
    required TResult Function(String message) timeout,
    required TResult Function(String message) unknown,
  }) {
    return unauthorized(message);
  }

  @override
  @optionalTypeArgs
  TResult? whenOrNull<TResult extends Object?>({
    TResult? Function(String message, int? statusCode)? network,
    TResult? Function(String message)? unauthorized,
    TResult? Function(String message, int? statusCode)? serverError,
    TResult? Function(String message)? timeout,
    TResult? Function(String message)? unknown,
  }) {
    return unauthorized?.call(message);
  }

  @override
  @optionalTypeArgs
  TResult maybeWhen<TResult extends Object?>({
    TResult Function(String message, int? statusCode)? network,
    TResult Function(String message)? unauthorized,
    TResult Function(String message, int? statusCode)? serverError,
    TResult Function(String message)? timeout,
    TResult Function(String message)? unknown,
    required TResult orElse(),
  }) {
    if (unauthorized != null) {
      return unauthorized(message);
    }
    return orElse();
  }

  @override
  @optionalTypeArgs
  TResult map<TResult extends Object?>({
    required TResult Function(NetworkException value) network,
    required TResult Function(UnauthorizedException value) unauthorized,
    required TResult Function(ServerException value) serverError,
    required TResult Function(TimeoutException value) timeout,
    required TResult Function(UnknownException value) unknown,
  }) {
    return unauthorized(this);
  }

  @override
  @optionalTypeArgs
  TResult? mapOrNull<TResult extends Object?>({
    TResult? Function(NetworkException value)? network,
    TResult? Function(UnauthorizedException value)? unauthorized,
    TResult? Function(ServerException value)? serverError,
    TResult? Function(TimeoutException value)? timeout,
    TResult? Function(UnknownException value)? unknown,
  }) {
    return unauthorized?.call(this);
  }

  @override
  @optionalTypeArgs
  TResult maybeMap<TResult extends Object?>({
    TResult Function(NetworkException value)? network,
    TResult Function(UnauthorizedException value)? unauthorized,
    TResult Function(ServerException value)? serverError,
    TResult Function(TimeoutException value)? timeout,
    TResult Function(UnknownException value)? unknown,
    required TResult orElse(),
  }) {
    if (unauthorized != null) {
      return unauthorized(this);
    }
    return orElse();
  }
}

abstract class UnauthorizedException implements ApiException {
  const factory UnauthorizedException({final String message}) =
      _$UnauthorizedExceptionImpl;

  @override
  String get message;
  @override
  @JsonKey(ignore: true)
  _$$UnauthorizedExceptionImplCopyWith<_$UnauthorizedExceptionImpl>
      get copyWith => throw _privateConstructorUsedError;
}

/// @nodoc
abstract class _$$ServerExceptionImplCopyWith<$Res>
    implements $ApiExceptionCopyWith<$Res> {
  factory _$$ServerExceptionImplCopyWith(_$ServerExceptionImpl value,
          $Res Function(_$ServerExceptionImpl) then) =
      __$$ServerExceptionImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String message, int? statusCode});
}

/// @nodoc
class __$$ServerExceptionImplCopyWithImpl<$Res>
    extends _$ApiExceptionCopyWithImpl<$Res, _$ServerExceptionImpl>
    implements _$$ServerExceptionImplCopyWith<$Res> {
  __$$ServerExceptionImplCopyWithImpl(
      _$ServerExceptionImpl _value, $Res Function(_$ServerExceptionImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? message = null,
    Object? statusCode = freezed,
  }) {
    return _then(_$ServerExceptionImpl(
      message: null == message
          ? _value.message
          : message // ignore: cast_nullable_to_non_nullable
              as String,
      statusCode: freezed == statusCode
          ? _value.statusCode
          : statusCode // ignore: cast_nullable_to_non_nullable
              as int?,
    ));
  }
}

/// @nodoc

class _$ServerExceptionImpl implements ServerException {
  const _$ServerExceptionImpl({required this.message, this.statusCode});

  @override
  final String message;
  @override
  final int? statusCode;

  @override
  String toString() {
    return 'ApiException.serverError(message: $message, statusCode: $statusCode)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ServerExceptionImpl &&
            (identical(other.message, message) || other.message == message) &&
            (identical(other.statusCode, statusCode) ||
                other.statusCode == statusCode));
  }

  @override
  int get hashCode => Object.hash(runtimeType, message, statusCode);

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$ServerExceptionImplCopyWith<_$ServerExceptionImpl> get copyWith =>
      __$$ServerExceptionImplCopyWithImpl<_$ServerExceptionImpl>(
          this, _$identity);

  @override
  @optionalTypeArgs
  TResult when<TResult extends Object?>({
    required TResult Function(String message, int? statusCode) network,
    required TResult Function(String message) unauthorized,
    required TResult Function(String message, int? statusCode) serverError,
    required TResult Function(String message) timeout,
    required TResult Function(String message) unknown,
  }) {
    return serverError(message, statusCode);
  }

  @override
  @optionalTypeArgs
  TResult? whenOrNull<TResult extends Object?>({
    TResult? Function(String message, int? statusCode)? network,
    TResult? Function(String message)? unauthorized,
    TResult? Function(String message, int? statusCode)? serverError,
    TResult? Function(String message)? timeout,
    TResult? Function(String message)? unknown,
  }) {
    return serverError?.call(message, statusCode);
  }

  @override
  @optionalTypeArgs
  TResult maybeWhen<TResult extends Object?>({
    TResult Function(String message, int? statusCode)? network,
    TResult Function(String message)? unauthorized,
    TResult Function(String message, int? statusCode)? serverError,
    TResult Function(String message)? timeout,
    TResult Function(String message)? unknown,
    required TResult orElse(),
  }) {
    if (serverError != null) {
      return serverError(message, statusCode);
    }
    return orElse();
  }

  @override
  @optionalTypeArgs
  TResult map<TResult extends Object?>({
    required TResult Function(NetworkException value) network,
    required TResult Function(UnauthorizedException value) unauthorized,
    required TResult Function(ServerException value) serverError,
    required TResult Function(TimeoutException value) timeout,
    required TResult Function(UnknownException value) unknown,
  }) {
    return serverError(this);
  }

  @override
  @optionalTypeArgs
  TResult? mapOrNull<TResult extends Object?>({
    TResult? Function(NetworkException value)? network,
    TResult? Function(UnauthorizedException value)? unauthorized,
    TResult? Function(ServerException value)? serverError,
    TResult? Function(TimeoutException value)? timeout,
    TResult? Function(UnknownException value)? unknown,
  }) {
    return serverError?.call(this);
  }

  @override
  @optionalTypeArgs
  TResult maybeMap<TResult extends Object?>({
    TResult Function(NetworkException value)? network,
    TResult Function(UnauthorizedException value)? unauthorized,
    TResult Function(ServerException value)? serverError,
    TResult Function(TimeoutException value)? timeout,
    TResult Function(UnknownException value)? unknown,
    required TResult orElse(),
  }) {
    if (serverError != null) {
      return serverError(this);
    }
    return orElse();
  }
}

abstract class ServerException implements ApiException {
  const factory ServerException(
      {required final String message,
      final int? statusCode}) = _$ServerExceptionImpl;

  @override
  String get message;
  int? get statusCode;
  @override
  @JsonKey(ignore: true)
  _$$ServerExceptionImplCopyWith<_$ServerExceptionImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class _$$TimeoutExceptionImplCopyWith<$Res>
    implements $ApiExceptionCopyWith<$Res> {
  factory _$$TimeoutExceptionImplCopyWith(_$TimeoutExceptionImpl value,
          $Res Function(_$TimeoutExceptionImpl) then) =
      __$$TimeoutExceptionImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String message});
}

/// @nodoc
class __$$TimeoutExceptionImplCopyWithImpl<$Res>
    extends _$ApiExceptionCopyWithImpl<$Res, _$TimeoutExceptionImpl>
    implements _$$TimeoutExceptionImplCopyWith<$Res> {
  __$$TimeoutExceptionImplCopyWithImpl(_$TimeoutExceptionImpl _value,
      $Res Function(_$TimeoutExceptionImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? message = null,
  }) {
    return _then(_$TimeoutExceptionImpl(
      message: null == message
          ? _value.message
          : message // ignore: cast_nullable_to_non_nullable
              as String,
    ));
  }
}

/// @nodoc

class _$TimeoutExceptionImpl implements TimeoutException {
  const _$TimeoutExceptionImpl(
      {this.message = 'Request timeout. Check your connection.'});

  @override
  @JsonKey()
  final String message;

  @override
  String toString() {
    return 'ApiException.timeout(message: $message)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$TimeoutExceptionImpl &&
            (identical(other.message, message) || other.message == message));
  }

  @override
  int get hashCode => Object.hash(runtimeType, message);

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$TimeoutExceptionImplCopyWith<_$TimeoutExceptionImpl> get copyWith =>
      __$$TimeoutExceptionImplCopyWithImpl<_$TimeoutExceptionImpl>(
          this, _$identity);

  @override
  @optionalTypeArgs
  TResult when<TResult extends Object?>({
    required TResult Function(String message, int? statusCode) network,
    required TResult Function(String message) unauthorized,
    required TResult Function(String message, int? statusCode) serverError,
    required TResult Function(String message) timeout,
    required TResult Function(String message) unknown,
  }) {
    return timeout(message);
  }

  @override
  @optionalTypeArgs
  TResult? whenOrNull<TResult extends Object?>({
    TResult? Function(String message, int? statusCode)? network,
    TResult? Function(String message)? unauthorized,
    TResult? Function(String message, int? statusCode)? serverError,
    TResult? Function(String message)? timeout,
    TResult? Function(String message)? unknown,
  }) {
    return timeout?.call(message);
  }

  @override
  @optionalTypeArgs
  TResult maybeWhen<TResult extends Object?>({
    TResult Function(String message, int? statusCode)? network,
    TResult Function(String message)? unauthorized,
    TResult Function(String message, int? statusCode)? serverError,
    TResult Function(String message)? timeout,
    TResult Function(String message)? unknown,
    required TResult orElse(),
  }) {
    if (timeout != null) {
      return timeout(message);
    }
    return orElse();
  }

  @override
  @optionalTypeArgs
  TResult map<TResult extends Object?>({
    required TResult Function(NetworkException value) network,
    required TResult Function(UnauthorizedException value) unauthorized,
    required TResult Function(ServerException value) serverError,
    required TResult Function(TimeoutException value) timeout,
    required TResult Function(UnknownException value) unknown,
  }) {
    return timeout(this);
  }

  @override
  @optionalTypeArgs
  TResult? mapOrNull<TResult extends Object?>({
    TResult? Function(NetworkException value)? network,
    TResult? Function(UnauthorizedException value)? unauthorized,
    TResult? Function(ServerException value)? serverError,
    TResult? Function(TimeoutException value)? timeout,
    TResult? Function(UnknownException value)? unknown,
  }) {
    return timeout?.call(this);
  }

  @override
  @optionalTypeArgs
  TResult maybeMap<TResult extends Object?>({
    TResult Function(NetworkException value)? network,
    TResult Function(UnauthorizedException value)? unauthorized,
    TResult Function(ServerException value)? serverError,
    TResult Function(TimeoutException value)? timeout,
    TResult Function(UnknownException value)? unknown,
    required TResult orElse(),
  }) {
    if (timeout != null) {
      return timeout(this);
    }
    return orElse();
  }
}

abstract class TimeoutException implements ApiException {
  const factory TimeoutException({final String message}) =
      _$TimeoutExceptionImpl;

  @override
  String get message;
  @override
  @JsonKey(ignore: true)
  _$$TimeoutExceptionImplCopyWith<_$TimeoutExceptionImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class _$$UnknownExceptionImplCopyWith<$Res>
    implements $ApiExceptionCopyWith<$Res> {
  factory _$$UnknownExceptionImplCopyWith(_$UnknownExceptionImpl value,
          $Res Function(_$UnknownExceptionImpl) then) =
      __$$UnknownExceptionImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String message});
}

/// @nodoc
class __$$UnknownExceptionImplCopyWithImpl<$Res>
    extends _$ApiExceptionCopyWithImpl<$Res, _$UnknownExceptionImpl>
    implements _$$UnknownExceptionImplCopyWith<$Res> {
  __$$UnknownExceptionImplCopyWithImpl(_$UnknownExceptionImpl _value,
      $Res Function(_$UnknownExceptionImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? message = null,
  }) {
    return _then(_$UnknownExceptionImpl(
      message: null == message
          ? _value.message
          : message // ignore: cast_nullable_to_non_nullable
              as String,
    ));
  }
}

/// @nodoc

class _$UnknownExceptionImpl implements UnknownException {
  const _$UnknownExceptionImpl({required this.message});

  @override
  final String message;

  @override
  String toString() {
    return 'ApiException.unknown(message: $message)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$UnknownExceptionImpl &&
            (identical(other.message, message) || other.message == message));
  }

  @override
  int get hashCode => Object.hash(runtimeType, message);

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$UnknownExceptionImplCopyWith<_$UnknownExceptionImpl> get copyWith =>
      __$$UnknownExceptionImplCopyWithImpl<_$UnknownExceptionImpl>(
          this, _$identity);

  @override
  @optionalTypeArgs
  TResult when<TResult extends Object?>({
    required TResult Function(String message, int? statusCode) network,
    required TResult Function(String message) unauthorized,
    required TResult Function(String message, int? statusCode) serverError,
    required TResult Function(String message) timeout,
    required TResult Function(String message) unknown,
  }) {
    return unknown(message);
  }

  @override
  @optionalTypeArgs
  TResult? whenOrNull<TResult extends Object?>({
    TResult? Function(String message, int? statusCode)? network,
    TResult? Function(String message)? unauthorized,
    TResult? Function(String message, int? statusCode)? serverError,
    TResult? Function(String message)? timeout,
    TResult? Function(String message)? unknown,
  }) {
    return unknown?.call(message);
  }

  @override
  @optionalTypeArgs
  TResult maybeWhen<TResult extends Object?>({
    TResult Function(String message, int? statusCode)? network,
    TResult Function(String message)? unauthorized,
    TResult Function(String message, int? statusCode)? serverError,
    TResult Function(String message)? timeout,
    TResult Function(String message)? unknown,
    required TResult orElse(),
  }) {
    if (unknown != null) {
      return unknown(message);
    }
    return orElse();
  }

  @override
  @optionalTypeArgs
  TResult map<TResult extends Object?>({
    required TResult Function(NetworkException value) network,
    required TResult Function(UnauthorizedException value) unauthorized,
    required TResult Function(ServerException value) serverError,
    required TResult Function(TimeoutException value) timeout,
    required TResult Function(UnknownException value) unknown,
  }) {
    return unknown(this);
  }

  @override
  @optionalTypeArgs
  TResult? mapOrNull<TResult extends Object?>({
    TResult? Function(NetworkException value)? network,
    TResult? Function(UnauthorizedException value)? unauthorized,
    TResult? Function(ServerException value)? serverError,
    TResult? Function(TimeoutException value)? timeout,
    TResult? Function(UnknownException value)? unknown,
  }) {
    return unknown?.call(this);
  }

  @override
  @optionalTypeArgs
  TResult maybeMap<TResult extends Object?>({
    TResult Function(NetworkException value)? network,
    TResult Function(UnauthorizedException value)? unauthorized,
    TResult Function(ServerException value)? serverError,
    TResult Function(TimeoutException value)? timeout,
    TResult Function(UnknownException value)? unknown,
    required TResult orElse(),
  }) {
    if (unknown != null) {
      return unknown(this);
    }
    return orElse();
  }
}

abstract class UnknownException implements ApiException {
  const factory UnknownException({required final String message}) =
      _$UnknownExceptionImpl;

  @override
  String get message;
  @override
  @JsonKey(ignore: true)
  _$$UnknownExceptionImplCopyWith<_$UnknownExceptionImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
