#!/usr/bin/env python3
"""CLI entry point for auto-improve."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure improve/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="auto-improve",
        description="Hill-climbing optimizer for editorial-rules.md",
    )
    sub = parser.add_subparsers(dest="command")

    # auto-improve command
    run_parser = sub.add_parser("auto-improve", help="Run the optimization loop")
    run_parser.add_argument(
        "--dates",
        nargs="*",
        help="Fixture dates to use (default: auto-discover all)",
    )
    run_parser.add_argument(
        "--max-iters",
        type=int,
        default=10,
        help="Maximum iterations (default: 10)",
    )
    run_parser.add_argument(
        "--runs-per-iter",
        type=int,
        default=3,
        help="Digest runs per fixture per iteration (default: 3)",
    )
    run_parser.add_argument(
        "--digest-model",
        default="sonnet",
        help="Model for digest generation (default: sonnet)",
    )
    run_parser.add_argument(
        "--judge-model",
        default="opus",
        help="Model for judge scoring (default: opus)",
    )
    run_parser.add_argument(
        "--proposer-model",
        default="opus",
        help="Model for proposing changes (default: opus)",
    )

    args = parser.parse_args()

    if args.command == "auto-improve":
        from loop import run_auto_improve

        result = run_auto_improve(
            dates=args.dates,
            max_iters=args.max_iters,
            runs_per_iter=args.runs_per_iter,
            digest_model=args.digest_model,
            judge_model=args.judge_model,
            proposer_model=args.proposer_model,
        )
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
