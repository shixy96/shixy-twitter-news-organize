#!/usr/bin/env python3
"""
CLI entry point for x-news eval.

Usage:
    python3 -m eval.cli run --date 2026-04-01
    python3 -m eval.cli diagnose --date 2026-04-01
    python3 -m eval.cli compare <run-a> <run-b>
    python3 -m eval.cli history
    python3 -m eval.cli cases list
    python3 -m eval.cli suite --suite suite-2026-04-01
"""

import argparse
import sys
from pathlib import Path

# Add eval directory to path
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
    """Run eval for a date or stage."""
    if args.with_fixtures:
        # Fixture copy mode
        result = analyze_stage(
            stage=args.stage or "editorial",
            report_date=args.date,
            case_id=args.case_id,
            runs=args.runs,
        )
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            return 1
        print(f"Invocation: {result['invocation_path']}")
        print(f"Benchmark: {result['benchmark_path']}")
        benchmark = result.get("benchmark", {})
        print(f"Status: {benchmark.get('fail_count', 0)} fail / {benchmark.get('warn_count', 0)} warn / {benchmark.get('pass_count', 0)} pass")
        return 0

    # Agent mode would go here (not implemented in simplified version)
    print("Error: Agent mode not implemented. Use --with-fixtures.", file=sys.stderr)
    return 1


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Diagnose all stages for a date."""
    result = diagnose_daily(args.date)
    print(f"Overall: {result.get('overall_status', 'UNKNOWN')}")
    for skill, summary in result.get("skills", {}).items():
        if "error" in summary:
            print(f"  {skill}: ERROR - {summary['error']}")
        else:
            benchmark = summary.get("benchmark", {})
            print(f"  {skill}: {benchmark.get('fail_count', 0)} fail / {benchmark.get('warn_count', 0)} warn / {benchmark.get('pass_count', 0)} pass")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare two invocations."""
    result = compare_invocations(args.run_a, args.run_b)
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    print(f"Invocation A: {result.get('path_a')}")
    print(f"Invocation B: {result.get('path_b')}")
    print(f"Status A: {result.get('status_a')}")
    print(f"Status B: {result.get('status_b')}")
    print(f"Same status: {result.get('same_status')}")
    if "candidate_jaccard" in result:
        print(f"Candidate Jaccard: {result['candidate_jaccard']:.3f}" if result['candidate_jaccard'] else "Candidate Jaccard: N/A")
    if "selected_jaccard" in result:
        print(f"Selected Jaccard: {result['selected_jaccard']:.3f}" if result['selected_jaccard'] else "Selected Jaccard: N/A")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Show eval history."""
    stage = args.stage or None
    if stage:
        stage = normalize_stage(stage)
    output = history_table(stage=stage, limit=args.limit)
    print(output)
    return 0


def cmd_cases_list(args: argparse.Namespace) -> int:
    """List all available cases."""
    if args.skill:
        skill = normalize_stage(args.skill)
        cases = list_skill_cases(skill)
        print(f"# Cases for {skill}\n")
        if not cases:
            print("No cases found.")
            return 0
        for case in cases:
            print(f"- {case['id']} ({case.get('report_date', 'N/A')}) - {case.get('skill', 'N/A')}")
        return 0

    # List all skills
    for skill in ["x-news-data-pipeline", "x-news-editorial", "x-news-to-daily-post"]:
        cases = list_skill_cases(skill)
        print(f"\n## {skill} ({len(cases)} cases)\n")
        for case in cases:
            print(f"- {case['id']} ({case.get('report_date', 'N/A')})")
    return 0


def cmd_suite(args: argparse.Namespace) -> int:
    """Run a suite evaluation."""
    result = run_suite(args.suite, runs=args.runs)
    print(render_suite_report_markdown(result))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run multiple runs and show aggregate benchmark."""
    result = analyze_stage(
        stage=args.stage or "editorial",
        report_date=args.date,
        runs=args.runs,
    )
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    benchmark = result.get("benchmark", {})
    print(f"\n## Benchmark for {result['skill']} / {result['report_date']}\n")
    print(f"- Runs: {benchmark.get('runs', 0)}")
    print(f"- Pass: {benchmark.get('pass_count', 0)}")
    print(f"- Warn: {benchmark.get('warn_count', 0)}")
    print(f"- Fail: {benchmark.get('fail_count', 0)}")

    if "avg_pairwise_jaccard" in benchmark:
        jaccard = benchmark["avg_pairwise_jaccard"]
        print(f"- Avg Jaccard: {jaccard:.3f}" if jaccard else "- Avg Jaccard: N/A")

    if "thin_summary_rates" in benchmark:
        rates = benchmark["thin_summary_rates"]
        if rates:
            avg = sum(rates) / len(rates)
            print(f"- Avg thin rate: {avg:.2%}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="x-news eval CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # run command
    run_parser = subparsers.add_parser("run", help="Run eval for a date")
    run_parser.add_argument("--date", required=True, help="Report date (YYYY-MM-DD)")
    run_parser.add_argument("--stage", help="Stage to run (default: editorial)")
    run_parser.add_argument("--case-id", dest="case_id", help="Specific case ID")
    run_parser.add_argument("--runs", type=int, default=8, help="Number of runs (default: 8)")
    run_parser.add_argument("--with-fixtures", action="store_true", help="Use fixture copy mode")
    run_parser.set_defaults(func=cmd_run)

    # diagnose command
    diag_parser = subparsers.add_parser("diagnose", help="Diagnose all stages for a date")
    diag_parser.add_argument("--date", required=True, help="Report date (YYYY-MM-DD)")
    diag_parser.set_defaults(func=cmd_diagnose)

    # compare command
    cmp_parser = subparsers.add_parser("compare", help="Compare two invocations")
    cmp_parser.add_argument("run_a", help="First invocation path or date")
    cmp_parser.add_argument("run_b", help="Second invocation path or date")
    cmp_parser.set_defaults(func=cmd_compare)

    # history command
    hist_parser = subparsers.add_parser("history", help="Show eval history")
    hist_parser.add_argument("--stage", help="Filter by stage")
    hist_parser.add_argument("--limit", type=int, default=20, help="Max entries (default: 20)")
    hist_parser.set_defaults(func=cmd_history)

    # cases list command
    cases_parser = subparsers.add_parser("cases", help="List cases")
    cases_parser.add_argument("subcommand", nargs="?", default="list", help="Subcommand (list)")
    cases_parser.add_argument("--skill", help="Filter by skill")
    cases_parser.set_defaults(func=cmd_cases_list)

    # suite command
    suite_parser = subparsers.add_parser("suite", help="Run a suite evaluation")
    suite_parser.add_argument("--suite", required=True, help="Suite ID (e.g., suite-2026-04-01)")
    suite_parser.add_argument("--runs", type=int, default=8, help="Number of runs (default: 8)")
    suite_parser.set_defaults(func=cmd_suite)

    # benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Run benchmark")
    bench_parser.add_argument("--date", required=True, help="Report date (YYYY-MM-DD)")
    bench_parser.add_argument("--stage", help="Stage (default: editorial)")
    bench_parser.add_argument("--runs", type=int, default=8, help="Number of runs (default: 8)")
    bench_parser.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
