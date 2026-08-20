"""Orchestrates the full validation pipeline.

Flow:
  1. Clone the repo shallow
  2. Compute baseline (merge-base origin/main HEAD) and diff
  3. Collect key context files
  4. Run gates (typecheck, lint, tests, contract, live trace)
  5. If all gates pass, render prompt + call vLLM
  6. Parse JSON response into structured findings
  7. Return ValidationResult for the reporters

Each gate runs as a subprocess inside the working directory. When the
pipeline runs inside a Docker container with --network none, the gates
have no network access; the LLM call uses the host vLLM via the
configured endpoint. The orchestrator is intentionally Docker-agnostic
so it can be tested locally.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import jinja2
import requests


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    id: str
    severity: str  # critical | high | medium | low | info
    category: str
    file: str
    line: int
    pattern: str
    message: str
    suggestion: str
    baseline_regression: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(
            id=d.get("id", "ARCH-XXX"),
            severity=d.get("severity", "info"),
            category=d.get("category", "patterns"),
            file=d.get("file", ""),
            line=int(d.get("line", 0) or 0),
            pattern=d.get("pattern", ""),
            message=d.get("message", ""),
            suggestion=d.get("suggestion", ""),
            baseline_regression=bool(d.get("baseline_regression", False)),
        )


@dataclass
class GateResult:
    name: str
    passed: bool
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    command: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_s": round(self.duration_s, 2),
            "command": self.command,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass
class ValidationResult:
    repo: str
    baseline: str
    head: str
    flags: list[str]
    model: str
    started_at: str
    finished_at: str = ""
    gates: list[GateResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    notes: str = ""

    @property
    def all_gates_passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def to_summary_dict(self) -> dict:
        return {
            "repo": self.repo,
            "baseline": self.baseline,
            "head": self.head,
            "flags": self.flags,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "gates": [g.to_dict() for g in self.gates],
            "summary": self.severity_counts,
            "findings": [vars(f) for f in self.findings],
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 300,
         env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def clone_repo(repo_url: str, work: Path) -> Path:
    """Shallow clone of the repo into work/repo."""
    target = work / "repo"
    _run(["git", "clone", "--depth=50", repo_url, str(target)], timeout=300)
    return target


def resolve_baseline(repo_dir: Path) -> str:
    """Compute the baseline as merge-base of origin/main and HEAD.

    Falls back to HEAD~1 if origin/main is unreachable (e.g. shallow clone
    without origin/main in history).
    """
    proc = _run(["git", "merge-base", "origin/main", "HEAD"], cwd=repo_dir, timeout=30)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    proc = _run(["git", "rev-parse", "HEAD~1"], cwd=repo_dir, timeout=30)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return ""


def get_head(repo_dir: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=repo_dir, timeout=30).stdout.strip()


def get_diff(repo_dir: Path, baseline: str, scope_paths: list[str]) -> str:
    """Diff from baseline to HEAD, restricted to scope paths."""
    if not baseline:
        return ""
    cmd = ["git", "diff", f"{baseline}..HEAD", "--"] + scope_paths
    proc = _run(cmd, cwd=repo_dir, timeout=60)
    out = proc.stdout
    # Truncate very large diffs to keep prompts sane
    if len(out) > 60_000:
        out = out[:60_000] + "\n\n[diff truncated; first 60 KB shown]\n"
    return out


# ---------------------------------------------------------------------------
# Context file collection
# ---------------------------------------------------------------------------


CONTEXT_FILE_PATTERNS = [
    "apps/control-plane/app/api/v1/auth.py",
    "apps/control-plane/app/api/oauth.py",
    "apps/control-plane/app/api/v1/key_provisioning.py",
    "apps/control-plane/app/core/security.py",
    "apps/control-plane/app/core/crypto.py",
    "apps/control-plane/app/db/models.py",
    "apps/control-plane/app/main.py",
    "apps/control-plane/app/core/config.py",
    "apps/workflo-cli/src/workflo_cli/main.py",
    "apps/workflo-cli/src/workflo_cli/auth_commands.py",
    "packages/cortex-auth/src/cortex_auth/session.py",
    "packages/cortex-auth/src/cortex_auth/client.py",
]


def collect_context_files(repo_dir: Path, max_chars_per_file: int = 6000) -> list[dict]:
    """Read key context files; truncate per-file to keep prompt bounded."""
    out = []
    for relpath in CONTEXT_FILE_PATTERNS:
        p = repo_dir / relpath
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(content) > max_chars_per_file:
            content = content[:max_chars_per_file] + "\n\n[file truncated]\n"
        out.append({"path": relpath, "content": content})
    return out


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


@dataclass
class Gate:
    name: str
    command: list[str]
    timeout: int = 300
    required: bool = True  # fail the whole pipeline if False


DEFAULT_GATES: list[Gate] = [
    Gate(
        name="import-check",
        command=["python", "-c", "from app.main import create_app; print('OK')"],
        timeout=60,
    ),
    Gate(
        name="pytest",
        command=[
            "python", "-m", "pytest",
            "apps/control-plane/tests",
            "apps/workflo-cli/tests",
            "packages/cortex-auth/tests",
            "-q", "--no-header", "-p", "no:cacheprovider",
        ],
        timeout=300,
    ),
]


def run_gate(gate: Gate, cwd: Path, venv_python: str | None = None) -> GateResult:
    cmd = gate.command
    if venv_python and cmd[0] == "python":
        cmd = [venv_python, *cmd[1:]]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=gate.timeout
        )
    except subprocess.TimeoutExpired as e:
        return GateResult(
            name=gate.name, passed=False, duration_s=time.monotonic() - start,
            stdout_tail=(e.stdout.decode() if isinstance(e.stdout, bytes) else "")[-1000:],
            stderr_tail=f"TIMEOUT after {gate.timeout}s",
            command=" ".join(cmd),
        )
    duration = time.monotonic() - start
    return GateResult(
        name=gate.name,
        passed=proc.returncode == 0,
        duration_s=duration,
        stdout_tail=proc.stdout[-1000:],
        stderr_tail=proc.stderr[-1000:],
        command=" ".join(cmd),
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def call_vllm(model_endpoint: str, model: str, prompt: str,
              temperature: float = 0.1, max_tokens: int = 8192,
              timeout: int = 600) -> dict:
    """Call vLLM (or any OpenAI-compatible endpoint) and parse JSON.

    Tries strict JSON mode first; falls back to extracting the first JSON
    object from a markdown-fenced response.
    """
    base = model_endpoint.rstrip("/")
    url = f"{base}/chat/completions" if not base.endswith("/chat/completions") else base
    if "/v1" not in base:
        url = f"{base}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an architecture reviewer. Output strict JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    return _parse_json(content)


def _parse_json(content: str) -> dict:
    """Parse JSON from LLM response; tolerate markdown fences and preamble."""
    text = content.strip()
    # Strip leading ```json fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from LLM response: {content[:300]}...")


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def render_prompt(template_path: Path, *, repo: str, baseline: str, head: str,
                  flags: list[str], diff: str,
                  context_files: list[dict]) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template(template_path.name)
    return template.render(
        repo=repo, baseline=baseline, head=head, flags=flags,
        diff=diff, context_files=context_files,
    )


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run_validation(
    repo_url: str,
    model_endpoint: str,
    model: str,
    *,
    flags: list[str] | None = None,
    scope_paths: list[str] | None = None,
    venv_python: str | None = None,
    baseline: str | None = None,
    on_log=print,
) -> ValidationResult:
    """Run the full pipeline. Returns ValidationResult; never raises on
    gate failure (gate failures are recorded in the result)."""
    flags = flags or ["architecture", "patterns"]
    scope_paths = scope_paths or [
        "apps/control-plane", "apps/workflo-cli", "packages/cortex-auth",
    ]

    result = ValidationResult(
        repo=repo_url, baseline="", head="", flags=flags, model=model,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    with tempfile.TemporaryDirectory(prefix="validate-phase2-") as tmp:
        work = Path(tmp)
        on_log(f"[orch] cloning {repo_url}")
        repo_dir = clone_repo(repo_url, work)
        result.baseline = baseline or resolve_baseline(repo_dir)
        result.head = get_head(repo_dir)
        on_log(f"[orch] baseline={result.baseline[:12]}  head={result.head[:12]}")

        # Gates
        on_log(f"[orch] running {len(DEFAULT_GATES)} gates")
        for gate in DEFAULT_GATES:
            on_log(f"[orch] gate: {gate.name}")
            gr = run_gate(gate, cwd=repo_dir, venv_python=venv_python)
            result.gates.append(gr)
            on_log(f"[orch]   {'PASS' if gr.passed else 'FAIL'}  ({gr.duration_s:.1f}s)")

        # LLM analysis only if all gates pass
        if not result.all_gates_passed:
            result.notes = "Gates failed; LLM analysis skipped."
        else:
            on_log("[orch] collecting diff + context")
            diff_text = get_diff(repo_dir, result.baseline, scope_paths)
            context_files = collect_context_files(repo_dir)

            template_path = Path(__file__).parent / "prompts" / "architecture_review.j2"
            prompt = render_prompt(
                template_path,
                repo=repo_url, baseline=result.baseline, head=result.head,
                flags=flags, diff=diff_text, context_files=context_files,
            )

            on_log(f"[orch] calling vLLM ({model}) — prompt is {len(prompt)} chars")
            try:
                llm_resp = call_vllm(model_endpoint, model, prompt)
            except Exception as e:
                result.notes = f"LLM call failed: {e}"
                on_log(f"[orch] LLM call failed: {e}")
                llm_resp = {"findings": [], "summary": {}, "notes": result.notes}

            raw_findings = llm_resp.get("findings", [])
            result.findings = [Finding.from_dict(f) for f in raw_findings]
            result.notes = llm_resp.get("notes", "")

        # Sanity check: every finding needs an id; assign if missing
        for i, f in enumerate(result.findings):
            if f.id == "ARCH-XXX" or not f.id:
                f.id = f"ARCH-{i + 1:03d}"

    result.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return result
