"""Normalized input types — agents only see ReviewTarget."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class ChangedRange:
    line_start: int
    line_end: int
    change_type: Literal["added", "modified"]


@dataclass
class ReviewFile:
    path: str            # relative to workdir
    content: str
    language: str
    changed_ranges: list[ChangedRange] = field(default_factory=list)


@dataclass
class ReviewTarget:
    source: Literal["file", "pr"]
    workdir: Path
    files: list[ReviewFile]
    metadata: dict
