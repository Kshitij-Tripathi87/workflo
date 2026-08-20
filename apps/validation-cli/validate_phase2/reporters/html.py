"""HTML reporter — single-file self-contained page with severity badges."""

from __future__ import annotations

import html as html_lib
from pathlib import Path

from ..orchestrator import Finding, GateResult, ValidationResult


SEVERITY_CLASS = {
    "critical": "sev-critical",
    "high": "sev-high",
    "medium": "sev-medium",
    "low": "sev-low",
    "info": "sev-info",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

STYLE = """\
:root { color-scheme: light dark; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 1100px; margin: 0 auto; padding: 2rem 1rem; line-height: 1.55;
       background: #fafafa; color: #1a1a1a; }
@media (prefers-color-scheme: dark) {
  body { background: #0f1115; color: #e6e6e6; }
}
h1 { font-size: 1.8rem; margin-bottom: 0.25rem; }
h2 { border-bottom: 1px solid #ddd; padding-bottom: 0.3rem; margin-top: 2rem; }
.meta { color: #777; font-size: 0.9rem; margin-bottom: 1.5rem; }
.summary { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }
.summary .card { padding: 0.75rem 1rem; border-radius: 6px; background: white;
                 border: 1px solid #e5e5e5; min-width: 110px; text-align: center; }
@media (prefers-color-scheme: dark) {
  .summary .card { background: #181a20; border-color: #2a2d35; }
}
.summary .count { font-size: 1.5rem; font-weight: 600; display: block; }
.summary .label { font-size: 0.8rem; text-transform: uppercase; color: #888; }
.gates { margin: 1rem 0; }
.gate { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.7rem;
        border-radius: 4px; margin-bottom: 0.3rem; background: white;
        border: 1px solid #e5e5e5; }
@media (prefers-color-scheme: dark) {
  .gate { background: #181a20; border-color: #2a2d35; }
}
.gate.passed { border-left: 3px solid #16a34a; }
.gate.failed { border-left: 3px solid #dc2626; }
.findings { margin-top: 1rem; }
details { margin: 0.5rem 0; padding: 0.75rem 1rem; background: white;
          border: 1px solid #e5e5e5; border-radius: 6px; }
@media (prefers-color-scheme: dark) {
  details { background: #181a20; border-color: #2a2d35; }
}
summary { cursor: pointer; font-weight: 500; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
         font-size: 0.75rem; font-weight: 600; margin-right: 0.5rem;
         text-transform: uppercase; }
.sev-critical { background: #7f1d1d; color: white; }
.sev-high     { background: #dc2626; color: white; }
.sev-medium   { background: #f97316; color: white; }
.sev-low      { background: #facc15; color: #1a1a1a; }
.sev-info     { background: #2563eb; color: white; }
pre { background: #0f1115; color: #e6e6e6; padding: 0.75rem; border-radius: 4px;
      overflow-x: auto; font-size: 0.85rem; }
code { font-family: 'SF Mono', Monaco, monospace; }
.kv { display: grid; grid-template-columns: 110px 1fr; gap: 0.25rem 0.75rem; margin: 0.5rem 0; }
.kv .k { color: #888; }
"""


def _esc(s) -> str:
    """HTML-escape a value (coerces non-strings to str first)."""
    return html_lib.escape(str(s), quote=True)


def write(result: ValidationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    counts = result.severity_counts

    sev_cards = "".join(
        _render_severity_card(sev, counts.get(sev, 0))
        for sev in ("critical", "high", "medium", "low", "info")
    )

    gate_rows = "".join(_render_gate(g) for g in result.gates)

    sorted_findings = sorted(
        result.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99)
    )
    if not sorted_findings:
        finding_blocks_html = "<p><em>No findings reported.</em></p>"
    else:
        finding_blocks_html = "".join(_render_finding(f) for f in sorted_findings)

    notes_html = ""
    if result.notes:
        notes_html = (
            f'<p class="meta"><strong>Notes</strong> {_esc(result.notes)}</p>'
        )

    gates_passed = sum(1 for g in result.gates if g.passed)
    gates_total = len(result.gates)
    findings_count = len(sorted_findings)
    generated = _esc(result.finished_at or result.started_at)

    parts: list[str] = []
    parts.append("<!doctype html>\n")
    parts.append('<html lang="en">\n')
    parts.append("<head>\n")
    parts.append('<meta charset="utf-8">\n')
    parts.append(f"<title>Architecture Review &mdash; {_esc(result.repo)}</title>\n")
    parts.append("<style>")
    parts.append(STYLE)
    parts.append("</style>\n")
    parts.append("</head>\n")
    parts.append("<body>\n")
    parts.append("<h1>Architecture Review</h1>\n")
    parts.append('<p class="meta">\n')
    parts.append(f"  <code>{_esc(result.repo)}</code> &middot;\n")
    parts.append(f"  baseline <code>{_esc(result.baseline[:12] or 'N/A')}</code> &middot;\n")
    parts.append(f"  head <code>{_esc(result.head[:12] or 'N/A')}</code> &middot;\n")
    parts.append(f"  model <code>{_esc(result.model)}</code>\n")
    parts.append("</p>\n")
    parts.append("<h2>Summary</h2>\n")
    parts.append('<div class="summary">\n')
    parts.append(sev_cards)
    parts.append("</div>\n")
    parts.append(f"<p>{gates_passed}/{gates_total} gates passed</p>\n")
    parts.append(notes_html)
    parts.append("\n")
    parts.append("<h2>Gates</h2>\n")
    parts.append('<div class="gates">\n')
    parts.append(gate_rows)
    parts.append("</div>\n")
    parts.append(f"<h2>Findings ({findings_count})</h2>\n")
    parts.append('<div class="findings">\n')
    parts.append(finding_blocks_html)
    parts.append("\n</div>\n")
    parts.append(f'<p class="meta">Generated {generated}</p>\n')
    parts.append("</body>\n")
    parts.append("</html>\n")

    out_path.write_text("".join(parts), encoding="utf-8")


def _render_severity_card(severity: str, count: int) -> str:
    return (
        f'<div class="card">'
        f'<span class="count">{count}</span>'
        f'<span class="label">{_esc(severity)}</span>'
        f"</div>"
    )


def _render_gate(g: GateResult) -> str:
    css = "passed" if g.passed else "failed"
    marker = "&#10003;" if g.passed else "&#10007;"
    tail = (g.stderr_tail or g.stdout_tail).strip()
    tail_short = tail.splitlines()[-1] if tail else ""
    duration = f"{g.duration_s:.1f}s"
    return (
        f'<div class="gate {css}">'
        f"<strong>{marker}</strong> "
        f"<code>{_esc(g.name)}</code> "
        f'<span class="meta">({duration} &mdash; {_esc(tail_short)})</span>'
        f"</div>"
    )


def _render_finding(f: Finding) -> str:
    cls = SEVERITY_CLASS.get(f.severity, "sev-info")
    location = f"{_esc(f.file)}:{f.line}" if f.file else "&mdash;"
    baseline_regr = (
        "<p><strong>Baseline regression</strong> yes</p>"
        if f.baseline_regression
        else ""
    )
    return (
        f"<details>"
        f"<summary>"
        f'<span class="badge {cls}">{_esc(f.severity)}</span> '
        f"<code>{_esc(f.id)}</code> &mdash; "
        f"{_esc(f.pattern)}"
        f' <span class="meta">&middot; {location}</span>'
        f"</summary>"
        f'<div class="kv">'
        f'<span class="k">Category</span><span>{_esc(f.category)}</span>'
        f'<span class="k">File</span><span><code>{location}</code></span>'
        f'<span class="k">Message</span><span>{_esc(f.message)}</span>'
        f'<span class="k">Suggestion</span><span>{_esc(f.suggestion)}</span>'
        f"</div>"
        f"{baseline_regr}"
        f"</details>"
    )
