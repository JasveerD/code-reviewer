"""CLI entry point."""
import asyncio
import os
import sys
from pathlib import Path
import click
from rich.console import Console

from .ingestion.loader import from_path

console = Console()


@click.command()
@click.argument("target", type=str, required=False)
@click.option("--verify-gemini", is_flag=True, help="Check API connectivity and exit.")
def main(target: str | None, verify_gemini: bool) -> None:
    """Review a file, directory, or PR."""
    if verify_gemini:
        asyncio.run(_verify_gemini())
        return

    if target is None:
        console.print("[red]Provide a path or use --verify-gemini.[/red]")
        sys.exit(1)

    if target.startswith("http") or "#" in target:
        console.print("[yellow]PR mode not implemented yet (Day 2).[/yellow]")
        sys.exit(1)

    try:
        review_target = from_path(Path(target))
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(f"[green]✓[/green] Loaded {len(review_target.files)} file(s)")
    for f in review_target.files:
        lines = f.content.count("\n") + 1
        console.print(f"  - {f.path} ({f.language}, {lines} lines)")

    console.print("[dim]Agents not wired up yet — Day 2.[/dim]")


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


if __name__ == "__main__":
    main()
