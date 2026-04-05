---
description: List available eval cases and suites
argument-hint: 'list [--skill pipeline|editorial|dailypost] | suites'
---

List available cases and suites for planning evaluation runs.

## Options
- `list [--skill X]`: List cases for a skill (pipeline, editorial, dailypost)
- `suites`: List all available suites

## Steps
1. List cases: `PYTHONPATH=src python3 eval/cli.py cases list [--skill X]`
2. List suites: `ls eval/cases/suites/`
3. Report case/suite listings with IDs, dates, and skill coverage.
