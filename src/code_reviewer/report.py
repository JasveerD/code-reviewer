"""Render a ReviewReport as markdown — suitable for PR comments, files, or stdout."""
from .schemas import ReviewReport, FinalFinding, Severity

def render_markdown(report: ReviewReport) -> str:
    """Render a ReviewReport as markdown."""
    lines: list[str] = []
    lines.append("# Code Review Report")
    lines.append("")
    lines.append(_render_summary(report))
    lines.append("")

    if not report.findings:
        lines.append("**No issues found.**")
        return "\n".join(lines)

    lines.append("## Findings")
    lines.append("")
    for i, finding in enumerate(report.findings, 1):
        lines.append(_render_finding(i, finding))
        lines.append("")

    lines.append("---")
    lines.append(_render_footer(report))
    return "\n".join(lines)


def _render_summary(report: ReviewReport) -> str:
    stats = report.stats
    total = stats.get("total", 0)
    parts = []
    for sev in ("critical", "high", "medium", "low", "info"):
        n = stats.get(sev, 0)
        if n:
            parts.append(f"**{n}** {sev}")
    grounded = stats.get("grounded", 0)
    inferred = stats.get("llm_inferred", 0)

    summary_line = f"**{total} issue(s) found**: " + " · ".join(parts) if parts else f"**{total} issue(s) found**"
    grounding_line = (
        f"_{grounded} grounded by static analysis, {inferred} from LLM inference._"
    )
    files_line = f"_Files reviewed: {', '.join(f'`{p}`' for p in report.files_reviewed)}._"
    return f"{summary_line}\n\n{grounding_line}\n\n{files_line}"


def _render_finding(index: int, f: FinalFinding) -> str:
    sev = f.severity.value.upper()
    loc = f.location

    lines: list[str] = []
    lines.append(f"### {index}. [{sev}] {f.title}")
    lines.append(f"**Location:** `{loc.file}`, lines {loc.line_start}-{loc.line_end}")
    lines.append("")
    lines.append(f"{f.description}")
    lines.append("")

    meta = []
    meta.append(f"**Found by:** {', '.join(f.contributing_agents)}")
    if f.grounding:
        meta.append(f"**Grounded by:** {', '.join(f'`{g}`' for g in f.grounding)}")
    meta.append(f"**Confidence:** {f.confidence:.2f}")
    lines.append(" · ".join(meta))

    if f.disagreement:
        lines.append("")
        lines.append(f"> **Agent disagreement:** {f.disagreement}")

    if f.suggested_fix:
        lines.append("")
        lines.append("**Suggested fix:**")
        lines.append("")
        # If the fix contains code-ish content, wrap in a code block
        if "(" in f.suggested_fix or "=" in f.suggested_fix or "def " in f.suggested_fix:
            lines.append("```python")
            lines.append(f.suggested_fix)
            lines.append("```")
        else:
            lines.append(f.suggested_fix)

    return "\n".join(lines)


def _render_footer(report: ReviewReport) -> str:
    stats = report.stats
    agent_counts = []
    for key, val in stats.items():
        if key.startswith("by_"):
            agent_counts.append(f"{key[3:]}: {val}")
    breakdown = ", ".join(agent_counts) if agent_counts else "no per-agent breakdown"
    return f"_Per-agent contributing finding counts: {breakdown}_"
