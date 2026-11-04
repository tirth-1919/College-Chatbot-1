import os
from pydantic_settings import BaseSettings, SettingsConfigDict

_side = os.getenv("APP_SIDE", "user").lower()
_side_env = "../.env.admin" if _side == "admin" else "../.env.user"

class Settings(BaseSettings):
    # Common secrets/database stay in the shared root env; side files override
    # only process-specific settings such as CORS and APP_SIDE.
    model_config = SettingsConfigDict(env_file=("../.env", _side_env), extra="ignore")
    database_url: str = "postgresql://chatbot:chatbot_password@localhost:5432/chatbot"
    database_url_fallback: str = "sqlite:///./chatbot.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "development-only-change-me"
    super_admin_email: str = ""
    super_admin_password: str = ""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Refuse to start in production with default SECRET_KEY
        if self.app_env == "production" and self.secret_key in ("development-only-change-me", "replace-with-a-random-secret-at-least-32-characters"):
            raise ValueError("SECURITY: Cannot start in production with default SECRET_KEY. Set a strong secret in .env")
    access_token_minutes: int = 15
    cookie_secure: bool = False
    gemini_api_key: str = ""
    xkiro_api_key: str = ""
    openai_api_key: str = ""
    app_env: str = "development"
    maintenance_mode: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@example.invalid"
    public_base_url: str = "http://localhost:3000"
    monthly_ai_budget: float = 0
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "ap-south-1"
    xkiro_api_url: str = ""
    ai_provider_order: str = "gemini,xkiro"
    gemini_cost_per_million_tokens_usd: float = 0
    xkiro_cost_per_million_tokens_usd: float = 0
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
    app_side: str = "all"
    clamav_host: str = ""
    clamav_port: int = 3310
    sentry_dsn: str = ""

settings = Settings()
