# Multi-Agent Code Review System — Writeup

## Problem

Code review is the chokepoint of modern software delivery. Reviewers
get tired, security issues slip through under deadline pressure, and
the quality of feedback drops on long pull requests. Tools like
linters help, but they produce raw findings without context.

This project builds a multi-agent system that automates the *review*
part of code review: specialized agents look at a code change from
distinct perspectives, and a coordinator synthesizes their output into
one prioritized, actionable report.

## Architecture

Five-stage pipeline:

1. **Ingestion** — accepts a local file, a directory, or a GitHub PR
   URL. PR mode shallow-clones the head commit so static analyzers see
   a real filesystem. Both inputs normalize to the same `ReviewTarget`
   type; downstream stages don't know which one they got.

2. **Preprocessing** — parses each file once with tree-sitter into a
   `CodeContext` containing functions, classes, imports, and line
   ranges. Single source of truth shared across agents; tree-sitter
   recovers from syntax errors, so in-progress PRs are reviewable.

3. **Three specialized agents run in parallel:**
   - **Correctness agent** grounded by **pyright** — type errors,
     None dereferences, missing returns.
   - **Security agent** grounded by **bandit** — injection, weak
     crypto, hardcoded secrets, with CWE annotations.
   - **Performance agent** grounded by **ruff** PERF rules — O(n²)
     algorithms, N+1 patterns, anti-idioms.

   Each agent runs its static tool first, then passes the diagnostics
   and source to Gemini 2.5 Flash for contextual reasoning and false-
   positive filtering. Output is a structured Pydantic schema, so
   parsing never fails.

4. **Coordinator** synthesizes the three agent reports into one
   `ReviewReport`. Two-phase: deterministic spatial clustering groups
   findings by file and line proximity (cheap), then Gemini 2.5 Flash
   reasons about which clustered findings are the same underlying
   issue vs. genuinely separate. The merge step also resolves severity
   disagreements between agents and surfaces them in the output —
   when correctness and performance disagree, the report says so.

5. **Renderer** outputs to terminal (Rich) or markdown (suitable for
   PR comments, files, GitHub Action summaries).

## Google Technology

Two Google technologies, used where they fit:

**Google ADK (Agent Development Kit)** for orchestration. The three
sub-agents are wrapped as `BaseAgent` subclasses, composed into a
`ParallelAgent`, and the full pipeline is a `SequentialAgent([parallel,
coordinator])`. Session state carries the file, code map, and
intermediate reports between stages. ADK's declarative agent topology
makes the architecture readable directly from the code — adding a
fourth specialist would be one node.

**Gemini API** for the LLM layer. Sub-agents use Gemini 2.5 Flash
(cheap, fast, sufficient for grounded reasoning). The coordinator
also uses Flash given quota constraints, though Gemini 2.5 Pro would
be appropriate for the harder synthesis step in production. Structured
output via response schemas eliminates JSON parsing — every agent
returns a typed Pydantic object.

## Tradeoffs and what I'd improve

- **Performance bottleneck is Gemini latency.** End-to-end review 
  is ~15s per file; the three parallel agent calls each take 3-5s,
  and ADK adds negligible overhead. Real speedup would
  require batching multiple files into single Gemini calls.

- **Confidence scores are LLM self-reports.** They're correlated with
  actual reliability but not calibrated. A proper calibration pass
  (replay 100 PRs, compare findings to human review) would close that
  loop.

- **C++ and TypeScript work via pure LLM inference** because tree-
  sitter parsers exist but I haven't wired the static analyzers. The
  architecture supports this cleanly — adding `cppcheck` as a security
  tool would be a single file. The system degrades when language support
  is partial due to empty grounding, lower confidence, but findings
  are still produced.

- **PR comment posting is not wired up.** The markdown renderer
  produces PR-ready output, and posting it back to GitHub via PyGithub
  is a small addition. Kept the demo path local to avoid live API
  failure modes.

- **Single-file focus.** Multi-file findings (a function defined in
  one file misused in another) aren't surfaced because each file is
  reviewed in isolation. A cross-file pass over the code map would
  enable this.

## Reproducing

```bash
uv sync --extra dev
export GOOGLE_API_KEY=...
uv run review examples/sample.py -o review.md
uv run review https://github.com/owner/repo/pull/N -o pr-review.md
```

Both commands produce the same structured report from the same
pipeline — file mode and PR mode share everything except ingestion.
