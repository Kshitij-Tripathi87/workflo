"""Cortex Autopilot Impact Gate — entrypoint.

Reads cortex.yml from the repo, builds a FutureSearchRequest, calls the
Cortex server, evaluates the policy summary, posts a PR comment, and
optionally notifies Slack. Exits non-zero when the verdict is `block`.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, List

from cortex_lib import (
    build_request_payload,
    load_config,
    detect_change_from_diff,
    write_outputs,
    post_pr_comment,
    parse_inline_policy,
    resolve_policies,
    DEFAULT_POLICIES,
)
from report import build_pr_comment, build_slack_message
from notify_slack import post_slack


def main() -> int:
    cortex_yml_path = os.environ.get("INPUT_CORTEX_YML", "cortex.yml")
    schema_change_raw = os.environ.get("INPUT_SCHEMA_CHANGE", "").strip()
    inline_policy_yaml = os.environ.get("INPUT_POLICY", "").strip()
    slack_webhook = os.environ.get("INPUT_SLACK_WEBHOOK", "").strip()
    cortex_server = os.environ.get("INPUT_CORTEX_SERVER", "http://localhost:8000").rstrip("/")
    api_token = os.environ.get("INPUT_API_TOKEN", "").strip()

    repo_root = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    pr_number = _parse_pr_number()

    config = load_config(repo_root / cortex_yml_path)

    inline_policy = parse_inline_policy(inline_policy_yaml)
    backend_defaults = fetch_backend_defaults(cortex_server, api_token)
    policies = resolve_policies(
        inline=inline_policy,
        repo_config=config,
        backend_defaults=backend_defaults,
    )

    if inline_policy:
        print(f"::notice::Using {len(policies)} inline policy(ies)")
    elif config.get("policies"):
        print(f"::notice::Using {len(policies)} policy(ies) from cortex.yml")
    else:
        print(
            f"::notice::Using {len(policies)} default policy(ies) "
            "from Cortex Autopilot server"
        )

    schema_change: Optional[Dict[str, Any]] = None
    if schema_change_raw:
        try:
            schema_change = json.loads(schema_change_raw)
        except json.JSONDecodeError as e:
            print(f"::error::Invalid schema_change JSON: {e}")
            return 2

    if not schema_change:
        schema_change = detect_change_from_diff(repo_root)

    payload = build_request_payload(config, schema_change, policies)

    try:
        plan, policy_result = call_cortex_server(cortex_server, payload, api_token)
    except RuntimeError as e:
        print(f"::error::Cortex server call failed: {e}")
        print(f"::error::Hint: start Cortex with `docker run -p 8000:8000 cortex/server`")
        return 2

    verdict = policy_result.get("verdict", "pass") if policy_result else "pass"
    if "block" not in verdict and "warn" not in verdict and "pass" not in verdict:
        verdict = "pass"

    blast_radius = plan.get("ranked_choice", {}).get("predicted_blast_radius", 0)
    plan_id = plan.get("plan_id", "")

    write_outputs(verdict=verdict, blast_radius=blast_radius, plan_id=plan_id)

    auto_fix = fetch_auto_fix(
        server=cortex_server,
        plan=plan,
        verdict=verdict,
        token=api_token,
    )

    comment_body = build_pr_comment(plan, policy_result, verdict, auto_fix=auto_fix)
    print(comment_body)

    if pr_number is not None and _can_post_comments():
        try:
            post_pr_comment(pr_number, comment_body)
        except RuntimeError as e:
            print(f"::warning::Failed to post PR comment: {e}")

    if slack_webhook and verdict in ("warn", "block"):
        slack_message = build_slack_message(plan, policy_result, verdict, pr_number)
        try:
            post_slack(slack_webhook, slack_message)
        except RuntimeError as e:
            print(f"::warning::Slack notification failed: {e}")

    if verdict == "block":
        print("::error::Cortex policy gate BLOCKED this change.")
        return 1

    return 0


def _parse_pr_number() -> Optional[int]:
    ref = os.environ.get("GITHUB_REF", "")
    if "/pull/" in ref:
        try:
            return int(ref.rsplit("/", 1)[-1])
        except (ValueError, IndexError):
            return None

    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if event_path and Path(event_path).exists():
        try:
            event = json.loads(Path(event_path).read_text())
            if "pull_request" in event and "number" in event["pull_request"]:
                return int(event["pull_request"]["number"])
        except Exception:
            return None

    return None


def _can_post_comments() -> bool:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("INPUT_GITHUB_TOKEN")
    return bool(token)


def call_cortex_server(
    server: str,
    payload: Dict[str, Any],
    token: str,
):
    import httpx

    url = f"{server}/future-search/run"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not reach Cortex server at {server}: {e}")

    if resp.status_code != 200:
        raise RuntimeError(
            f"Cortex returned {resp.status_code}: {resp.text[:300]}"
        )

    body = resp.json()
    policy_result = body.get("policy_result")
    return body, policy_result


def fetch_backend_defaults(server: str, token: str) -> Optional[list]:
    """Fetch the server-side default policy list.

    Returns None on any error — the resolver falls back to its own
    built-in defaults in that case.
    """
    import httpx

    url = f"{server}/policy/defaults"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            body = resp.json()
            policies = body.get("policies")
            if isinstance(policies, list) and policies:
                return policies
    except httpx.HTTPError:
        pass
    return None


_ACTION_TYPE_FOR_SCENARIO = {
    "schema_rename": "patch_sql",
    "schema_remove": "patch_sql",
    "type_change": "patch_sql",
    "owner_missing": "assign_owner",
    "pipeline_failure": "patch_dag",
    "dataset_deprecation": "archive_asset",
}


def fetch_auto_fix(
    server: str,
    plan: Dict[str, Any],
    verdict: str,
    token: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a ready-to-apply artifact from /artifacts/generate.

    Returns None for `pass` verdicts (nothing to fix) or on any error.
    The artifact is included in the PR comment so the developer can
    review and apply the migration.
    """
    if verdict == "pass":
        return None

    import httpx

    ranked = plan.get("ranked_choice", {}) or {}
    scenario_type = ranked.get("scenario_type", "auto_detected")
    action_type = _ACTION_TYPE_FOR_SCENARIO.get(scenario_type, "patch_sql")
    asset_urn = plan.get("asset_urn", "asset")
    asset_name = asset_urn.rsplit(":", 1)[-1] if ":" in asset_urn else asset_urn

    payload = {
        "action_type": action_type,
        "title": f"Suggested migration for {asset_name}",
        "rationale": (
            f"Auto-generated migration addressing scenario '{scenario_type}' "
            f"on asset {asset_name}. Review and apply."
        ),
        "impact_id": plan.get("plan_id", ""),
        "confidence": float(ranked.get("confidence", 0.7)),
        "risk": "low",
        "artifacts": [],
        "fallback_action": None,
    }

    url = f"{server}/artifacts/generate"
    params = {
        "scenario_type": scenario_type,
        "asset_name": asset_name,
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = httpx.post(
            url, params=params, json=payload, headers=headers, timeout=15.0
        )
    except httpx.HTTPError as e:
        print(f"::warning::Could not fetch auto-fix from {server}: {e}")
        return None

    if resp.status_code != 200:
        print(
            f"::warning::Auto-fix endpoint returned {resp.status_code}: "
            f"{resp.text[:200]}"
        )
        return None

    return resp.json()


if __name__ == "__main__":
    sys.exit(main())
