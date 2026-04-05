#!/usr/bin/env python3
"""
Enrichment script for x-news-to-daily-post.

Fetches additional context for companion.json items via twitter CLI, gh CLI, and WebFetch.

Usage:
    python3 enrich.py --companion <path> --output <path> [--media-dir <path>]

Exit codes:
    0 - Success (even with partial failures that degraded gracefully)
    1 - Invalid arguments
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log, normalize_x_url


def log_progress(
    message: str,
    *,
    event: str = "progress",
    status: str = "info",
    meta: dict[str, Any] | None = None,
    daily_dir: Path | None = None,
) -> None:
    """Emit progress logs to stderr for long-running enrich runs."""
    print(f"[enrich] {message}", file=sys.stderr)
    append_run_log(
        skill="x-news-to-daily-post",
        script="enrich.py",
        event=event,
        status=status,
        message=message,
        meta=meta,
        daily_dir=daily_dir,
    )


def run_command(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def fetch_twitter_tweet(tweet_url: str) -> dict[str, Any]:
    """Fetch tweet details via twitter CLI.

    Returns:
        dict with 'fetch_status': 'success' | 'failed' | 'degraded'
    """
    normalized_url = normalize_x_url(tweet_url)
    if not normalized_url:
        return {"fetch_status": "failed", "error": "Invalid X URL"}

    # Extract tweet ID from URL
    parts = normalized_url.split("/")
    if len(parts) < 6:
        return {"fetch_status": "failed", "error": "Invalid tweet URL format"}

    tweet_id = parts[-1]

    returncode, stdout, stderr = run_command(["twitter", "tweet", tweet_id, "--json"])

    if "rate limit" in stderr.lower() or "429" in stderr:
        log_progress(
            f"twitter rate limit while fetching {tweet_id}: {stderr.strip()[:200]}",
            event="fetch_failed",
            status="warn",
            meta={"tweet_id": tweet_id, "stderr": stderr.strip()[:200]},
        )

    if returncode != 0:
        return {"fetch_status": "failed", "error": (stderr or "twitter CLI failed")[:200]}

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {"fetch_status": "degraded", "error": "Invalid JSON response", "raw": stdout[:500]}

    if not isinstance(payload, dict):
        return {"fetch_status": "degraded", "error": "Invalid twitter payload"}

    if not payload.get("ok", False):
        error = payload.get("error", {})
        message = error.get("message") if isinstance(error, dict) else "twitter API error"
        return {"fetch_status": "failed", "error": str(message)[:200]}

    data = payload.get("data")
    if isinstance(data, dict):
        tweet = data
    elif isinstance(data, list):
        tweet = next((item for item in data if isinstance(item, dict)), None)
    else:
        tweet = None

    if tweet is None:
        return {"fetch_status": "degraded", "error": "Empty tweet payload", "data": payload}

    return {"fetch_status": "success", "data": tweet}


def fetch_github_repo(repo_url: str) -> dict[str, Any]:
    """Fetch GitHub repo metadata via gh CLI.

    Returns:
        dict with 'fetch_status': 'success' | 'failed'
    """
    # Extract owner/repo from URL
    # Formats: https://github.com/owner/repo, https://github.com/owner/repo/
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 2:
        return {"fetch_status": "failed", "error": "Invalid GitHub URL"}

    owner = parts[-2]
    repo = parts[-1]

    returncode, stdout, stderr = run_command(
        ["gh", "repo", "view", f"{owner}/{repo}", "--json", "description,stargazerCount"]
    )

    if returncode != 0:
        return {"fetch_status": "failed", "error": stderr[:200]}

    try:
        data = json.loads(stdout)
        return {
            "fetch_status": "success",
            "data": {
                "description": data.get("description", ""),
                "stars": data.get("stargazerCount", 0),
            },
        }
    except json.JSONDecodeError:
        return {"fetch_status": "failed", "error": "Invalid JSON response"}


def download_media(url: str, dest_path: Path) -> tuple[bool, str]:
    """Download media file to local path.

    Args:
        url: Media URL
        dest_path: Destination file path

    Returns:
        (success, error_message)
    """
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(content)
            return True, ""
    except Exception as e:
        return False, str(e)[:200]


def fetch_web_content(url: str) -> dict[str, Any]:
    """Fetch web content via WebFetch (simple HTTP request).

    This is a basic implementation. For production, use the WebFetch MCP tool.

    Returns:
        dict with 'fetch_status': 'success' | 'failed'
    """
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode("utf-8", errors="replace")
            # Simple title extraction
            title = ""
            if "<title" in content.lower():
                start = content.lower().find("<title") + 6
                end = content.find(">", start)
                if end > start:
                    title_start = end + 1
                    title_end = content.lower().find("</title", title_start)
                    if title_end > title_start:
                        title = content[title_start:title_end].strip()
                        # Unescape HTML entities
                        title = (
                            title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        )

            return {
                "fetch_status": "success",
                "data": {
                    "title": title,
                    "summary": title,  # Simplified - in production would extract description
                },
            }
    except Exception as e:
        return {"fetch_status": "failed", "error": str(e)[:200]}


def fetch_item_context(item: dict, media_dir: Path | None) -> dict[str, Any]:
    """Fetch context for a single item.

    Args:
        item: Companion item
        media_dir: Directory to save media files

    Returns:
        Enrichment data for the item
    """
    # Initialize primary_url_fetch to a failure object as default
    _FAILED_FETCH = {"fetch_status": "failed", "error": "no primary_url or fetch failed"}

    result = {
        "index": item.get("index"),
        "fetch_status": {
            "primary_url": "success",
            "related_urls": "success",
            "link_fetches": "success",
            "media": "skipped",
        },
        "primary_url_fetch": _FAILED_FETCH,
        "related_url_fetches": [],
        "link_fetches": [],
        "selected_context_facts": [],
        "media_files": [],
        "warnings": [],
    }

    def add_summary_fallback(reason: str, source_type: str = "companion_summary") -> None:
        summary = (item.get("summary") or "").strip()
        if summary:
            result["selected_context_facts"].append(
                {
                    "text": summary,
                    "source_url": item.get("primary_url", ""),
                    "source_type": source_type,
                }
            )
        result["warnings"].append(reason)

    # Fetch primary URL (should be X tweet)
    primary_url = item.get("primary_url")
    if primary_url and primary_url.strip():
        if normalize_x_url(primary_url):
            tweet_data = fetch_twitter_tweet(primary_url)
            result["primary_url_fetch"] = tweet_data
            if tweet_data.get("fetch_status") == "failed":
                result["fetch_status"]["primary_url"] = "degraded"
                add_summary_fallback(
                    f"primary_url fetch failed, used summary fallback: "
                    f"{tweet_data.get('error', 'unknown')}"
                )
            elif tweet_data.get("fetch_status") == "degraded":
                result["fetch_status"]["primary_url"] = "degraded"
                add_summary_fallback(
                    f"primary_url fetch degraded, used summary fallback: "
                    f"{tweet_data.get('error', 'unknown')}"
                )
        else:
            # Non-X URL, try as web content
            web_data = fetch_web_content(primary_url)
            result["primary_url_fetch"] = web_data
            result["fetch_status"]["primary_url"] = web_data.get("fetch_status", "failed")
            if web_data.get("fetch_status") != "success":
                add_summary_fallback(
                    f"primary_url web fetch failed, used summary fallback: "
                    f"{web_data.get('error', 'unknown')}",
                    source_type="companion_summary",
                )
    else:
        # Empty or missing primary_url - mark as failed
        result["fetch_status"]["primary_url"] = "degraded"
        add_summary_fallback("primary_url is empty or missing")

    # Fetch related URLs (X URLs)
    related_urls = item.get("related_urls", [])[:2]  # Limit to 2
    for url in related_urls:
        if normalize_x_url(url):
            tweet_data = fetch_twitter_tweet(url)
            result["related_url_fetches"].append(tweet_data)
            if tweet_data.get("fetch_status") != "success":
                if result["fetch_status"]["related_urls"] == "success":
                    result["fetch_status"]["related_urls"] = "partial"
        else:
            web_data = fetch_web_content(url)
            result["related_url_fetches"].append(web_data)
            if web_data.get("fetch_status") != "success":
                if result["fetch_status"]["related_urls"] == "success":
                    result["fetch_status"]["related_urls"] = "partial"

    # Fetch link content (GitHub, etc.)
    strong_links = item.get("strong_links", [])
    for link in strong_links[:3]:  # Limit to 3
        if isinstance(link, dict):
            url = link.get("url", "")
            link_type = link.get("kind", "web")
        else:
            url = str(link)
            link_type = "web"

        if not url:
            continue

        if "github.com" in url:
            gh_data = fetch_github_repo(url)
            link_fetch = {
                "url": url,
                "type": "github",
                "data": gh_data.get("data", {}),
                "fetch_status": gh_data.get("fetch_status", "failed"),
            }
            result["link_fetches"].append(link_fetch)
            if gh_data.get("fetch_status") != "success":
                if result["fetch_status"]["link_fetches"] == "success":
                    result["fetch_status"]["link_fetches"] = "partial"
        else:
            web_data = fetch_web_content(url)
            link_fetch = {
                "url": url,
                "type": "webfetch",
                "data": web_data.get("data", {}),
                "fetch_status": web_data.get("fetch_status", "failed"),
            }
            result["link_fetches"].append(link_fetch)
            if web_data.get("fetch_status") != "success":
                if result["fetch_status"]["link_fetches"] == "success":
                    result["fetch_status"]["link_fetches"] = "partial"

    # Extract URLs from tweet data to link_fetches
    if result["primary_url_fetch"].get("fetch_status") == "success":
        primary_data = result["primary_url_fetch"].get("data", {})
        for url_item in primary_data.get("urls", []):
            if isinstance(url_item, dict):
                url = url_item.get("url", "")
            else:
                url = str(url_item) if url_item else ""
            if url and not normalize_x_url(url):
                result["link_fetches"].append(
                    {
                        "url": url,
                        "type": "webfetch",
                        "data": {"url": url},
                        "fetch_status": "success",
                    }
                )

    # Select context facts from successful fetches
    if result["primary_url_fetch"].get("fetch_status") == "success":
        primary_data = result["primary_url_fetch"].get("data", {})
        if primary_data.get("text") or primary_data.get("full_text"):
            result["selected_context_facts"].append(
                {
                    "text": primary_data.get("text", "") or primary_data.get("full_text", ""),
                    "source_url": primary_url,
                    "source_type": "x",
                }
            )

    for link_fetch in result["link_fetches"]:
        if link_fetch.get("fetch_status") == "success":
            link_data = link_fetch.get("data", {})
            # Web fetches (non-GitHub) return title/summary, not description
            fact_text = (
                link_data.get("description") or link_data.get("title") or link_data.get("summary")
            )
            if fact_text:
                result["selected_context_facts"].append(
                    {
                        "text": fact_text,
                        "source_url": link_fetch["url"],
                        "source_type": link_fetch.get("type", "web"),
                    }
                )

    # Download media for highlight items
    if item.get("is_highlight") and media_dir:
        primary_data = result["primary_url_fetch"].get("data", {})
        media_list = primary_data.get("media", [])

        if not media_list:
            result["fetch_status"]["media"] = "skipped"
        else:
            for media_idx, media_item in enumerate(media_list):
                if isinstance(media_item, dict):
                    media_url = media_item.get("url", "")
                    media_type = media_item.get("type", "image")
                else:
                    media_url = str(media_item) if media_item else ""
                    media_type = "image"
                if not media_url:
                    continue

                # Determine file extension from URL or type
                if media_type == "video":
                    ext = ".mp4"
                else:
                    ext = ".jpg"

                # Build local path: media/{date}/{tweet_id}_{idx}.{ext}
                tweet_id = primary_data.get("id", str(item.get("index", "")))
                filename = f"{tweet_id}_{media_idx}{ext}"
                dest_path = media_dir / filename

                success, error = download_media(media_url, dest_path)
                if success:
                    result["media_files"].append(str(dest_path))
                else:
                    result["warnings"].append(f"media download failed: {error}")

            if result["media_files"]:
                result["fetch_status"]["media"] = "success"
            else:
                result["fetch_status"]["media"] = "degraded"

    return result


def enrich_companion(companion_path: Path, output_path: Path, media_dir: Path | None) -> dict:
    """Enrich all items in companion.json.

    Args:
        companion_path: Path to companion.json
        output_path: Path to write enrichment.json
        media_dir: Directory to save media files

    Returns:
        Enrichment data dict
    """
    with open(companion_path, encoding="utf-8") as f:
        companion = json.load(f)

    items = companion.get("items", [])
    total_items = len(items)
    daily_dir = output_path.expanduser().parent

    # Idempotency: skip if enrichment.json already exists with the correct item count
    if output_path.exists():
        try:
            with open(output_path, encoding="utf-8") as f:
                existing = json.load(f)
            if len(existing.get("items", [])) == total_items:
                append_run_log(
                    skill="x-news-to-daily-post",
                    script="enrich.py",
                    event="step_skipped",
                    message="enrichment.json already complete, skipping re-enrichment",
                    meta={"output": str(output_path), "item_count": total_items},
                    daily_dir=daily_dir,
                )
                return existing
        except (json.JSONDecodeError, OSError):
            pass  # Unreadable or invalid — proceed with fresh enrichment

    results = []
    append_run_log(
        skill="x-news-to-daily-post",
        script="enrich.py",
        event="step_start",
        message="starting enrich",
        meta={
            "companion": companion_path,
            "output": output_path,
            "media_dir": media_dir,
            "item_count": total_items,
        },
        daily_dir=daily_dir,
    )

    for idx, item in enumerate(items, start=1):
        item_index = item.get("index", idx)
        title = (item.get("title") or "")[:80]
        started_at = time.monotonic()
        log_progress(
            f"[{idx}/{total_items}] start item {item_index}: {title}",
            event="item_start",
            meta={"index": item_index, "title": title, "position": idx, "total": total_items},
            daily_dir=daily_dir,
        )
        enriched = fetch_item_context(item, media_dir)
        results.append(enriched)
        elapsed = time.monotonic() - started_at
        statuses = enriched.get("fetch_status", {})
        log_progress(
            f"[{idx}/{total_items}] done item {item_index} in {elapsed:.1f}s "
            f"(primary={statuses.get('primary_url')}, related={statuses.get('related_urls')}, "
            f"links={statuses.get('link_fetches')}, media={statuses.get('media')}, "
            f"warnings={len(enriched.get('warnings', []))})",
            event="item_complete",
            meta={
                "index": item_index,
                "position": idx,
                "total": total_items,
                "duration_ms": int(elapsed * 1000),
                "primary_url": statuses.get("primary_url"),
                "related_urls": statuses.get("related_urls"),
                "link_fetches": statuses.get("link_fetches"),
                "media": statuses.get("media"),
                "warning_count": len(enriched.get("warnings", [])),
            },
            daily_dir=daily_dir,
        )

    enrichment = {"items": results}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enrichment, f, ensure_ascii=False, indent=2)

    # Print warnings to stderr
    total_warnings = sum(len(r.get("warnings", [])) for r in results)
    if total_warnings > 0:
        log_progress(
            f"{total_warnings} warnings (some fetches failed or degraded)",
            event="step_warning",
            status="warn",
            meta={"warning_count": total_warnings},
            daily_dir=daily_dir,
        )

    append_run_log(
        skill="x-news-to-daily-post",
        script="enrich.py",
        event="write_output",
        message="wrote enrichment output",
        meta={"output": output_path, "item_count": len(results)},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-to-daily-post",
        script="enrich.py",
        event="step_complete",
        message="finished enrich",
        meta={"output": output_path, "item_count": len(results), "warning_count": total_warnings},
        daily_dir=daily_dir,
    )

    return enrichment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich companion.json items with additional context"
    )
    parser.add_argument("--companion", type=Path, required=True, help="Path to companion.json")
    parser.add_argument("--output", type=Path, required=True, help="Path to write enrichment.json")
    parser.add_argument(
        "--media-dir", type=Path, required=True, help="Directory to save media files"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.output.expanduser().parent
    lock_path = daily_dir / ".enrich.lock"

    if not args.companion.exists():
        append_run_log(
            skill="x-news-to-daily-post",
            script="enrich.py",
            event="step_failed",
            status="error",
            message="companion.json not found",
            meta={"companion": args.companion},
            daily_dir=daily_dir,
        )
        print(f"Error: companion.json not found: {args.companion}", file=sys.stderr)
        return 1

    if lock_path.exists():
        print(
            f"[enrich] Another enrich.py instance is running (lock: {lock_path}). Exiting.",
            file=sys.stderr,
        )
        append_run_log(
            skill="x-news-to-daily-post",
            script="enrich.py",
            event="step_skipped",
            status="warning",
            message="enrich already running (lock exists), skipping duplicate invocation",
            meta={"lock": str(lock_path)},
            daily_dir=daily_dir,
        )
        return 1

    lock_path.write_text("locked")
    try:
        args.media_dir.mkdir(parents=True, exist_ok=True)
        enrich_companion(args.companion, args.output, args.media_dir)
    finally:
        lock_path.unlink(missing_ok=True)

    print(f"[enrich] Wrote enrichment to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
