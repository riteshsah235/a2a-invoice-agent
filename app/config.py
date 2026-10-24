import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_base_url() -> str:
    """Return default BASE_URL with production fallback or Render auto-assigned external URL."""
    render_external = os.getenv("RENDER_EXTERNAL_URL")
    if render_external:
        return f"{render_external.rstrip('/')}/a2a/"
    return "https://a2a-invoice-agent-kkbk.onrender.com/a2a/"


class Settings(BaseSettings):
    APP_NAME: str = "A2A Invoice Agent"
    APP_DESCRIPTION: str = "A2A HTTP+JSON 1.0 Autonomous Invoice Agent: evidence-based decisions, approval limits, duplicate payments, and safe recovery."
    APP_VERSION: str = "1.0.0"
    
    # Base URL where this agent is reached (used in Agent Card supportedInterfaces)
    # Production default: https://a2a-invoice-agent-kkbk.onrender.com/a2a/
    # Configurable locally via .env or environment variable BASE_URL=http://localhost:8000/a2a/
    BASE_URL: str = get_default_base_url()
    
    # Database connection URL (PostgreSQL for Render, SQLite for local/testing fallback)
    DATABASE_URL: str = "sqlite:///./invoice_agent.db"
    
    # Optional LLM API keys
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    
    # Constraints
    MAX_PAYLOAD_SIZE: int = 512 * 1024  # 512 KiB per specification
    DEFAULT_HISTORY_LENGTH: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def clean_database_url(self) -> str:
        """Render PostgreSQL URLs often start with postgres://, which SQLAlchemy requires as postgresql://."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


settings = Settings()
