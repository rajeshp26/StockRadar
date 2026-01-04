import 'dart:ui';
import 'package:flutter/material.dart';

// StockerPro Mobile Preview for Zapp.run
// Copy this code into a new project on Zapp.run to see the UI.

void main() {
  runApp(const MaterialApp(
    debugShowCheckedModeBanner: false,
    home: WatchlistScreenPreview(),
  ));
}

class WatchlistScreenPreview extends StatelessWidget {
  const WatchlistScreenPreview({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        title: const Text('StockerPro Preview', style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(icon: const Icon(Icons.add, color: Colors.white), onPressed: () {}),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: const [
          StockCardPreview(symbol: 'AAPL', name: 'Apple Inc.', price: '\$182.40', buy: '\$150.00'),
          StockCardPreview(symbol: 'NVDA', name: 'Nvidia Corp.', price: '\$892.12', buy: '\$750.00'),
          StockCardPreview(symbol: 'TSLA', name: 'Tesla Inc.', price: '\$176.54', buy: '\$160.00'),
        ],
      ),
    );
  }
}

class StockCardPreview extends StatelessWidget {
  final String symbol;
  final String name;
  final String price;
  final String buy;

  const StockCardPreview({
    super.key,
    required this.symbol,
    required this.name,
    required this.price,
    required this.buy,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.white.withOpacity(0.1)),
            ),
            child: Row(
              children: [
                CircleAvatar(
                  backgroundColor: Colors.indigo.withOpacity(0.3),
                  child: Text(symbol[0], style: const TextStyle(color: Colors.white)),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(symbol, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                      Text(name, style: const TextStyle(color: Colors.grey, fontSize: 14)),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(price, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                    Text('Buy: $buy', style: const TextStyle(color: Colors.green, fontSize: 12)),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
