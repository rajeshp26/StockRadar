import 'package:flutter/material.dart';
import 'package:stockerpro/core/models/watchlist.dart';

/// [StockCard] displays individual stock data.
/// Uses package-based imports for architectural stability.
class StockCard extends StatelessWidget {
  final WatchlistItem item;

  const StockCard({super.key, required this.item});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: CircleAvatar(
          backgroundColor: Theme.of(context).colorScheme.primaryContainer,
          child: Text(
            item.symbol[0],
            style: TextStyle(color: Theme.of(context).colorScheme.onPrimaryContainer),
          ),
        ),
        title: Text(
          item.symbol,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
        ),
        subtitle: Text(item.companyName),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (item.targetBuy != null)
              Text(
                'Buy: \$${item.targetBuy!.toStringAsFixed(2)}',
                style: const TextStyle(color: Colors.green, fontSize: 12),
              ),
            if (item.targetSell != null)
              Text(
                'Sell: \$${item.targetSell!.toStringAsFixed(2)}',
                style: const TextStyle(color: Colors.red, fontSize: 12),
              ),
          ],
        ),
      ),
    );
  }
}
