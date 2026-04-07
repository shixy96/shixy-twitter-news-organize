#!/usr/bin/env python3
"""Hill-climbing loop for auto-improving editorial-rules.md."""

from __future__ import annotations

import json
import subprocess
import statistics
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IMPROVE_DIR = Path(__file__).resolve().parent
EXPERIMENTS_LOG = IMPROVE_DIR / "experiments.jsonl"
EDITORIAL_RULES = REPO_ROOT / "skills" / "x-news-digest" / "reference" / "editorial-rules.md"
EVAL_DIR = REPO_ROOT / "eval"

sys.path.insert(0, str(EVAL_DIR))
from eval_lib import ensure_dir, evaluate_digest, load_json, write_json
from live_runner import run_single

from judge import composite_score, score_digest, structural_score
from proposer import propose_change


def discover_fixtures() -> list[str]:
    """Find all fixture dates that have filtered.json."""
    fixtures_dir = EVAL_DIR / "fixtures"
    dates = []
    if fixtures_dir.exists():
        for d in sorted(fixtures_dir.iterdir()):
            if d.is_dir() and (d / "filtered.json").exists():
                dates.append(d.name)
    return dates


def evaluate_candidate(
    dates: list[str],
    runs_per_iter: int,
    digest_model: str,
    judge_model: str,
) -> dict:
    """Evaluate current editorial-rules.md across all fixture dates.

    Returns {
        "scores_by_date": {date: median_composite},
        "judge_feedback": [judge_outputs...],
        "any_fail": bool,
    }
    """
    scores_by_date: dict[str, int] = {}
    all_judge_feedback: list[dict] = []
    any_fail = False

    for date in dates:
        filtered_path = EVAL_DIR / "fixtures" / date / "filtered.json"
        date_scores: list[int] = []
        date_feedback: list[dict] = []

        for i in range(runs_per_iter):
            # Create temp run dir
            run_dir = ensure_dir(IMPROVE_DIR / "tmp_runs" / date / f"run-{i + 1:03d}")
            try:
                metrics = run_single(date, run_dir, filtered_path, digest_model, False, i + 1)
            except Exception as e:
                metrics = {"status": "FAIL", "errors": [str(e)]}
                any_fail = True
                date_scores.append(0)
                date_feedback.append({"scores": {}, "total": 0, "major_issues": [str(e)]})
                continue

            s_score = structural_score(metrics)
            if metrics.get("status") == "FAIL":
                any_fail = True
                e_score = 0
                judge_result = {"scores": {}, "total": 0, "major_issues": ["structurally failed"]}
            else:
                artifacts_dir = run_dir / "results" / "artifacts"
                post_path = artifacts_dir / "post.json"
                if post_path.exists():
                    filtered_json = filtered_path.read_text(encoding="utf-8")
                    post_json = post_path.read_text(encoding="utf-8")
                    judge_result = score_digest(filtered_json, post_json, judge_model)
                    e_score = judge_result.get("total", 0)
                else:
                    e_score = 0
                    judge_result = {"scores": {}, "total": 0, "major_issues": ["no post.json"]}

            c_score = composite_score(s_score, e_score)
            date_scores.append(c_score)
            date_feedback.append(judge_result)
            all_judge_feedback.append(judge_result)

        scores_by_date[date] = int(statistics.median(date_scores)) if date_scores else 0

    # Clean up tmp_runs
    _rmtree(IMPROVE_DIR / "tmp_runs")

    return {
        "scores_by_date": scores_by_date,
        "judge_feedback": all_judge_feedback,
        "any_fail": any_fail,
    }


def _rmtree(p: Path) -> None:
    """Remove directory tree (stdlib only)."""
    if not p.exists():
        return
    for child in p.iterdir():
        if child.is_dir():
            _rmtree(child)
        else:
            child.unlink()
    p.rmdir()


def _git_commit_rules(message: str) -> str:
    """Commit editorial-rules.md, return commit hash."""
    subprocess.run(
        ["git", "add", str(EDITORIAL_RULES)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    diff_result = subprocess.run(
        ["git", "diff", "--staged", "--stat"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not diff_result.stdout.strip():
        return "no-change"
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_discard_rules() -> None:
    """Discard changes to editorial-rules.md."""
    subprocess.run(
        ["git", "checkout", str(EDITORIAL_RULES)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


def _log_experiment(entry: dict) -> None:
    """Append experiment to JSONL log."""
    with open(EXPERIMENTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _pareto_improved(new_scores: dict[str, int], best_scores: dict[str, int]) -> bool:
    """Check Pareto improvement: no date regresses, at least one improves."""
    any_better = False
    for date in best_scores:
        if new_scores.get(date, 0) < best_scores[date]:
            return False
        if new_scores.get(date, 0) > best_scores[date]:
            any_better = True
    return any_better


def run_auto_improve(
    dates: list[str] | None = None,
    max_iters: int = 10,
    runs_per_iter: int = 3,
    digest_model: str = "sonnet",
    judge_model: str = "opus",
    proposer_model: str = "opus",
) -> dict:
    """Run the hill-climbing auto-improve loop.

    Returns summary dict with results.
    """
    if not dates:
        dates = discover_fixtures()
    if not dates:
        return {"error": "No fixture dates found in eval/fixtures/"}

    original_rules = EDITORIAL_RULES.read_text(encoding="utf-8")
    original_size = len(original_rules)

    # Load experiment history
    history: list[dict] = []
    if EXPERIMENTS_LOG.exists():
        for line in EXPERIMENTS_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                history.append(json.loads(line))

    print(f"[auto-improve] fixtures: {dates}")
    print(f"[auto-improve] max_iters={max_iters}, runs_per_iter={runs_per_iter}")
    print(f"[auto-improve] digest={digest_model}, judge={judge_model}, proposer={proposer_model}")
    print()

    # Baseline evaluation
    print("[auto-improve] Evaluating baseline...")
    baseline = evaluate_candidate(dates, runs_per_iter, digest_model, judge_model)
    best_scores = baseline["scores_by_date"]
    print(f"[auto-improve] Baseline scores: {best_scores}")

    if baseline["any_fail"]:
        print("[auto-improve] WARNING: baseline has FAILs")
    print()

    accepted_count = 0
    rejected_count = 0

    for iteration in range(1, max_iters + 1):
        print(f"[auto-improve] === Iteration {iteration}/{max_iters} ===")

        # Read current rules
        current_rules = EDITORIAL_RULES.read_text(encoding="utf-8")

        # Check size guard
        if len(current_rules) > original_size * 2:
            print("[auto-improve] Rules file too large, instructing proposer to consolidate")

        # Propose change
        print("[auto-improve] Proposing change...")
        try:
            new_rules = propose_change(
                current_rules, history, baseline["judge_feedback"], proposer_model
            )
        except Exception as e:
            print(f"[auto-improve] Proposer failed: {e}")
            _log_experiment(
                {
                    "iter": iteration,
                    "timestamp": datetime.now().isoformat(),
                    "accepted": False,
                    "error": str(e),
                    "change_summary": "proposer_failed",
                }
            )
            history.append(
                {"iter": iteration, "accepted": False, "change_summary": "proposer_failed"}
            )
            continue

        # Compute a brief summary of what changed
        change_summary = _summarize_diff(current_rules, new_rules)
        print(f"[auto-improve] Change: {change_summary}")

        # Apply
        EDITORIAL_RULES.write_text(new_rules, encoding="utf-8")

        # Evaluate
        print("[auto-improve] Evaluating...")
        result = evaluate_candidate(dates, runs_per_iter, digest_model, judge_model)
        new_scores = result["scores_by_date"]
        print(f"[auto-improve] New scores: {new_scores} (best: {best_scores})")

        # Decide
        accept = False
        if result["any_fail"]:
            print("[auto-improve] REJECT (has FAILs)")
        elif _pareto_improved(new_scores, best_scores):
            accept = True
            print("[auto-improve] ACCEPT (Pareto improvement)")
        else:
            print("[auto-improve] REJECT (no Pareto improvement)")

        entry = {
            "iter": iteration,
            "timestamp": datetime.now().isoformat(),
            "scores_by_date": new_scores,
            "best_scores": best_scores,
            "accepted": accept,
            "change_summary": change_summary,
            "any_fail": result["any_fail"],
        }

        if accept:
            commit_msg = f"improve: iter {iteration} — {change_summary}"
            commit_hash = _git_commit_rules(commit_msg)
            entry["commit"] = commit_hash
            if commit_hash != "no-change":
                best_scores = new_scores
            accepted_count += 1
            # Update judge feedback for next iteration
            baseline = result
        else:
            _git_discard_rules()
            rejected_count += 1

        _log_experiment(entry)
        history.append(entry)
        print()

    print(f"[auto-improve] Done. Accepted: {accepted_count}, Rejected: {rejected_count}")
    print(f"[auto-improve] Final best scores: {best_scores}")

    return {
        "iterations": max_iters,
        "accepted": accepted_count,
        "rejected": rejected_count,
        "best_scores": best_scores,
        "baseline_scores": baseline["scores_by_date"],
    }


def _summarize_diff(old: str, new: str) -> str:
    """Quick summary: lines added/removed."""
    old_lines = set(old.splitlines())
    new_lines = set(new.splitlines())
    added = len(new_lines - old_lines)
    removed = len(old_lines - new_lines)
    return f"+{added}/-{removed} lines"
