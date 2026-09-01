"""SARIF 2.1.0 reporter — GitHub Code Scanning compatible."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from ..orchestrator import ValidationResult

SARIF_SCHEMA = "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json"

SEVERITY_TO_SARIF_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}


def write(result: ValidationResult, out_path: Path) -> None:
    """Emit SARIF 2.1.0 JSON to out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rules: dict[str, dict] = {}
    results: list[dict] = []

    for f in result.findings:
        rule_id = f.id
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": f.pattern or rule_id,
                "shortDescription": {"text": f.pattern or "architecture finding"},
                "fullDescription": {"text": f.message},
                "defaultConfiguration": {"level": SEVERITY_TO_SARIF_LEVEL.get(f.severity, "warning")},
                "properties": {
                    "category": f.category,
                    "severity": f.severity,
                    "tags": ["architecture", f.category],
                },
            }

        location: dict = {}
        if f.file:
            location = {
                "physicalLocation": {
                    "artifactLocation": {"uri": _repo_relative_uri(f.file)},
                    "region": {"startLine": max(1, int(f.line or 1))},
                }
            }

        results.append({
            "ruleId": rule_id,
            "level": SEVERITY_TO_SARIF_LEVEL.get(f.severity, "warning"),
            "message": {"text": f"{f.message}\n\nSuggestion: {f.suggestion}"},
            "locations": [location] if location else [],
            "properties": {
                "category": f.category,
                "severity": f.severity,
                "baseline_regression": f.baseline_regression,
            },
        })

    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "validate-phase2",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/workflowpro-tests/validate-phase2",
                        "rules": list(rules.values()),
                    }
                },
                "originalUriBaseIds": {
                    "REPO_ROOT": {"uri": _repo_root_uri(result.repo)}
                },
                "results": results,
                "properties": {
                    "baseline": result.baseline,
                    "head": result.head,
                    "model": result.model,
                    "flags": result.flags,
                    "gates": [g.to_dict() for g in result.gates],
                },
            }
        ],
    }

    out_path.write_text(
        json.dumps(sarif, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _repo_relative_uri(path: str) -> str:
    """Return a URI fragment for SARIF physical location."""
    return urllib.parse.quote(path, safe="/._-~")


def _repo_root_uri(repo_url: str) -> str:
    """Return a URI string for the repo root (used as originalUriBaseId)."""
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    if cleaned.startswith(("http://", "https://", "git@")):
        return cleaned + "/"
    return cleaned + "/"
