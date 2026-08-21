"""SOC 2 tenant-isolation evidence report generator.

Reads the JSON results emitted by the Tenant Shield pytest plugin and renders a
self-contained, auditor-readable HTML report mapping each test to AICPA SOC 2
Trust Services Criteria (CC6.1, CC6.6). Optionally produces a PDF when
WeasyPrint is installed.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

from workflo.reporting.results import RunReport, TestResult

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
DEFAULT_REPORT_DIR = os.path.join("reports", "compliance")
DEFAULT_HISTORY = os.path.join(DEFAULT_REPORT_DIR, "history.jsonl")

CONTROL_DESCRIPTIONS = {
    "CC6.1": "Logical and physical access controls: implements and evaluates access to information assets.",
    "CC6.6": "Security measures over information assets: protects against unauthorized access, and logs/deticates anomalies.",
    "CC6.7": "Boundary protection: restricts external network connections and traffic flows.",
    "CC7.2": "Monitors system performance and detects anomalies.",
}


def _env():
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _tenant_pairs(results):
    pairs = []
    for r in results:
        p = r.tenant_pair or []
        if len(p) >= 2:
            key = (p[0], p[1])
            if key not in pairs:
                pairs.append(key)
    return pairs


def _control_mappings(results):
    mapping = {}
    for r in results:
        for c in (r.soc2_controls or []):
            mapping.setdefault(c, []).append(r.test_name)
    return {c: sorted(set(names)) for c, names in mapping.items()}


def _positive_controls(results):
    return [r for r in results if r.pattern == "positive_control"]


def _short(run_id):
    return run_id.split("-")[0] if run_id else ""


def _pass_rate(summary):
    if not summary.get("total"):
        return 100 if summary.get("failed") == 0 else 0
    return round(100 * summary.get("passed", 0) / summary["total"], 1)


def _read_history(path, limit=10):
    if not path or not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return rows[-limit:]


def _append_history(path, entry):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def build_context(report):
    summary = report.summary
    results = report.results
    ctx = {
        "run_id_short": _short(report.test_run_id),
        "generated": report.timestamp,
        "suite": report.suite,
        "summary": summary,
        "pass_rate_pct": _pass_rate(summary),
        "tenant_pairs": [_to_pair_display(p) for p in _tenant_pairs(results)],
        "control_mappings": _control_mappings(results),
        "control_descriptions": CONTROL_DESCRIPTIONS,
        "results": [r.to_dict() for r in results],
        "positive_controls": [r.to_dict() for r in _positive_controls(results)],
        "history": [],
    }
    return ctx


def _to_pair_display(key):
    return [key[0], key[1]]


def render_html(report, history=None):
    ctx = build_context(report)
    ctx["history"] = history or []
    env = _env()
    template = env.get_template("soc2_report.html")
    return template.render(**ctx)


def render_pdf(report, html=None, history=None):
    try:
        from weasyprint import HTML
    except Exception:
        return None
    html = html or render_html(report, history)
    return HTML(string=html).write_pdf()


def generate_report(results_path, out=None, fmt="html", history_path=DEFAULT_HISTORY):
    report = RunReport.from_json_file(results_path)
    history = _read_history(history_path)

    if out is None:
        ext = "html" if fmt == "html" else "pdf"
        out = os.path.join(
            DEFAULT_REPORT_DIR,
            f"soc2_evidence_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.{ext}",
        )

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    if fmt == "pdf":
        content = render_pdf(report)
        if content is None:
            sys.stderr.write("PDF output requires WeasyPrint (pip install 'workflo[report]'). Falling back to HTML.\n")
            fmt = "html"
            out = out[:-4] + ".html"
        else:
            with open(out, "wb") as f:
                f.write(content)

    if fmt == "html":
        html = render_html(report, history=history)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)

    entry = {
        "timestamp": report.timestamp,
        "run_id_short": _short(report.test_run_id),
        "total": report.summary["total"],
        "passed": report.summary["passed"],
        "pass_rate_pct": _pass_rate(report.summary),
    }
    if history_path:
        _append_history(history_path, entry)

    print(f"Report written: {out}")
    return out


def from_cli(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="workflo report", description="Generate a SOC 2 tenant isolation evidence report.")
    parser.add_argument("--results", "-r", required=True, help="Path to the JSON results file emitted by the plugin.")
    parser.add_argument("--format", "-f", choices=["html", "pdf"], default="html", help="Output format (default: html).")
    parser.add_argument("--out", "-o", default=None, help="Output file path (default: reports/compliance/soc2_evidence_<date>.html).")
    parser.add_argument("--history", default=DEFAULT_HISTORY, help="Path to the history JSONL file (default: reports/compliance/history.jsonl).")
    args = parser.parse_args(argv)

    if not os.path.exists(args.results):
        sys.stderr.write(f"Results file not found: {args.results}\n")
        return 2
    generate_report(args.results, out=args.out, fmt=args.format, history_path=args.history)
    return 0


if __name__ == "__main__":
    sys.exit(from_cli())
