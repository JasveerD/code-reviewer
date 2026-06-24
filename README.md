# code-reviewer

A multi-agent code review system. Three specialized agents — correctness, security, performance — review a file or PR in parallel, each grounded in real static analysis tools. A coordinator merges their findings into one prioritized actionable report.

Built for the GDG on Campus York University AI case competition (June 2026).

## What it does

```bash
$ uv run review examples/sample.py

✓ Loaded 1 file(s)
  - sample.py (python, 50 lines)
    → 5 functions, 1 classes, 2 imports

Reviewing sample.py...

═══ Review Report ═══
9 issue(s): 3 critical, 4 high, 1 medium, 1 low. 5 grounded by static analysis.

CRITICAL line 6: Hardcoded API Key
  An API key is hardcoded directly in the source code...
  found by: security
  fix: Remove the hardcoded API key. Store sensitive credentials in...

CRITICAL line 29: Command Injection Vulnerability
  The run_command function executes a shell command using subprocess.run with shell=True...
  found by: security
  grounded by: bandit:B602, CWE-78
  ...
```

Works on local files, directories, and public GitHub PR URLs.

## Architecture

```
File / PR  ──▶  Preprocessing  ──▶  ┌─ Correctness agent ─┐
                (tree-sitter)       │  (pyright)          │
                                    ├─ Security agent ────┤  ──▶  Coordinator  ──▶  Report
                                    │  (bandit)           │       (synthesis)       (markdown)
                                    └─ Performance agent ─┘
                                       (ruff)
```

Each agent runs its static tool first (deterministic findings with rule IDs), then passes the results plus the source to Gemini 2.5 Flash for contextual reasoning and false-positive filtering. Output is a structured Pydantic schema — never raw text. The coordinator clusters findings by spatial proximity, then uses Gemini to merge cross-agent duplicates and surface severity disagreements.

Orchestration is built on **Google Agent Development Kit (ADK)** — the three reviewers compose into a `ParallelAgent`, and the full pipeline is `SequentialAgent([parallel, coordinator])`.

Full architectural writeup in [`WRITEUP.md`](./WRITEUP.md).

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Gemini API key from [aistudio.google.com](https://aistudio.google.com/) — paid tier recommended (free tier is 20 requests/day, which is ~5 reviews)
- macOS, Linux, or WSL — tested on macOS Apple Silicon

## Installation

```bash
git clone https://github.com/JasveerD/code-reviewer.git
cd code-reviewer
uv sync --extra dev
export GOOGLE_API_KEY="your-key-here"
```

Verify the Gemini connection:

```bash
uv run review --verify-gemini
# → ✓ Gemini responded: pong
```

## Usage

**Review a single file:**

```bash
uv run review examples/sample.py
```

**Review and write a markdown report:**

```bash
uv run review examples/sample.py -o review.md
```

**Review a public GitHub PR:**

```bash
uv run review https://github.com/owner/repo/pull/N
```

**Cap the number of files reviewed (useful for large PRs):**

```bash
uv run review https://github.com/owner/repo/pull/N --max-files 3
```

**See raw per-agent output alongside the synthesized report:**

```bash
uv run review examples/sample.py -v
```

## How the agents work

Each sub-agent has the same shape: a deterministic static analyzer wrapped as a tool, a focused system prompt, and Pydantic-typed structured output.

| Agent | Tool | What it catches |
| --- | --- | --- |
| Correctness | [pyright](https://github.com/microsoft/pyright) | Type errors, None dereferences, missing returns, logic bugs |
| Security | [bandit](https://github.com/PyCQA/bandit) | Injection, weak crypto, hardcoded secrets, with CWE refs |
| Performance | [ruff](https://github.com/astral-sh/ruff) PERF rules | O(n²) patterns, anti-idioms, inefficient constructions |

Every finding carries a `grounding` field. If a static tool flagged it, the field shows the rule ID (`bandit:B602`, `pyright:reportOptionalSubscript`). If the LLM inferred it, the field is empty and the confidence score is lower. The coordinator uses this when prioritizing.

## Coordinator behavior

When multiple agents flag the same issue (a blocking I/O call in an async function shows up as both a correctness bug and a performance bug), the coordinator merges them into one finding with `found by: correctness, performance`. When agents disagree on severity for the same issue, the merged finding includes an explicit `Agent disagreement:` note explaining the resolution. The synthesis step is the difference between "three linters in a trench coat" and a coherent review.

## Languages

Python is fully supported (all three static analyzers run). For other languages — JavaScript, TypeScript, Go, Rust, C, C++, Java — tree-sitter still parses and the LLM-based agents still produce findings, but with empty `grounding` and lower confidence since the static tools don't run. Adding a per-language static-analyzer adapter (e.g. `cppcheck` for C++) is a single new file under `src/code_reviewer/tools/`.

## Project structure

```
src/code_reviewer/
├── cli.py                  # entry point
├── schemas.py              # Finding, AgentReport, ReviewReport
├── context.py              # CodeContext, FileMap, FunctionInfo
├── preprocessing.py        # tree-sitter parse → CodeContext
├── coordinator.py          # synthesis: cluster + LLM merge
├── orchestrator.py         # ADK SequentialAgent([ParallelAgent, Coordinator])
├── report.py               # markdown renderer
├── ingestion/
│   ├── types.py            # ReviewTarget, ReviewFile, ChangedRange
│   ├── loader.py           # file/directory ingestion
│   ├── pr.py               # PR ingestion via shallow clone
│   └── language.py         # extension → language map
├── agents/
│   ├── correctness.py
│   ├── security.py
│   ├── performance.py
│   └── _prompts.py         # shared formatters + retry helper
└── tools/
    ├── pyright_tool.py
    ├── bandit_tool.py
    └── ruff_tool.py
```

## License

MIT.

## Author

Jasveer Singh Dhillon — [JasveerD](https://github.com/JasveerD)
