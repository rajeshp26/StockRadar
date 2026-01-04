import '../api/api_client.dart';
import '../api/api_result.dart';
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

  /// Adds a ticker to the user's default watchlist.
  /// Triggers the background sync process on the Python backend.
  Future<ApiResult<void>> addStock(String ticker) async {
    return _apiClient.post(
      path: '/watchlist-items',
      data: {'ticker': ticker},
      parser: (_) => null, // We only care about success/failure for this call
    );
  }
}
