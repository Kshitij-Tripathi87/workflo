"""Synthetic dbt corpus generator for the Cortex Benchmark 2026.

Generates N synthetic dbt manifest.json files, each modeling the
structure of a real analytics warehouse. Output is reproducible given
the same seed.

Usage:
    python -m backend.tests.benchmark.repo_generator \
        --output-dir backend/tests/benchmark/corpus \
        --num-repos 100 \
        --num-changes-per-repo 100 \
        --seed 20260801
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


CHANGE_TYPES = [
    ("column_remove", 0.30),
    ("column_rename", 0.25),
    ("type_change", 0.15),
    ("add_not_null", 0.10),
    ("add_column", 0.10),
    ("no_change", 0.10),
]


# Severity bands used to bucket scores
BAND_BOUNDARIES = [(0, 24), (25, 49), (50, 74), (75, 100)]
BANDS = ["low", "medium", "high", "critical"]


def _band_for(score: int) -> str:
    for (lo, hi), band in zip(BAND_BOUNDARIES, BANDS):
        if lo <= score <= hi:
            return band
    return "critical"


def _pick_change_type(rng: random.Random) -> str:
    r = rng.random()
    cumulative = 0.0
    for name, weight in CHANGE_TYPES:
        cumulative += weight
        if r <= cumulative:
            return name
    return "no_change"


def _make_column_name(rng: random.Random) -> str:
    """Generate a realistic snake_case column name."""
    nouns = [
        "id", "name", "email", "amount", "count", "value",
        "date", "status", "type", "code", "score", "rate",
        "user_id", "order_id", "customer_id", "product_id",
        "created_at", "updated_at", "deleted_at",
    ]
    qualifiers = [
        "", "primary", "secondary", "first", "last",
        "total", "current", "previous", "next", "raw",
    ]
    return f"{rng.choice(qualifiers)}_{rng.choice(nouns)}".lstrip("_")


def _make_model_name(rng: random.Random, prefix: str, idx: int) -> str:
    families = ["orders", "customers", "products", "events", "transactions", "sessions", "subscriptions", "invoices", "users", "accounts"]
    kinds = ["core", "staging", "intermediate", "marts"]
    family = rng.choice(families)
    kind = rng.choice(kinds)
    return f"{prefix}_{family}_{kind}_{idx}"


def _generate_repo(rng: random.Random, repo_id: int) -> Dict[str, Any]:
    """Build a single synthetic manifest.json dict."""
    project_name = f"synth_{repo_id:04d}"

    # Repo shape: 20-200 models, 2-12 sources, average ~1.8 deps per model
    n_models = max(20, min(200, int(rng.gauss(60, 25))))
    n_sources = max(2, min(12, int(rng.gauss(4, 2))))

    # Build sources first
    sources: Dict[str, Dict[str, Any]] = {}
    source_ids: List[str] = []
    for s_idx in range(n_sources):
        src_name = f"raw_{rng.choice(['orders', 'customers', 'products', 'events', 'sessions'])}"
        src_id = f"source.{project_name}.raw.{src_name}_{s_idx}"
        source_ids.append(src_id)
        n_cols = rng.randint(3, 8)
        sources[src_id] = {
            "name": src_name,
            "resource_type": "source",
            "source_name": "raw",
            "package_name": project_name,
            "identifier": f"{src_name}_{s_idx}",
            "description": f"Synthetic raw source {src_name}",
            "columns": {
                _make_column_name(rng): {"name": _make_column_name(rng)} for _ in range(n_cols)
            },
            "tags": ["raw"],
        }

    # Build models in waves so dependencies go upstream -> downstream
    nodes: Dict[str, Dict[str, Any]] = {}
    parent_map: Dict[str, List[str]] = {}
    child_map: Dict[str, List[str]] = {}

    # First wave: models that depend directly on sources
    first_wave_size = max(2, n_sources)
    first_wave_ids: List[str] = []
    for m_idx in range(first_wave_size):
        node_id = f"model.{project_name}.stg_{m_idx}"
        first_wave_ids.append(node_id)
        parent = rng.choice(source_ids)
        n_cols = rng.randint(3, 8)
        nodes[node_id] = {
            "name": f"stg_{m_idx}",
            "resource_type": "model",
            "package_name": project_name,
            "description": f"Staging model {m_idx}",
            "depends_on": {"nodes": [parent]},
            "config": {"materialized": "view"},
            "columns": {
                _make_column_name(rng): {"name": _make_column_name(rng)} for _ in range(n_cols)
            },
            "tags": ["staging"],
            "meta": {"owner": "data-platform"},
        }
        parent_map[node_id] = [parent]
        child_map.setdefault(parent, []).append(node_id)

    # Subsequent waves: each model picks ~1.8 parents from prior waves
    all_model_ids = list(first_wave_ids)
    for m_idx in range(first_wave_size, n_models):
        node_id = f"model.{project_name}.model_{m_idx}"
        n_parents = max(1, int(round(rng.gauss(1.8, 0.8))))
        n_parents = min(n_parents, len(all_model_ids))
        parents = rng.sample(all_model_ids, n_parents)

        n_cols = rng.randint(3, 8)
        # Some models marked critical for severity variety
        is_critical = rng.random() < 0.10
        tags = ["core"]
        if is_critical:
            tags.append("critical")
        nodes[node_id] = {
            "name": f"model_{m_idx}",
            "resource_type": "model",
            "package_name": project_name,
            "description": f"Synthetic model {m_idx}",
            "depends_on": {"nodes": parents},
            "config": {"materialized": "table"},
            "columns": {
                _make_column_name(rng): {"name": _make_column_name(rng)} for _ in range(n_cols)
            },
            "tags": tags,
            "meta": {"owner": "analytics"} if not is_critical else {"owner": None},
        }
        parent_map[node_id] = parents
        for p in parents:
            child_map.setdefault(p, []).append(node_id)
        all_model_ids.append(node_id)

    manifest: Dict[str, Any] = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v8.json",
            "dbt_version": "1.5.0",
            "generated_at": "2026-08-01T00:00:00.000Z",
            "project_name": project_name,
            "project_id": project_name,
        },
        "nodes": nodes,
        "sources": sources,
        "parent_map": parent_map,
        "child_map": child_map,
    }
    return manifest


def _urn_for_model(node_id: str, raw: Dict[str, Any]) -> str:
    """Mirror the dbt parser's URN scheme."""
    project = raw.get("package_name", "dbt_project")
    name = raw.get("name", node_id)
    return f"urn:dbt:model:{project}:{name}"


def generate_corpus(
    num_repos: int,
    num_changes_per_repo: int,
    seed: int,
    output_dir: Path,
) -> Tuple[int, int]:
    """Generate the full corpus. Returns (repos_written, changes_written)."""
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    repos_written = 0
    changes_written = 0
    for repo_idx in range(num_repos):
        manifest = _generate_repo(rng, repo_idx)
        # Re-seed per-repo changes deterministically (derived from seed + repo_idx)
        change_rng = random.Random(seed * 1000 + repo_idx)
        changes = []
        for c_idx in range(num_changes_per_repo):
            model_ids = [
                node_id for node_id, raw in manifest["nodes"].items()
                if raw.get("resource_type") == "model"
            ]
            if not model_ids:
                continue
            target_model = change_rng.choice(model_ids)
            target_raw = manifest["nodes"][target_model]
            columns = list(target_raw.get("columns", {}).keys())
            change_type = _pick_change_type(change_rng)

            if change_type == "no_change" or not columns:
                changes.append({
                    "change_id": f"change_{c_idx:04d}",
                    "asset_urn": _urn_for_model(target_model, target_raw),
                    "change_type": "no_change",
                    "affected_column": None,
                    "new_value": None,
                })
                continue

            affected_column = change_rng.choice(columns)
            new_value = None
            if change_type == "column_rename":
                new_value = f"{affected_column}_renamed"
            elif change_type == "type_change":
                new_value = change_rng.choice(["INTEGER", "VARCHAR", "BOOLEAN", "NUMERIC", "DATE"])

            changes.append({
                "change_id": f"change_{c_idx:04d}",
                "asset_urn": _urn_for_model(target_model, target_raw),
                "change_type": change_type,
                "affected_column": affected_column,
                "new_value": new_value,
            })

        repo_dir = output_dir / f"repo-{repo_idx:04d}"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (repo_dir / "changes.json").write_text(json.dumps(changes, indent=2))
        repos_written += 1
        changes_written += len(changes)

    return repos_written, changes_written


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic dbt corpus")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--num-repos", type=int, default=100)
    parser.add_argument("--num-changes-per-repo", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260801)
    args = parser.parse_args()

    repos, changes = generate_corpus(
        num_repos=args.num_repos,
        num_changes_per_repo=args.num_changes_per_repo,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    print(f"[ok] Generated {repos} repos with {changes} total changes")
    print(f"[ok] Output: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
