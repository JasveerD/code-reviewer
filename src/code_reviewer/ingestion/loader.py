"""Load files or PRs into a normalized ReviewTarget."""
from pathlib import Path
from .types import ReviewTarget, ReviewFile
from .language import detect_language


def from_path(path: Path) -> ReviewTarget:
    """Load a single file or a directory of files."""
    path = path.resolve()
    if path.is_file():
        return _single_file(path)
    if path.is_dir():
        return _directory(path)
    raise FileNotFoundError(f"{path} does not exist")


def _single_file(path: Path) -> ReviewTarget:
    content = path.read_text(encoding="utf-8")
    return ReviewTarget(
        source="file",
        workdir=path.parent,
        files=[ReviewFile(
            path=path.name,
            content=content,
            language=detect_language(path),
        )],
        metadata={"filename": path.name},
    )


def _directory(path: Path) -> ReviewTarget:
    files = []
    for p in path.rglob("*"):
        if not p.is_file() or _ignored(p):
            continue
        lang = detect_language(p)
        if lang == "unknown":
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(ReviewFile(
            path=str(p.relative_to(path)),
            content=content,
            language=lang,
        ))
    return ReviewTarget(
        source="file",
        workdir=path,
        files=files,
        metadata={"root": str(path)},
    )


_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def _ignored(p: Path) -> bool:
    return any(part in _IGNORE_DIRS for part in p.parts)
