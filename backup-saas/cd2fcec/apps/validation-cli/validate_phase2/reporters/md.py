"""Markdown reporter — human-readable executive summary + findings table."""

from __future__ import annotations

from pathlib import Path

from ..orchestrator import Finding, GateResult, ValidationResult


SEVERITY_BADGES = {
    "critical": "🛑",
    "high": "🔴",
    "medium": "🟠",
    "low": "🟡",
    "info": "🔵",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _gate_row(g: GateResult) -> str:
    badge = "✅" if g.passed else "❌"
    return (
        f"| `{g.name}` | {badge} | {g.duration_s:.1f}s | "
        f"`{_truncate(g.command, 60)}` |"
    )


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def write(result: ValidationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = result.severity_counts

    lines: list[str] = []
    lines.append(f"# Architecture Review — `{result.repo}`")
    lines.append("")
    lines.append(f"_Generated: {result.finished_at or result.started_at}_")
    lines.append(f"_Model: `{result.model}`_")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Baseline**: `{result.baseline[:12] or 'N/A'}`")
    lines.append(f"- **HEAD**: `{result.head[:12] or 'N/A'}`")
    lines.append(f"- **Flags**: {', '.join(result.flags)}")
    lines.append("")
    lines.append("### Severity counts")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|------:|")
    for sev in ("critical", "high", "medium", "low", "info"):
        lines.append(f"| {sev.capitalize()} | {counts.get(sev, 0)} |")
    lines.append("")
    lines.append(f"**Gates**: {sum(1 for g in result.gates if g.passed)}/"
                 f"{len(result.gates)} passed")
    if result.notes:
        lines.append("")
        lines.append(f"> {result.notes}")
    lines.append("")

    # Gates table
    lines.append("## Gates")
    lines.append("")
    lines.append("| Gate | Result | Duration | Command |")
    lines.append("|------|--------|---------:|---------|")
    for g in result.gates:
        lines.append(_gate_row(g))
    lines.append("")

    # Failed-gate detail
    failed = [g for g in result.gates if not g.passed]
    if failed:
        lines.append("## Failed Gate Detail")
        lines.append("")
        for g in failed:
            lines.append(f"### `{g.name}`")
            lines.append("")
            lines.append("```")
            lines.append(g.stderr_tail.strip() or g.stdout_tail.strip() or "(no output)")
            lines.append("```")
            lines.append("")

    # Findings
    sorted_findings = sorted(
        result.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99)
    )

    lines.append("## Findings")
    lines.append("")
    if not sorted_findings:
        lines.append("_No findings reported._")
        lines.append("")
    else:
        lines.append("| ID | Severity | Category | File:Line | Pattern | Message |")
        lines.append("|----|----------|----------|-----------|---------|---------|")
        for f in sorted_findings:
            badge = SEVERITY_BADGES.get(f.severity, "•")
            loc = f"`{f.file}:{f.line}`" if f.file else "—"
            msg = _truncate(f.message.replace("|", "\\|"), 80)
            lines.append(
                f"| `{f.id}` | {badge} {f.severity} | {f.category} | "
                f"{loc} | `{f.pattern}` | {msg} |"
            )
        lines.append("")

        lines.append("### Detail")
        lines.append("")
        for f in sorted_findings:
            badge = SEVERITY_BADGES.get(f.severity, "•")
            lines.append(f"#### `{f.id}` {badge} {f.severity} — {f.pattern}")
            lines.append("")
            lines.append(f"- **File**: `{f.file}:{f.line}`")
            lines.append(f"- **Category**: {f.category}")
            if f.baseline_regression:
                lines.append(f"- **Baseline regression**: yes")
            lines.append(f"- **Message**: {f.message}")
            lines.append(f"- **Suggestion**: {f.suggestion}")
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
