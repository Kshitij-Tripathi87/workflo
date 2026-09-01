"""Run specification models — the contract between CLI and Worker."""

from typing import Optional
from pydantic import BaseModel, Field

from workflo_schema.enums import Goal, BrowserMode


class TestTargets(BaseModel):
    include: list[str] = Field(default_factory=list, description="Glob patterns of test paths to include")
    exclude: list[str] = Field(default_factory=list, description="Glob patterns to exclude")


class ArtifactsConfig(BaseModel):
    screenshots: bool = True
    traces: str = "on-failure"  # "always" | "on-failure" | "off"
    soc2_report: bool = True
    logs: bool = True


class RunConfig(BaseModel):
    browsers: list[str] = Field(default_factory=lambda: ["chromium"], description="Browser engines, e.g. chromium, firefox, webkit")
    mobile_devices: list[str] = Field(default_factory=list, description="Device names for emulation, e.g. iPhone 14, Galaxy S23")
    parallelism: int = Field(default=4, ge=1, le=64)
    retries: int = Field(default=2, ge=0, le=10)
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    browser_mode: BrowserMode = BrowserMode.CONTAINER


class RunSpec(BaseModel):
    goal: Goal
    markers: list[str] = Field(default_factory=list, description="pytest -m marker expressions")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variable overrides")
    targets: TestTargets = Field(default_factory=TestTargets)
    config: RunConfig = Field(default_factory=RunConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)
    project_id: Optional[str] = None
    repo_url: Optional[str] = Field(default=None, description="Git repo URL for worker checkout")
    commit_sha: Optional[str] = Field(default=None, description="Specific commit to test")
