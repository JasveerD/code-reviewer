"""Run bandit as a subprocess and return structured diagnostics."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BanditDiagnostic:
    file: str
    line_start: int
    line_end: int
    severity: str         # HIGH | MEDIUM | LOW (bandit's scale)
    confidence: str       # HIGH | MEDIUM | LOW
    test_id: str          # e.g., "B608"
    test_name: str
    message: str
    cwe: int | None       # CWE number if available


def run_bandit(workdir: Path, target_file: str | None = None) -> list[BanditDiagnostic]:
    cmd = ["uv", "run", "bandit", "-f", "json", "-q"]
    if target_file:
        cmd.append(target_file)
    else:
        cmd.extend(["-r", "."])

    try:
        result = subprocess.run(
            cmd, cwd=workdir, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return []

    if not result.stdout:
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    diagnostics: list[BanditDiagnostic] = []
    for r in data.get("results", []):
        line_range = r.get("line_range") or [r.get("line_number", 1)]
        cwe_data = r.get("issue_cwe") or {}
        cwe_id = cwe_data.get("id") if isinstance(cwe_data, dict) else None
        diagnostics.append(BanditDiagnostic(
            file=r.get("filename", ""),
            line_start=line_range[0] if line_range else 1,
            line_end=line_range[-1] if line_range else 1,
            severity=r.get("issue_severity", "MEDIUM"),
            confidence=r.get("issue_confidence", "MEDIUM"),
            test_id=r.get("test_id", ""),
            test_name=r.get("test_name", ""),
            message=r.get("issue_text", ""),
            cwe=cwe_id,
        ))
    return diagnostics
