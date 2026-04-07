---
description: Run auto-improve hill-climbing loop to optimize editorial-rules.md
argument-hint: '[--dates YYYY-MM-DD ...] [--max-iters N] [--runs-per-iter N]'
---

Run the auto-improve hill-climbing loop that iteratively optimizes `editorial-rules.md` using LLM-as-judge feedback.

## Steps

1. Parse arguments from `$ARGUMENTS`: extract `--dates`, `--max-iters`, `--runs-per-iter`, `--digest-model`, `--judge-model`, `--proposer-model`. Defaults: all fixtures, 10 iters, 3 runs, sonnet digest, opus judge, opus proposer.

2. Run the auto-improve CLI:

```bash
cd $PROJECT_ROOT
python3 improve/cli.py auto-improve $ARGUMENTS
```

3. After completion, display:
   - Number of accepted/rejected iterations
   - Best scores per fixture date
   - Git log of accepted commits: `git log --oneline -20`

4. If any iterations were accepted, show the diff of editorial-rules.md from before the run:
```bash
git diff HEAD~N -- skills/x-news-digest/reference/editorial-rules.md
```
(where N = number of accepted iterations)
