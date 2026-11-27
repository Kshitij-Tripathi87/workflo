from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Tenant Shield Control Plane"
    environment: str = "development"
    # Explicit production flag ("PRODUCTION=true"). Production posture is
    # also implied by ENVIRONMENT=production|prod. Either one arms the
    # fail-closed startup guards in app/core/startup_guards.py.
    production: bool = False
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
    # Durable dispatch (Product Engineering Brief §8, Phase 2): every run is
    # admitted with a transactional outbox row (dispatch intent committed in
    # the SAME transaction as the run), one RunAttempt per sandbox execution,
    # and lease/heartbeat claim semantics. The claim/execute worker either
    # runs in-process (development default) or as the dispatcher loop.
    # Production REQUIRES the loop (fail-closed startup guard): an admitted
    # run must survive an API restart without losing its dispatch intent.
    dispatcher_enabled: bool = False
    dispatch_lease_seconds: int = 300
    dispatch_heartbeat_interval: int = 60
    dispatch_max_attempts: int = 3
    dispatch_retry_backoff_seconds: int = 30
    # Run creation idempotency: dev permits absent keys (one is generated);
    # production must require the client-supplied Idempotency-Key.
    require_idempotency_key: bool = False
    # Anonymous API-key creation (POST /v1/keys with no credential). This
    # exists so a fresh local deployment can mint its first key, but it is
    # also an unauthenticated write that accepts a client-supplied
    # project_id — i.e. arbitrary-tenant key minting. It is therefore
    # default-CLOSED and must be opted into explicitly for local development.
    # Authenticated callers can always mint keys for their own project.
    allow_anonymous_key_bootstrap: bool = False

    # Fixed demo API key (POST /v1/auth/demo-token) hands out a constant key
    # that carries run_tests/read_reports/admin on the demo project. Production
    # always refuses it, but any deployment that merely is not labelled
    # production would otherwise expose an admin credential anonymously, so it
    # is default-CLOSED and must be opted into for local demos.
    enable_demo_token: bool = False

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
