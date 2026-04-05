---
description: Run eval with control over stage, runs, and suites
argument-hint: '--date YYYY-MM-DD [--stage pipeline|editorial|dailypost] [--runs N] | --suite <suite-id> [--runs N]'
---

Run evaluation with configurable parameters for skill development.

## Options
- `--date YYYY-MM-DD`: Report date to evaluate
- `--stage X`: Stage to run (pipeline, editorial, dailypost), default: editorial
- `--runs N`: Number of runs, default: 8 for statistical significance
- `--suite <suite-id>`: Run a full suite instead (e.g., suite-2026-04-01)

## Steps
1. Run eval:
   - Single stage: `PYTHONPATH=src python3 eval/cli.py run --date YYYY-MM-DD --with-fixtures --stage X --runs N`
   - Suite: `PYTHONPATH=src python3 eval/cli.py suite --suite <suite-id> --runs N`
2. Report invocation path, pass/fail status, and aggregate metrics.
