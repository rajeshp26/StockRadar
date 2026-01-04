// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'watchlist.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

Watchlist _$WatchlistFromJson(Map<String, dynamic> json) {
  return _Watchlist.fromJson(json);
}

/// @nodoc
mixin _$Watchlist {
  int get id => throw _privateConstructorUsedError;
  @JsonKey(name: 'watchlist_name')
  String get name => throw _privateConstructorUsedError;
  @JsonKey(name: 'is_default')
  bool get isDefault => throw _privateConstructorUsedError;
  List<WatchlistItem> get items => throw _privateConstructorUsedError;

  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;
  @JsonKey(ignore: true)
  $WatchlistCopyWith<Watchlist> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $WatchlistCopyWith<$Res> {
  factory $WatchlistCopyWith(Watchlist value, $Res Function(Watchlist) then) =
      _$WatchlistCopyWithImpl<$Res, Watchlist>;
  @useResult
  $Res call(
      {int id,
      @JsonKey(name: 'watchlist_name') String name,
      @JsonKey(name: 'is_default') bool isDefault,
      List<WatchlistItem> items});
}

/// @nodoc
class _$WatchlistCopyWithImpl<$Res, $Val extends Watchlist>
    implements $WatchlistCopyWith<$Res> {
  _$WatchlistCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? name = null,
    Object? isDefault = null,
    Object? items = null,
  }) {
    return _then(_value.copyWith(
      id: null == id
          ? _value.id
          : id // ignore: cast_nullable_to_non_nullable
              as int,
      name: null == name
          ? _value.name
          : name // ignore: cast_nullable_to_non_nullable
              as String,
      isDefault: null == isDefault
          ? _value.isDefault
          : isDefault // ignore: cast_nullable_to_non_nullable
              as bool,
      items: null == items
          ? _value.items
          : items // ignore: cast_nullable_to_non_nullable
              as List<WatchlistItem>,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$WatchlistImplCopyWith<$Res>
    implements $WatchlistCopyWith<$Res> {
  factory _$$WatchlistImplCopyWith(
          _$WatchlistImpl value, $Res Function(_$WatchlistImpl) then) =
      __$$WatchlistImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call(
      {int id,
      @JsonKey(name: 'watchlist_name') String name,
      @JsonKey(name: 'is_default') bool isDefault,
      List<WatchlistItem> items});
}

/// @nodoc
class __$$WatchlistImplCopyWithImpl<$Res>
    extends _$WatchlistCopyWithImpl<$Res, _$WatchlistImpl>
    implements _$$WatchlistImplCopyWith<$Res> {
  __$$WatchlistImplCopyWithImpl(
      _$WatchlistImpl _value, $Res Function(_$WatchlistImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? name = null,
    Object? isDefault = null,
    Object? items = null,
  }) {
    return _then(_$WatchlistImpl(
      id: null == id
          ? _value.id
          : id // ignore: cast_nullable_to_non_nullable
              as int,
      name: null == name
          ? _value.name
          : name // ignore: cast_nullable_to_non_nullable
              as String,
      isDefault: null == isDefault
          ? _value.isDefault
          : isDefault // ignore: cast_nullable_to_non_nullable
              as bool,
      items: null == items
          ? _value._items
          : items // ignore: cast_nullable_to_non_nullable
              as List<WatchlistItem>,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$WatchlistImpl implements _Watchlist {
  const _$WatchlistImpl(
      {required this.id,
      @JsonKey(name: 'watchlist_name') required this.name,
      @JsonKey(name: 'is_default') required this.isDefault,
      final List<WatchlistItem> items = const []})
      : _items = items;

  factory _$WatchlistImpl.fromJson(Map<String, dynamic> json) =>
      _$$WatchlistImplFromJson(json);

  @override
  final int id;
  @override
  @JsonKey(name: 'watchlist_name')
  final String name;
  @override
  @JsonKey(name: 'is_default')
  final bool isDefault;
  final List<WatchlistItem> _items;
  @override
  @JsonKey()
  List<WatchlistItem> get items {
    if (_items is EqualUnmodifiableListView) return _items;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_items);
  }

  @override
  String toString() {
    return 'Watchlist(id: $id, name: $name, isDefault: $isDefault, items: $items)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$WatchlistImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.name, name) || other.name == name) &&
            (identical(other.isDefault, isDefault) ||
                other.isDefault == isDefault) &&
            const DeepCollectionEquality().equals(other._items, _items));
  }

  @JsonKey(ignore: true)
  @override
  int get hashCode => Object.hash(runtimeType, id, name, isDefault,
      const DeepCollectionEquality().hash(_items));

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$WatchlistImplCopyWith<_$WatchlistImpl> get copyWith =>
      __$$WatchlistImplCopyWithImpl<_$WatchlistImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$WatchlistImplToJson(
      this,
    );
  }
}

abstract class _Watchlist implements Watchlist {
  const factory _Watchlist(
      {required final int id,
      @JsonKey(name: 'watchlist_name') required final String name,
      @JsonKey(name: 'is_default') required final bool isDefault,
      final List<WatchlistItem> items}) = _$WatchlistImpl;

  factory _Watchlist.fromJson(Map<String, dynamic> json) =
      _$WatchlistImpl.fromJson;

  @override
  int get id;
  @override
  @JsonKey(name: 'watchlist_name')
  String get name;
  @override
  @JsonKey(name: 'is_default')
  bool get isDefault;
  @override
  List<WatchlistItem> get items;
  @override
  @JsonKey(ignore: true)
  _$$WatchlistImplCopyWith<_$WatchlistImpl> get copyWith =>
      throw _privateConstructorUsedError;
}

WatchlistItem _$WatchlistItemFromJson(Map<String, dynamic> json) {
  return _WatchlistItem.fromJson(json);
}

/// @nodoc
mixin _$WatchlistItem {
  @JsonKey(name: 'watchlist_item_id')
  int get id => throw _privateConstructorUsedError;
  @JsonKey(name: 'ticker_symbol')
  String get symbol => throw _privateConstructorUsedError;
  @JsonKey(name: 'company_name')
  String get companyName => throw _privateConstructorUsedError;
  @JsonKey(name: 'target_buy')
  double? get targetBuy => throw _privateConstructorUsedError;
  @JsonKey(name: 'target_sell')
  double? get targetSell => throw _privateConstructorUsedError;

  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;
  @JsonKey(ignore: true)
  $WatchlistItemCopyWith<WatchlistItem> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $WatchlistItemCopyWith<$Res> {
  factory $WatchlistItemCopyWith(
          WatchlistItem value, $Res Function(WatchlistItem) then) =
      _$WatchlistItemCopyWithImpl<$Res, WatchlistItem>;
  @useResult
  $Res call(
      {@JsonKey(name: 'watchlist_item_id') int id,
      @JsonKey(name: 'ticker_symbol') String symbol,
      @JsonKey(name: 'company_name') String companyName,
      @JsonKey(name: 'target_buy') double? targetBuy,
      @JsonKey(name: 'target_sell') double? targetSell});
}

/// @nodoc
class _$WatchlistItemCopyWithImpl<$Res, $Val extends WatchlistItem>
    implements $WatchlistItemCopyWith<$Res> {
  _$WatchlistItemCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? symbol = null,
    Object? companyName = null,
    Object? targetBuy = freezed,
    Object? targetSell = freezed,
  }) {
    return _then(_value.copyWith(
      id: null == id
          ? _value.id
          : id // ignore: cast_nullable_to_non_nullable
              as int,
      symbol: null == symbol
          ? _value.symbol
          : symbol // ignore: cast_nullable_to_non_nullable
              as String,
      companyName: null == companyName
          ? _value.companyName
          : companyName // ignore: cast_nullable_to_non_nullable
              as String,
      targetBuy: freezed == targetBuy
          ? _value.targetBuy
          : targetBuy // ignore: cast_nullable_to_non_nullable
              as double?,
      targetSell: freezed == targetSell
          ? _value.targetSell
          : targetSell // ignore: cast_nullable_to_non_nullable
              as double?,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$WatchlistItemImplCopyWith<$Res>
    implements $WatchlistItemCopyWith<$Res> {
  factory _$$WatchlistItemImplCopyWith(
          _$WatchlistItemImpl value, $Res Function(_$WatchlistItemImpl) then) =
      __$$WatchlistItemImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call(
      {@JsonKey(name: 'watchlist_item_id') int id,
      @JsonKey(name: 'ticker_symbol') String symbol,
      @JsonKey(name: 'company_name') String companyName,
      @JsonKey(name: 'target_buy') double? targetBuy,
      @JsonKey(name: 'target_sell') double? targetSell});
}

/// @nodoc
class __$$WatchlistItemImplCopyWithImpl<$Res>
    extends _$WatchlistItemCopyWithImpl<$Res, _$WatchlistItemImpl>
    implements _$$WatchlistItemImplCopyWith<$Res> {
  __$$WatchlistItemImplCopyWithImpl(
      _$WatchlistItemImpl _value, $Res Function(_$WatchlistItemImpl) _then)
      : super(_value, _then);

  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? symbol = null,
    Object? companyName = null,
    Object? targetBuy = freezed,
    Object? targetSell = freezed,
  }) {
    return _then(_$WatchlistItemImpl(
      id: null == id
          ? _value.id
          : id // ignore: cast_nullable_to_non_nullable
              as int,
      symbol: null == symbol
          ? _value.symbol
          : symbol // ignore: cast_nullable_to_non_nullable
              as String,
      companyName: null == companyName
          ? _value.companyName
          : companyName // ignore: cast_nullable_to_non_nullable
              as String,
      targetBuy: freezed == targetBuy
          ? _value.targetBuy
          : targetBuy // ignore: cast_nullable_to_non_nullable
              as double?,
      targetSell: freezed == targetSell
          ? _value.targetSell
          : targetSell // ignore: cast_nullable_to_non_nullable
              as double?,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$WatchlistItemImpl implements _WatchlistItem {
  const _$WatchlistItemImpl(
      {@JsonKey(name: 'watchlist_item_id') required this.id,
      @JsonKey(name: 'ticker_symbol') required this.symbol,
      @JsonKey(name: 'company_name') required this.companyName,
      @JsonKey(name: 'target_buy') this.targetBuy,
      @JsonKey(name: 'target_sell') this.targetSell});

  factory _$WatchlistItemImpl.fromJson(Map<String, dynamic> json) =>
      _$$WatchlistItemImplFromJson(json);

  @override
  @JsonKey(name: 'watchlist_item_id')
  final int id;
  @override
  @JsonKey(name: 'ticker_symbol')
  final String symbol;
  @override
  @JsonKey(name: 'company_name')
  final String companyName;
  @override
  @JsonKey(name: 'target_buy')
  final double? targetBuy;
  @override
  @JsonKey(name: 'target_sell')
  final double? targetSell;

  @override
  String toString() {
    return 'WatchlistItem(id: $id, symbol: $symbol, companyName: $companyName, targetBuy: $targetBuy, targetSell: $targetSell)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$WatchlistItemImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.symbol, symbol) || other.symbol == symbol) &&
            (identical(other.companyName, companyName) ||
                other.companyName == companyName) &&
            (identical(other.targetBuy, targetBuy) ||
                other.targetBuy == targetBuy) &&
            (identical(other.targetSell, targetSell) ||
                other.targetSell == targetSell));
  }

  @JsonKey(ignore: true)
  @override
  int get hashCode =>
      Object.hash(runtimeType, id, symbol, companyName, targetBuy, targetSell);

  @JsonKey(ignore: true)
  @override
  @pragma('vm:prefer-inline')
  _$$WatchlistItemImplCopyWith<_$WatchlistItemImpl> get copyWith =>
      __$$WatchlistItemImplCopyWithImpl<_$WatchlistItemImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$WatchlistItemImplToJson(
      this,
    );
  }
}

abstract class _WatchlistItem implements WatchlistItem {
  const factory _WatchlistItem(
          {@JsonKey(name: 'watchlist_item_id') required final int id,
          @JsonKey(name: 'ticker_symbol') required final String symbol,
          @JsonKey(name: 'company_name') required final String companyName,
          @JsonKey(name: 'target_buy') final double? targetBuy,
          @JsonKey(name: 'target_sell') final double? targetSell}) =
      _$WatchlistItemImpl;

  factory _WatchlistItem.fromJson(Map<String, dynamic> json) =
      _$WatchlistItemImpl.fromJson;

  @override
  @JsonKey(name: 'watchlist_item_id')
  int get id;
  @override
  @JsonKey(name: 'ticker_symbol')
  String get symbol;
  @override
  @JsonKey(name: 'company_name')
  String get companyName;
  @override
  @JsonKey(name: 'target_buy')
  double? get targetBuy;
  @override
  @JsonKey(name: 'target_sell')
  double? get targetSell;
  @override
  @JsonKey(ignore: true)
  _$$WatchlistItemImplCopyWith<_$WatchlistItemImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
