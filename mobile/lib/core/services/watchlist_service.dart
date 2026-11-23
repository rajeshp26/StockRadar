import '../api/api_client.dart';
import '../api/api_result.dart';
import '../models/listing_identity.dart';
import '../models/watchlist.dart';

class WatchlistService {
  final ApiClient _apiClient;

  WatchlistService(this._apiClient);

  /// Retrieves the default watchlist for the authenticated user.
  /// Uses the type-safe [Watchlist] model.
  Future<ApiResult<Watchlist>> getDefaultWatchlist() async {
    return _apiClient.post(
      path: '/watchlists/default-with-items',
      parser: (data) => Watchlist.fromJson(data as Map<String, dynamic>),
    );
  }

  /// Adds a listing to the user's watchlist.
  ///
  /// The backend contract (API-001) expects `symbol`; the legacy `ticker` key was
  /// silently ignored, so this call never worked. When a [listing] is supplied its
  /// full identity is posted so the selected exchange is persisted, not guessed.
  Future<ApiResult<void>> addStock(
    String symbol, {
    ListingIdentity? listing,
    int? watchlistId,
  }) async {
    final payload = <String, dynamic>{
      'watchlist_id': watchlistId ?? 1,
      'symbol': listing?.symbol ?? symbol,
      if (listing != null) ...listing.toJson(),
    };
    return _apiClient.post(
      path: '/watchlist-items',
      data: payload,
      parser: (_) => null,
    );
  }
}
