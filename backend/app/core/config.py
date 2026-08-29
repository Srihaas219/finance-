from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment / .env.

    Defaults are chosen so the app runs locally with zero setup (SQLite + Mock AI).
    Docker Compose overrides DATABASE_URL to Postgres and may set a real AI key.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./loantrust.db"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # AI provider is Mock by default so the app never depends on an external service.
    ai_provider: str = "mock"  # mock | groq | anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    ai_timeout_seconds: int = 20

    # Groq real-AI provider (optional; requires AI_PROVIDER=groq)
    # Two keys enable credential failover (NOT rate-limit bypass; org limits still apply).
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: int = 20
    groq_max_retries: int = 2
    groq_backoff_base_seconds: float = 1.0

    cors_origins: str = "http://localhost:5173"
    log_level: str = "info"

    ruleset_path: str = "seed/validation_rules.json"
    seed_users_path: str = "seed/users.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
