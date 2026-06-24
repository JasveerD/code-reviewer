"""CLI entry point."""
import asyncio
import os
import sys
from pathlib import Path
import re
import click
from rich.console import Console
from .ingestion.loader import from_path
from .ingestion.pr import from_pr, parse_pr_ref
from .preprocessing import build_context
from .orchestrator import run_full_review
from .report import render_markdown

console = Console()


@click.command()
@click.argument("target", type=str, required=False)
@click.option("--verify-gemini", is_flag=True, help="Check API connectivity and exit.")
@click.option("--verbose", "-v", is_flag=True, help="Show per-agent raw findings.")
@click.option(
    "--output", "-o", type=click.Path(),
    help="Write the report as markdown to this path. Terminal output still shown.",)
@click.option(
    "--max-files", type=int, default=None,
    help="Limit number of files reviewed (useful for large PRs).",
)
def main(
    target: str | None,
    verify_gemini: bool,
    verbose: bool,
    output: str | None,
    max_files: int | None,
) -> None:    
    """Review a file, directory, or PR."""
    if verify_gemini:
        asyncio.run(_verify_gemini())
        return

    if target is None:
        console.print("[red]Provide a path or use --verify-gemini.[/red]")
        sys.exit(1)

    is_pr = target.startswith("http") or re.match(r"^[^/]+/[^/]+#\d+$", target)
    try:
        if is_pr:
            console.print(f"[dim]Cloning PR {target}...[/dim]")
            review_target = from_pr(target)
            pr_meta = review_target.metadata
            console.print(
                f"[green]✓[/green] PR #{pr_meta['number']}: "
                f"[bold]{pr_meta['title']}[/bold]"
            )
        else:
            review_target = from_path(Path(target))
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if max_files is not None:
        review_target.files = review_target.files[:max_files]

    console.print(f"[green]✓[/green] Loaded {len(review_target.files)} file(s)")
    context = build_context(review_target)
    if not review_target.files:
        console.print("[yellow]No reviewable code files in this PR.[/yellow]")
        return
    console.print()
    for f in review_target.files:
        fm = context.map_for(f.path)
        if fm is None:
            continue

        console.print(f"[bold]Reviewing {f.path}...[/bold]")
        agent_reports, review = asyncio.run(
            run_full_review(f, fm, review_target.workdir)
        )

        if verbose:
            _print_agent_reports(agent_reports)

        _print_review_report(review)

        if output:
            from pathlib import Path as _Path
            md = render_markdown(review)
            _Path(output).write_text(md)
            console.print(f"\n[green]✓[/green] Markdown report written to {output}")

async def _verify_gemini() -> None:
    """Smoke test: send a one-shot prompt through google-genai."""
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]Set GOOGLE_API_KEY in your environment.[/red]")
        sys.exit(1)

    from google import genai
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Reply with exactly one word: pong",
    )
    console.print(f"[green]✓[/green] Gemini responded: {resp.text.strip()}")

def _print_agent_reports(reports):
    for report in reports:
        console.print(f"\n[bold cyan]{report.agent}[/bold cyan]: [dim]{report.summary}[/dim]")
        if not report.findings:
            console.print("  [dim](no findings)[/dim]")
            continue
        for finding in report.findings:
            sev_color = _sev_color(finding.severity.value)
            console.print(
                f"  [{sev_color}]{finding.severity.value.upper()}[/{sev_color}] "
                f"line {finding.location.line_start}: {finding.title}"
            )
            console.print(f"    [dim]{finding.description}[/dim]")
            if finding.grounding:
                console.print(f"    [dim italic]grounded by: {', '.join(finding.grounding)}[/dim italic]")


def _print_review_report(review):
    console.print()
    console.print("[bold]═══ Review Report ═══[/bold]")
    console.print(f"[dim]{review.summary}[/dim]")
    console.print()
    if not review.findings:
        console.print("  [green]No issues found.[/green]")
        return
    for f in review.findings:
        sev_color = _sev_color(f.severity.value)
        console.print(
            f"[{sev_color}]{f.severity.value.upper()}[/{sev_color}] "
            f"line {f.location.line_start}: [bold]{f.title}[/bold]"
        )
        console.print(f"  {f.description}")
        agents = ", ".join(f.contributing_agents)
        console.print(f"  [dim]found by: {agents}[/dim]")
        if f.grounding:
            console.print(f"  [dim italic]grounded by: {', '.join(f.grounding)}[/dim italic]")
        if f.disagreement:
            console.print(f"  [yellow]⚠ disagreement:[/yellow] {f.disagreement}")
        if f.suggested_fix:
            console.print(f"  [dim]fix:[/dim] {f.suggested_fix}")
        console.print()


def _sev_color(severity: str) -> str:
    return {
        "critical": "red", "high": "red",
        "medium": "yellow", "low": "blue", "info": "dim",
    }.get(severity, "white")

if __name__ == "__main__":
    main()
