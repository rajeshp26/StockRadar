// GENERATED from api-001.openapi.yaml — do not edit by hand.

export interface SecurityListing {
  security_id: number;
  symbol: string;
  exchange: string;
  kind: "COMMON" | "CDR" | "ETF" | "FUND" | "INDEX";
  currency: string;
  provider_symbol: string;
  name?: string;
}

export interface SearchListingsResponse {
  results: unknown[];
}

export interface AddWatchlistItemRequest {
  watchlist_id: number;
  security_id: number;
  symbol: string;
  exchange: string;
  kind: "COMMON" | "CDR" | "ETF" | "FUND" | "INDEX";
  currency: string;
  provider_symbol: string;
  target_buy?: number;
  target_sell?: number;
}

export interface WatchlistItemAdded {
  watchlist_item_id: number;
  watchlist_id: number;
  security_id: number;
  symbol: string;
  exchange: string;
  kind: "COMMON" | "CDR" | "ETF" | "FUND" | "INDEX";
  currency: string;
  provider_symbol: string;
  target_buy?: number;
  target_sell?: number;
  price?: number;
  lastUpdated?: string;
}

export interface AddWatchlistItemResponse {
  watchlist_item: Record<string, unknown>;
  financials_loading: boolean;
  is_new_stock: boolean;
}

export interface QuoteSnapshot {
  security_id: number;
  symbol: string;
  exchange: string;
  kind: "COMMON" | "CDR" | "ETF" | "FUND" | "INDEX";
  currency: string;
  provider_symbol: string;
  price: number;
  change?: number;
  changePercent?: number;
  lastUpdated?: string;
  stale: boolean;
}

export interface QuoteEvent {
  type: "price_update";
  security_id: number;
  symbol: string;
  exchange: string;
  kind: "COMMON" | "CDR" | "ETF" | "FUND" | "INDEX";
  currency: string;
  provider_symbol: string;
  price: number;
  change?: number;
  changePercent?: number;
  lastUpdated: string;
  isStale: boolean;
  source?: string;
}

export interface ValidationError {
  code: string;
  message: string;
  fields?: unknown[];
}

