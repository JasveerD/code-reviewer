"""Run ruff's performance rules and return structured diagnostics."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RuffDiagnostic:
    file: str
    line_start: int
    line_end: int
    code: str        # e.g., "PERF401"
    message: str


def run_ruff_perf(workdir: Path, target_file: str) -> list[RuffDiagnostic]:
    """Run ruff with the PERF rule set on a single file."""
    cmd = [
        "uv", "run", "ruff", "check", target_file,
        "--select", "PERF",
        "--output-format", "json",
        "--no-fix",
    ]

    try:
        result = subprocess.run(
            cmd, cwd=workdir, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return []

    if not result.stdout:
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    diagnostics: list[RuffDiagnostic] = []
    for d in data:
        loc = d.get("location") or {}
        end_loc = d.get("end_location") or loc
        diagnostics.append(RuffDiagnostic(
            file=d.get("filename", ""),
            line_start=loc.get("row", 1),
            line_end=end_loc.get("row", loc.get("row", 1)),
            code=d.get("code", ""),
            message=d.get("message", ""),
        ))
    return diagnostics
