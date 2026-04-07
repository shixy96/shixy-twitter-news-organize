#!/usr/bin/env python3
"""
CLI entry point for x-news eval.

Usage:
    python3 eval/cli.py live-digest --date 2026-04-06 --runs 8
"""

import argparse
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent
sys.path.insert(0, str(EVAL_DIR))

from live_runner import run_live_eval


def cmd_live_digest(args: argparse.Namespace) -> int:
    result = run_live_eval(
        date=args.date,
        runs=args.runs,
        model=args.model,
        enrich=args.enrich,
        filtered_path=args.filtered,
    )
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    print(result.get("report", ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="x-news eval CLI")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("live-digest")
    p.add_argument("--date", required=True)
    p.add_argument("--runs", type=int, default=8)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--enrich", action="store_true")
    p.add_argument("--filtered")
    p.set_defaults(func=cmd_live_digest)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
