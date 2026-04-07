# x-news Eval Infrastructure

Eval harness for x-news-digest, providing live quality assessment.

## CLI

```bash
PYTHONPATH=. python3 eval/cli.py live-digest --date 2026-04-06 --runs 8
```

## Commands

| Command | Description |
|---------|-------------|
| `live-digest --date 2026-04-06 --runs 8` | Run live digest eval N times and produce comparison report |

## Structure

```
eval/
├── cli.py            # CLI entry point
├── eval_lib.py       # Core eval library (evaluate_digest, build_benchmark)
├── live_runner.py    # Live digest eval orchestrator
├── fixtures/         # Input fixture data (filtered.json per date)
│   └── 2026-04-06/
│       └── filtered.json
└── runs/             # eval output (gitignored)
    └── 2026-04-06/
```

## Quality Checks (x-news-digest)

- post.json has valid frontmatter fields
- Categories from allowed set
- Item titles are Chinese, not direct copies
- Item bodies are Chinese, minimum 80 chars
- No placeholder text
- Item count in 8-12 range

## Multi-run Stability

- Jaccard similarity >= 0.75 across runs (selected IDs)
- Selection frequency tracking across runs
- Item count mean/std for consistency measurement

## Auto-Improve (`improve/`)

A separate hill-climbing optimizer that builds on top of the eval infrastructure to automatically improve `editorial-rules.md`. See `improve/` directory and `/auto-improve` slash command.

Key integration: `improve/loop.py` reuses `live_runner.run_single()` and `eval_lib.evaluate_digest()` for running and scoring digest outputs, adding an LLM-as-judge layer (`improve/judge.py`) for editorial quality scoring beyond structural checks.
