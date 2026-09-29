"""workflo doctor — environment readiness report.

For every declared capability, distinguish:

    OK              — verified present and functional
    DEGRADED        — usable, but with reduced security guarantees
                      (e.g. Landlock absent on a compatible-mode host)
    NOT CONFIGURED  — optional and turns Workflo behavior off
    UNAVAILABLE     — required for the run contract and missing

Overall status:

    READY           — everything the run contract needs is present
    DEGRADED        — runnable in compatible mode (reduced guarantees)
    NOT READY       — a required capability is UNAVAILABLE
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

OK = "OK"
DEGRADED = "DEGRADED"
NOT_CONFIGURED = "NOT_CONFIGURED"
UNAVAILABLE = "UNAVAILABLE"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


@dataclass
class DoctorReport:
    sections: dict[str, list[Check]] = field(default_factory=dict)

    def add(self, section: str, check: Check) -> None:
        self.sections.setdefault(section, []).append(check)

    @property
    def overall(self) -> str:
        required_missing = any(
            c.status == UNAVAILABLE
            for section in ("Host", "Sandbox")
            for c in self.sections.get(section, [])
        )
        if required_missing:
            return "NOT READY"
        degraded = any(
            c.status == DEGRADED
            for sec in ("Host", "Sandbox") for c in self.sections.get(sec, [])
        )
        return "DEGRADED" if degraded else "READY"


# ---------------------------------------------------------------------------
# Individual checks — pure and separately testable
# ---------------------------------------------------------------------------

def check_host_linux() -> Check:
    if sys_platform() == "linux":
        return Check("Operating system", OK, "linux")
    return Check("Operating system", UNAVAILABLE,
                 f"{sys_platform()} — Workflo sandboxing requires Linux "
                 "(WSL2 is the supported Windows path)")


def check_kernel() -> Check:
    release = os.uname().release if hasattr(os, "uname") else ""
    if sys_platform() != "linux":
        return Check("Kernel", UNAVAILABLE, "not Linux")
    return Check("Kernel", OK, release)


def check_tool(name: str) -> Check:
    path = shutil.which(name)
    if path:
        return Check(name, OK, path)
    return Check(name, UNAVAILABLE, "not on PATH")


def check_cgroups_v2() -> Check:
    if sys_platform() != "linux":
        return Check("cgroups v2", UNAVAILABLE, "not Linux")
    if Path("/sys/fs/cgroup/cgroup.controllers").exists():
        return Check("cgroups v2", OK, "mounted")
    return Check("cgroups v2", UNAVAILABLE, "cgroup.controllers not found")


def check_seccomp() -> Check:
    if sys_platform() != "linux":
        return Check("seccomp", UNAVAILABLE, "not Linux")
    try:
        with open("/proc/self/status") as f:
            if "Seccomp:" in f.read():
                return Check("seccomp", OK, "enabled")
    except OSError:
        pass
    return Check("seccomp", UNAVAILABLE, "not exposed in /proc/self/status")


def check_landlock() -> Check:
    if sys_platform() != "linux":
        return Check("Landlock", UNAVAILABLE, "not Linux")
    from sandbox_runtime.landlock import probe_abi
    abi = probe_abi()
    if abi > 0:
        return Check("Landlock", OK, f"kernel ABI {abi}")
    return Check("Landlock", DEGRADED,
                 "kernel 5.13+ Landlock API not available — "
                 "hardened mode will refuse to run")


def check_network_tools() -> list[Check]:
    return [check_tool(t) for t in ("ip", "nft", "dnsmasq")]


def check_suid_supported() -> Check:
    # userns unshare smoke test
    if sys_platform() != "linux":
        return Check("userns+unshare", UNAVAILABLE, "not Linux")
    result = subprocess.run(["unshare", "--user", "--map-root-user", "true"],
                            capture_output=True)
    if result.returncode == 0:
        return Check("userns+unshare", OK, "")
    return Check("userns+unshare", UNAVAILABLE,
                 (result.stderr or b"").decode(errors="replace")[:80])


# ---------------------------------------------------------------------------
# Project / AI / signing
# ---------------------------------------------------------------------------

def check_project_config(project_root: Optional[Path]) -> list[Check]:
    from workflo_utils.project_config import ProjectConfig
    path = ProjectConfig.find(project_root)
    if path is None:
        return [Check("config file", NOT_CONFIGURED,
                      "no .workflo/config.yaml — run `workflo init`")]
    cfg = ProjectConfig.load(path)
    checks = [Check("config file", OK, str(path))]
    checks.append(Check("test command", OK if cfg.test_command
                        else NOT_CONFIGURED, cfg.test_command))
    checks.append(Check("start command",
                        OK if cfg.start_command else NOT_CONFIGURED,
                        cfg.start_command or "needed for web/deep tiers"))
    checks.append(Check("port",
                        OK if cfg.start_port else NOT_CONFIGURED,
                        str(cfg.start_port)))
    return checks


def check_ai() -> list[Check]:
    base = os.environ.get("WORKFLO_LLM_BASE_URL")
    mode = os.environ.get("WORKFLO_LLM_MODE", "direct")
    key = bool(os.environ.get("WORKFLO_LLM_API_KEY"))
    checks = []
    if base:
        checks.append(Check("inference endpoint", OK, f"{mode} @ {base}"))
        checks.append(Check("inference credentials",
                            OK if key else NOT_CONFIGURED,
                            "WORKFLO_LLM_API_KEY" if key
                            else "needed only for direct mode"))
    else:
        checks.append(Check("inference endpoint", NOT_CONFIGURED,
                            "agent tier disabled (task-spec fallback only)"))
    return checks


def check_signing() -> list[Check]:
    from workflo_utils.config import DEFAULT_CONFIG_DIR
    priv = DEFAULT_CONFIG_DIR / "signing" / "private_key.pem"
    pub = DEFAULT_CONFIG_DIR / "signing" / "public_key.pem"
    if priv.exists() and pub.exists():
        return [Check("signing identity", OK, str(pub))]
    return [Check("signing identity", NOT_CONFIGURED,
                  "no keypair — run `workflo keygen`")]


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def run_doctor(project_root: Optional[Path] = None) -> DoctorReport:
    report = DoctorReport()

    report.add("Host", check_host_linux())
    report.add("Host", check_kernel())
    report.add("Host", check_suid_supported())

    report.add("Sandbox", check_tool("bwrap"))
    report.add("Sandbox", check_cgroups_v2())
    report.add("Sandbox", check_seccomp())
    report.add("Sandbox", check_landlock())
    for c in check_network_tools():
        report.add("Sandbox", c)

    for c in check_project_config(project_root):
        report.add("Project", c)
    for c in check_ai():
        report.add("AI", c)
    for c in check_signing():
        report.add("Signing", c)

    return report


def sys_platform() -> str:
    import sys
    return sys.platform


def render(report: DoctorReport) -> str:
    ic = {OK: "+", DEGRADED: "~", NOT_CONFIGURED: "o", UNAVAILABLE: "!"}
    lines = ["Workflo Doctor", ""]
    for section, checks in report.sections.items():
        lines.append(section)
        for c in checks:
            line = f"  [{ic[c.status]}] {c.name}"
            if c.detail:
                line += f"  ({c.detail})"
            lines.append(line)
        lines.append("")
    lines.append(f"Security mode: see project config (mode=hardened locks it)")
    lines.append(f"STATUS: {report.overall}")
    return "\n".join(lines)
