---
description: Quick quality verification (diagnose + benchmark) for a date
argument-hint: '[date YYYY-MM-DD]'
---

Run diagnose + benchmark (8 runs) for a given date. This is the primary smoke test for pipeline quality.

## Steps
1. Run eval diagnose:
   ```bash
   PYTHONPATH=src python3 eval/cli.py diagnose --date YYYY-MM-DD
   ```
   (defaults to today in Asia/Shanghai if no date provided)
2. Run eval benchmark (8 runs for stability check):
   ```bash
   PYTHONPATH=src python3 eval/cli.py benchmark --date YYYY-MM-DD --runs 8
   ```
3. Report combined output including pass/fail status, Jaccard similarity, and any quality issues.
