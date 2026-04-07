---
description: Run live digest eval N times and produce comparison report
argument-hint: '<date YYYY-MM-DD> [--runs N] [--model sonnet|haiku|opus] [--enrich] [--filtered <path>]'
---

Run live digest evaluation for x-news-digest. Executes the digest skill N times via `claude -p`, validates each output, and produces a comparison report.

## Options
- `date`: Report date to evaluate (required)
- `--runs N`: Number of runs (default: 8)
- `--model X`: Claude model to use (default: sonnet)
- `--enrich`: Enable enrichment with tools (twitter/gh/WebFetch)
- `--filtered <path>`: Path to filtered.json (default: eval/fixtures/{date}/filtered.json)

## Steps
1. Parse date (required), optional `--runs` (default 8), `--model` (default sonnet), `--enrich` (default off)
2. Run: `PYTHONPATH=. python3 eval/cli.py live-digest --date {date} --runs {N} --model {model} [--enrich]`
3. Read and display the output report
