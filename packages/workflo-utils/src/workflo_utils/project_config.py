"""Project-level Workflo config (`.workflo/config.yaml`).

Distinct from the GLOBAL config (`~/.workflo/config.yaml`) — global config
carries developer-machine defaults; the project config is checked into the
repo and describes how Workflo interacts with this project.

Schema v1 fields map directly to the `run_contract.md` contract.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

PROJECT_CONFIG_DIR = ".workflo"
PROJECT_CONFIG_FILE = PROJECT_CONFIG_DIR + "/config.yaml"
PROJECT_POLICY_FILE = PROJECT_CONFIG_DIR + "/policies.yaml"
RUNS_DIR = PROJECT_CONFIG_DIR + "/runs"
RECEIPTS_DIR = PROJECT_CONFIG_DIR + "/receipts"


@dataclass
class AgentConfig:
    enabled: bool = True
    max_steps: int = 50
    # Model/tool budgets are planner-side; project config can only narrow,
    # never widen, the runtime's security budgets.


@dataclass
class InferenceConfig:
    mode: str = "gateway"          # gateway | direct
    model: Optional[str] = None
    api_key_env: Optional[str] = None


@dataclass
class ProjectConfig:
    """`.workflo/config.yaml` — schema v1."""

    # project
    name: str = ""
    test_command: str = "pytest"
    start_command: str = ""
    start_port: int = 0
    workspace: str = "."

    # execution / resources
    timeout_seconds: int = 300
    memory_mb: int = 4096
    cpu_cores: float = 2.0
    pids: int = 256

    # security
    security_mode: str = "compatible"   # compatible | hardened
    landlock_requested: bool = True

    # agent
    agent: AgentConfig = field(default_factory=AgentConfig)

    # inference
    inference: InferenceConfig = field(default_factory=InferenceConfig)

    # network
    network_allowlist: list[str] = field(default_factory=list)

    # outputs
    receipts_dir: str = RECEIPTS_DIR
    runs_dir: str = RUNS_DIR

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "project": {
                "name": self.name,
                "test_command": self.test_command,
                "start_command": self.start_command,
                "start_port": self.start_port,
                "workspace": self.workspace,
            },
            "execution": {
                "timeout_seconds": self.timeout_seconds,
            },
            "resources": {
                "memory_mb": self.memory_mb,
                "cpu_cores": self.cpu_cores,
                "pids": self.pids,
            },
            "security": {
                "mode": self.security_mode,
                "landlock_requested": self.landlock_requested,
            },
            "agent": {
                "enabled": self.agent.enabled,
                "max_steps": self.agent.max_steps,
            },
            "inference": {
                "mode": self.inference.mode,
                "model": self.inference.model,
                "api_key_env": self.inference.api_key_env,
            },
            "network": {
                "allowlist": list(self.network_allowlist),
            },
            "outputs": {
                "receipts_dir": self.receipts_dir,
                "runs_dir": self.runs_dir,
            },
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ProjectConfig":
        cfg = ProjectConfig()
        if not isinstance(data, dict):
            return cfg
        p = data.get("project", {})
        cfg.name = str(p.get("name", ""))
        cfg.test_command = str(p.get("test_command", "pytest"))
        cfg.start_command = str(p.get("start_command", ""))
        cfg.start_port = int(p.get("start_port", 0) or 0)
        cfg.workspace = str(p.get("workspace", "."))
        e = data.get("execution", {})
        cfg.timeout_seconds = int(e.get("timeout_seconds", 300))
        r = data.get("resources", {})
        cfg.memory_mb = int(r.get("memory_mb", 4096))
        cfg.cpu_cores = float(r.get("cpu_cores", 2.0))
        cfg.pids = int(r.get("pids", 256))
        s = data.get("security", {})
        cfg.security_mode = str(s.get("mode", "compatible"))
        cfg.landlock_requested = bool(s.get("landlock_requested", True))
        a = data.get("agent", {})
        cfg.agent = AgentConfig(
            enabled=bool(a.get("enabled", True)),
            max_steps=int(a.get("max_steps", 50)),
        )
        i = data.get("inference", {})
        cfg.inference = InferenceConfig(
            mode=str(i.get("mode", "gateway")),
            model=i.get("model"),
            api_key_env=i.get("api_key_env"),
        )
        n = data.get("network", {})
        cfg.network_allowlist = [str(x) for x in n.get("allowlist", [])]
        o = data.get("outputs", {})
        cfg.receipts_dir = str(o.get("receipts_dir", RECEIPTS_DIR))
        cfg.runs_dir = str(o.get("runs_dir", RUNS_DIR))
        return cfg

    # ---------- I/O ----------

    @staticmethod
    def find(project_root: Optional[Path] = None) -> Optional[Path]:
        """Locate `.workflo/config.yaml` from a project root."""
        root = Path(project_root) if project_root else Path.cwd()
        candidate = root / PROJECT_CONFIG_DIR / "config.yaml"
        return candidate if candidate.exists() else None

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def save(self, project_root: Optional[Path] = None) -> Path:
        root = Path(project_root) if project_root else Path.cwd()
        dir_path = root / PROJECT_CONFIG_DIR
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / "config.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, default_flow_style=False,
                           sort_keys=False, allow_unicode=True)
        return path

    def ensure_dirs(self, project_root: Optional[Path] = None) -> Path:
        root = Path(project_root) if project_root else Path.cwd()
        (root / PROJECT_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        (root / RUNS_DIR).mkdir(parents=True, exist_ok=True)
        (root / RECEIPTS_DIR).mkdir(parents=True, exist_ok=True)
        return root / PROJECT_CONFIG_DIR


DEFAULT_POLICIES_YAML = """version: 1

# Workflo per-project network policy. The sandbox is default-deny;
# add ONLY the hosts this project legitimately needs to reach.
network:
  policy:
    allow:
      # - "npmjs.com"      # package registry during prep
      # - "my-api.example.com"

# Resource policy: values narrow the runtime defaults; they never widen.
resources:
  memory_mb: 4096
  pids: 256

# Security: set to "hardened" when this project's CI must fail closed.
security:
  mode: compatible
"""
