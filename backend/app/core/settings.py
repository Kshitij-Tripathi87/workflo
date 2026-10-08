from typing import Literal, Optional
from pydantic import Field, AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    ENV: Literal["dev", "staging", "prod"] = "dev"
    LOG_LEVEL: str = "INFO"
    API_VERSION_PREFIX: str = "/api/v1"

    # DataHub
    DATAHUB_BASE_URL: Optional[AnyHttpUrl] = None
    DATAHUB_TOKEN: Optional[str] = None
    USE_MOCK_DATAHUB: bool = True
    DATAHUB_TIMEOUT: int = 30
    DATAHUB_MAX_RETRIES: int = 3
    DATAHUB_RATE_LIMIT_RPS: float = 10.0

    # Auth (OIDC)
    OIDC_ISSUER: Optional[str] = None
    OIDC_CLIENT_ID: Optional[str] = None
    OIDC_CLIENT_SECRET: Optional[str] = None
    AUTH_REQUIRED: bool = True
    ACCESS_TOKEN_TTL_MINUTES: int = 15

    # Database
    DATABASE_URL: Optional[PostgresDsn] = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    ENABLE_TRACING: bool = False
    METRICS_ENABLED: bool = True

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # Write-back
    WRITEBACK_PATH: str = "data/writeback.jsonl"

    # Autopilot
    CORTEX_AUTOPILOT_ENABLED: bool = False
    CORTEX_AUTOPILOT_POLL_INTERVAL: int = 300
    CORTEX_TIER: Literal["trial", "free", "paid"] = "trial"
    CORTEX_TRIAL_ACTIVE: bool = True
    CORTEX_MAX_AGENT_ITERATIONS: int = 12

    # LLM (Nvidia NIM by default — OpenAI-compatible)
    CORTEX_LLM_PROVIDER: Literal["nvidia", "openai", "none"] = "nvidia"
    CORTEX_NVIDIA_API_KEY: Optional[str] = None
    CORTEX_NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    CORTEX_NVIDIA_MODEL: str = "nvidia/llama-3.1-nemotron-70b-instruct"

    # Vector store (RAG context)
    CORTEX_CHROMA_PATH: str = "data/chromadb"
    CORTEX_CHROMA_COLLECTION: str = "cortex_context"

    @property
    def is_dev(self) -> bool:
        return self.ENV == "dev"

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"


settings = Settings()
