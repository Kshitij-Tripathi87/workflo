#!/usr/bin/env python3
"""
audit_flags.py — first-pass automated audit of a real `workflo` installation.

What this does:
  1. Runs each flag against a real repo (or --dry-run if no repo given) and
     records exit code, wall-clock time, and stdout/stderr.
  2. If a source path is given, greps for known inference-call patterns
     (vllm, openai, anthropic, LoRA, requests.post to a local model server)
     inside the file(s) that implement each flag, as a heuristic for whether
     a flag is AI-driven or static-only.
  3. Writes a JSON + Markdown report. Does NOT decide "working" vs "not" by
     itself — that judgment call (especially "does the output look real vs
     templated") still needs a human per FLAG_AUDIT_CHECKLIST.md.

Usage:
  python audit_flags.py --workflo-bin workflo \
      --repo https://github.com/pallets/click.git \
      --src-path /path/to/workflo/source \
      --out report

Safe to run with no --repo (falls back to --dry-run only, no live Docker use)
and no --src-path (skips the static code-pattern check).
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

FLAGS_TO_PROBE = [
    ("--dry-run", ["--dry-run"], False),          # (label, extra_args, needs_live_run)
    ("--test", ["--test"], True),
    ("--deep-test", ["--deep-test"], True),
    ("--aggressive-test", ["--aggressive-test"], True),
    ("--security", ["--security"], True),
    ("--web", ["--web"], True),
]

# Heuristic patterns suggesting a real model call vs static tooling.
# This is intentionally crude — it flags files worth reading by hand, it does
# not replace reading them.
AI_CALL_PATTERNS = [
    r"\bvllm\b", r"\bopenai\b", r"\banthropic\b", r"lora_request",
    r"chat/completions", r"/v1/completions", r"load_lora_adapter",
    r"\bLLM\(", r"model_router", r"AutoModelForCausalLM",
    r"\bollama\b", r"llama-server", r"/lora-adapters", r"\bModelServer\b",
    r"generate_from_model_output", r"json_schema",
]
STATIC_TOOL_PATTERNS = [
    r"\bhypothesis\b", r"given\(", r"@st\.", r"faker", r"\bfuzz\b",
]


def run_flag(workflo_bin: str, repo: str | None, flag_args: list[str], needs_live_run: bool) -> dict:
    if needs_live_run and not repo:
        return {"skipped": True, "reason": "no --repo given, needs live run"}

    cmd = [workflo_bin, "run"]
    if repo:
        cmd += ["--repo", repo]
    cmd += flag_args

    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        elapsed = time.time() - start
        return {
            "skipped": False,
            "cmd": " ".join(cmd),
            "exit_code": proc.returncode,
            "elapsed_sec": round(elapsed, 2),
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    except FileNotFoundError:
        return {"skipped": False, "error": f"'{workflo_bin}' not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"skipped": False, "error": "timed out after 600s"}


def grep_source_for_flag(src_path: Path, flag_label: str) -> dict:
    """
    Crude static check: search the whole source tree for files that mention
    the flag name, then check those files for AI-call vs static-tool patterns.
    Reports filenames so a human can go read them directly rather than trust
    this script's judgment.
    """
    flag_token = flag_label.lstrip("-").replace("-", "_")
    candidate_files = []
    for py_file in src_path.rglob("*.py"):
        try:
            text = py_file.read_text(errors="ignore")
        except OSError:
            continue
        if flag_token in text or flag_label in text:
            candidate_files.append(py_file)

    ai_hits, static_hits = [], []
    for f in candidate_files:
        text = f.read_text(errors="ignore")
        if any(re.search(p, text, re.IGNORECASE) for p in AI_CALL_PATTERNS):
            ai_hits.append(str(f))
        if any(re.search(p, text, re.IGNORECASE) for p in STATIC_TOOL_PATTERNS):
            static_hits.append(str(f))

    return {
        "candidate_files": [str(f) for f in candidate_files],
        "files_with_ai_call_patterns": ai_hits,
        "files_with_static_tool_patterns": static_hits,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflo-bin", default="workflo")
    ap.add_argument("--repo", default=None, help="Real repo URL to run flags against")
    ap.add_argument("--src-path", default=None, help="Path to workflo source, for static grep check")
    ap.add_argument("--out", default="report", help="Output file basename (writes .json and .md)")
    args = ap.parse_args()

    report = {"runtime_probes": {}, "static_checks": {}}

    for label, extra_args, needs_live in FLAGS_TO_PROBE:
        print(f"Probing {label} ...", file=sys.stderr)
        report["runtime_probes"][label] = run_flag(args.workflo_bin, args.repo, extra_args, needs_live)

    if args.src_path:
        src = Path(args.src_path)
        if src.exists():
            for label, _, _ in FLAGS_TO_PROBE:
                report["static_checks"][label] = grep_source_for_flag(src, label)
        else:
            print(f"WARNING: --src-path {src} does not exist, skipping static check", file=sys.stderr)

    Path(f"{args.out}.json").write_text(json.dumps(report, indent=2))

    md_lines = ["# workflo flag audit — automated report\n"]
    for label, _, _ in FLAGS_TO_PROBE:
        md_lines.append(f"## {label}\n")
        rp = report["runtime_probes"].get(label, {})
        if rp.get("skipped"):
            md_lines.append(f"- Skipped: {rp.get('reason')}\n")
        elif "error" in rp:
            md_lines.append(f"- ERROR: {rp['error']}\n")
        else:
            md_lines.append(f"- Exit code: `{rp.get('exit_code')}`  |  Elapsed: {rp.get('elapsed_sec')}s\n")
            md_lines.append(f"- Command: `{rp.get('cmd')}`\n")

        sc = report["static_checks"].get(label)
        if sc:
            md_lines.append(f"- Candidate source files: {sc['candidate_files'] or 'none found'}\n")
            md_lines.append(f"- Files matching AI-call patterns: {sc['files_with_ai_call_patterns'] or 'NONE — likely static-only'}\n")
            md_lines.append(f"- Files matching static-tool patterns: {sc['files_with_static_tool_patterns'] or 'none'}\n")
        md_lines.append("\n")

    Path(f"{args.out}.md").write_text("\n".join(md_lines))
    print(f"\nWrote {args.out}.json and {args.out}.md", file=sys.stderr)
    print("Remember: this script flags evidence, it does not make the final call.", file=sys.stderr)
    print("Fill in FLAG_AUDIT_CHECKLIST.md by hand using this report.", file=sys.stderr)


if __name__ == "__main__":
    main()
