from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Tenant Shield Control Plane"
    environment: str = "development"
    production: bool = False
    database_url: str = "sqlite+aiosqlite:///./workflo.db"
    redis_url: str = ""
    cp_port: int = 3001
    s3_endpoint: str = ""
    s3_bucket: str = "tenant-shield-artifacts"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    api_key_prefix: str = "ts_live_"

    # Hosted inference gateway.
    upstream_llm_base_url: str = ""
    upstream_llm_api_key: str = ""
    upstream_llm_model: str = "qwen3-4b-4bit"
    upstream_llm_timeout: float = 60.0
    inference_gateway_version: str = "0.3.0"

    # Dashboard cross-origin access. Set an explicit comma-separated allow-list
    # in hosted deployments; do not use wildcard origins with credentials.
    dashboard_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Operator-managed voice provider keys (optional). Project BYOK keys are
    # encrypted with the org DEK and take precedence over these defaults.
    sarvam_api_key: str = ""
    sarvam_tts_speaker: str = "simran_en_customer"
    fish_api_key: str = ""
    fish_tts_reference_id: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    voice_http_timeout_seconds: float = 60.0

    rate_limit_runs_per_minute: int = 60
    kek_provider: str = "static"
    master_kek_hex: str = ""
    rls_enabled: bool = False
    transparency_log_path: str = ""
    dispatcher_enabled: bool = False
    dispatch_lease_seconds: int = 300
    dispatch_heartbeat_interval: int = 60
    dispatch_max_attempts: int = 3
    dispatch_retry_backoff_seconds: int = 30
    require_idempotency_key: bool = False

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
