from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Tenant Shield Control Plane"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./workflo.db"
    redis_url: str = ""
    cp_port: int = 3001  # local-mode port for the auth site (WORKFLO_CP_PORT)
    s3_endpoint: str = ""
    s3_bucket: str = "tenant-shield-artifacts"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    api_key_prefix: str = "ts_live_"
    # Hosted-inference gateway upstream: the model server the gateway
    # proxies observation-only requests to. The gateway builds prompts
    # itself; the model NEVER receives source code or arbitrary prompts.
    upstream_llm_base_url: str = ""
    upstream_llm_api_key: str = ""
    upstream_llm_model: str = "qwen3-4b-4bit"
    upstream_llm_timeout: float = 60.0
    inference_gateway_version: str = "0.3.0"
    # Per-tenant run-submission ceiling (SOC 2 CC6.1: one tenant cannot
    # starve shared worker capacity). 0 disables.
    rate_limit_runs_per_minute: int = 60
    # Envelope encryption: KEK provider. "static" reads master_kek_hex from
    # config (dev); production wires a real KMS provider via entry point.
    kek_provider: str = "static"
    master_kek_hex: str = ""
    # PostgreSQL Row-Level Security defense-in-depth (db/rls/001_tenant_rls.sql).
    # App-layer project scoping stays the primary control; RLS is the tripwire.
    rls_enabled: bool = False
    # Receipt transparency log (append-only Merkle tree). Empty = disabled.
    # Production: ship this file to WORM object storage (S3 Object Lock).
    transparency_log_path: str = ""

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
