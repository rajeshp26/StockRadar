import logging
import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# CALCULATE PATHS
# This ensures we find .env regardless of where we start the process
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")


class Settings(BaseSettings):
    """
    StockerPro Configuration Settings.
    Strictly validated but compatible with both JWT and Legacy Supabase formats.
    """

    # ============================================
    # 🌍 Environment & Core
    # ============================================
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")

    # ============================================
    # 🗄️ Database (Supabase)
    # ============================================
    SUPABASE_URL: str = Field(..., description="The hosted Supabase project URL")

    # Corrected: min_length=20 to accommodate valid 46-char legacy keys
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., min_length=20, description="Supabase service_role key (JWT or Legacy)")
    # ============================================
    # 🔐 Authentication (Supabase JWT)
    # ============================================
    SUPABASE_JWT_SECRET: str = Field(..., min_length=20, description="Supabase JWT secret for HS256 token verification (from Settings → API → JWT Secret)")
    # ============================================
    # 🌐 API Server Configuration
    # ============================================
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8001, ge=1024, le=65535)

    # ============================================
    # 🛡️ Security & CORS
    # ============================================
    DEV_ORIGINS: list[str] = [
        "http://localhost:9000",      # Next.js Web App
        "http://127.0.0.1:9000",
        "http://localhost:9002",      # Legacy (keep for compatibility)
        "http://127.0.0.1:9002",
        "http://localhost:9003",      # Flutter Web App (NEW)
        "http://127.0.0.1:9003",
        "http://localhost:3000",      # Dev default
    ]
    # ============================================
    # 🤖 AI & External Providers
    # ============================================
    OPEN_ROUTER_KEY: str | None = Field(default=None, description="OpenRouter API key for AI stock analysis")
    OPEN_ROUTER_MODEL: str = Field(default="openai/gpt-oss-120b", description="OpenRouter model for suitability summaries")
    # EdgarTools Provider (SEC EDGAR filings)
    EDGAR_IDENTITY: str = Field(
        default="StockerPro stockerpro@example.com",
        description="SEC EDGAR API identity string (required by SEC for rate limiting)"
    )
    # ============================================
    # 📊 DEFEAT BETA INTEGRATION
    # ============================================

    # Earnings Refresh Scheduler
    EARNINGS_REFRESH_CHECK_INTERVAL_HOURS: int = Field(
        default=2,
        description="How often the earnings scheduler runs (in hours)"
    )
    EARNINGS_REFRESH_BUFFER_DAYS: int = Field(
        default=10,
        description="Buffer window for earnings date comparison (±N days). "
                    "±10 catches announcements from previous week with delayed availability."
    )

    # Retry Logic & Resilience
    RETRY_MAX_ATTEMPTS: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of retry attempts for failed requests"
    )
    RETRY_BACKOFF_SECONDS: list[int] = Field(
        default=[1, 2, 4],
        description="Exponential backoff delays in seconds for retries"
    )
    ENABLE_YFINANCE_FALLBACK: bool = Field(
        default=True,
        description="Enable fallback to yfinance when defeat-beta fails completely"
    )

    # Timeouts (seconds)
    YFINANCE_SINGLE_TIMEOUT_SECONDS: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Single stock price fetch timeout from yfinance"
    )
    YFINANCE_BATCH_TIMEOUT_SECONDS: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Batch price fetch timeout for multiple stocks"
    )
    DEFEAT_BETA_TIMEOUT_SECONDS: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Individual defeat-beta method call timeout"
    )
    COMPANY_REFRESH_TIMEOUT_SECONDS: int = Field(
        default=60,
        ge=1,
        le=300,
        description="Complete company refresh timeout (all financial methods)"
    )

    # On-Demand Refresh
    ENABLE_ON_DEMAND_FINANCIAL_REFRESH: bool = Field(
        default=True,
        description="Allow frontend to trigger immediate financial data refresh"
    )

    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )
    LOG_DEFEAT_BETA_CALLS: bool = Field(
        default=True,
        description="Enable detailed defeat-beta API call logging"
    )
    LOG_YFINANCE_CALLS: bool = Field(
        default=False,
        description="Enable detailed yfinance API call logging"
    )
    LOG_DEDUPLICATION_DETAILS: bool = Field(
        default=False,
        description="Log every filtered row during deduplication"
    )

    # Structured debug tracing
    LOG_NAMESPACE: str = Field(
        default="app",
        description="Root logger namespace for structured tracing, producing "
                    "<namespace>.debug.trace and <namespace>.debug.integrity. "
                    "Generic by default so the tracing modules drop into any "
                    "project; override to sit under this app's logger tree."
    )
    DEBUG_TRACE_ENABLED: bool = Field(
        default=False,
        description="Emit structured per-layer input/output records to the "
                    "<LOG_NAMESPACE>.debug logger tree. Off by default because "
                    "the emitters run inside repository pagination loops."
    )
    DEBUG_TRACE_ALWAYS_ON_SCOPES: tuple[str, ...] = Field(
        default=("snapshot", "http"),
        description="Trace scopes that emit even while DEBUG_TRACE_ENABLED is "
                    "off. The global flag stays off because its emitters sit "
                    "inside repository pagination loops; the daily snapshot run "
                    "and the HTTP request lifecycle are the flows an operator "
                    "has to be able to follow. Both are low volume -- the "
                    "snapshot roughly one record per account per day, and one "
                    "start/end pair per request."
    )
    DEBUG_LOG_ENABLED: bool = Field(
        default=True,
        description="Attach a rotating JSON-lines file sink for the "
                    "<LOG_NAMESPACE>.debug tree, so debug records survive the "
                    "process instead of scrolling away on stdout. On by default: "
                    "a scheduled run finishes and exits, so stdout-only records "
                    "are gone by the time anyone reads them."
    )
    DEBUG_LOG_DIR: str = Field(
        default="logs",
        description="Directory for the debug log file. A relative path is "
                    "anchored to the backend package, not the working "
                    "directory, so schedulers and scripts agree."
    )
    DEBUG_LOG_FILENAME: str = Field(
        default="debug.jsonl",
        description="File name of the rotating debug log inside DEBUG_LOG_DIR. "
                    "Project-neutral by default so the logging modules carry no "
                    "product name; override per project if desired."
    )
    DEBUG_LOG_LEVEL: str = Field(
        default="DEBUG",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum level written to the debug log file"
    )
    DEBUG_LOG_MAX_BYTES: int = Field(
        default=10_485_760,
        description="Rotate the debug log once it reaches this size (10 MiB)"
    )
    DEBUG_LOG_BACKUP_COUNT: int = Field(
        default=5,
        description="Number of rotated debug log files to retain"
    )

    # Timezone
    DEFAULT_TIMEZONE: str = Field(
        default="America/New_York",
        description="Default timezone for companies (used for earnings date comparisons)"
    )

    # Data Quality
    ENABLE_DATA_SOURCE_TRACKING: bool = Field(
        default=True,
        description="Track data source for each financial record (defeat-beta vs yfinance)"
    )
    ENABLE_CONFLICT_DETECTION: bool = Field(
        default=True,
        description="Detect and log conflicts when yfinance data differs from defeat-beta"
    )
    CONFLICT_DETECTION_THRESHOLD_PCT: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Percentage difference threshold to flag as conflict (e.g., 1.0 = 1%)"
    )
    DEFEAT_BETA_CONFIDENCE_SCORE: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for defeat-beta data (1.0 = 100% trust)"
    )
    YFINANCE_FALLBACK_CONFIDENCE_SCORE: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score for yfinance fallback data (0.8 = 80% trust)"
    )
    ENABLE_PRICE_PLAUSIBILITY_GATE: bool = Field(
        default=True,
        description="Reject price_history / current_market_data writes whose close/current "
                    "price exceeds the company's verified anchor (executed transaction "
                    "prices, last verified close, or provider current price) by more than "
                    "MAX_PRICE_UP_RATIO. Root-cause guard against provider scale errors "
                    "reaching performance data."
    )
    MAX_PRICE_UP_RATIO: float = Field(
        default=100.0,
        ge=1.5,
        le=10000.0,
        description="Plausibility envelope: an incoming price is rejected when it exceeds "
                    "the verified anchor multiplied by this ratio. 100 = a 100x jump above "
                    "ground truth is treated as corrupt (real reverse splits widen the "
                    "envelope via the splits table)."
    )

    # SSE (Server-Sent Events)
    SSE_UPDATE_INTERVAL_SECONDS: int = Field(
        default=10,
        ge=1,
        le=60,
        description="How often background price monitor updates in seconds"
    )

    # Batch Operations
    MAX_BATCH_SIZE: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum number of stocks to update in a single batch"
    )

    # Feature Flags
    ENABLE_PORTFOLIO_DASHBOARD: bool = Field(
        default=True,
        description="Enable the portfolio dashboard view-model endpoint (/portfolio/dashboard)",
    )
    ENABLE_EARNINGS_SCHEDULER: bool = Field(
        default=True,
        description="Enable the earnings refresh scheduler"
    )
    LOAD_FULL_HISTORY_ON_NEW_STOCK: bool = Field(
        default=True,
        description="Load full historical data when adding new stock (vs incremental)"
    )
    ENABLE_DEDUPLICATION_OPTIMIZATION: bool = Field(
        default=True,
        description="Use optimized filtering to prevent duplicate DB writes"
    )
    ENABLE_MARKET_DATA_SCHEDULER: bool = Field(
        default=True,
        description="Enable the market data refresh scheduler"
    )
    SUPER_INVESTORS_REFRESH_INTERVAL_HOURS: int = Field(
        default=24,
        description="Hours between super investors scheduler runs"
    )
    AGGREGATION_REFRESH_INTERVAL_HOURS: int = Field(
        default=24,
        description="Hours between sector metric aggregation runs"
    )
    ENABLE_AGGREGATION_SCHEDULER: bool = Field(
        default=True,
        description="Enable the sector metric aggregation scheduler"
    )
    ENABLE_SUPER_INVESTORS_SCHEDULER: bool = Field(
        default=True,
        description="Enable the super investors refresh scheduler"
    )
    SUPER_INVESTORS_INITIAL_QUARTERS: int = Field(
        default=20,
        description="Number of quarters to fetch on first run (20 = 5 years)"
    )
    SUPER_INVESTORS_GRACE_DAYS: int = Field(
        default=49,
        description="Days after quarter end before filing is due"
    )
    SUPER_INVESTORS_CACHE_TTL_SECONDS: int = Field(
        default=900,
        description=(
            "TTL for the in-process super-investor read cache. 13F data changes "
            "at most quarterly; the TTL is the authoritative coherence mechanism "
            "while the scheduler worker runs in a separate process."
        ),
    )
    SUPER_INVESTORS_CACHE_MAX_ENTRIES: int = Field(
        default=512,
        description="Maximum entries in the in-process super-investor read cache.",
    )
    SUPER_INVESTORS_API_SEC_FALLBACK: bool = Field(
        default=False,
        description=(
            "Allow the API to fall back to a live SEC 13F fetch on a database "
            "miss. Professional default is off: user requests are served from "
            "the database only, and the scheduler owns SEC ingestion. Kept as a "
            "kill-switch for emergency backfill scenarios."
        ),
    )
    ENABLE_RECONCILIATION_SCHEDULER: bool = Field(
        default=True,
        description="Enable the weekly data reconciliation scheduler (gap detection)"
    )
    RECONCILIATION_INTERVAL_HOURS: float = Field(
        default=168.0,
        description="Hours between reconciliation planner runs (168 = weekly)"
    )
    ENABLE_FRESHNESS_MONITOR_SCHEDULER: bool = Field(
        default=True,
        description="Enable the daily freshness coverage monitor scheduler"
    )
    FRESHNESS_ALERT_THRESHOLD_PCT: float = Field(
        default=95.0,
        description="Coverage percentage below which the freshness monitor alerts"
    )
    PRICE_HISTORY_RETENTION_YEARS: int = Field(
    default=10,
    description="Number of years of price history to retain"
    )

    # Price Ingestion Pipeline
    ENABLE_PRICE_INGESTION_SCHEDULER: bool = Field(
        default=True,
        description="Enable the price ingestion scheduler (refreshes price_sources from yfinance+supabase)"
    )

    # Valuation Computation Pipeline
    ENABLE_VALUATION_SCHEDULER: bool = Field(
        default=True,
        description="Enable the valuation computation scheduler (pre-computes all 5 methods for active companies)"
    )
    VALUATION_REFRESH_INTERVAL_HOURS: int = Field(
        default=24,
        description="Hours between valuation computation scheduler runs"
    )

    DASHBOARD_READ_PATH: str = Field(
        default="off",
        pattern="^(off|shadow|serve)$",
        description="Dashboard read path mode: 'off' (old only), 'shadow' (both, log compare, old serves), 'serve' (new only)"
    )

    # FX Currency Conversion
    ENABLE_FX_CONVERSION: bool = Field(
        default=True,
        description="Enable FX currency conversion for multi-currency portfolio holdings"
    )

    # Portfolio Snapshot Feature Flags
    ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER: bool = Field(
        True,
        description="Enable daily portfolio snapshot computation job (23:00 UTC)"
    )

    ENABLE_BENCHMARK_SERIES_SCHEDULER: bool = Field(
        True,
        description="Enable the daily refresh of the materialised benchmark "
                    "comparison series (migration 015). The request path still "
                    "simulates live and stores on a miss, so disabling this "
                    "costs performance, never correctness."
    )

    ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH: bool = Field(
        True,
        description="Enable snapshot-based read path for /api/portfolio/performance "
                    "(shadow-mode before full cutover)"
    )

    ENABLE_PORTFOLIO_RESPONSE_CACHE: bool = Field(
        True,
        description="Cache the /portfolio/performance response per "
                    "(account set, period), keyed on a fingerprint of the "
                    "snapshot inputs plus the resolved window dates. A warm hit "
                    "serves the identical series without re-running the merge; "
                    "the snapshot rows are still read (their fingerprint is the "
                    "key), so a corrected or appended snapshot misses rather "
                    "than serving stale values. Disabling costs performance, "
                    "never correctness."
    )

    ENABLE_PORTFOLIO_VALUE_SERIES: bool = Field(
        True,
        description="Serve /portfolio/performance from the materialised value "
                    "series (migration 017) when its input fingerprint still "
                    "matches the snapshot rows the request read. A period switch "
                    "or a weekend becomes a slice of the stored build instead of "
                    "a re-merge. The fingerprint is recomputed from live "
                    "snapshots on every request, so an appended, corrected or "
                    "backdated snapshot rebuilds before any stored point is "
                    "served. Disabling costs performance, never correctness."
    )

    PORTFOLIO_SNAPSHOT_FALLBACK_ENABLED: bool = Field(
        True,
        description="Enable fallback FIFO computation when snapshots not yet available"
    )

    ENABLE_PERFORMANCE_LOCF: bool = Field(
        True,
        description="Apply last-observation-carried-forward when merging per-account "
                    "snapshots: accounts missing a snapshot on a given date will "
                    "carry forward their last known total_value instead of $0. "
                    "Eliminates artificial dips in the performance chart."
    )

    # Event-Replay Feature Flags (Phase 4 cut-over)
    ENABLE_EVENT_REPLAY_SNAPSHOTS: bool = Field(
        False,
        description="Use event-replay engine instead of mutable state to build snapshots "
                    "(Phase 4: set True after backfill and 7-day comparison pass)"
    )

    EVENT_REPLAY_COMPARISON_MODE: bool = Field(
        True,
        description="When True, compute snapshots via BOTH old and replay paths, log "
                    "mismatches, but still write the old-path result. Set to False only "
                    "after comparison passes for all accounts."
    )

    SNAPSHOT_SPIKE_THRESHOLD: float = Field(
        default=0.20,
        description="Maximum allowed fractional change in total_value between consecutive "
                    "snapshots before a write is withheld for recomputation. 0.20 = 20%. "
                    "A value that still spikes after gap recomputation is stored with "
                    "data_quality_flag SPIKE_CONFIRMED. "
                    "Deposits/withdrawals are excluded from spike detection."
    )

    SNAPSHOT_GAP_FILL_ENABLED: bool = Field(
        default=True,
        description="When True, the daily snapshot job fills missing dates between the "
                    "last known snapshot and today using event-replay with consistent pricing."
    )

    SNAPSHOT_GAP_REPAIR_LOOKBACK_DAYS: int = Field(
        default=730,
        ge=0,
        description="How far back the daily snapshot job repairs missing weekday "
                    "snapshots. Forward-only filling leaves a hole permanently behind "
                    "the newest row once a later date exists (e.g. the June 2026 "
                    "snapshot gap); this bounded look-back rebuilds those interior "
                    "holes. 0 disables the look-back and restores forward-only repair."
    )

    # Debugging & Development
    DEBUG_FILTERING_LOGIC: bool = Field(
        default=False,
        description="Log every row comparison during filtering (VERBOSE!)"
    )
    DRY_RUN_MODE: bool = Field(
        default=False,
        description="Don't actually write to DB, just log what would be written"
    )

    # ============================================
    # ⚙️ Computed Properties
    # ============================================

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        if self.is_production:
            return [
                "https://stockerpro.com",
                "https://app.stockerpro.com",
            ]
        # Dev allows:
        # - localhost ports (9000, 9002, 9003, 3000)
        # - Cloud Workstation previews for both web (9000, 9002) and mobile (9003)
        return [
            *self.DEV_ORIGINS,
            "https://9000-*.cloudworkstations.dev",
            "https://9002-*.cloudworkstations.dev",
            "https://9003-*.cloudworkstations.dev",
        ]

    # ============================================
    # ⚙️ Validators
    # ============================================
    @field_validator("SUPABASE_SERVICE_ROLE_KEY")
    @classmethod
    def validate_supabase_key(cls, v: str) -> str:
        """
        Supports both modern JWT (eyJ...) and legacy (sb_secret_...) formats.
        """
        is_jwt = v.startswith("eyJ")
        is_legacy = v.startswith("sb_secret_")

        if not (is_jwt or is_legacy):
            raise ValueError(
                f"Invalid Supabase key format. Must be JWT (starts with 'eyJ') or Legacy (starts with 'sb_secret_'). "
                f"Got: {v[:10]}..."
            )
        return v

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,  # ✅ Use absolute path
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="forbid",
    )

def config_summary_lines(s) -> list[str]:
    """Build the ASCII-only startup summary.

    Kept as a pure function so the exact bytes written to the console are
    testable. Non-ASCII glyphs (e.g. `±`) render as `?` on cp1252/cp437 Windows
    consoles, which turned `Earnings Buffer: ±10 days` into `?10 days`.
    """
    key_type = "JWT" if s.SUPABASE_SERVICE_ROLE_KEY.startswith("eyJ") else "Legacy"
    lines = [
        "=" * 60,
        "[OK] STOCKERPRO CONFIGURATION LOADED",
        "=" * 60,
        f"Environment  : {s.ENVIRONMENT}",
        f"API Endpoint : {s.API_HOST}:{s.API_PORT}",
        f"Supabase URL : {s.SUPABASE_URL}",
        f"Supabase Key : {key_type} format detected",
        "Auth Provider: Supabase JWT (local JWKS verification)",
        f"AI Provider  : {'OpenRouter Enabled *' if s.OPEN_ROUTER_KEY else 'AI Disabled'}",
        f"Defeat Beta  : {'Enabled *' if s.ENABLE_EARNINGS_SCHEDULER else 'Disabled'}",
        f"Market Data  : {'Enabled *' if s.ENABLE_MARKET_DATA_SCHEDULER else 'Disabled'}",
    ]
    if s.ENABLE_MARKET_DATA_SCHEDULER:
        lines.append(
            f"  - Scheduler Interval: {getattr(s, 'MARKET_DATA_REFRESH_INTERVAL_HOURS', 24)}h"
        )
    lines.extend(
        [
            f"  - Scheduler Interval: {s.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS}h",
            f"  - Earnings Buffer: +/-{s.EARNINGS_REFRESH_BUFFER_DAYS} days",
            f"  - Retry Attempts: {s.RETRY_MAX_ATTEMPTS} with backoff {s.RETRY_BACKOFF_SECONDS}",
            f"  - YFinance Fallback: {'Enabled' if s.ENABLE_YFINANCE_FALLBACK else 'Disabled'}",
            f"  - Deduplication: {'Enabled (97.5% optimization)' if s.ENABLE_DEDUPLICATION_OPTIMIZATION else 'Disabled'}",
            "=" * 60,
        ]
    )
    return lines


def validate_config():
    """Validates settings and prints a summary on startup."""
    try:
        s = Settings()
        print("\n" + "\n".join(config_summary_lines(s)) + "\n")
        return s
    except Exception as e:
        print("\n" + "!"*60)
        print("[ERROR] CONFIGURATION ERROR: Backend cannot start.")
        print("!"*50)
        print(f"\n{e!s}\n")
        print("Troubleshooting:")
        print(f"1. Checked .env at: {ENV_FILE}")
        print("2. Ensure all required variables (URL, Key, Project ID) are present.")
        print("!"*60 + "\n")
        raise


# Initialize settings
settings = validate_config()
