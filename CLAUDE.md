# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**x-news-skills** is a monorepo of 5 distributable pipeline skills that produce a daily AI news digest:

| Skill | Phase | Output |
|-------|-------|--------|
| `skills/x-news-data-pipeline` | 1 | `filtered.json` (engagement-filtered candidates) |
| `skills/x-news-editorial` | 2 | `companion.json` (human-selected + categorized items) |
| `skills/x-news-to-daily-post` | 3 | `post.md` (rendered daily post) |
| `skills/x-news-tts` | 4 | `audio.mp3` (TTS朗读) |
| `skills/x-news-quality-audit` | 5 | `qa-report.md` (bypass QA, non-blocking) |

**Runtime state contract**: `RUN_ROOT/daily/{date}/`. Shared skill inputs are `RUN_ROOT` and `REPORT_DATE`. `RUN_LOG_PATH` defaults to `RUN_ROOT/daily/{date}/run.log.jsonl`, and `RUN_ID` is optional for traceability. A common local choice is `RUN_ROOT=state.local`, which is gitignored, but `state.local` is not part of the shared skill protocol.

## Pipeline Workflow

Each skill has a `SKILL.md` that defines its interface. Run the full pipeline with `/run-pipeline`. For individual phases, read each skill's `SKILL.md` and run its scripts manually.

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

## Shared Module

`src/x_news_shared/` provides:
- `normalize.py` — URL normalization utilities
- `runlog.py` — structured `run.log.jsonl` helpers
- `schema.py` — JSON Schema for all pipeline artifacts + `ALLOWED_CATEGORIES`
- `validate.py` — `validate_json_schema()` generic validator

Import via: `from x_news_shared import normalize, schema, validate`

## Running the Pipeline

```bash
RUN_ROOT="/path/to/runtime-root"
REPORT_DATE="$(TZ=Asia/Shanghai date '+%Y-%m-%d')"
DAILY_DIR="$RUN_ROOT/daily/$REPORT_DATE"
RUN_ID="${RUN_ID:-run-${REPORT_DATE}-$(TZ=UTC date '+%H%M%SZ')}"
RUN_LOG_PATH="$DAILY_DIR/run.log.jsonl"
mkdir -p "$DAILY_DIR"
export RUN_ROOT REPORT_DATE RUN_ID RUN_LOG_PATH
# ... follow SKILL.md for each phase; each skill derives its own internal paths from RUN_ROOT + REPORT_DATE
```

Or use `/run-pipeline` skill for the full end-to-end run.
