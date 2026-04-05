"""Subprocess tests for editorial dedup entrypoint."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def run_dedup(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(__import__("os").environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills/x-news-editorial/scripts/dedup.py"),
            *args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_dedup_entrypoint_allows_no_prior_companions(tmp_path):
    filtered_path = tmp_path / "filtered.json"
    filtered = {
        "stats": {
            "total_raw": 1,
            "unique": 1,
            "within_window": 1,
            "grouped_candidates": 1,
            "strong": 1,
            "medium": 0,
            "backfill": 0,
            "skipped": 0,
            "skipped_breakdown": {},
        },
        "strong": [
            {
                "_canonical_id": "123",
                "url": "https://x.com/test/status/123",
                "author": "@test (Test)",
                "text": "new item",
            }
        ],
        "medium": [],
        "backfill": [],
    }
    filtered_path.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")

    result = run_dedup("--filtered", str(filtered_path))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload["auto_resolved"]) == 1
    assert payload["history_prior_match"] == []
    assert payload["require_decision"] == []
