"""Output schemas for agents and the final report."""
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Location(BaseModel):
    file: str
    line_start: int
    line_end: int


class Finding(BaseModel):
    agent: Literal["correctness", "security", "performance"]
    category: str
    severity: Severity
    location: Location
    title: str
    description: str
    suggested_fix: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    grounding: list[str] = Field(
        default_factory=list,
        description="Static-tool rule IDs that support this finding, e.g. 'bandit:B608'",
    )


class AgentReport(BaseModel):
    agent: str
    findings: list[Finding]
    summary: str
