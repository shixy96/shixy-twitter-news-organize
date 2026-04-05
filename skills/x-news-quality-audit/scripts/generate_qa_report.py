#!/usr/bin/env python3
"""
generate_qa_report: Aggregate QA results from stages 1-3 into qa-report.md.

Calls stage_json_validate.py, stage_contract.py, editorial_review.py as subprocesses,
parses their stderr output (FAIL:/WARN: prefixes), and generates a markdown report.

Usage:
    python3 generate_qa_report.py \
      --raw <path> \
      --filtered <path> \
      --companion <path> \
      --post <path> \
      --output <path>

Exit codes:
    0 - Always succeeds (QA is non-blocking)
"""

import argparse
import subprocess
import sys
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log


STAGE_JSON_VALIDATE = "stage_json_validate.py"
STAGE_CONTRACT = "stage_contract.py"
EDITORIAL_REVIEW = "editorial_review.py"


def run_stage(script_name: str, args: list[str]) -> tuple[int, str, str]:
    """Run a stage script and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            [sys.executable, script_name] + args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Stage timed out"
    except Exception as e:
        return -1, "", str(e)


def parse_stage_output(returncode: int, stdout: str, stderr: str) -> tuple[str, list[str]]:
    """Parse stage output.

    Returns:
        (summary_line, issue_lines)
    """
    summary = ""
    issues = []
    combined = []
    if stdout:
        combined.extend(stdout.strip().split("\n"))
    if stderr:
        combined.extend(stderr.strip().split("\n"))

    for raw_line in combined:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("FAIL:", "WARN:")):
            issues.append(line)
            continue
        if re.match(r"^(JSON_VALIDATION|CONTRACT_VALIDATION|EDITORIAL_REVIEW):", line):
            summary = line

    if returncode != 0 and not summary:
        summary = f"FAILED (exit {returncode})"

    if returncode != 0 and not issues:
        fallback_lines = [
            line.strip()
            for line in stderr.strip().split("\n")
            if line.strip()
        ]
        issues.extend(fallback_lines[:5])

    if returncode == 0 and not summary:
        summary = "PASS"

    return summary, issues


def generate_report(
    report_date: str,
    json_result: tuple[int, str],
    contract_result: tuple[int, str],
    editorial_result: tuple[int, str],
    output_path: Path,
) -> None:
    """Generate qa-report.md from stage results."""
    json_rc, json_out, json_err = json_result
    contract_rc, contract_out, contract_err = contract_result
    editorial_rc, editorial_out, editorial_err = editorial_result

    json_summary, json_errors = parse_stage_output(json_rc, json_out, json_err)
    contract_summary, contract_errors = parse_stage_output(contract_rc, contract_out, contract_err)
    editorial_summary, editorial_warnings = parse_stage_output(
        editorial_rc, editorial_out, editorial_err
    )

    # Determine overall status
    overall_fail = (
        (json_rc != 0 and json_errors)
        or (contract_rc != 0 and contract_errors)
        or (editorial_rc != 0 and editorial_warnings)
    )

    lines = []
    lines.append(f"# AI 资讯日报 {report_date} - QA Report\n")
    lines.append("## Overall Status\n")
    lines.append(f"- **Overall**: {'FAIL' if overall_fail else 'PASS'}\n")
    lines.append(f"- **JSON Validation**: {json_summary if json_summary else 'NOT RUN'}\n")
    lines.append(
        f"- **Contract Validation**: {contract_summary if contract_summary else 'NOT RUN'}\n"
    )
    lines.append(
        f"- **Editorial Review**: {editorial_summary if editorial_summary else 'NOT RUN'}\n"
    )

    # Stage 1
    lines.append("\n## Stage 1: JSON Schema Validation\n")
    if json_errors:
        lines.append(f"**Result**: FAIL ({len(json_errors)} errors)\n\n")
        for err in json_errors:
            lines.append(f"- {err}\n")
    else:
        lines.append("**Result**: PASS\n\n")

    # Stage 2
    lines.append("\n## Stage 2: Contract Validation\n")
    if contract_errors:
        lines.append(f"**Result**: FAIL ({len(contract_errors)} errors)\n\n")
        for err in contract_errors:
            lines.append(f"- {err}\n")
    else:
        lines.append("**Result**: PASS\n\n")

    # Stage 3
    lines.append("\n## Stage 3: Editorial Review\n")
    if editorial_rc != 0 and editorial_warnings:
        lines.append(f"**Result**: FAIL ({len(editorial_warnings)} errors)\n\n")
        for warn in editorial_warnings:
            lines.append(f"- {warn}\n")
    elif editorial_warnings:
        lines.append(f"**Result**: PASS ({len(editorial_warnings)} warnings for human review)\n\n")
        lines.append("### Warnings\n")
        for warn in editorial_warnings:
            lines.append(f"- {warn}\n")
    else:
        lines.append("**Result**: PASS\n\n")

    # Summary table
    lines.append("\n## Summary\n\n")
    lines.append("| Dimension | Status |\n")
    lines.append("|-----------|--------|\n")
    lines.append(f"| Schema valid | {'✗' if json_errors else '✓'} |\n")
    lines.append(f"| Cross-ref integrity | {'✗' if contract_errors else '✓'} |\n")
    editorial_status = "✗" if editorial_rc != 0 else "✓ (warnings)" if editorial_warnings else "✓"
    lines.append(f"| Readability | {editorial_status} |\n")
    lines.append(f"| Completeness | {editorial_status} |\n")
    lines.append(f"| Daily post feel | {editorial_status} |\n")

    report = "".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[generate_qa_report] wrote {output_path}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate QA report from stage results")
    parser.add_argument("--raw", type=Path, default=None, help="Path to raw.json")
    parser.add_argument("--filtered", type=Path, required=True, help="Path to filtered.json")
    parser.add_argument("--companion", type=Path, required=True, help="Path to companion.json")
    parser.add_argument("--post", type=Path, required=True, help="Path to post.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qa-report.md"),
        help="Output path for qa-report.md",
    )
    parser.add_argument(
        "--report-date",
        type=str,
        default="",
        help="Report date (YYYY-MM-DD). Extracted from post.json if not provided.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.output.expanduser().parent
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="step_start",
        message="starting qa report generation",
        meta={
            "raw": args.raw,
            "filtered": args.filtered,
            "companion": args.companion,
            "post": args.post,
            "output": args.output,
        },
        daily_dir=daily_dir,
    )

    # Determine report date
    report_date = args.report_date
    if not report_date and args.post.exists():
        import json

        try:
            with open(args.post, encoding="utf-8") as f:
                post_data = json.load(f)
            report_date = post_data.get("pubDate", "")
        except Exception:
            pass

    if not report_date:
        report_date = "Unknown Date"

    # Get script directory
    skill_dir = Path(__file__).parent

    # Stage 1: JSON validation
    json_args = []
    if args.raw:
        json_args += ["--raw", str(args.raw)]
    json_args += [
        "--filtered",
        str(args.filtered),
        "--companion",
        str(args.companion),
        "--post",
        str(args.post),
    ]
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="stage_start",
        message="running stage_json_validate.py",
        meta={"args": json_args},
        daily_dir=daily_dir,
    )
    json_result = run_stage(str(skill_dir / STAGE_JSON_VALIDATE), json_args)
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="stage_complete",
        status="error" if json_result[0] != 0 else "info",
        message="finished stage_json_validate.py",
        meta={"returncode": json_result[0]},
        daily_dir=daily_dir,
    )

    # Stage 2: Contract validation
    contract_args = [
        "--filtered",
        str(args.filtered),
        "--companion",
        str(args.companion),
        "--post",
        str(args.post),
    ]
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="stage_start",
        message="running stage_contract.py",
        meta={"args": contract_args},
        daily_dir=daily_dir,
    )
    contract_result = run_stage(str(skill_dir / STAGE_CONTRACT), contract_args)
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="stage_complete",
        status="error" if contract_result[0] != 0 else "info",
        message="finished stage_contract.py",
        meta={"returncode": contract_result[0]},
        daily_dir=daily_dir,
    )

    # Stage 3: Editorial review
    editorial_args = ["--post", str(args.post)]
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="stage_start",
        message="running editorial_review.py",
        meta={"args": editorial_args},
        daily_dir=daily_dir,
    )
    editorial_result = run_stage(str(skill_dir / EDITORIAL_REVIEW), editorial_args)
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="stage_complete",
        status="error" if editorial_result[0] != 0 else "info",
        message="finished editorial_review.py",
        meta={"returncode": editorial_result[0]},
        daily_dir=daily_dir,
    )

    # Generate report
    generate_report(report_date, json_result, contract_result, editorial_result, args.output)
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="write_output",
        message="wrote qa-report.md",
        meta={"output": args.output},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-quality-audit",
        script="generate_qa_report.py",
        event="step_complete",
        message="finished qa report generation",
        meta={"output": args.output},
        daily_dir=daily_dir,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
