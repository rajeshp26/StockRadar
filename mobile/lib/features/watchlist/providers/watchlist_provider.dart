import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:stockerpro/core/models/listing_identity.dart';
import 'package:stockerpro/core/models/watchlist.dart';
import 'package:stockerpro/core/providers/api_provider.dart';

part 'watchlist_provider.g.dart';

@riverpod
class WatchlistNotifier extends _$WatchlistNotifier {
  @override
  Future<Watchlist?> build() async {
    final service = ref.read(watchlistServiceProvider);
    final result = await service.getDefaultWatchlist();
    return result.when(success: (data) => data, failure: (err) => throw err);
  }

  Future<void> addStock(
    String symbol, {
    ListingIdentity? listing,
  }) async {
    final service = ref.read(watchlistServiceProvider);
    final watchlistId = await future.then((watchlist) => watchlist?.id);
    final result = await service.addStock(
      symbol,
      listing: listing,
      watchlistId: watchlistId,
    );
    result.when(success: (_) => ref.invalidateSelf(), failure: (err) => throw err);
  }
}
