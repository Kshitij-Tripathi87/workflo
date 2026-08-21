import os
import yaml
from dataclasses import dataclass
from typing import Optional


@dataclass
class EnvironmentConfig:
    base_url: str
    api_url: str
    tenant_id: str
    default_timeout: int = 15000
    headless: bool = True

    @classmethod
    def from_env(cls, env_name: Optional[str] = None):
        env = env_name or os.getenv("TEST_ENV", "local")
        config_path = os.path.join(
            os.path.dirname(__file__),
            "environments",
            f"{env}.yaml",
        )
        if os.path.exists(config_path):
            with open(config_path) as f:
                data = yaml.safe_load(f)
            return cls(**data)
        return cls(
            base_url=os.getenv("BASE_URL", "https://app.workflowpro.com"),
            api_url=os.getenv("API_BASE_URL", "https://api.workflowpro.com"),
            tenant_id=os.getenv("TENANT_ID", "company1"),
            default_timeout=int(os.getenv("DEFAULT_TIMEOUT", "15000")),
            headless=os.getenv("HEADLESS", "true").lower() == "true",
        )


@dataclass
class BrowserStackConfig:
    username: str
    access_key: str
    project_name: str = "WorkFlow Pro"
    build_name: str = ""
    local: bool = False
    local_identifier: Optional[str] = None
    network_logs: bool = True
    console_logs: str = "errors"
    video: bool = True

    def __post_init__(self):
        if not self.build_name:
            self.build_name = f"Build {os.getenv('CI_BUILD_ID', 'local')}"

    @classmethod
    def from_env(cls):
        return cls(
            username=os.getenv("BROWSERSTACK_USERNAME", ""),
            access_key=os.getenv("BROWSERSTACK_ACCESS_KEY", ""),
        )
