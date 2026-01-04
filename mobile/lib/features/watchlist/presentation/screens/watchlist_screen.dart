import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:stockerpro/features/watchlist/providers/watchlist_provider.dart';
import 'package:stockerpro/features/watchlist/presentation/widgets/stock_card.dart';
import 'package:stockerpro/shared/widgets/watchlist_shimmer.dart';
import 'package:stockerpro/core/api/api_exception.dart';

class WatchlistScreen extends ConsumerWidget {
  const WatchlistScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final watchlistAsync = ref.watch(watchlistNotifierProvider);

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        title: const Text('StockerPro'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.add_chart_outlined),
            onPressed: () => _showAddStockDialog(context, ref),
          ),
        ],
      ),
      body: watchlistAsync.when(
        data: (watchlist) {
          if (watchlist == null || watchlist.items.isEmpty) {
            return const Center(child: Text('Empty Watchlist'));
          }
          return RefreshIndicator(
            onRefresh: () => ref.refresh(watchlistNotifierProvider.future),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: watchlist.items.length,
              itemBuilder: (context, index) => StockCard(item: watchlist.items[index]),
            ),
          );
        },
        loading: () => const WatchlistShimmer(),
        error: (err, stack) => Center(child: Text('Error: $err')),
      ),
    );
  }

  // Dialog code remains largely the same but uses hardened logic
  void _showAddStockDialog(BuildContext context, WidgetRef ref) {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add Ticker'),
        content: TextField(controller: controller, textCapitalization: TextCapitalization.characters),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () async {
              final ticker = controller.text.trim().toUpperCase();
              if (ticker.isNotEmpty) {
                Navigator.pop(context);
                await ref.read(watchlistNotifierProvider.notifier).addStock(ticker);
              }
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
  }
}
