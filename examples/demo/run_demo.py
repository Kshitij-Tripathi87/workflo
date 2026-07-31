"""
Cortex Autopilot — Working Demo Runner.

Walks through the full CI/CD Impact Gate flow without requiring GitHub:
  1. Loads the sample dbt manifest.json + catalog.json from disk
  2. Simulates a "risky change" by computing a baseline snapshot
  3. Calls the /future-search/run endpoint with declared policies
  4. Prints the verdict, PR comment, and Slack alert

Usage:
    # Start the backend first:
    #   cd backend && uvicorn app.main:app --reload --port 8000
    # Then from the repo root:
    python examples/demo/run_demo.py

Requirements:
    pip install httpx pyyaml
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DBT = REPO_ROOT / "examples" / "sample_dbt_project"
MANIFEST = SAMPLE_DBT / "target" / "manifest.json"
CATALOG = SAMPLE_DBT / "target" / "catalog.json"
CORTEX_YML = SAMPLE_DBT / "cortex.yml"

SERVER_URL = os.environ.get("CORTEX_SERVER", "http://localhost:8000")


def _load_cortex_yml() -> Dict[str, Any]:
    if not CORTEX_YML.exists():
        return {}
    return yaml.safe_load(CORTEX_YML.read_text()) or {}


def _check_prerequisites() -> None:
    if not MANIFEST.exists():
        sys.exit(f"ERROR: manifest not found at {MANIFEST}")
    if not CATALOG.exists():
        sys.exit(f"ERROR: catalog not found at {CATALOG}")
    print(f"manifest.json : {MANIFEST}")
    print(f"catalog.json  : {CATALOG}")
    print(f"cortex.yml    : {CORTEX_YML}")
    print(f"server        : {SERVER_URL}")
    print()


async def _healthcheck(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{SERVER_URL}/health", timeout=5.0)
        if r.status_code == 200:
            print(f"[ok] backend healthy: {r.json()}")
            return True
    except httpx.HTTPError as e:
        print(f"[warn] backend unreachable: {e}")
    return False


async def _verify_connectors(client: httpx.AsyncClient) -> List[str]:
    try:
        r = await client.get(f"{SERVER_URL}/future-search/connectors", timeout=5.0)
        if r.status_code == 200:
            connectors = r.json().get("connectors", [])
            print(f"[ok] registered connectors: {connectors}")
            return connectors
    except httpx.HTTPError:
        pass
    return []


async def _evaluate(client: httpx.AsyncClient, payload: Dict[str, Any]) -> Dict[str, Any]:
    print()
    print("=" * 60)
    print("POST /future-search/run")
    print("=" * 60)
    print(json.dumps(payload, indent=2, default=str))
    print()

    r = await client.post(
        f"{SERVER_URL}/future-search/run",
        json=payload,
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def _print_pr_comment(plan: Dict[str, Any], policy_result: Dict[str, Any]) -> None:
    """Format the PR comment the GitHub Action would post."""
    ranked = plan.get("ranked_choice", {})
    severity = ranked.get("predicted_severity", 0)
    blast = ranked.get("predicted_blast_radius", 0)
    asset = plan.get("asset_urn", "asset")
    verdict = policy_result.get("verdict", "pass") if policy_result else "pass"

    severity_band = (
        "CRITICAL" if severity >= 75
        else "HIGH" if severity >= 50
        else "MEDIUM" if severity >= 25
        else "LOW"
    )
    emoji = {"pass": "[OK]", "warn": "[WARN]", "block": "[BLOCK]"}.get(verdict, "[?]")

    print("-" * 60)
    print("GitHub PR comment:")
    print("-" * 60)
    print(f"{emoji} Cortex Autopilot {verdict.upper()}")
    print(f"Asset    : {asset}")
    print(f"Severity : {severity_band} ({severity}/100)")
    print(f"Blast    : {blast} downstream assets")

    if policy_result and policy_result.get("results"):
        print("\nPolicy evaluation:")
        for res in policy_result["results"]:
            print(f"  - {res.get('policy_name')}: {res.get('verdict').upper()} - {res.get('reason')}")

    rationale = plan.get("explanation", [])
    if rationale:
        print("\nWhy this verdict:")
        for line in rationale[:4]:
            print(f"  * {line}")

    print("-" * 60)


def _print_slack_alert(plan: Dict[str, Any], policy_result: Dict[str, Any]) -> None:
    """Format the Slack alert message."""
    ranked = plan.get("ranked_choice", {})
    severity = ranked.get("predicted_severity", 0)
    blast = ranked.get("predicted_blast_radius", 0)
    asset = plan.get("asset_urn", "asset")
    verdict = policy_result.get("verdict", "pass") if policy_result else "pass"

    if verdict not in ("warn", "block"):
        print("(Slack alert suppressed — verdict is 'pass')\n")
        return

    print("-" * 60)
    print("Slack alert payload:")
    print("-" * 60)
    payload = {
        "channel": "#data-platform",
        "text": (
            f":rotating_light: *Cortex Autopilot {verdict.upper()}*\n"
            f"Asset: `{asset}`\n"
            f"Severity: {severity}/100\n"
            f"Blast radius: {blast} downstream assets"
        ),
    }
    print(json.dumps(payload, indent=2))
    print("-" * 60)


async def main() -> int:
    _check_prerequisites()
    cfg = _load_cortex_yml()
    if not cfg:
        sys.exit(f"ERROR: cortex.yml missing at {CORTEX_YML}")

    asset_urn = cfg.get("asset_urn")
    policies = cfg.get("policies", [])
    objective = cfg.get("objective", "minimize incident risk")

    if not asset_urn:
        sys.exit("ERROR: cortex.yml has no asset_urn")

    async with httpx.AsyncClient() as client:
        healthy = await _healthcheck(client)
        if not healthy:
            print()
            print("Start the backend with:")
            print("  cd backend && uvicorn app.main:app --reload --port 8000")
            return 1

        connectors = await _verify_connectors(client)
        if "dbt" not in connectors:
            print("[warn] 'dbt' connector not registered — falling back to datahub")

        # Use the dbt connector so the impact is read from the manifest.json
        payload = {
            "asset_urn": asset_urn,
            "objective": objective,
            "connector": "dbt",
            "policies": policies,
        }

        plan = await _evaluate(client, payload)
        policy_result = plan.get("policy_result") or {}
        verdict = policy_result.get("verdict", "pass")

        _print_pr_comment(plan, policy_result)
        _print_slack_alert(plan, policy_result)

        print()
        print("=" * 60)
        print(f"Final verdict: {verdict.upper()}")
        print("=" * 60)

        return 0 if verdict == "pass" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
