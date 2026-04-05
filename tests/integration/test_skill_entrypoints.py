"""Subprocess tests for skill-native script entrypoints."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def script_path(relative_path: str) -> Path:
    return ROOT / relative_path


def read_run_log(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_script(relative_path: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    if env:
        clean_env.update(env)
    return subprocess.run(
        [sys.executable, str(script_path(relative_path)), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=clean_env,
    )


def make_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def minimal_filtered() -> dict:
    return {
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
                "_canonical_url": "https://x.com/test/status/123",
                "url": "https://x.com/test/status/123",
            }
        ],
        "medium": [],
        "backfill": [],
    }


def minimal_companion(*, categories: list[dict] | None = None, is_highlight: bool = True) -> dict:
    item = {
        "index": 1,
        "canonical_id": "123",
        "title": "测试条目",
        "author": "Test Author",
        "author_screen_name": "test",
        "category": "开发生态",
        "is_highlight": is_highlight,
        "summary": "这是用于降级和校验的摘要内容，足够作为回退上下文。",
        "metrics": {"likes": 10, "views": 100, "bookmarks": 3},
        "primary_url": "https://x.com/test/status/123",
        "strong_links": [],
        "external_links": [],
        "related_urls": [],
        "is_backfill": False,
        "is_followup": False,
    }
    return {
        "generated_at": "2026-04-02T06:00:00+08:00",
        "report_date": "2026-04-02",
        "title": "测试条目【AI 资讯日报 2026-04-02】",
        "description": "每日 AI 领域精选资讯",
        "stats": {"strong": 1, "medium": 0, "backfill": 0, "total": 1, "selected": 1},
        "categories": categories if categories is not None else [{"name": "开发生态", "items": [item]}],
        "items": [item],
    }


def minimal_post() -> dict:
    return {
        "title": "测试条目【AI 资讯日报 2026-04-02】",
        "description": "每日 AI 领域精选资讯",
        "pubDate": "2026-04-02",
        "tags": ["AI", "资讯"],
        "slug": "ai-news-2026-04-02",
        "categories": [
            {
                "name": "开发生态",
                "items": [
                    {
                        "index": 1,
                        "title": "测试条目进入落地阶段，开发生态继续推进",
                        "link": "https://x.com/test/status/123",
                        "body": (
                            "这是一段足够长的正文，用来通过基础可读性检查，同时保留结构化输出所需的内容。"
                            "\n第二段继续补充背景信息，避免被 QA 识别为空洞内容。"
                        ),
                        "media": [],
                        "related_links": [],
                    }
                ],
            }
        ],
    }


def test_raw_validate_entrypoint_runs_without_pythonpath(tmp_path):
    raw_path = tmp_path / "raw.json"
    write_json(
        raw_path,
        [
            {
                "id": "123",
                "url": "https://x.com/test/status/123",
                "author": "@test (Test)",
                "text": "hello world",
                "time": "2026-04-02T01:00:00+00:00",
                "likes": 10,
                "views": 100,
                "bookmarks": 3,
                "links": [],
                "media": [],
            }
        ],
    )

    result = run_script(
        "skills/x-news-data-pipeline/scripts/raw_validate.py",
        "--input",
        str(raw_path),
    )

    assert result.returncode == 0
    assert "RAW_JSON_OK" in result.stderr


def test_raw_validate_entrypoint_writes_run_log(tmp_path):
    raw_path = tmp_path / "raw.json"
    run_root = tmp_path / "runtime"
    log_path = run_root / "daily" / "2026-04-02" / "run.log.jsonl"
    write_json(
        raw_path,
        [
            {
                "id": "123",
                "url": "https://x.com/test/status/123",
                "author": "@test (Test)",
                "text": "hello world",
                "time": "2026-04-02T01:00:00+00:00",
                "likes": 10,
                "views": 100,
                "bookmarks": 3,
                "links": [],
                "media": [],
            }
        ],
    )

    result = run_script(
        "skills/x-news-data-pipeline/scripts/raw_validate.py",
        "--input",
        str(raw_path),
        env={
            "RUN_ROOT": str(run_root),
            "REPORT_DATE": "2026-04-02",
            "RUN_ID": "test-run",
            "RUN_LOG_PATH": str(log_path),
        },
    )

    assert result.returncode == 0
    events = read_run_log(log_path)
    assert [event["event"] for event in events] == [
        "step_start",
        "validate_pass",
        "step_complete",
    ]
    assert all(event["script"] == "raw_validate.py" for event in events)


def test_validate_companion_entrypoint_rejects_missing_category_projection(tmp_path):
    filtered_path = tmp_path / "filtered.json"
    companion_path = tmp_path / "companion.json"
    write_json(filtered_path, minimal_filtered())
    write_json(companion_path, minimal_companion(categories=[{"name": "开发生态", "items": []}]))

    result = run_script(
        "skills/x-news-editorial/scripts/validate_companion.py",
        "--companion",
        str(companion_path),
        "--filtered",
        str(filtered_path),
    )

    assert result.returncode == 1
    assert "companion.categories: missing items with indices: [1]" in result.stderr


def test_validate_companion_entrypoint_rejects_unfiltered_full_selection(tmp_path):
    filtered_path = tmp_path / "filtered.json"
    companion_path = tmp_path / "companion.json"
    filtered = {
        "stats": {
            "total_raw": 13,
            "unique": 13,
            "within_window": 13,
            "grouped_candidates": 13,
            "strong": 8,
            "medium": 4,
            "backfill": 1,
            "skipped": 0,
            "skipped_breakdown": {},
        },
        "strong": [
            {"_canonical_id": f"s{i}", "url": f"https://x.com/test/status/s{i}", "_canonical_url": f"https://x.com/test/status/s{i}"}
            for i in range(8)
        ],
        "medium": [
            {"_canonical_id": f"m{i}", "url": f"https://x.com/test/status/m{i}", "_canonical_url": f"https://x.com/test/status/m{i}"}
            for i in range(4)
        ],
        "backfill": [
            {"_canonical_id": "b0", "url": "https://x.com/test/status/b0", "_canonical_url": "https://x.com/test/status/b0"}
        ],
    }
    companion = {
        "generated_at": "2026-04-02T06:00:00+08:00",
        "report_date": "2026-04-02",
        "title": "测试条目【AI 资讯日报 2026-04-02】",
        "description": "每日 AI 领域精选资讯",
        "stats": {"strong": 8, "medium": 4, "backfill": 1, "total": 13, "selected": 13},
        "categories": [{"name": "开发生态", "items": []}],
        "items": [],
    }
    for idx, cid in enumerate([f"s{i}" for i in range(8)] + [f"m{i}" for i in range(4)] + ["b0"], start=1):
        item = {
            "index": idx,
            "canonical_id": cid,
            "title": f"title-{cid}",
            "author": "a",
            "author_screen_name": "a",
            "category": "开发生态",
            "is_highlight": False,
            "summary": "s",
            "metrics": {"likes": 1, "views": 1, "bookmarks": 0},
            "primary_url": f"https://x.com/test/status/{cid}",
            "strong_links": [],
            "external_links": [],
            "related_urls": [],
            "is_backfill": cid == "b0",
            "is_followup": False,
        }
        companion["items"].append(item)
        companion["categories"][0]["items"].append({"index": idx, "category": "开发生态"})

    write_json(filtered_path, filtered)
    write_json(companion_path, companion)

    result = run_script(
        "skills/x-news-editorial/scripts/validate_companion.py",
        "--companion",
        str(companion_path),
        "--filtered",
        str(filtered_path),
    )

    assert result.returncode == 1
    assert "selected 13 items, expected at most 12 from 13 candidates" in result.stderr


def test_enrich_entrypoint_degrades_to_summary_fallback(tmp_path):
    companion_path = tmp_path / "companion.json"
    output_path = tmp_path / "enrichment.json"
    run_root = tmp_path / "runtime"
    log_path = run_root / "daily" / "2026-04-02" / "run.log.jsonl"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_executable(
        bin_dir / "twitter",
        "#!/bin/sh\n"
        "echo 'rate limited' 1>&2\n"
        "exit 1\n",
    )
    write_json(companion_path, minimal_companion())

    result = run_script(
        "skills/x-news-to-daily-post/scripts/enrich.py",
        "--companion",
        str(companion_path),
        "--output",
        str(output_path),
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "RUN_ROOT": str(run_root),
            "REPORT_DATE": "2026-04-02",
            "RUN_ID": "test-run",
            "RUN_LOG_PATH": str(log_path),
        },
    )

    assert result.returncode == 0
    enrichment = json.loads(output_path.read_text(encoding="utf-8"))
    item = enrichment["items"][0]
    assert item["fetch_status"]["primary_url"] == "degraded"
    assert item["primary_url_fetch"]["fetch_status"] == "failed"
    assert item["selected_context_facts"][0]["text"] == minimal_companion()["items"][0]["summary"]
    assert "used summary fallback" in item["warnings"][0]
    assert "[1/1] start item 1" in result.stderr
    assert "[1/1] done item 1" in result.stderr
    events = read_run_log(log_path)
    assert "item_start" in [event["event"] for event in events]
    assert "item_complete" in [event["event"] for event in events]
    assert any(event["event"] == "fetch_failed" for event in events)


def test_validate_output_entrypoint_blocks_highlight_degraded_fetch(tmp_path):
    companion_path = tmp_path / "companion.json"
    post_path = tmp_path / "post.json"
    enrichment_path = tmp_path / "enrichment.json"
    run_root = tmp_path / "runtime"
    log_path = run_root / "daily" / "2026-04-02" / "run.log.jsonl"
    write_json(companion_path, minimal_companion())
    write_json(post_path, minimal_post())
    write_json(
        enrichment_path,
        {
            "items": [
                {
                    "index": 1,
                    "fetch_status": {
                        "primary_url": "degraded",
                        "related_urls": "success",
                        "link_fetches": "success",
                        "media": "skipped",
                    },
                    "selected_context_facts": [],
                }
            ]
        },
    )

    result = run_script(
        "skills/x-news-to-daily-post/scripts/validate_output.py",
        "--post-json",
        str(post_path),
        "--companion",
        str(companion_path),
        "--enrichment",
        str(enrichment_path),
        env={
            "RUN_ROOT": str(run_root),
            "REPORT_DATE": "2026-04-02",
            "RUN_ID": "test-run",
            "RUN_LOG_PATH": str(log_path),
        },
    )

    assert result.returncode == 1
    assert "highlight item 1: primary_url_fetch is degraded" in result.stderr
    events = read_run_log(log_path)
    assert [event["event"] for event in events] == ["step_start", "step_failed"]


def test_validate_output_entrypoint_rejects_verbatim_companion_title(tmp_path):
    companion_path = tmp_path / "companion.json"
    post_path = tmp_path / "post.json"
    companion = minimal_companion()
    post = minimal_post()
    post["categories"][0]["items"][0]["title"] = companion["items"][0]["title"]

    write_json(companion_path, companion)
    write_json(post_path, post)

    result = run_script(
        "skills/x-news-to-daily-post/scripts/validate_output.py",
        "--post-json",
        str(post_path),
        "--companion",
        str(companion_path),
    )

    assert result.returncode == 1
    assert "items[1].title: must be rewritten for post.json" in result.stderr


def test_editorial_review_entrypoint_emits_real_warnings(tmp_path):
    post_path = tmp_path / "post.json"
    post = minimal_post()
    post["categories"][0]["items"][0]["body"] = "这条消息已经确定上线，但据说也可能延期。"
    post["categories"][0]["items"][0]["link"] = ""
    post["categories"][0]["items"][0]["media"] = ["media/missing.png"]
    write_json(post_path, post)

    result = run_script(
        "skills/x-news-quality-audit/scripts/editorial_review.py",
        "--post",
        str(post_path),
    )

    assert result.returncode == 0
    assert "mixes assertion words" in result.stderr
    assert "items[1].link: empty" in result.stderr
    assert "missing file 'media/missing.png'" in result.stderr


def test_generate_qa_report_entrypoint_surfaces_stage_failures(tmp_path):
    filtered_path = tmp_path / "filtered.json"
    companion_path = tmp_path / "companion.json"
    output_path = tmp_path / "qa-report.md"
    missing_post_path = tmp_path / "missing-post.json"
    write_json(filtered_path, minimal_filtered())
    write_json(companion_path, minimal_companion())

    result = run_script(
        "skills/x-news-quality-audit/scripts/generate_qa_report.py",
        "--filtered",
        str(filtered_path),
        "--companion",
        str(companion_path),
        "--post",
        str(missing_post_path),
        "--output",
        str(output_path),
        "--report-date",
        "2026-04-02",
    )

    report = output_path.read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "- **Overall**: FAIL" in report
    assert "**Result**: FAIL" in report
    assert "File not found" in report
