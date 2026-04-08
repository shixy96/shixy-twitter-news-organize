#!/usr/bin/env python3
"""Proposes changes to editorial-rules.md via LLM."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

META_PATH = Path(__file__).resolve().parent / "meta.md"


def _format_llm_error(exc: Exception) -> str:
    """Return a short, log-friendly LLM error string."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"proposer timeout ({exc.timeout}s)"
    if isinstance(exc, subprocess.CalledProcessError):
        return f"proposer exit_code={exc.returncode}"
    if isinstance(exc, FileNotFoundError):
        return "proposer command_not_found"
    return str(exc)


def propose_change(
    current_rules: str,
    experiment_history: list[dict],
    judge_feedback: list[dict],
    model: str = "opus",
    consolidate: bool = False,
) -> str:
    """Propose a new editorial-rules.md.

    Args:
        current_rules: Current editorial-rules.md content.
        experiment_history: List of past experiment dicts (iter, accepted, scores, summary).
        judge_feedback: List of judge outputs from most recent evaluation.
        model: Model to use for proposing.

    Returns:
        Complete new editorial-rules.md content.
    """
    meta = META_PATH.read_text(encoding="utf-8")

    # Build context for the proposer
    parts = [
        "## Current editorial-rules.md\n",
        current_rules,
        "",
    ]

    if experiment_history:
        parts.append("## Experiment History\n")
        for exp in experiment_history[-10:]:  # last 10 experiments
            status = "ACCEPTED" if exp.get("accepted") else "REJECTED"
            run_id = exp.get("run_id", "?")
            scores_str = json.dumps(exp.get("scores_by_date", {}), ensure_ascii=False)
            parts.append(
                f"- [{run_id}] Iter {exp.get('iter', '?')} [{status}] "
                f"scores={scores_str} — {exp.get('change_summary', '?')}"
            )
        parts.append("")

    if judge_feedback:
        parts.append("## Latest Judge Feedback\n")
        for i, fb in enumerate(judge_feedback):
            parts.append(f"### Run {i + 1}")
            for dim, detail in fb.get("scores", {}).items():
                parts.append(f"- {dim}: {detail.get('score', '?')}/10 — {detail.get('reason', '')}")
            issues = fb.get("major_issues", [])
            if issues:
                parts.append(f"- Major issues: {'; '.join(issues)}")
            parts.append("")

    instructions = (
        "## Instructions\n\n"
        "IMPORTANT: The rules file has grown too large. "
        "You MUST consolidate and shorten it — merge redundant rules, "
        "remove low-value guidance, and keep the file concise.\n\n"
        if consolidate
        else "## Instructions\n\n"
    )
    instructions += (
        "Output the COMPLETE new editorial-rules.md content. "
        "No markdown fences, no explanation — just the file content."
    )
    parts.append(instructions)

    user_prompt = "\n".join(parts)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(user_prompt)
        prompt_file = f.name

    try:
        cmd = [
            "claude",
            "-p",
            "--bare",
            "--model",
            model,
            "--system-prompt",
            meta,
        ]
        try:
            with open(prompt_file, "r", encoding="utf-8") as pf:
                result = subprocess.run(cmd, stdin=pf, capture_output=True, text=True, timeout=300)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(_format_llm_error(e)) from e
        output = result.stdout.strip()

        # Strip markdown fences if the model wrapped its output
        if output.startswith("```"):
            lines = output.splitlines()
            # Remove first and last fence lines
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            output = "\n".join(lines)

        if len(output) < 100:
            raise ValueError(f"Proposer output too short ({len(output)} chars)")

        return output

    finally:
        Path(prompt_file).unlink(missing_ok=True)
