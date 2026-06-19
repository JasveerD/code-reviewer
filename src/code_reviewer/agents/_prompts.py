"""Shared prompt construction helpers used by all sub-agents."""
from ..context import FileMap


def format_code_map(fm: FileMap) -> str:
    parts: list[str] = []
    if fm.functions:
        parts.append("Functions:")
        for f in fm.functions:
            parts.append(f"  - {f.signature} (lines {f.line_start}-{f.line_end})")
    if fm.classes:
        parts.append("Classes:")
        for c in fm.classes:
            parts.append(
                f"  - class {c.name} (lines {c.line_start}-{c.line_end}), "
                f"methods: {c.methods}"
            )
    if fm.imports:
        parts.append("Imports:")
        for imp in fm.imports:
            parts.append(f"  - {imp}")
    return "\n".join(parts) if parts else "(empty)"


def format_source(content: str) -> str:
    """Prefix each line with its 1-indexed line number for the LLM."""
    return "\n".join(f"{i+1:4d}  {line}" for i, line in enumerate(content.splitlines()))
