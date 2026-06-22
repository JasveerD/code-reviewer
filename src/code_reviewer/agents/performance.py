"""Performance agent: identifies inefficiencies and anti-patterns."""
import os
from pathlib import Path
from google import genai
from google.genai import types

from ..ingestion.types import ReviewFile
from ..context import FileMap
from ..schemas import AgentReport, Finding
from ..tools.ruff_tool import run_ruff_perf, RuffDiagnostic
from ._prompts import format_code_map, format_source, gemini_with_retry


_SYSTEM_INSTRUCTION = """You are a code review agent specialized in performance.

You receive:
- One source file (with line numbers)
- A code map
- Diagnostics from ruff's PERF rule set, possibly empty

Produce a JSON list of Finding objects.

RULES:
1. Every ruff PERF finding produces a Finding. Grounding="ruff:<code>".
2. Add findings for performance issues ruff can't catch: superlinear algorithms where linear would do (O(n²) lookups instead of sets/dicts), N+1 patterns (loop calling a function that hits a database/network per iteration), unnecessary repeated I/O, large objects copied when references would suffice, redundant computation in hot paths, missing memoization opportunities for pure functions called with same args, eager loading of data that could be streamed. These have grounding=[].
3. DO NOT flag: correctness, security, style. Other agents.
4. Severity:
   - critical: O(n²) or worse on user-controlled input; will degrade or crash at scale
   - high: meaningful slowdown on typical input
   - medium: noticeable improvement opportunity
   - low: minor optimization
   - info: stylistic preference for performance
5. confidence: 0.9+ for ruff-grounded; 0.5-0.8 for LLM inference.
6. Be specific: "this is O(n²) where O(n) would do with a set" beats "could be faster". Cite the actual complexity or inefficiency.
7. Return at most 8 findings. agent="performance" on every finding.
"""


def _format_ruff(diagnostics: list[RuffDiagnostic]) -> str:
    if not diagnostics:
        return "(no ruff PERF diagnostics)"
    return "\n".join(
        f"  line {d.line_start}-{d.line_end} [{d.code}]: {d.message}"
        for d in diagnostics
    )


def review_performance(file: ReviewFile, file_map: FileMap, workdir: Path) -> AgentReport:
    diagnostics = run_ruff_perf(workdir, target_file=file.path)

    prompt = f"""File: {file.path}

CODE MAP:
{format_code_map(file_map)}

RUFF PERFORMANCE DIAGNOSTICS:
{_format_ruff(diagnostics)}

SOURCE:
{format_source(file.content)}
"""

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    response = gemini_with_retry(
        client,
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=list[Finding],
            temperature=0.2,
        ),
    )
    findings: list[Finding] = response.parsed or []
    summary = (
        f"Reviewed {file.path}: {len(findings)} finding(s), "
        f"{len(diagnostics)} ruff PERF diagnostic(s) considered."
    )
    return AgentReport(agent="performance", findings=findings, summary=summary)
