# Plan: `/eval-digest` — Live Eval for x-news-digest

## Context

Current eval system is fixture-only: it validates pre-existing `post.json` files but never runs the digest skill. User needs **live eval** — actually execute x-news-digest N times via `claude -p`, validate each output, compare across runs for selection stability and writing quality.

Target UX: `/eval-digest 2026-04-06` → 8 runs, comparison report.

---

## Architecture

```
/eval-digest 2026-04-06
    → Claude Code reads slash command, runs:
      python3 eval/cli.py live-digest --date 2026-04-06 --runs 8
    → live_runner.py orchestrates 8 sequential claude -p calls
    → each call: prompt(filtered.json + rules) → post.json → evaluate_digest()
    → build_benchmark() + render report
```

---

## Files to Create

### 1. `eval/live_runner.py` (NEW, ~150 lines)

Core orchestrator for live digest eval.

**Functions:**
- `build_prompt(filtered_json: str, editorial_rules: str, skill_spec: str, date: str) -> str`
  - Constructs the full prompt with inlined filtered.json + rules
  - System: editorial rules + writing format spec
  - User: filtered.json content + date + "output post.json only"

- `run_single(date: str, run_dir: Path, filtered_path: Path, model: str, enrich: bool) -> dict`
  1. Read filtered.json + editorial-rules.md + SKILL.md
  2. Build prompt via `build_prompt()` (no-enrich: skip Step 3 instructions)
  3. Write user prompt to temp file
  4. Run: `claude -p --bare --model {model} [--tools ""/tool flags] < prompt.txt`
  5. Extract JSON from stdout (strip markdown fences if present)
  6. Write `post.json` to `run_dir/artifacts/`
  7. Run `render_md.py` to produce `post.md`
  8. Call `evaluate_digest(artifacts_dir)` → metrics
  9. Write `metrics.json`
  10. Return metrics dict

- `run_live_eval(date: str, runs: int, model: str, enrich: bool, filtered_path: Path | None) -> dict`
  1. Resolve filtered_path (fixture → `eval/fixtures/{date}/filtered.json`)
  2. Create invocation dir: `eval/runs/{date}/{timestamp}-live-{id}/`
  3. Sequential loop: `run_single()` × N runs
  4. `build_benchmark()` on collected metrics
  5. Render comparison report
  6. Return result dict with benchmark + report text

- `render_report(benchmark: dict, metrics_list: list[dict]) -> str`
  - Per-run status table
  - Selection frequency table (which items selected how many times)
  - Jaccard similarity
  - Category distribution across runs
  - Issues summary

### 2. `.claude/commands/eval-digest.md` (NEW, ~25 lines)

```yaml
---
description: Run live digest eval N times and produce comparison report
argument-hint: '<date YYYY-MM-DD> [--runs N] [--model sonnet|haiku|opus] [--enrich]'
---
```

Instructions:
1. Parse date (required), optional `--runs` (default 8), `--model` (default sonnet), `--enrich` (default off)
2. Run: `PYTHONPATH=. python3 eval/cli.py live-digest --date {date} --runs {N} --model {model} [--enrich]`
3. Read and display the output report

---

## Files to Modify

### 3. `eval/cli.py` — Add `live-digest` command

Add subparser `live-digest` with args: `--date`, `--runs` (default 8), `--model` (default sonnet), `--enrich` (store_true)
Add `cmd_live_digest()` that calls `live_runner.run_live_eval()` and prints report.

### 4. `eval/eval_lib.py` — Enhanced benchmark metrics

Add to `build_benchmark()` for digest:
- `item_count_mean`, `item_count_std` — selection count stability
- `selection_frequency` — dict mapping canonical_id → count (how many runs selected it)
- Keep existing: `avg_pairwise_jaccard`, pass/warn/fail counts

---

## Prompt Strategy

**System context** (built in `build_prompt()`):
- Inline `editorial-rules.md` content
- SKILL.md Steps 1, 2, 4, 5 (skip Step 3 enrich, Step 6 render)
- post.json schema + example from SKILL.md
- Hard constraint: "Output ONLY the JSON object for post.json. No explanation, no markdown fences."

**User message**:
```
REPORT_DATE: 2026-04-06

## filtered.json

{full filtered.json content}
```

**No-enrich mode** (default):
```bash
claude -p \
  --bare \
  --model sonnet \
  --tools "" \
  --system-prompt "$SYSTEM_PROMPT" \
  < user_prompt.txt
```
- `--bare`: skip hooks, CLAUDE.md, etc.
- `--tools ""`: disable all tools (pure text generation)
- `--model sonnet`: cost-effective for eval (8 runs)
- Prompt includes filtered.json inline, skip Step 3

**Enrich mode** (`--enrich`):
```bash
claude -p \
  --bare \
  --model sonnet \
  --allowed-tools "Bash,Read,Write,WebFetch" \
  --dangerously-skip-permissions \
  --system-prompt "$SYSTEM_PROMPT" \
  < user_prompt.txt
```
- Enables tool access for twitter CLI, gh CLI, WebFetch
- Full SKILL.md Steps 1-6
- More expensive, slower, less deterministic

Note: user prompt written to temp file and piped via stdin (too large for CLI arg).

---

## Report Format

```
# Live Eval Report: x-news-digest / 2026-04-06

**Runs**: 8 | **Pass**: 6 | **Warn**: 1 | **Fail**: 1
**Avg Jaccard (selected_ids)**: 0.72
**Item Count**: mean 10.2, std 1.1

## Per-Run Summary

| Run | Status | Items | Issues |
|-----|--------|-------|--------|
| 001 | PASS   | 10    |        |
| 002 | PASS   | 11    |        |
| 003 | WARN   | 7     | only 7 items |

## Selection Frequency (top items)

| canonical_id        | Selected | % | Avg Rank |
|---------------------|----------|---|----------|
| 2039805659525644595 | 8/8      | 100% | 1.2 |
| 2040204860080230594 | 7/8      | 88%  | 3.0 |
| ...

## Category Distribution

| Category | Avg Items | Std |
|----------|-----------|-----|
| 模型发布  | 2.5       | 0.5 |
| 开发生态  | 3.1       | 0.8 |
| ...
```

---

## Reuse Existing Code

| Function | From | Purpose |
|----------|------|---------|
| `evaluate_digest()` | eval_lib.py | Validate each run's post.json |
| `build_benchmark()` | eval_lib.py | Aggregate metrics across runs |
| `pairwise_jaccard()` | eval_lib.py | Selection stability |
| `create_invocation_dir()` | eval_lib.py | Timestamped run dirs |
| `load_json()`, `write_json()` | eval_lib.py | JSON I/O |
| `ensure_dir()` | eval_lib.py | Dir creation |
| `find_case_for_date()` | eval_ops.py | Resolve fixture path |
| `render_md.py` | scripts/ | post.json → post.md |

---

## Verification

```bash
# Smoke test (2 runs, fast)
/eval-digest 2026-04-06 --runs 2

# Full eval (8 runs, default)
/eval-digest 2026-04-06

# With enrich
/eval-digest 2026-04-06 --enrich --runs 2

# Manual CLI
PYTHONPATH=. python3 eval/cli.py live-digest --date 2026-04-06 --runs 8

# Check outputs
ls eval/runs/2026-04-06/*/results/run-*/artifacts/post.json
cat eval/runs/2026-04-06/*/results/benchmark.json
```

---

## Implementation Order

1. `eval/live_runner.py` — core logic (prompt build + run + report)
2. `eval/eval_lib.py` — add enhanced benchmark metrics
3. `eval/cli.py` — add `live-digest` command
4. `.claude/commands/eval-digest.md` — slash command
5. Test with: `/eval-digest 2026-04-06 --runs 2` (small run first)
