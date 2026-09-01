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

    model_config = {"env_file": ".env", "env_prefix": ""}


settings = Settings()
