# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**x-news-skills** is a monorepo of 3 distributable pipeline skills that produce a daily AI news digest:

| Skill | Phase | Output |
|-------|-------|--------|
| `skills/x-news-fetch` | 1 | `filtered.json` (engagement-filtered candidates) |
| `skills/x-news-digest` | 2 | `post.json` + `post.md` (curated daily post) |
| `skills/x-news-tts` | 3 | `audio.mp3` (TTS朗读) |

**Runtime state contract**: `RUN_ROOT/daily/{date}/`. Shared skill inputs are `RUN_ROOT` and `REPORT_DATE`. A common local choice is `RUN_ROOT=state.local`, which is gitignored.

## Pipeline Workflow

Each skill has a `SKILL.md` that defines its interface. Run the full pipeline with `/run-pipeline`. For individual phases, read each skill's `SKILL.md` and run its scripts manually.

The core skill is **x-news-digest**: it reads filtered.json, selects 8-12 items, enriches them with tools (twitter/gh/WebFetch), writes Chinese titles and body text, and outputs post.json + post.md. Editorial rules are in `skills/x-news-digest/reference/editorial-rules.md`.

## Code Style

- **Python only** — all scripts are Python 3
- **Max 200 lines per script** (enforced by pipeline design)
- **Stdlib only** — no external Python dependencies beyond stdlib
- **Subprocess calls** use `twitter`, `gh`, `edge-tts` as external tools

## Git Conventions

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `refactor:`, etc.
- **Branch naming**: `feat/`, `fix/`, `docs/` prefixes

## Eval Harness

Run `eval/` harness with `python3 eval/cli.py <command>`:
- `eval diagnose --date YYYY-MM-DD` — diagnose quality issues
- `eval run --date YYYY-MM-DD` — full eval with 8 runs
- `eval benchmark --date YYYY-MM-DD` — multi-run aggregate metrics
- `eval cases list` — list all cases and fixtures

## Auto-Improve

Hill-climbing optimizer that iteratively improves `editorial-rules.md` using LLM-as-judge feedback. Inspired by [autoresearch](https://github.com/karpathy/autoresearch).

```bash
python3 improve/cli.py auto-improve --max-iters 10
python3 improve/cli.py auto-improve --dates 2026-04-06 --max-iters 5 --runs-per-iter 2
```

Or use `/auto-improve` slash command. See `improve/` directory for details.

- **Scoring**: structural (0-30, from eval_lib) + LLM-as-judge editorial quality (0-70, 7 dimensions) = composite 0-100
- **Loop**: propose rules change → run digest × N → judge → keep if Pareto-improved across all fixtures, discard otherwise
- **Tracking**: accepted changes committed to git, all experiments logged to `improve/experiments.jsonl`

## Running the Pipeline

```bash
RUN_ROOT="/path/to/runtime-root"
REPORT_DATE="$(TZ=Asia/Shanghai date '+%Y-%m-%d')"
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
mkdir -p "$DAILY_DIR"
export RUN_ROOT REPORT_DATE
# ... follow SKILL.md for each phase; each skill derives its own internal paths from RUN_ROOT + REPORT_DATE
```

Or use `/run-pipeline` skill for the full end-to-end run.
