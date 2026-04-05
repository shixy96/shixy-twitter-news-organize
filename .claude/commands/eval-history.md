---
description: View eval history and compare invocations
argument-hint: '[--stage pipeline|editorial|dailypost] [--limit N] | compare <run-a> <run-b>'
---

View historical eval invocations and compare two runs.

## Options
- `--stage X`: Filter by stage (pipeline, editorial, dailypost)
- `--limit N`: Maximum entries to show, default: 20
- `compare <run-a> <run-b>`: Compare two runs by date or invocation path

## Steps
1. View history: `PYTHONPATH=src python3 eval/cli.py history [--stage X] [--limit N]`
2. Compare runs: `PYTHONPATH=src python3 eval/cli.py compare <run-a> <run-b>`
3. Report table or comparison results including Jaccard similarity and quality delta.
