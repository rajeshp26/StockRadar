from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Optional
import os
import logging

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
    # 🔥 Authentication (Firebase)
    # ============================================
    FIREBASE_PROJECT_ID: str = Field(..., description="Firebase project ID for token verification")
    # ============================================
    # 🌐 API Server Configuration
    # ============================================
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8001, ge=1024, le=65535)
    
    # ============================================
    # 🛡️ Security & CORS
    # ============================================
    DEV_ORIGINS: List[str] = [
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
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Google Gemini API key for stock analysis")
    
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
    RETRY_BACKOFF_SECONDS: List[int] = Field(
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
    def allowed_origins(self) -> List[str]:
        if self.is_production:
            return [
                "https://stockerpro.com",
                "https://app.stockerpro.com",
            ]
        # Dev allows:
        # - localhost ports (9000, 9002, 9003, 3000)
        # - Cloud Workstation previews for both web (9000, 9002) and mobile (9003)
        return self.DEV_ORIGINS + [
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

def validate_config():
    """Validates settings and prints a summary on startup."""
    try:
        s = Settings()
        key_type = "JWT" if s.SUPABASE_SERVICE_ROLE_KEY.startswith("eyJ") else "Legacy"
        print("\n" + "="*60)
        print("✅ STOCKERPRO CONFIGURATION LOADED")
        print("="*60)
        print(f"Environment  : {s.ENVIRONMENT}")
        print(f"API Endpoint : {s.API_HOST}:{s.API_PORT}")
        print(f"Supabase URL : {s.SUPABASE_URL}")
        print(f"Supabase Key : {key_type} format detected")
        print(f"Firebase PID : {s.FIREBASE_PROJECT_ID}")
        print(f"AI Provider  : {'Gemini Enabled ✨' if s.GEMINI_API_KEY else 'AI Disabled'}")
        print(f"Defeat Beta  : {'Enabled ✨' if s.ENABLE_EARNINGS_SCHEDULER else 'Disabled'}")
        print(f"  - Scheduler Interval: {s.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS}h")
        print(f"  - Earnings Buffer: ±{s.EARNINGS_REFRESH_BUFFER_DAYS} days")
        print(f"  - Retry Attempts: {s.RETRY_MAX_ATTEMPTS} with backoff {s.RETRY_BACKOFF_SECONDS}")
        print(f"  - YFinance Fallback: {'Enabled' if s.ENABLE_YFINANCE_FALLBACK else 'Disabled'}")
        print(f"  - Deduplication: {'Enabled (97.5% optimization)' if s.ENABLE_DEDUPLICATION_OPTIMIZATION else 'Disabled'}")
        print("="*60 + "\n")
        return s
    except Exception as e:
        print("\n" + "!"*60)
        print("❌ CONFIGURATION ERROR: Backend cannot start.")
        print("!"*50)
        print(f"\n{str(e)}\n")
        print("Troubleshooting:")
        print(f"1. Checked .env at: {ENV_FILE}")
        print("2. Ensure all required variables (URL, Key, Project ID) are present.")
        print("!"*60 + "\n")
        raise


# Initialize settings
settings = validate_config()