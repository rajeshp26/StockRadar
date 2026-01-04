import 'package:freezed_annotation/freezed_annotation.dart';

part 'watchlist.freezed.dart';
part 'watchlist.g.dart';

@freezed
class Watchlist with _$Watchlist {
  const factory Watchlist({
    required int id,
    @JsonKey(name: 'watchlist_name') required String name,
    @JsonKey(name: 'is_default') required bool isDefault,
    @Default([]) List<WatchlistItem> items,
  }) = _Watchlist;

  factory Watchlist.fromJson(Map<String, dynamic> json) =>
      _$WatchlistFromJson(json);
}

@freezed
class WatchlistItem with _$WatchlistItem {
  const factory WatchlistItem({
    @JsonKey(name: 'watchlist_item_id') required int id,
    @JsonKey(name: 'ticker_symbol') required String symbol,
    @JsonKey(name: 'company_name') required String companyName,
    @JsonKey(name: 'target_buy') double? targetBuy,
    @JsonKey(name: 'target_sell') double? targetSell,
  }) = _WatchlistItem;

  factory WatchlistItem.fromJson(Map<String, dynamic> json) =>
      _$WatchlistItemFromJson(json);
}
