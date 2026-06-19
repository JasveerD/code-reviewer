"""Async-callable wrappers around the synchronous review functions."""
import asyncio
from pathlib import Path

from ..ingestion.types import ReviewFile
from ..context import FileMap
from ..schemas import AgentReport

from .correctness import review_correctness
from .security import review_security
from .performance import review_performance


async def correctness_async(file: ReviewFile, file_map: FileMap, workdir: Path) -> AgentReport:
    return await asyncio.to_thread(review_correctness, file, file_map, workdir)


async def security_async(file: ReviewFile, file_map: FileMap, workdir: Path) -> AgentReport:
    return await asyncio.to_thread(review_security, file, file_map, workdir)


async def performance_async(file: ReviewFile, file_map: FileMap, workdir: Path) -> AgentReport:
    return await asyncio.to_thread(review_performance, file, file_map, workdir)
