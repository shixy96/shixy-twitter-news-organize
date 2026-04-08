#!/usr/bin/env python3
"""LLM-as-judge scoring for digest quality."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

RUBRIC_PATH = Path(__file__).resolve().parent / "judge_rubric.md"

DIMENSIONS = [
    "selection_relevance",
    "selection_dedup",
    "title_quality",
    "body_quality",
    "link_quality",
    "editorial_judgment",
    "overall_coherence",
]


def _format_llm_error(exc: Exception) -> str:
    """Return a short, log-friendly LLM error string."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"judge timeout ({exc.timeout}s)"
    if isinstance(exc, subprocess.CalledProcessError):
        return f"judge exit_code={exc.returncode}"
    if isinstance(exc, FileNotFoundError):
        return "judge command not found"
    if isinstance(exc, json.JSONDecodeError):
        return f"judge json_parse: {exc}"
    return str(exc)


def structural_score(metrics: dict) -> int:
    """Convert evaluate_digest() status to 0-30 score."""
    status = metrics.get("status", "FAIL")
    return {"PASS": 30, "WARN": 20}.get(status, 0)


def score_digest(
    filtered_json: str,
    post_json: str,
    judge_model: str = "opus",
) -> dict:
    """Score a digest output using LLM-as-judge.

    Returns {"scores": {...}, "total": int, "major_issues": [...]}
    """
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")

    system_prompt = rubric
    user_prompt = (
        "## filtered.json (candidate pool)\n\n"
        f"{filtered_json}\n\n"
        "## post.json (generated digest)\n\n"
        f"{post_json}\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(user_prompt)
        prompt_file = f.name

    try:
        cmd = [
            "claude",
            "-p",
            "--bare",
            "--model",
            judge_model,
            "--system-prompt",
            system_prompt,
        ]
        with open(prompt_file, "r", encoding="utf-8") as pf:
            result = subprocess.run(cmd, stdin=pf, capture_output=True, text=True, timeout=300)

        raw = result.stdout.strip()

        # Extract JSON (strip markdown fences if present)
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        json_str = m.group(1).strip() if m else raw.strip()

        data = json.loads(json_str)
        _validate_judge_output(data)
        return data

    except (
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        KeyError,
        AttributeError,
        FileNotFoundError,
    ) as e:
        return {
            "scores": {d: {"score": 0, "reason": "judge error"} for d in DIMENSIONS},
            "total": 0,
            "major_issues": [_format_llm_error(e)],
        }
    finally:
        Path(prompt_file).unlink(missing_ok=True)


def _validate_judge_output(data: dict) -> None:
    """Ensure judge output has correct structure; fix total if needed."""
    if not isinstance(data, dict):
        raise AttributeError(f"expected dict, got {type(data).__name__}")
    scores = data.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}
    total = 0
    for dim in DIMENSIONS:
        if dim not in scores:
            scores[dim] = {"score": 0, "reason": "missing"}
        s = scores[dim]
        if not isinstance(s.get("score"), (int, float)):
            s["score"] = 0
        s["score"] = max(0, min(10, int(s["score"])))
        total += s["score"]
    data["scores"] = scores
    data["total"] = total
    if "major_issues" not in data:
        data["major_issues"] = []


def composite_score(structural: int, editorial: int) -> int:
    """Combine structural (0-30) and editorial (0-70) scores."""
    return max(0, min(100, structural + editorial))
