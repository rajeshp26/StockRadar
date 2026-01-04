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
