"""Security-stage orchestration for the worker: resolve config, start the app,
run security probes (tenant isolation, etc.), stop the app, and produce the
report payload.

The security tier uses the SAME app bootstrap primitive as the web tier
(start_app_under_test) but runs API-based security probes instead of
Playwright browser probes. This ensures security tests run against a live
application with proper multi-tenant isolation.

Configuration contract (same as web tier):
    security:
      start_command: "python app.py"
      port: 5000

Resolution precedence (spec/env wins over workflo.yaml):
    1. WORKFLO_SECURITY_START_COMMAND / WORKFLO_SECURITY_PORT env vars
       (set by the executor from the run spec's env)
    2. WORKFLO_START_COMMAND / WORKFLO_WEB_PORT env vars (fallback to web config)
    3. workflo.yaml in the cloned repo root
    4. neither -> fail closed with an actionable error naming what's missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from workflo_worker.web.app_starter import (
    start_app_under_test,
    stop_app_under_test,
)
from probe_engine import ProbeConfig, ProbeGenerator, ProbeRunner


class SecurityConfigError(Exception):
    """Raised when the security tier is requested but its config is unresolvable."""


def resolve_security_config(repo_path: str, env: Optional[dict] = None) -> dict:
    """Resolve (start_command, port) for the security tier, failing fast.

    Args:
        repo_path: the cloned repo root (workflo.yaml is read from here).
        env: dict of env var values (defaults to os.environ). Keys honored:
            WORKFLO_SECURITY_START_COMMAND, WORKFLO_SECURITY_PORT,
            WORKFLO_START_COMMAND, WORKFLO_WEB_PORT (fallback).

    Returns:
        {"start_command": str, "port": int}

    Raises:
        SecurityConfigError: security tier requested but neither source provides
            the required values. Message names exactly what's missing.
    """
    env = env if env is not None else os.environ

    # Primary: security-specific env vars
    start_command = env.get("WORKFLO_SECURITY_START_COMMAND")
    port_raw = env.get("WORKFLO_SECURITY_PORT")

    # Fallback: web tier env vars (for configs that use the same app)
    if not start_command:
        start_command = env.get("WORKFLO_START_COMMAND")
    if not port_raw:
        port_raw = env.get("WORKFLO_WEB_PORT")

    # Fall back to workflo.yaml in the repo root if env is absent.
    if not start_command or not port_raw:
        yaml_cfg = _read_workflo_yaml(repo_path)
        if not start_command:
            start_command = yaml_cfg.get("start_command")
        if not port_raw:
            port_raw = yaml_cfg.get("port")

    missing = []
    if not start_command:
        missing.append("start_command")
    if not port_raw:
        missing.append("port")

    if missing:
        raise SecurityConfigError(
            f"security tier requested but missing: {', '.join(missing)}. "
            f"Provide them via WORKFLO_SECURITY_START_COMMAND/WORKFLO_SECURITY_PORT env, "
            f"or WORKFLO_START_COMMAND/WORKFLO_WEB_PORT (web tier fallback), "
            f"the CLI's --start-command/--port flags, or a workflo.yaml in "
            f"the repo root with:\n"
            f"  security:\n"
            f"    start_command: <cmd>\n"
            f"    port: <n>\n"
            f"  # or use web:\n"
            f"  web:\n"
            f"    start_command: <cmd>\n"
            f"    port: <n>"
        )

    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        raise SecurityConfigError(f"security port is not an integer: {port_raw!r}")
    if not (1 <= port <= 65535):
        raise SecurityConfigError(f"security port out of range: {port}")

    return {"start_command": start_command, "port": port}


def _read_workflo_yaml(repo_path: str) -> dict:
    """Read the `security:` (or `web:` as fallback) section of workflo.yaml from the repo root.

    Returns an empty dict when absent or invalid — resolution falls back
    to env/CLI flags, and if those are also absent, resolve_security_config
    raises with a message naming exactly what's missing.
    """
    candidates = ["workflo.yaml", "workflo.yml"]
    repo = Path(repo_path)
    for name in candidates:
        path = repo / name
        if not path.is_file():
            continue
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(data, dict):
            # Check security section first, then fall back to web
            for section_name in ("security", "web"):
                if isinstance(data.get(section_name), dict):
                    section = data[section_name]
                    return {
                        "start_command": section.get("start_command"),
                        "port": section.get("port"),
                    }
    return {}


def run_security_stage(repo_path: str, env: Optional[dict] = None) -> dict:
    """Run the full security stage and return the WORKFLO_SECURITY_PROBES payload.

    The payload is ALWAYS produced (even on config/app/probe failures) —
    the executor's receipt distinguishes "security tier not requested"
    (no line) from "security tier ran and failed" (line with failures).
    This matches the web-stage / model-teardown discipline.

    Returns:
        {"base_url": str, "probes": [...], "app_start_error": str|None}
    """
    try:
        cfg = resolve_security_config(repo_path, env)
    except SecurityConfigError as e:
        return {"base_url": "", "probes": [], "app_start_error": str(e)}

    base_url = f"http://127.0.0.1:{cfg['port']}"
    proc = None
    try:
        # Set WORKFLO_API_BASE_URL for the security probes to use
        old_api_base = os.environ.get("WORKFLO_API_BASE_URL")
        os.environ["WORKFLO_API_BASE_URL"] = base_url

        proc = start_app_under_test(repo_path, cfg["start_command"], cfg["port"])
        
        # Run security probes using ProbeRunner (API-based tenant isolation checks)
        security_probes = _run_security_probes(base_url)
        return {"base_url": base_url, "probes": security_probes, "app_start_error": None}
    except Exception as e:
        # App crashed / port never opened / probe infrastructure failed —
        # all valid reportable outcomes.
        return {
            "base_url": base_url,
            "probes": [],
            "app_start_error": f"{type(e).__name__}: {e}",
        }
    finally:
        # Restore original WORKFLO_API_BASE_URL if it existed
        if old_api_base is not None:
            os.environ["WORKFLO_API_BASE_URL"] = old_api_base
        else:
            os.environ.pop("WORKFLO_API_BASE_URL", None)
        stop_app_under_test(proc)


def _run_security_probes(base_url: str) -> list[dict]:
    """Run the default security probes (tenant isolation) against the app.

    Uses the probe_engine's default security probes and ProbeRunner.
    Returns a list of probe results in the format expected by the receipt.
    """
    try:
        # Generate default security probe config
        config = ProbeGenerator.default_config(groups=["security"])
        
        # Create a simple HTTP client for the probes
        import requests
        
        class _ProbeHttpClient:
            def __init__(self, base_url: str, tenant_id: str, auth_token: str = "mock-token"):
                self.base_url = base_url.rstrip("/")
                self.tenant_id = tenant_id
                self.auth_token = auth_token

            def _headers(self) -> dict:
                return {
                    "X-Tenant-ID": self.tenant_id,
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json",
                }

            def get(self, path: str):
                return requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=10)

            def post(self, path: str, json=None):
                return requests.post(f"{self.base_url}{path}", json=json, headers=self._headers(), timeout=10)

            def put(self, path: str, json=None):
                return requests.put(f"{self.base_url}{path}", json=json, headers=self._headers(), timeout=10)

            def delete(self, path: str):
                return requests.delete(f"{self.base_url}{path}", headers=self._headers(), timeout=10)

        creator_client = _ProbeHttpClient(base_url, tenant_id="company1")
        intruder_client = _ProbeHttpClient(base_url, tenant_id="company2")
        
        runner = ProbeRunner(config)
        
        # Create a test resource first
        response = creator_client.post("/api/v1/projects", json={"name": "workflo-security-probe-resource"})
        if response.status_code not in (200, 201):
            return [{
                "name": "resource_creation",
                "passed": False,
                "detail": f"Cannot create resource for probing (HTTP {response.status_code}) — app-under-test not probe-ready"
            }]
        
        resource_id = response.json().get("id")
        if not resource_id:
            return [{
                "name": "resource_creation",
                "passed": False,
                "detail": "Create response missing id — app-under-test not probe-ready"
            }]

        try:
            # Run all security probes
            summary = runner.run_all(
                creator_client=creator_client,
                intruder_client=intruder_client,
                resource_id=resource_id,
            )
            
            # Convert to the format expected by the receipt
            results = []
            for probe_result in summary.results:
                results.append({
                    "name": probe_result.name,
                    "passed": probe_result.passed,
                    "detail": probe_result.detail,
                })
            return results
        finally:
            # Clean up the test resource
            try:
                creator_client.delete(f"/api/v1/projects/{resource_id}")
            except Exception:
                pass
                
    except Exception as e:
        return [{
            "name": "security_probe_infrastructure",
            "passed": False,
            "detail": f"{type(e).__name__}: {e}"
        }]