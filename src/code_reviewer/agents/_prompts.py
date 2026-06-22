"""Shared prompt construction helpers used by all sub-agents."""
import time
from google import genai
from google.genai import errors as genai_errors
from ..context import FileMap

def gemini_with_retry(client, *, max_attempts=6, **kwargs):
    """Call generate_content with exponential backoff on transient errors."""
    delay = 3.0
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as e:
            status = getattr(e, "code", None) or getattr(e, "status_code", None)
            transient = status in (429, 500, 503, 504)
            if not transient or attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2


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
