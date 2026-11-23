/// A tradable listing on the security master.
///
/// `symbol` alone is not an instrument: META / NMS / COMMON and META / NEO / CDR
/// are different listings with different quotes. The exchange/selection must be
/// carried from search through add to quote.
class ListingIdentity {
  final int securityId;
  final String symbol;
  final String exchange;
  final String kind;
  final String currency;
  final String providerSymbol;

  const ListingIdentity({
    required this.securityId,
    required this.symbol,
    required this.exchange,
    required this.kind,
    required this.currency,
    required this.providerSymbol,
  });

  Map<String, dynamic> toJson() => {
        'security_id': securityId,
        'symbol': symbol,
        'exchange': exchange,
        'kind': kind,
        'currency': currency,
        'provider_symbol': providerSymbol,
      };

  factory ListingIdentity.fromJson(Map<String, dynamic> json) => ListingIdentity(
        securityId: json['security_id'] as int,
        symbol: json['symbol'] as String,
        exchange: json['exchange'] as String,
        kind: json['kind'] as String,
        currency: json['currency'] as String,
        providerSymbol: json['provider_symbol'] as String,
      );
}
