"""ADK-based parallel orchestration of the three review agents."""
from __future__ import annotations
from typing import AsyncGenerator
from pathlib import Path
import asyncio

from google.adk.agents import BaseAgent, ParallelAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from typing_extensions import override
from google.adk.agents import SequentialAgent
from .coordinator import synthesize
from .schemas import ReviewReport

from .agents import correctness_async, security_async, performance_async
from .ingestion.types import ReviewFile
from .context import FileMap
from .schemas import AgentReport


class _ReviewerAgent(BaseAgent):
    """Thin ADK wrapper: reads file+map+workdir from session state, writes report back."""

    _kind: str   # "correctness" | "security" | "performance"

    def __init__(self, *, name: str, kind: str):
        super().__init__(name=name)
        self._kind = kind

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        file: ReviewFile = state["__file"]
        file_map: FileMap = state["__file_map"]
        workdir: Path = state["__workdir"]

        runner_fn = {
            "correctness": correctness_async,
            "security": security_async,
            "performance": performance_async,
        }[self._kind]

        report: AgentReport = await runner_fn(file, file_map, workdir)

        # Write the result into session state under a per-agent key,
        # serializing through dict so ADK's state diff is clean
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={f"report_{self._kind}": report.model_dump()}),
        )

class _CoordinatorAgent(BaseAgent):
    """ADK wrapper around the synthesize() function. Reads sub-agent reports from state."""

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        reports: list[AgentReport] = []
        for kind in ("correctness", "security", "performance"):
            data = state.get(f"report_{kind}")
            if data is not None:
                reports.append(AgentReport.model_validate(data))

        file = state["__file"]
        review_report = await asyncio.to_thread(synthesize, reports, [file.path])

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta={"review_report": review_report.model_dump()}),
        )


def _build_parallel_agent() -> ParallelAgent:
    return ParallelAgent(
        name="parallel_reviewers",
        sub_agents=[
            _ReviewerAgent(name="correctness_agent", kind="correctness"),
            _ReviewerAgent(name="security_agent",   kind="security"),
            _ReviewerAgent(name="performance_agent", kind="performance"),
        ],
    )


async def run_parallel_review(
    file: ReviewFile, file_map: FileMap, workdir: Path
) -> list[AgentReport]:
    parallel = _build_parallel_agent()
    runner = InMemoryRunner(agent=parallel, app_name="code_reviewer")

    session = await runner.session_service.create_session(
        app_name="code_reviewer",
        user_id="local",
        state={"__file": file, "__file_map": file_map, "__workdir": workdir},
    )

    dummy = genai_types.Content(role="user", parts=[genai_types.Part(text="review")])

    async for _ in runner.run_async(
        user_id="local", session_id=session.id, new_message=dummy
    ):
        pass

    final = await runner.session_service.get_session(
        app_name="code_reviewer", user_id="local", session_id=session.id
    )

    reports: list[AgentReport] = []
    for kind in ("correctness", "security", "performance"):
        data = final.state.get(f"report_{kind}")
        if data is not None:
            reports.append(AgentReport.model_validate(data))
    return reports

async def run_full_review(
    file: ReviewFile, file_map: FileMap, workdir: Path
) -> tuple[list[AgentReport], ReviewReport]:
    """Run parallel agents followed by coordinator, all through ADK."""
    parallel = _build_parallel_agent()
    coordinator = _CoordinatorAgent(name="coordinator")
    full = SequentialAgent(name="full_review", sub_agents=[parallel, coordinator])

    runner = InMemoryRunner(agent=full, app_name="code_reviewer")
    session = await runner.session_service.create_session(
        app_name="code_reviewer",
        user_id="local",
        state={"__file": file, "__file_map": file_map, "__workdir": workdir},
    )

    dummy = genai_types.Content(role="user", parts=[genai_types.Part(text="review")])
    async for _ in runner.run_async(
        user_id="local", session_id=session.id, new_message=dummy
    ):
        pass

    final = await runner.session_service.get_session(
        app_name="code_reviewer", user_id="local", session_id=session.id
    )

    # Pull sub-agent reports
    agent_reports: list[AgentReport] = []
    for kind in ("correctness", "security", "performance"):
        data = final.state.get(f"report_{kind}")
        if data is not None:
            agent_reports.append(AgentReport.model_validate(data))

    # Pull synthesized report
    review_data = final.state.get("review_report")
    review_report = (
        ReviewReport.model_validate(review_data)
        if review_data is not None
        else ReviewReport(findings=[], summary="Synthesis unavailable.", files_reviewed=[file.path])
    )

    return agent_reports, review_report
