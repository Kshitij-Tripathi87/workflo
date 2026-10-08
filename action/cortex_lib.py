"""Policy resolution hierarchy for the Cortex Autopilot Impact Gate.

Three layers, in priority order:
  1. Action input (highest priority) — `INPUT_POLICY` env var.
  2. Repo `cortex.yml` — committed by the user alongside the code.
  3. Backend defaults (lowest priority) — fetched from /policy/defaults.

This makes per-PR overrides possible without forcing the user to update
cortex.yml, while still allowing teams to ship a baseline policy that
applies to every PR.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Layer 3: Backend defaults — what the server returns when nothing else is set
# ---------------------------------------------------------------------------
DEFAULT_POLICIES: List[Dict[str, Any]] = [
    {
        "name": "Cortex Autopilot default — block on critical severity",
        "max_severity": 75,
        "max_blast_radius": 10,
        "action": "block",
    },
    {
        "name": "Cortex Autopilot default — warn on ML downstream impact",
        "max_severity": 50,
        "max_blast_radius": 3,
        "action": "warn",
    },
]


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        print(f"::warning::Failed to parse cortex.yml at {path}: {e}")
        return {}


def parse_inline_policy(raw: str) -> Optional[List[Dict[str, Any]]]:
    """Parse the `INPUT_POLICY` env var (a YAML string).

    Returns a list of policy dicts, or None if the input was empty or
    could not be parsed.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"::warning::Failed to parse inline policy YAML: {e}")
        return None
    if parsed is None:
        return None
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return None


def resolve_policies(
    inline: Optional[List[Dict[str, Any]]],
    repo_config: Dict[str, Any],
    backend_defaults: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Resolve the active policy list given all three sources.

    The first non-empty source wins. We never silently merge — that
    would make it impossible to reason about which rules apply.
    """
    if inline:
        return inline
    repo_policies = repo_config.get("policies") or []
    if repo_policies:
        return repo_policies
    return backend_defaults or DEFAULT_POLICIES


def detect_change_from_diff(repo_root: Path) -> Dict[str, Any]:
    """Best-effort detection of a dbt/Snowflake change from git diff.

    Returns an empty dict if no change can be detected. The caller will
    then fall back to the schema declared in cortex.yml.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD^", "HEAD"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return {}

    changed_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    sql_files = [f for f in changed_files if f.endswith(".sql")]
    yml_files = [f for f in changed_files if f.endswith((".yml", ".yaml"))]

    if not sql_files and not yml_files:
        return {}

    changed = {"action": "schema change - review", "files": changed_files}

    if sql_files:
        changed["dbt_models"] = [Path(f).stem for f in sql_files]

    return changed


def build_request_payload(
    config: Dict[str, Any],
    schema_change: Optional[Dict[str, Any]],
    policies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    asset_urn = (
        schema_change.get("asset_urn") if schema_change else None
    ) or config.get("asset_urn")

    if not asset_urn:
        raise ValueError(
            "No asset_urn found. Provide one in cortex.yml or schema_change input."
        )

    change = (schema_change or {}).get("change") or schema_change or config.get("change", {})

    objective = config.get("objective", "minimize incident risk")
    constraints = config.get("constraints", {})

    payload: Dict[str, Any] = {
        "asset_urn": asset_urn,
        "objective": objective,
        "constraints": constraints,
    }
    if policies:
        payload["policies"] = policies

    return payload


def write_outputs(verdict: str, blast_radius: int, plan_id: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as f:
        f.write(f"verdict={verdict}\n")
        f.write(f"blast_radius={blast_radius}\n")
        f.write(f"plan_id={plan_id}\n")


def post_pr_comment(pr_number: int, body: str) -> None:
    import httpx

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY not set")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("INPUT_GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = httpx.post(url, json={"body": body}, headers=headers, timeout=15.0)
    if resp.status_code >= 400:
        raise RuntimeError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")
