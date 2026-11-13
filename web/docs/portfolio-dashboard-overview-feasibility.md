# Portfolio Dashboard Overview Tab — Feasibility Analysis

## 1. Current State

The Overview tab (`web/src/features/portfolio/components/OverviewTab.tsx` — 93 lines) currently displays:
- **4 summary cards**: Total Value, Total Gain/Loss ($), Gain/Loss (%), Total Dividends
- **Portfolio performance chart**: Recharts `ComposedChart` (portfolio value, net deposits, benchmark overlays)

Data flows from `GET /portfolio/overview` → `PortfolioOverview` type.

**Key architectural observations:**
- `PortfolioTabShell` (the shell component that wraps all tabs) already mounts `AccountChipStrip` at the shell level (line 96), not inside `OverviewTab`. This makes sense as the account filter is global.
- `OverviewTab` receives `accountIds` prop but **does not pass it** to `usePortfolioOverview()` — the hook always fetches unfiltered data.
- `PortfolioService.getPortfolioOverview()` does not accept any `accountId` parameter — always calls `GET /portfolio/overview` without query params.

---

## 2. Desired Features vs. Current Availability

### 2.1 Account-wise Breakdown of Value, Gain/Loss

| Aspect | Status |
|--------|--------|
| Data exists in API? | **Yes** — `PortfolioOverview.account_breakdown[]` already returns per-account `gain_loss`, `gain_loss_pct`, `total_value`, `total_cost` |
| Frontend renders it? | **Partially** — `PortfolioOverview.tsx` (standalone page, 214 lines, used at `/portfolio` route) renders account breakdown with per-account rows showing type badge, name, brokerage, positions, value, gain/loss. However, `OverviewTab.tsx` (tab inside `PortfolioTabShell`) does NOT render it. |
| Account filter exists? | **Yes** — `AccountChipStrip` in `PortfolioTabShell` (not inside `OverviewTab`), `usePortfolioNavigation` supports `?account=1` query param. Backend `GET /portfolio/overview?account_id=X` already supports per-account filtering (line 480). |
| **Effort**: Low–Medium | Service method and hook must be updated to accept `accountIds`. Account breakdown rendering needed in `OverviewTab`. Backend is fully ready. |

### 2.2 Top Movers (10–15 Positions: Gainers & Losers)

| Aspect | Status |
|--------|--------|
| Data exists? | **Yes, computable** — `useAllHoldings()` returns `Holding[]` with `unrealized_gain_loss` and `unrealized_gain_loss_pct` per holding. Sort by `gain_loss_pct` descending for gainers, ascending for losers. |
| Existing component? | **No** — No "top movers" component exists anywhere. Must be built from scratch. |
| Real-time prices? | **Yes** — `GlobalSSEProvider` pushes live prices into React Query cache via `queryClient.setQueryData(QK.price(symbol))`. Holdings update when SSE fires, but the hook refetch interval is 2 min stale time (not instant). |
| **Effort**: Low–Medium | Build a `TopMovers` component that consumes `useAllHoldings()`, sorts by `unrealized_gain_loss_pct`, renders top N gainers/losers. No backend changes needed. |

### 2.3 Mini Sparkline (7-Day or 30-Day Price History per Holding)

| Aspect | Status |
|--------|--------|
| Historical price data exists? | **Yes, on backend** — `price_history` table stores daily OHLCV data. `analysis_repository.get_price_history_range()` and `risk_repository.get_price_history_range()` already query it. `defeat_beta_provider` can fetch price history via SDK `Ticker.price()`. `PriceDataProvider` (`shared/price_data_provider.py`) exists but uses **yfinance directly** (not the primary provider chain) for bulk price fetches. |
| Frontend API to fetch it? | **No** — No frontend service method or React Query hook exists to fetch individual stock price history. A new API endpoint (e.g., `GET /stocks/{symbol}/price-history?days=7`) and a new service method + hook are required. |
| SVG sparkline component exists? | **No** — The document previously referenced `DividendSparkline` in `dividend-panel.tsx`, but **no such file or component exists** in the codebase. A sparkline component must be built from scratch (using Recharts or a lightweight SVG approach). |
| **Effort**: Medium–High | Need: (1) new backend endpoint with `price_history` DB query, (2) frontend service method, (3) React Query hook, (4) `PriceSparkline` component built from scratch. No existing sparkline to adapt. |

### 2.4 Alerts or News

| Aspect | Alerts | News |
|--------|--------|------|
| Data exists? | **No** — No alerts table, no alert CRUD, no notification system anywhere in the codebase. | **No** — No news API integration, no news table, no news component. |
| Can it be added? | **Yes** — Requires new DB table (`alerts`), backend CRUD API, frontend service, and a notification delivery mechanism (toast, email, or in-app). Could use existing SSE for real-time delivery. | **Yes** — Integrate a news API (Finnhub, NewsAPI, etc.) via a new backend endpoint. Frontend component to display headlines. |
| **Effort**: High (alerts) / Medium (news) | Alerts is a full feature (schema, CRUD, triggers, UI, delivery). News depends on third-party API integration and cost. |

---

## 3. Data Flow Summary for Enhanced Overview Tab

```
PortfolioTabShell (current container — line 117)
  ├── Header buttons (Add Trade, Import CSV)
  ├── AccountChipStrip (existing — global account filter at shell level)
  ├── TabBar (existing)
  │
  └── OverviewTab (with account filter)
        ├── Summary Cards (existing, 4 cards; expandable to add accounts_count, holdings_count)
        ├── Account Breakdown Cards (new — per-account value, gain/loss, %)
        ├── Top Movers (new) — Gainers & Losers sorted from useAllHoldings()
        │     └── Mini Sparkline (new) — 7d/30d price history per holding
        ├── Alerts/News Feed (new) — feed of recent alerts or news headlines
        └── PortfolioPerformanceChart (existing)
```

---

## 4. Required Changes — Detailed Breakdown

### 4.1 Account Filter + Account Breakdown (P0)

#### Backend
- **None required** — `GET /portfolio/overview?account_id=X` (line 480) already supported.

#### Frontend Service (`portfolio.service.ts:138`)
- Update `getPortfolioOverview()` to accept optional `accountId?: number` parameter and pass it as `?account_id=` query param.

#### Frontend Hook (`usePortfolio.ts:36`)
- Update `usePortfolioOverview()` to accept optional `accountIds?: number[]` and:
  - Derive query key including account IDs
  - Pass the first `accountId` to the service method

#### Frontend Component (`OverviewTab.tsx`)
- The `accountIds` prop is already accepted but currently unused for the query — wire it through to `usePortfolioOverview`.
- Render `AccountChipStrip` is **not needed** inside OverviewTab (it's already at shell level). Instead, read `selectedAccountId` via `usePortfolioNavigation`.
- Add account breakdown section rendering `AccountBreakdown[]` data.

### 4.2 Top Movers (P1)

#### Backend
- **None required**.

#### Frontend
- New `TopMovers` component accepting `holdings: Holding[]`.
- Sort by `unrealized_gain_loss_pct`: top 5–7 gainers (desc), top 5–7 losers (asc).
- Visual: list/rows with symbol, company name, gain/loss %, current price, and later sparkline.

### 4.3 Mini Sparkline (P1)

#### Backend
- New endpoint needed: `GET /stocks/{symbol}/price-history?days=7|30`
- Query `price_history` table by `company_id` (resolved from symbol) and `price_date` range.
- Option: enhance `analysis_repository` or create a new method in `financial_repository`.
- Consider using the existing `defeat_beta_provider` or `yfinance_provider` for price history if DB lacks data for a symbol.

#### Frontend Service
- New method: `getPriceHistory(symbol: string, days: number)` → `GET /stocks/{symbol}/price-history?days=7`

#### Frontend Hook
- New React Query hook: `usePriceHistory(symbol, days)` with ~1–2 min stale time, disabled when no symbol.

#### Frontend Component
- Build `PriceSparkline` from scratch (no existing sparkline to adapt). Options:
  - Recharts `AreaChart` (consistent with rest of app)
  - Lightweight inline SVG polyline

### 4.4 News Feed (P2 — Now Lower Effort)

**Key discovery: No third-party API needed.** Both existing providers already have news capabilities built in. This changes the cost/effort profile significantly.

#### Backend Options

| Option | Provider | Method | Data | Freshness | Effort |
|--------|----------|--------|------|-----------|--------|
| **A** (Recommended) | `defeatbeta_api` | `Ticker.news()` → `News` object wrapping `pd.DataFrame` | Full articles with highlights, paragraphs, publisher, type, link | Historical snapshot (HuggingFace Parquet dataset) | **Low** |
| **B** | `yfinance` | `Ticker.news` property → `list[dict]` | Headlines, summary, link, publisher, related tickers | **Live/real-time** from Yahoo Finance | **Low** |
| **C** | Combined | Primary: defeatbeta (historical depth + structured data), Fallback: yfinance (live freshness) | Full coverage | Both historical + live | **Medium** |

**Recommended: Option C (Combined)** — Add `get_news()` to `StockDataProvider` base interface, implement in `DefeatBetaProvider` (primary) and `YFinanceProvider` (fallback). The `NewsService` orchestrates which to call.

##### Architecture

```
GET /stocks/{symbol}/news?limit=10
  └── NewsService.get_news(symbol, limit)
        ├── (primary)  DefeatBetaProvider.get_news(symbol)    ← Ticker.news()
        │     └── Returns: pd.DataFrame [uuid, title, publisher, report_date, type, link, related_symbols, news[]]
        └── (fallback) YFinanceProvider.get_news(symbol, limit) ← Ticker.news
              └── Returns: list[dict] [id, title, summary, link, publisher, relatedTickers, type, ...]
```

##### Provider interface addition (`providers/base.py`)
```python
class StockDataProvider(ABC):
    @abstractmethod
    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]: ...
    @abstractmethod
    def get_stock_details(self, ticker_symbol: str) -> Optional[StockDetails]: ...

    # NEW:
    def get_news(self, ticker_symbol: str, limit: int = 10) -> Optional[List[NewsArticle]]:
        """Optional — not all providers implement news."""
        return None
```

With a standardized `NewsArticle` Pydantic model:
```python
class NewsArticle(BaseModel):
    uuid: Optional[str] = None
    title: str
    summary: Optional[str] = None
    publisher: str
    published_at: datetime
    article_type: str          # "STORY", "PRESS_RELEASE", etc.
    url: str
    related_symbols: List[str]
    content: Optional[List[dict]] = None  # [{highlight, paragraph}, ...]
```

##### DefeatBeta implementation (`defeat_beta_provider.py`)
```python
def get_news(self, ticker_symbol: str, limit: int = 10) -> Optional[List[NewsArticle]]:
    ticker = Ticker(ticker_symbol)
    news = ticker.news()                     # returns News object
    df = news.get_news_list()                # returns pd.DataFrame
    # Map df columns → NewsArticle list, apply limit, sort by report_date desc
    ...
```

##### YFinance implementation (`yfinance_provider.py`)
```python
def get_news(self, ticker_symbol: str, limit: int = 10) -> Optional[List[NewsArticle]]:
    tkr = yf.Ticker(self._resolve_symbol(ticker_symbol))
    raw = tkr.news                           # returns list[dict]
    # Map dict fields → NewsArticle list, filter ads, apply limit
    ...
```

#### Frontend
- New service method: `getStockNews(symbol: string, limit?: number)` → `GET /stocks/{symbol}/news`
- New React Query hook: `useStockNews(symbol, limit)` with 5 min stale time
- New `NewsFeed` component: scrollable list of news cards with title, publisher, timestamp, link

### 4.5 Alerts System (P2 — Higher Effort, No Provider Support)

**Neither defeatbeta_api nor yfinance nor any existing provider offers alert/notification functionality.** Alerts must be built entirely as a custom feature.

#### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Alert System                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  DB: alerts table                                    │
│  ┌──────────┬───────────┬───────────┬────────────┐  │
│  │ alert_id │ user_id   │ symbol    │ type       │  │
│  │ threshold│ direction │ is_active │ created_at │  │
│  │ triggered_at │                                  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                      │
│  Check Modes:                                        │
│  ├── Real-time: In SSE price_update handler          │
│  │     (every SSE event checks if any alert's       │
│  │      threshold is crossed for that symbol)        │
│  └── Scheduled: Background job runs every N minutes  │
│        (catch-up for any missed SSE events)          │
│                                                      │
│  Delivery:                                           │
│  ├── SSE event: `alert_triggered` pushed to client   │
│  └── In-app: Toast/notification via UI component     │
└─────────────────────────────────────────────────────┘
```

#### Alert Types

| Type | Trigger Condition | Example |
|------|------------------|---------|
| `price_above` | Current price ≥ threshold | "AAPL above $200" |
| `price_below` | Current price ≤ threshold | "AAPL below $180" |
| `gain_pct` | Daily gain % ≥ threshold | "Portfolio up 3% in a day" |
| `loss_pct` | Daily loss % ≥ threshold | "Portfolio down 5% in a day" |
| `volume_spike` | Volume > N× average | "NVDA volume 10× average" |

#### Database Schema (`alerts` table)
```sql
CREATE TABLE alerts (
    alert_id      BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(user_id),
    symbol        VARCHAR(10) NOT NULL,           -- NULL for portfolio-level alerts
    alert_type    VARCHAR(20) NOT NULL CHECK (alert_type IN (
                    'price_above','price_below','gain_pct','loss_pct','volume_spike'
                  )),
    direction     VARCHAR(4) CHECK (direction IN ('above','below')),  -- for price alerts
    threshold     DECIMAL(18,4) NOT NULL,
    is_active     BOOLEAN DEFAULT TRUE,
    last_triggered_at TIMESTAMPTZ,
    cooldown_minutes INT DEFAULT 60,              -- prevent re-trigger spam
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_user_active ON alerts(user_id, is_active) WHERE is_active = TRUE;
CREATE INDEX idx_alerts_symbol_active ON alerts(symbol, is_active) WHERE is_active = TRUE;
```

#### Backend Components

1. **AlertRepository** — CRUD for `alerts` table
2. **AlertService** — Business logic:
   - `create_alert()`, `update_alert()`, `delete_alert()`, `list_alerts()`
   - `check_alerts(symbol, current_price)` — evaluates all active alerts for a symbol
   - `check_portfolio_alerts(user_id, portfolio_stats)` — evaluates portfolio-level alerts
3. **Alert API routes**: `POST/GET/PATCH/DELETE /alerts`
4. **SSE Integration**: In the existing price SSE handler, after `queryClient.setQueryData(QK.price(symbol))`, call `AlertService.check_alerts(symbol, price)`. If triggered, push an `alert_triggered` SSE event.
5. **Scheduler** (optional): Periodic job to re-check alerts for any symbols that may have been missed.

#### Frontend Components

1. **AlertService** — CRUD API calls
2. **useAlerts** hook — React Query for listing/managing alerts
3. **AlertBanner** — In-page banner/toast triggered by SSE `alert_triggered` event
4. **AlertForm** — Create/Edit modal (symbol picker, type, threshold, direction)
5. **AlertList** — Manage active alerts with toggle/delete

#### Infrastructure reuse
- **SSE**: Already exists via `GlobalSSEProvider` listening on `/api/proxy/watchlists/stream`. Add a new event type `alert_triggered` to the same stream.
- **Auth**: Firebase JWT already verified; alerts are user-scoped via `user_id`.
- **No new third-party dependencies**: Everything built on existing Supabase + FastAPI + SSE.

---

## 5. Required Changes Summary

| Feature | Backend Changes | Frontend Changes | Priority |
|---------|----------------|------------------|----------|
| Account breakdown in Overview tab | **None** (full support at line 480) | Update `PortfolioService.getPortfolioOverview()` to accept `accountId`; update `usePortfolioOverview` hook to accept and pass `accountIds`; render account breakdown in `OverviewTab.tsx` | **P0** |
| Account filter through to overview API | **None** (already supported) | Wire `accountIds` prop → `usePortfolioOverview` → `PortfolioService.getPortfolioOverview(accountId)` | **P0** |
| Top Movers (gainers/losers) | **None** (data from `useAllHoldings()`) | New `TopMovers` component. Sort by `unrealized_gain_loss_pct`. | **P1** |
| Mini Sparkline | New endpoint: `GET /stocks/{symbol}/price-history?days=7\|30` querying `price_history` table | New service method, React Query hook, `PriceSparkline` component (build from scratch — no existing sparkline component) | **P1** |
| News Feed | Add `get_news()` to `StockDataProvider` + implement in `DefeatBetaProvider` and `YFinanceProvider`. New endpoint `GET /stocks/{symbol}/news`. **No third-party API needed.** | New service method, `useStockNews` hook, `NewsFeed` component | **P2** |
| Alerts Feed | New `alerts` DB table + CRUD API + SSE integration for real-time checks | New service, `useAlerts` hook, `AlertBanner`/`AlertForm`/`AlertList` components | **P2** |

---

## 6. Underlying Infrastructure Summary

### Provider Chain (fallback order)
```
PRIMARY:   DefeatBetaProvider (proprietary SDK, financial statements + price history + forecasts + NEWS)
  ├── Fallback 1: StockdexMacrotrendsProvider (Macrotrends scraper, 15+ years statements, no news)
  ├── Fallback 2: EdgarToolsProvider (SEC EDGAR XBRL, 10-K/10-Q filings only, no news)
  └── Fallback 3: YFinanceProvider (Yahoo Finance, prices/summary/forecasts/statements + LIVE NEWS)
```

### News Data Sources
| Provider | Method | Data Format | Freshness | Notes |
|----------|--------|-------------|-----------|-------|
| **DefeatBeta** (primary) | `Ticker.news()` → `News` object → `pd.DataFrame` | Columns: uuid, title, publisher, report_date, type, link, related_symbols, news[] (highlights + paragraphs) | Historical snapshot (HuggingFace Parquet dataset) | Full article body available; structured and queryable |
| **YFinance** (fallback) | `Ticker.news` property → `list[dict]` | Fields: id, title, summary, link, publisher, provider, relatedTickers, type, thumbnail | **Live/real-time** from Yahoo Finance `/xhr/ncp` endpoint | Headlines/summary only; ad-filtered; supports tabs: "news", "all", "press releases" |

**Strategy**: Primary = defeatbeta (structured historical data with full articles), Fallback = yfinance (live headlines for recent/current news). Combine both for maximum coverage.

### Alerts Data Sources
- **Neither** defeatbeta_api nor yfinance nor any other provider offers alert/notification functionality.
- Alerts must be built as a **custom feature** (see §4.5 for full architecture).
- The existing SSE infrastructure provides the real-time delivery channel; only the alert evaluation logic and DB storage are new.

### Price History Data Sources
- **Primary**: DefeatBeta SDK `Ticker.price()` / `Ticker.splits()`
- **Fallback**: YFinance via `yfinance_provider`
- **Bulk/utility**: `PriceDataProvider` (`shared/price_data_provider.py`) uses yfinance directly for multi-symbol fetch
- **DB**: `price_history` table already populated by scheduled `market_data_scheduler.py`

### Key Supabase Tables for Overview
| Table | Role |
|-------|------|
| `portfolio_accounts` | User accounts with type, brokerage, currency |
| `portfolio_holdings` | Current positions with quantity, cost basis |
| `portfolio_transactions` | Historical trades |
| `portfolio_performance` | Daily portfolio value snapshots |
| `portfolio_dividends` | Dividend payments per account |
| `current_market_data` | Latest prices for holdings |
| `price_history` | Daily OHLCV for sparklines |
| `companies` | Symbol → company_id resolution |

---

## 7. Feasibility Verdict

| Feature | Feasible? | Key Risk |
|---------|-----------|----------|
| Account-wise breakdown | ✅ **Immediate** (data ready) | Only the service method and hook need the `accountId` parameter wired through |
| Account filter dropdown | ✅ **Immediate** (components + backend ready) | Already partially wired — complete the data flow |
| Top movers (gainers/losers) | ✅ **Low effort** | No backend changes; pure frontend component from existing `useAllHoldings()` |
| Mini sparkline (7d/30d) | ⚠️ **Medium–High effort** | No existing sparkline component to adapt; need new backend endpoint + frontend hook + component from scratch |
| News | ✅ **Low effort** | Both existing providers (defeatbeta + yfinance) have news built in. No third-party API, no cost. Effort is now integration-only. |
| Alerts | ⚠️ **High effort** | Full CRUD feature; no existing infrastructure |

### Recommended MVP (Phase 1)
1. **Account filter + account breakdown** in `OverviewTab` (wire existing data through service/hook)
2. **Top movers** (gainers/losers) from existing holdings data (pure frontend)
3. **Mini 7-day / 30-day sparkline** per holding (new backend endpoint + frontend sparkline from scratch)

### Future (Phase 2)
4. **News feed** (now Lower effort since both providers already have news — see §4.4)
5. **Alerts system** (full CRUD + delivery — see §4.5; no provider supports this)

---

## 8. Critical Corrections from Initial Analysis

| Original Claim | Actual Finding | Correction Impact |
|----------------|----------------|-------------------|
| `DividendSparkline` exists in `dividend-panel.tsx:194` | **No sparkline component exists** anywhere in the codebase | Sparkline effort increases from Medium to Medium–High |
| `AccountChipStrip` needs to move into `OverviewTab` | Already at `PortfolioTabShell` level (correct location) | No move needed; just wire the `accountId` prop through |
| `usePortfolioOverview` just needs `accountIds` param | Service method also needs `accountId` parameter | Both hook + service need updating (2 files) |
| `PortfolioOverview.tsx` renders account breakdown at lines 152–197 | This is a **separate standalone page** component, not the tab | Correct — the standalone page and tab are separate; the tab needs the breakdown added |
| News requires third-party API (Finnhub/NewsAPI) | **Both defeatbeta_api and yfinance already have news built in**. No third-party API needed. | News effort drops from Medium to Low; zero cost |
| No provider supports alerts | Confirmed — no existing provider supports alerts | Alerts remain a full custom build; effort remains High |
