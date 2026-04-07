#!/usr/bin/env python3
"""
Live digest eval: runs x-news-digest N times via `claude -p` and produces comparison report.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIGEST_DIR = REPO_ROOT / "skills" / "x-news-digest"
SKILL_MD = SKILL_DIGEST_DIR / "SKILL.md"
EDITORIAL_RULES = SKILL_DIGEST_DIR / "reference" / "editorial-rules.md"
RENDER_MD = SKILL_DIGEST_DIR / "scripts" / "render_md.py"

EVAL_ROOT = REPO_ROOT / "eval"
EVAL_RUNS_ROOT = EVAL_ROOT / "runs"

import sys

_EVAL_DIR = EVAL_ROOT
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from eval_lib import (
    EVAL_ROOT,
    EVAL_RUNS_ROOT,
    build_benchmark,
    ensure_dir,
    evaluate_digest,
    load_json,
    short_id,
    timestamp_token,
    write_json,
)


def build_prompt(
    filtered_json: str,
    editorial_rules: str,
    skill_spec: str,
    date: str,
    enrich: bool = False,
) -> tuple[str, str]:
    """Build system prompt and user prompt for live digest eval.

    Returns (system_prompt, user_prompt).
    """
    system_parts = [
        editorial_rules,
        "",
        "## Writing Format Spec",
        skill_spec,
    ]
    system_prompt = "\n".join(system_parts)

    user_parts = [
        f"REPORT_DATE: {date}",
        "",
        "## filtered.json",
        filtered_json,
    ]

    if not enrich:
        user_parts.extend(
            [
                "",
                "Note: Do NOT use any tools. Do NOT enrich. Output ONLY the JSON object.",
            ]
        )
    else:
        user_parts.extend(
            [
                "",
                "You may use Bash, Read, Write, WebFetch to enrich information.",
            ]
        )

    user_prompt = "\n".join(user_parts)
    return system_prompt, user_prompt


def run_single(
    date: str,
    run_dir: Path,
    filtered_path: Path,
    model: str,
    enrich: bool,
    run_index: int,
) -> dict:
    """Run a single live digest eval.

    Returns metrics dict.
    """
    artifacts_dir = ensure_dir(run_dir / "results" / "artifacts")

    # Read inputs
    filtered_json = filtered_path.read_text(encoding="utf-8")
    editorial_rules = EDITORIAL_RULES.read_text(encoding="utf-8")
    skill_md = SKILL_MD.read_text(encoding="utf-8")

    # Build prompt - extract relevant steps from SKILL.md
    # Steps 1, 2, 4, 5 (skip Step 3 enrich unless enrich=True, skip Step 6 render)
    lines = skill_md.splitlines()
    step_markers = []
    for i, line in enumerate(lines):
        if re.match(r"^### Step \d+:", line):
            step_markers.append((i, re.match(r"^### Step (\d+):", line).group(1)))

    skill_spec_parts = []
    for idx, (line_no, step_num) in enumerate(step_markers):
        step_num_int = int(step_num)
        if step_num_int in (1, 2, 4, 5):
            pass  # include
        elif step_num_int == 3 and enrich:
            pass  # include when enriching
        else:
            continue  # skip
        next_marker = step_markers[idx + 1][0] if idx + 1 < len(step_markers) else len(lines)
        step_content = "\n".join(lines[line_no:next_marker])
        skill_spec_parts.append(step_content)

    skill_spec = "\n\n".join(skill_spec_parts)

    system_prompt, user_prompt = build_prompt(
        filtered_json, editorial_rules, skill_spec, date, enrich=enrich
    )

    # Write user prompt to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(user_prompt)
        prompt_file = f.name

    try:
        # Build claude command
        cmd = [
            "claude",
            "-p",
            "--bare",
            "--model",
            model,
        ]

        if enrich:
            cmd += [
                "--allowed-tools",
                "Bash,Read,Write,WebFetch",
                "--dangerously-skip-permissions",
            ]

        cmd += [
            "--system-prompt",
            system_prompt,
        ]

        # Pipe user prompt via stdin
        with open(prompt_file, "r", encoding="utf-8") as pf:
            result = subprocess.run(
                cmd,
                stdin=pf,
                capture_output=True,
                text=True,
                timeout=120,
            )

        raw_output = result.stdout.strip()

        # Extract JSON from output (strip markdown fences if present)
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```",
            raw_output,
            re.DOTALL,
        )
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find raw JSON object
            json_str = raw_output.strip()

        # Parse JSON
        try:
            post_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            write_json(
                artifacts_dir / "post.json", {"_parse_error": str(e), "_raw": raw_output[:500]}
            )
            return {
                "skill": "x-news-digest",
                "status": "FAIL",
                "errors": [f"JSON parse error: {e}"],
                "run": run_index,
            }

        # Write post.json
        post_json_path = artifacts_dir / "post.json"
        write_json(post_json_path, post_data)

        # Render post.md
        post_md_path = artifacts_dir / "post.md"
        try:
            subprocess.run(
                [
                    "python3",
                    str(RENDER_MD),
                    "--input",
                    str(post_json_path),
                    "--output",
                    str(post_md_path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            pass  # render failure is non-fatal

        # Evaluate
        metrics = evaluate_digest(artifacts_dir)
        metrics["run"] = run_index
        write_json(run_dir / "results" / f"run-{run_index:03d}" / "metrics.json", metrics)

        return metrics

    finally:
        Path(prompt_file).unlink(missing_ok=True)


def run_live_eval(
    date: str,
    runs: int = 8,
    model: str = "sonnet",
    enrich: bool = False,
    filtered_path: Path | None = None,
) -> dict:
    """Run live digest eval N times and produce benchmark report."""
    # Resolve filtered path
    if filtered_path is None:
        fixture_path = EVAL_ROOT / "fixtures" / date / "filtered.json"
        if fixture_path.exists():
            filtered_path = fixture_path
        else:
            return {
                "error": f"No filtered.json found for {date}. Run pipeline first or provide --filtered."
            }

    # Create invocation dir: eval/runs/{date}/{timestamp}-live-{id}/
    run_root = ensure_dir(EVAL_RUNS_ROOT / date)
    inv_dir = None
    for _ in range(10):
        name = f"{timestamp_token()}-live-{short_id()}"
        d = run_root / name
        if not d.exists():
            ensure_dir(d / "results")
            inv_dir = d
            break
    if inv_dir is None:
        return {"error": "Failed to create invocation directory"}

    metrics_list = []
    for i in range(runs):
        run_dir = ensure_dir(inv_dir / f"run-{i + 1:03d}")
        try:
            metrics = run_single(date, run_dir, filtered_path, model, enrich, i + 1)
        except Exception as e:
            metrics = {"skill": "x-news-digest", "status": "FAIL", "errors": [str(e)], "run": i + 1}
            write_json(run_dir / "results" / f"run-{i + 1:03d}" / "metrics.json", metrics)
        metrics_list.append(metrics)

    # Build benchmark
    case = {"id": f"live-{date}", "report_date": date}
    benchmark = build_benchmark("x-news-digest", case, metrics_list)

    benchmark_path = inv_dir / "results" / "benchmark.json"
    write_json(benchmark_path, benchmark)

    # Render report
    report_text = render_report(benchmark, metrics_list)

    return {
        "skill": "x-news-digest",
        "report_date": date,
        "invocation_path": str(inv_dir),
        "benchmark_path": str(benchmark_path),
        "runs": runs,
        "benchmark": benchmark,
        "report": report_text,
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return variance**0.5


def render_report(benchmark: dict, metrics_list: list[dict]) -> str:
    """Render a human-readable comparison report."""
    from collections import Counter

    runs = benchmark.get("runs", len(metrics_list))
    pass_count = benchmark.get("pass_count", 0)
    warn_count = benchmark.get("warn_count", 0)
    fail_count = benchmark.get("fail_count", 0)
    avg_jaccard = benchmark.get("avg_pairwise_jaccard")
    item_mean = benchmark.get("item_count_mean", 0)
    item_std = benchmark.get("item_count_std", 0)

    lines = [
        f"# Live Eval Report: x-news-digest / {benchmark.get('report_date', 'unknown')}",
        "",
        f"**Runs**: {runs} | **Pass**: {pass_count} | **Warn**: {warn_count} | **Fail**: {fail_count}",
    ]

    if avg_jaccard is not None:
        lines.append(f"**Avg Jaccard (selected_ids)**: {avg_jaccard:.2f}")
    if item_mean:
        lines.append(f"**Item Count**: mean {item_mean:.1f}, std {item_std:.1f}")
    lines.append("")

    # Per-run summary table
    lines.append("## Per-Run Summary")
    lines.append("")
    lines.append("| Run | Status | Items | Issues |")
    lines.append("|-----|--------|-------|--------|")
    for m in metrics_list:
        run_num = m.get("run", "?")
        status = m.get("status", "?")
        item_count = m.get("item_count", "?")
        errs = m.get("errors", [])
        warns = m.get("warnings", [])
        issues = ", ".join((errs + warns)[:2])
        lines.append(f"| {run_num:03d} | {status} | {item_count} | {issues} |")
    lines.append("")

    # Selection frequency
    sel_freq = benchmark.get("selection_frequency", {})
    if sel_freq:
        lines.append("## Selection Frequency (top items)")
        lines.append("")
        lines.append("| canonical_id | Selected | % |")
        lines.append("|-------------|----------|---|")
        sorted_freq = sorted(sel_freq.items(), key=lambda x: -x[1])
        for cid, count in sorted_freq[:15]:
            pct = count / runs * 100
            lines.append(f"| {cid} | {count}/{runs} | {pct:.0f}% |")
        lines.append("")

    # Category distribution
    category_counts: dict[str, list[int]] = {}
    for m in metrics_list:
        for cat_check in m.get("category_checks", []):
            cat_name = cat_check.get("name", "?")
            cat_count = cat_check.get("item_count", 0)
            if cat_name not in category_counts:
                category_counts[cat_name] = []
            category_counts[cat_name].append(cat_count)

    if category_counts:
        lines.append("## Category Distribution")
        lines.append("")
        lines.append("| Category | Avg Items | Std |")
        lines.append("|----------|-----------|-----|")
        for cat_name, counts in sorted(category_counts.items()):
            avg = _mean(counts)
            std = _std(counts) if len(counts) > 1 else 0
            lines.append(f"| {cat_name} | {avg:.1f} | {std:.1f} |")
        lines.append("")

    return "\n".join(lines)
