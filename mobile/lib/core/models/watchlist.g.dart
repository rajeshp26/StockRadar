// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'watchlist.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$WatchlistImpl _$$WatchlistImplFromJson(Map<String, dynamic> json) =>
    _$WatchlistImpl(
      id: (json['id'] as num).toInt(),
      name: json['watchlist_name'] as String,
      isDefault: json['is_default'] as bool,
      items: (json['items'] as List<dynamic>?)
              ?.map((e) => WatchlistItem.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
    );

Map<String, dynamic> _$$WatchlistImplToJson(_$WatchlistImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'watchlist_name': instance.name,
      'is_default': instance.isDefault,
      'items': instance.items,
    };

_$WatchlistItemImpl _$$WatchlistItemImplFromJson(Map<String, dynamic> json) =>
    _$WatchlistItemImpl(
      id: (json['watchlist_item_id'] as num).toInt(),
      symbol: json['ticker_symbol'] as String,
      companyName: json['company_name'] as String,
      targetBuy: (json['target_buy'] as num?)?.toDouble(),
      targetSell: (json['target_sell'] as num?)?.toDouble(),
    );

Map<String, dynamic> _$$WatchlistItemImplToJson(_$WatchlistItemImpl instance) =>
    <String, dynamic>{
      'watchlist_item_id': instance.id,
      'ticker_symbol': instance.symbol,
      'company_name': instance.companyName,
      'target_buy': instance.targetBuy,
      'target_sell': instance.targetSell,
    };
