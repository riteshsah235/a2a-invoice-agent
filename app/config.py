import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "A2A Invoice Agent"
    APP_DESCRIPTION: str = "A2A HTTP+JSON 1.0 Autonomous Invoice Agent: evidence-based decisions, approval limits, duplicate payments, and safe recovery."
    APP_VERSION: str = "1.0.0"
    
    # Base URL where this agent is reached (used in Agent Card supportedInterfaces)
    # Example: https://my-agent.onrender.com or https://my-agent.onrender.com/a2a
    BASE_URL: str = "http://localhost:8000"
    
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
