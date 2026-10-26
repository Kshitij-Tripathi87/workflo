"""Snowflake connector configuration sourced from environment variables."""
import os
from dataclasses import dataclass


@dataclass
class SnowflakeConfig:
    account: str
    user: str
    password: str | None
    private_key_path: str | None
    warehouse: str | None
    database: str
    schema: str
    role: str | None
    mock_mode: bool


def snowflake_config_from_env() -> SnowflakeConfig:
    """Read Snowflake connection config from environment variables.

    Required for real connection:
        CORTEX_SNOWFLAKE_ACCOUNT, CORTEX_SNOWFLAKE_USER,
        CORTEX_SNOWFLAKE_DATABASE, CORTEX_SNOWFLAKE_SCHEMA

    Auth (one of):
        CORTEX_SNOWFLAKE_PASSWORD
        CORTEX_SNOWFLAKE_PRIVATE_KEY_PATH

    Optional:
        CORTEX_SNOWFLAKE_WAREHOUSE, CORTEX_SNOWFLAKE_ROLE

    If CORTEX_SNOWFLAKE_MOCK=true, returns a config that skips
    connection attempts (used for tests and offline development).
    """
    mock_mode = os.environ.get("CORTEX_SNOWFLAKE_MOCK", "").lower() in ("1", "true", "yes")
    return SnowflakeConfig(
        account=os.environ.get("CORTEX_SNOWFLAKE_ACCOUNT", ""),
        user=os.environ.get("CORTEX_SNOWFLAKE_USER", ""),
        password=os.environ.get("CORTEX_SNOWFLAKE_PASSWORD"),
        private_key_path=os.environ.get("CORTEX_SNOWFLAKE_PRIVATE_KEY_PATH"),
        warehouse=os.environ.get("CORTEX_SNOWFLAKE_WAREHOUSE"),
        database=os.environ.get("CORTEX_SNOWFLAKE_DATABASE", ""),
        schema=os.environ.get("CORTEX_SNOWFLAKE_SCHEMA", "PUBLIC"),
        role=os.environ.get("CORTEX_SNOWFLAKE_ROLE"),
        mock_mode=mock_mode,
    )
