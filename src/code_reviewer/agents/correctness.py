"""
Correctness agent: detects logic bugs and type errors.

Uses pyright as a grounding tool, then asks Gemini to contextualize,
filter false positives, and add findings pyright can't catch.
"""
import os
from pathlib import Path
from google import genai
from google.genai import types

from ..ingestion.types import ReviewFile
from ..context import FileMap
from ..schemas import AgentReport, Finding
from ..tools.pyright_tool import run_pyright, PyrightDiagnostic
from ._prompts import format_code_map, format_source, gemini_with_retry

_SYSTEM_INSTRUCTION = """You are a code review agent specialized in correctness and logic bugs.

You receive:
- One source file's full content (with line numbers)
- A code map: functions and classes with line ranges
- Diagnostics from pyright (a static type checker), possibly empty

Produce a JSON list of Finding objects. Each Finding represents one real issue.

RULES:
1. Every pyright "error" should produce a Finding UNLESS you can explain why it's a false positive. Include "pyright:<rule>" in grounding. For pyright "warning" and "information", use judgment.
2. Add findings for logic bugs pyright cannot catch: off-by-one errors, missing edge cases (empty input, None, zero, negative), wrong operator, incorrect order of operations, missing error handling where it matters, race conditions. These have grounding=[].
3. DO NOT flag: style, naming, formatting, performance, or security issues. Those belong to other agents. Stay in your lane.
4. Severity:
   - critical: definitely a bug; crashes or corrupts data under normal use
   - high: likely a bug; fails on common inputs
   - medium: bug in edge cases
   - low: minor robustness issue
   - info: observation only
5. confidence: 0.9+ for pyright-grounded findings; 0.5-0.8 for LLM-inferred. Be honest.
6. Return at most 8 findings. Prioritize highest-severity.
7. agent="correctness" on every finding.
"""


def _format_pyright(diagnostics: list[PyrightDiagnostic]) -> str:
    if not diagnostics:
        return "(no pyright diagnostics)"
    lines = []
    for d in diagnostics:
        rule = f" [{d.rule}]" if d.rule else ""
        lines.append(f"  line {d.line_start}-{d.line_end} {d.severity}{rule}: {d.message}")
    return "\n".join(lines)


def review_correctness(file: ReviewFile, file_map: FileMap, workdir: Path) -> AgentReport:
    """Run pyright + Gemini, return a structured AgentReport."""
    diagnostics = run_pyright(workdir, target_file=file.path)

    prompt = f"""File: {file.path}

CODE MAP:
{format_code_map(file_map)}

PYRIGHT DIAGNOSTICS:
{_format_pyright(diagnostics)}

SOURCE (line numbers prefixed):
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
        f"{len(diagnostics)} pyright diagnostic(s) considered."
    )
    return AgentReport(agent="correctness", findings=findings, summary=summary)
