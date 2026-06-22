"""Coordinator: synthesizes findings from parallel agents into a final report."""
import os
from collections import defaultdict
from google import genai
from google.genai import types as genai_types
from .agents._prompts import gemini_with_retry

from .schemas import AgentReport, Finding, FinalFinding, ReviewReport, Severity


_SYSTEM_INSTRUCTION = """You are the coordinator for a multi-agent code review system.

Three specialized agents (correctness, security, performance) have each produced findings on the same code. Your job is to synthesize them into one prioritized actionable report.

You receive CLUSTERS of findings grouped by spatial proximity in the source. Within each cluster:

1. MERGE: if multiple findings describe the same underlying issue (e.g., blocking I/O in an async function flagged by both correctness and performance), combine them into ONE FinalFinding. List all contributing agents. Consolidate grounding tags. Take the highest severity UNLESS one agent has materially higher confidence on a lower severity.

2. SPLIT: if findings in a cluster are actually different issues that happen to be near each other (e.g., line 13 has blocking I/O and line 14 has unsanitized URL — same area, different bugs), keep them as separate FinalFindings.

3. DISAGREEMENT: if contributing agents picked materially different severities (e.g., one MEDIUM, one HIGH) for what is genuinely the same issue, fill the `disagreement` field with a one-sentence note explaining what they disagreed on and why you resolved it the way you did. Otherwise leave it null.

Rules:
- Output ordered by severity (critical first), then by confidence within a severity.
- Every FinalFinding must be supported by at least one input finding. Do NOT invent findings.
- Consolidate descriptions: keep what's distinctive, drop redundancy. Aim for 2-4 sentences.
- For confidence: average the contributing agents' confidences, then boost by 0.05 per additional corroborating agent (cap at 0.98). Multiple agents agreeing IS evidence.
- For grounding: union of all contributing findings' grounding tags, deduplicated.
- For suggested_fix: prefer the most concrete fix from contributing findings; synthesize one if none provided.
- contributing_agents must be deduplicated.
"""


def _cluster_by_proximity(reports: list[AgentReport], proximity: int = 5) -> list[list[Finding]]:
    """Group findings within `proximity` lines in the same file. LLM decides merge vs split."""
    by_file: dict[str, list[Finding]] = defaultdict(list)
    for report in reports:
        for f in report.findings:
            by_file[f.location.file].append(f)

    clusters: list[list[Finding]] = []
    for findings in by_file.values():
        findings.sort(key=lambda f: f.location.line_start)
        current: list[Finding] = []
        current_end = -10
        for f in findings:
            if not current or f.location.line_start <= current_end + proximity:
                current.append(f)
                current_end = max(current_end, f.location.line_end)
            else:
                clusters.append(current)
                current = [f]
                current_end = f.location.line_end
        if current:
            clusters.append(current)
    return clusters


def _format_clusters(clusters: list[list[Finding]]) -> str:
    """Render clusters for the LLM."""
    lines = []
    for i, cluster in enumerate(clusters, 1):
        first = cluster[0]
        start = min(f.location.line_start for f in cluster)
        end = max(f.location.line_end for f in cluster)
        lines.append(f"\nCLUSTER {i} ({first.location.file}, lines {start}-{end}):")
        for f in cluster:
            grounding = ", ".join(f.grounding) if f.grounding else "(none)"
            lines.append(
                f"  - [{f.agent}, {f.severity.value.upper()}, conf={f.confidence:.2f}] "
                f"line {f.location.line_start}: {f.title}"
            )
            lines.append(f"    {f.description}")
            lines.append(f"    grounding: {grounding}")
            if f.suggested_fix:
                lines.append(f"    suggested_fix: {f.suggested_fix}")
    return "\n".join(lines) if lines else "(no findings)"


def _compute_stats(findings: list[FinalFinding]) -> dict[str, int]:
    stats: dict[str, int] = defaultdict(int)
    stats["total"] = len(findings)
    for f in findings:
        stats[f.severity.value] += 1
        for agent in f.contributing_agents:
            stats[f"by_{agent}"] += 1
        if f.grounding:
            stats["grounded"] += 1
        else:
            stats["llm_inferred"] += 1
    return dict(stats)


def synthesize(reports: list[AgentReport], files_reviewed: list[str]) -> ReviewReport:
    """Cluster findings, run LLM synthesis, return final report."""
    if not any(r.findings for r in reports):
        return ReviewReport(
            findings=[],
            summary="No issues found across correctness, security, or performance.",
            stats={"total": 0},
            files_reviewed=files_reviewed,
        )

    clusters = _cluster_by_proximity(reports)

    prompt = f"""Synthesize these findings into a final review report.

{_format_clusters(clusters)}

Produce a JSON list of FinalFinding objects following the rules in your instructions.
"""

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    response = gemini_with_retry(
        client,
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=list[FinalFinding],
            temperature=0.1,
        ),
    )

    final_findings: list[FinalFinding] = response.parsed or []
    # Order: severity rank, then confidence desc within same severity
    sev_rank = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4}
    final_findings.sort(key=lambda f: (sev_rank.get(f.severity, 5), -f.confidence))

    stats = _compute_stats(final_findings)
    summary = _build_summary(stats)

    return ReviewReport(
        findings=final_findings,
        summary=summary,
        stats=stats,
        files_reviewed=files_reviewed,
    )


def _build_summary(stats: dict[str, int]) -> str:
    total = stats.get("total", 0)
    if total == 0:
        return "No issues found."
    parts = []
    for sev in ("critical", "high", "medium", "low", "info"):
        n = stats.get(sev, 0)
        if n:
            parts.append(f"{n} {sev}")
    grounded = stats.get("grounded", 0)
    return f"{total} issue(s): " + ", ".join(parts) + f". {grounded} grounded by static analysis."
