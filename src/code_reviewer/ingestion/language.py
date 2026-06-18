"""Map file extensions to language identifiers."""
from pathlib import Path

_EXT_MAP = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".h": "cpp",
    ".c": "c",
}


def detect_language(path: Path) -> str:
    return _EXT_MAP.get(path.suffix.lower(), "unknown")
