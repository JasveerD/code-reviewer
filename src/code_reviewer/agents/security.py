"""Security agent: detects vulnerabilities and unsafe patterns."""
import os
from pathlib import Path
from google import genai
from google.genai import types

from ..ingestion.types import ReviewFile
from ..context import FileMap
from ..schemas import AgentReport, Finding
from ..tools.bandit_tool import run_bandit, BanditDiagnostic
from ._prompts import format_code_map, format_source, gemini_with_retry


_SYSTEM_INSTRUCTION = """You are a code review agent specialized in security vulnerabilities.

You receive:
- One source file (with line numbers)
- A code map: functions and classes
- Diagnostics from bandit (a Python security linter), possibly empty

Produce a JSON list of Finding objects.

RULES:
1. Every bandit finding with HIGH severity AND HIGH confidence should produce a Finding. For MEDIUM/LOW, use judgment — bandit has false positives. Grounding="bandit:<test_id>". Mention CWE if relevant.
2. Add findings for security issues bandit can't catch: business logic flaws (auth bypass, IDOR), missing input validation on user-controlled data, sensitive info in logs, insecure defaults, race conditions in security-critical paths, missing rate limiting. These have grounding=[].
3. Categories: injection (SQL, command, XSS, LDAP), authentication, authorization, cryptography weakness, hardcoded secrets, dangerous deserialization, SSRF, path traversal, weak randomness for security purposes.
4. DO NOT flag: correctness bugs, type errors, performance, style. Stay in your lane.
5. Severity:
   - critical: remote code execution, SQL injection, auth bypass, secrets in code committed to repo
   - high: XSS, weak crypto (MD5/SHA1 for security), SSRF, path traversal
   - medium: information disclosure, missing validation, insecure defaults
   - low: defense-in-depth concerns
   - info: hardening observations
6. confidence: 0.9+ for bandit HIGH/HIGH grounded; 0.6-0.8 for LLM inference.
7. Return at most 8 findings. agent="security" on every finding.
"""


def _format_bandit(diagnostics: list[BanditDiagnostic]) -> str:
    if not diagnostics:
        return "(no bandit diagnostics)"
    lines = []
    for d in diagnostics:
        cwe = f" CWE-{d.cwe}" if d.cwe else ""
        lines.append(
            f"  line {d.line_start}-{d.line_end} [{d.test_id}{cwe}] "
            f"severity={d.severity} confidence={d.confidence}: {d.message}"
        )
    return "\n".join(lines)


def review_security(file: ReviewFile, file_map: FileMap, workdir: Path) -> AgentReport:
    diagnostics = run_bandit(workdir, target_file=file.path)

    prompt = f"""File: {file.path}

CODE MAP:
{format_code_map(file_map)}

BANDIT DIAGNOSTICS:
{_format_bandit(diagnostics)}

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
        f"{len(diagnostics)} bandit diagnostic(s) considered."
    )
    return AgentReport(agent="security", findings=findings, summary=summary)
