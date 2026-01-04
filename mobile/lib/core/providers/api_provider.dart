import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:stockerpro/core/api/api_client.dart';
import 'package:stockerpro/core/services/watchlist_service.dart';

part 'api_provider.g.dart';

@Riverpod(keepAlive: true)
ApiClient apiClient(ApiClientRef ref) => ApiClient();

@Riverpod(keepAlive: true)
WatchlistService watchlistService(WatchlistServiceRef ref) {
  return WatchlistService(ref.watch(apiClientProvider));
}
