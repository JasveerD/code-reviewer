"""Run pyright as a subprocess and return structured diagnostics."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PyrightDiagnostic:
    file: str
    line_start: int       # 1-indexed
    line_end: int
    severity: str         # "error" | "warning" | "information"
    message: str
    rule: str | None      # e.g. "reportGeneralTypeIssues", may be None


def run_pyright(workdir: Path, target_file: str | None = None) -> list[PyrightDiagnostic]:
    """Run pyright in JSON output mode. Returns parsed diagnostics.

    If target_file is None, pyright analyzes the whole workdir.
    Empty list on parse failure or no findings — never raises.
    """
    cmd = ["uv", "run", "pyright", "--outputjson"]
    if target_file:
        cmd.append(target_file)

    try:
        result = subprocess.run(
            cmd, cwd=workdir, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return []

    # pyright exits non-zero when it finds errors — that's expected, don't treat as failure
    if not result.stdout:
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    diagnostics = []
    for d in data.get("generalDiagnostics", []):
        rng = d.get("range", {})
        diagnostics.append(PyrightDiagnostic(
            file=d.get("file", ""),
            line_start=rng.get("start", {}).get("line", 0) + 1,  # 0→1 indexed
            line_end=rng.get("end", {}).get("line", 0) + 1,
            severity=d.get("severity", "warning"),
            message=d.get("message", ""),
            rule=d.get("rule"),
        ))
    return diagnostics
