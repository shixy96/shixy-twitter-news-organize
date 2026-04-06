#!/usr/bin/env python3
"""
CLI entry point for x-news eval.

Usage:
    python3 -m eval.cli run --date 2026-04-01 --with-fixtures
    python3 -m eval.cli diagnose --date 2026-04-01
    python3 -m eval.cli benchmark --date 2026-04-01
    python3 -m eval.cli compare <run-a> <run-b>
    python3 -m eval.cli history
    python3 -m eval.cli cases list
"""

import argparse
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent
sys.path.insert(0, str(EVAL_DIR))

from eval_lib import list_skill_cases, list_suites, render_suite_report_markdown
from eval_ops import (
    analyze_stage,
    compare_invocations,
    diagnose_daily,
    history_table,
    normalize_stage,
    run_suite,
)


def cmd_run(args: argparse.Namespace) -> int:
    if not args.with_fixtures:
        print("Error: Use --with-fixtures for fixture mode.", file=sys.stderr)
        return 1
    result = analyze_stage(
        stage=args.stage or "digest",
        report_date=args.date,
        case_id=args.case_id,
        runs=args.runs,
    )
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    b = result.get("benchmark", {})
    print(f"Invocation: {result['invocation_path']}")
    print(
        f"Status: {b.get('fail_count', 0)} fail / {b.get('warn_count', 0)} warn / {b.get('pass_count', 0)} pass"
    )
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    result = diagnose_daily(args.date)
    print(f"Overall: {result.get('overall_status', 'UNKNOWN')}")
    for skill, summary in result.get("skills", {}).items():
        if "error" in summary:
            print(f"  {skill}: ERROR - {summary['error']}")
        else:
            b = summary.get("benchmark", {})
            print(
                f"  {skill}: {b.get('fail_count', 0)} fail / {b.get('warn_count', 0)} warn / {b.get('pass_count', 0)} pass"
            )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    result = compare_invocations(args.run_a, args.run_b)
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    print(f"A: {result.get('path_a')}  Status: {result.get('status_a')}")
    print(f"B: {result.get('path_b')}  Status: {result.get('status_b')}")
    for key in ("candidate_ids_jaccard", "selected_ids_jaccard"):
        if key in result and result[key] is not None:
            print(f"{key}: {result[key]:.3f}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    stage = normalize_stage(args.stage) if args.stage else None
    print(history_table(stage=stage, limit=args.limit))
    return 0


def cmd_cases(args: argparse.Namespace) -> int:
    if args.skill:
        skill = normalize_stage(args.skill)
        cases = list_skill_cases(skill)
        print(f"# Cases for {skill}\n")
        for c in cases:
            print(f"- {c['id']} ({c.get('report_date', 'N/A')})")
        return 0
    for skill in ["x-news-fetch", "x-news-digest"]:
        cases = list_skill_cases(skill)
        print(f"\n## {skill} ({len(cases)} cases)\n")
        for c in cases:
            print(f"- {c['id']} ({c.get('report_date', 'N/A')})")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    result = analyze_stage(stage=args.stage or "digest", report_date=args.date, runs=args.runs)
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    b = result.get("benchmark", {})
    print(f"\n## Benchmark: {result['skill']} / {result['report_date']}\n")
    print(f"- Runs: {b.get('runs', 0)}")
    print(
        f"- Pass: {b.get('pass_count', 0)}  Warn: {b.get('warn_count', 0)}  Fail: {b.get('fail_count', 0)}"
    )
    j = b.get("avg_pairwise_jaccard")
    if j is not None:
        print(f"- Avg Jaccard: {j:.3f}")
    return 0


def cmd_suite(args: argparse.Namespace) -> int:
    result = run_suite(args.suite, runs=args.runs)
    print(render_suite_report_markdown(result))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="x-news eval CLI")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("run")
    p.add_argument("--date", required=True)
    p.add_argument("--stage", default=None)
    p.add_argument("--case-id", dest="case_id")
    p.add_argument("--runs", type=int, default=8)
    p.add_argument("--with-fixtures", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("diagnose")
    p.add_argument("--date", required=True)
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser("compare")
    p.add_argument("run_a")
    p.add_argument("run_b")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("history")
    p.add_argument("--stage")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("cases")
    p.add_argument("subcommand", nargs="?", default="list")
    p.add_argument("--skill")
    p.set_defaults(func=cmd_cases)

    p = sub.add_parser("benchmark")
    p.add_argument("--date", required=True)
    p.add_argument("--stage", default=None)
    p.add_argument("--runs", type=int, default=8)
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("suite")
    p.add_argument("--suite", required=True)
    p.add_argument("--runs", type=int, default=8)
    p.set_defaults(func=cmd_suite)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
