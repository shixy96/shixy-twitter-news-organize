#!/usr/bin/env python3
"""
High-level eval operations for x-news-skills.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eval_lib import (
    EVAL_ROOT,
    EVAL_RUNS_ROOT,
    build_benchmark,
    create_invocation_dir,
    ensure_dir,
    evaluate_digest,
    evaluate_fetch,
    list_skill_cases,
    load_case,
    load_suite,
    render_suite_report_markdown,
    short_id,
    stage_fixtures,
    write_json,
)

SKILL_ORDER = ["x-news-fetch", "x-news-digest"]

STAGE_ALIAS = {
    "fetch": "x-news-fetch",
    "pipeline": "x-news-fetch",
    "data-pipeline": "x-news-fetch",
    "data_pipeline": "x-news-fetch",
    "digest": "x-news-digest",
    "editorial": "x-news-digest",
    "daily-post": "x-news-digest",
    "daily_post": "x-news-digest",
}


def normalize_stage(value: str) -> str:
    if value in STAGE_ALIAS:
        return STAGE_ALIAS[value]
    if value in set(STAGE_ALIAS.values()):
        return value
    for alias, full in STAGE_ALIAS.items():
        if alias in value.lower():
            return full
    return value


def find_case_for_date(skill: str, report_date: str) -> dict | None:
    cases = list_skill_cases(skill)
    for case in reversed(cases):
        if case.get("report_date") == report_date:
            return case
    return cases[-1] if cases else None


def resolve_invocation_ref(value: str) -> Path | None:
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        date_dir = EVAL_RUNS_ROOT / value
        if not date_dir.exists():
            return None
        invocations = sorted(date_dir.iterdir(), reverse=True)
        return invocations[0] if invocations else None
    p = Path(value)
    return p if p.exists() else None


def run_fixture_eval(skill: str, case: dict, invocation_dir: Path) -> dict:
    """Run fixture-based evaluation."""
    artifacts_dir = ensure_dir(invocation_dir / "results" / "artifacts")

    try:
        stage_fixtures(case, artifacts_dir)
    except FileNotFoundError as e:
        return {"status": "ERROR", "error": str(e)}

    if skill == "x-news-fetch":
        return evaluate_fetch(artifacts_dir)
    elif skill == "x-news-digest":
        return evaluate_digest(artifacts_dir)
    return {"status": "ERROR", "error": f"Unknown skill: {skill}"}


def analyze_stage(stage: str, report_date: str, case_id: str | None = None, runs: int = 8) -> dict:
    """Analyze a stage with multiple fixture runs."""
    stage = normalize_stage(stage)

    if case_id:
        case = load_case(stage, case_id)
    else:
        case = find_case_for_date(stage, report_date)
        if case is None:
            return {"error": f"No case found for {stage}/{report_date}"}

    inv_dir = create_invocation_dir(report_date, "fixture")

    metrics_list = []
    for i in range(runs):
        metrics = run_fixture_eval(stage, case, inv_dir)
        write_json(inv_dir / "results" / f"run-{i + 1:03d}" / "metrics.json", metrics)
        metrics_list.append(metrics)

    benchmark = build_benchmark(stage, case, metrics_list)
    benchmark_path = inv_dir / "results" / "benchmark.json"
    write_json(benchmark_path, benchmark)

    return {
        "skill": stage,
        "case_id": case.get("id", ""),
        "report_date": report_date,
        "invocation_path": str(inv_dir),
        "benchmark_path": str(benchmark_path),
        "runs": runs,
        "benchmark": benchmark,
    }


def diagnose_daily(report_date: str) -> dict:
    results: dict[str, Any] = {"report_date": report_date, "skills": {}}

    for skill in SKILL_ORDER:
        result = analyze_stage(skill, report_date, runs=1)
        if "error" in result:
            results["skills"][skill] = {"error": result["error"]}
        else:
            results["skills"][skill] = {"benchmark": result.get("benchmark", {})}

    all_pass = all(
        r.get("benchmark", {}).get("fail_count", 1) == 0
        for r in results["skills"].values()
        if "benchmark" in r
    )
    results["overall_status"] = "PASS" if all_pass else "FAIL"
    return results


def run_suite(suite_id: str, runs: int = 8) -> dict:
    suite = load_suite(suite_id)
    report_date = suite.get("report_date", "")
    skill_rows = []
    overall = "PASS"

    for skill in SKILL_ORDER:
        case_id = suite.get("skills", {}).get(skill)
        if not case_id:
            continue
        result = analyze_stage(skill, report_date, case_id=case_id, runs=runs)
        if "error" in result:
            overall = "FAIL"
            skill_rows.append({"skill": skill, "status": "ERROR", "error": result["error"]})
            continue
        b = result.get("benchmark", {})
        s = "FAIL" if b.get("fail_count", 0) else "WARN" if b.get("warn_count", 0) else "PASS"
        if s == "FAIL":
            overall = "FAIL"
        elif s == "WARN" and overall == "PASS":
            overall = "WARN"
        skill_rows.append({"skill": skill, "status": s})

    return {
        "overall_status": overall,
        "skills": skill_rows,
        "suite_id": suite_id,
        "report_date": report_date,
    }


def compare_invocations(path_a: str | Path, path_b: str | Path) -> dict:
    from eval_lib import load_json

    a = resolve_invocation_ref(str(path_a)) if not Path(str(path_a)).exists() else Path(str(path_a))
    b = resolve_invocation_ref(str(path_b)) if not Path(str(path_b)).exists() else Path(str(path_b))
    if not a:
        return {"error": f"Cannot resolve: {path_a}"}
    if not b:
        return {"error": f"Cannot resolve: {path_b}"}

    def load_metrics(p: Path) -> dict:
        mp = p / "metrics.json"
        return load_json(mp) if mp.exists() else {}

    ma, mb = load_metrics(a), load_metrics(b)
    result = {
        "path_a": str(a),
        "path_b": str(b),
        "status_a": ma.get("status", "UNKNOWN"),
        "status_b": mb.get("status", "UNKNOWN"),
        "same_status": ma.get("status") == mb.get("status"),
    }

    for key in ("candidate_ids", "selected_ids"):
        if key in ma and key in mb:
            sa, sb = set(ma[key]), set(mb[key])
            result[f"{key}_jaccard"] = len(sa & sb) / len(sa | sb) if sa | sb else None

    return result


def history_table(stage: str | None = None, limit: int = 20) -> str:
    if not EVAL_RUNS_ROOT.exists():
        return "# No eval runs found\n"

    rows = []
    for date_dir in sorted(EVAL_RUNS_ROOT.iterdir(), reverse=True)[:limit]:
        if not date_dir.is_dir():
            continue
        for inv_dir in sorted(date_dir.iterdir(), reverse=True):
            if not inv_dir.is_dir():
                continue
            for mp in sorted((inv_dir / "results").glob("run-*/metrics.json"))[:1]:
                try:
                    m = json.loads(mp.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
                skill = m.get("skill", "?")
                if stage and normalize_stage(stage) != skill:
                    continue
                errs = m.get("errors", [])
                rows.append(
                    [
                        date_dir.name,
                        inv_dir.name,
                        skill,
                        m.get("status", "?"),
                        errs[0][:50] if errs else "",
                    ]
                )

    if not rows:
        return "# No eval runs found\n"

    lines = [
        "# Eval History\n",
        "| Date | Invocation | Skill | Status | Error |",
        "|------|------------|-------|--------|-------|",
    ]
    for r in rows[:limit]:
        lines.append(f"| {' | '.join(str(c) for c in r)} |")
    return "\n".join(lines) + "\n"
