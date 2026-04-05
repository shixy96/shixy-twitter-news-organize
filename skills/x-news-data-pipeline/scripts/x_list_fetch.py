#!/usr/bin/env python3
"""
x_list_fetch: Fetch tweets from X Lists via twitter CLI.

Usage:
    python3 x_list_fetch.py --config <path> --hours <N> --until <iso8601> [--fetch-log <path>] > raw.json

Exit codes:
    0 - Success (raw.json written and validated)
    1 - Fetch failed or validation failed
    2 - Missing required arguments
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log

FETCH_STAGE_LABELS = {
    "list_fetch": "列表抓取失败",
}


def parse_iso(value: str) -> datetime:
    """Parse ISO 8601 datetime string, normalizing shorthand forms."""
    normalized = value.strip()
    if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def prepare_fetch_log(fetch_log_path: Path | None) -> Path | None:
    """Ensure the fetch log path is writable before we start appending JSONL rows."""
    if fetch_log_path is None:
        return None
    path = fetch_log_path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return path


def resolve_daily_dir(fetch_log_path: Path | None) -> Path | None:
    if fetch_log_path is not None:
        return fetch_log_path.expanduser().parent
    raw_path = os.environ.get("RAW_PATH")
    if raw_path:
        return Path(raw_path).expanduser().parent
    return None


def trim_log_text(value: str, limit: int = 500) -> str:
    """Keep logged stderr/stdout previews small and stable."""
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def stream_text(value) -> str:
    """Normalize subprocess partial stdout/stderr into text for logging."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def is_rate_limited_message(*values: str) -> bool:
    """Best-effort rate limit detection for stderr/stdout/API errors."""
    haystack = " ".join(value.lower() for value in values if value)
    return "rate limit" in haystack or "rate_limited" in haystack or "429" in haystack


def classify_api_error(error_code: str | None, message: str) -> str:
    """Classify API failures into stable buckets for fetch logs."""
    if error_code == "rate_limited" or is_rate_limited_message(error_code or "", message):
        return "rate_limited"
    return "api_error"


def resolve_progress_timestamp() -> str:
    """Use REPORT_BOUNDARY timezone when available so logs stay consistent with the run."""
    boundary = os.environ.get("REPORT_BOUNDARY")
    if boundary:
        try:
            return datetime.now(parse_iso(boundary).tzinfo).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_fetch_failure_row(
    *,
    stage: str,
    error_type: str,
    message: str,
    cmd: list[str],
    source_name: str | None = None,
    list_id: str | None = None,
    returncode: int | None = None,
    stderr: str | None = None,
    stdout_preview: str | None = None,
) -> dict:
    """Build a structured fetch failure row compatible with the pipeline log format."""
    meta = {
        "fetch_stage": stage,
        "error_type": error_type,
        "cmd": cmd,
    }
    if source_name:
        meta["source_name"] = source_name
    if list_id:
        meta["list_id"] = list_id
    if returncode is not None:
        meta["returncode"] = returncode
    if stderr:
        meta["stderr"] = trim_log_text(stderr)
    if stdout_preview:
        meta["stdout_preview"] = trim_log_text(stdout_preview)

    return {
        "ts": resolve_progress_timestamp(),
        "run_id": os.environ.get("RUN_ID", ""),
        "step": "data_fetch",
        "status": "error",
        "message": f"{FETCH_STAGE_LABELS.get(stage, stage)}: {trim_log_text(message, 240)}",
        "meta": meta,
    }


def append_fetch_failure(
    fetch_log_path: Path | None,
    *,
    stage: str,
    error_type: str,
    message: str,
    cmd: list[str],
    source_name: str | None = None,
    list_id: str | None = None,
    returncode: int | None = None,
    stderr: str | None = None,
    stdout_preview: str | None = None,
) -> dict:
    """Append a structured JSONL error row and return it for in-memory summaries."""
    event = build_fetch_failure_row(
        stage=stage,
        error_type=error_type,
        message=message,
        cmd=cmd,
        source_name=source_name,
        list_id=list_id,
        returncode=returncode,
        stderr=stderr,
        stdout_preview=stdout_preview,
    )
    if fetch_log_path is not None:
        with fetch_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    append_run_log(
        skill="x-news-data-pipeline",
        script="x_list_fetch.py",
        event="fetch_failed",
        status="error",
        message=message,
        meta=event.get("meta", {}),
        daily_dir=resolve_daily_dir(fetch_log_path),
    )
    return event


def update_error_info(error_info: dict | None, event: dict | None) -> None:
    """Mutate an optional error info dict so callers can inspect a fetch failure."""
    if error_info is None or event is None:
        return
    error_info.clear()
    error_info.update(event)


def run_twitter_json(
    cmd: list[str],
    *,
    timeout: int,
    error_prefix: str,
    fetch_log_path: Path | None = None,
    stage: str,
    source_name: str | None = None,
    list_id: str | None = None,
    error_info: dict | None = None,
) -> list[dict]:
    """Run twitter-cli and return the envelope's data array when successful."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path(__file__).resolve().parent,
        )
    except FileNotFoundError:
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type="missing_tool",
            message="'twitter' command not found",
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: 'twitter' command not found", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired as exc:
        partial_stdout = stream_text(exc.stdout)
        partial_stderr = stream_text(exc.stderr)
        error_type = (
            "rate_limited" if is_rate_limited_message(partial_stdout, partial_stderr) else "timeout"
        )
        message = (
            "rate limited while waiting for twitter-cli retries"
            if error_type == "rate_limited"
            else "timed out"
        )
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type=error_type,
            message=message,
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
            stdout_preview=partial_stdout,
            stderr=partial_stderr,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: {message}", file=sys.stderr)
        return []

    parsed_envelope = None
    json_error = None
    if result.stdout.strip():
        try:
            parsed_envelope = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            json_error = exc

    if result.returncode != 0:
        if isinstance(parsed_envelope, dict) and not parsed_envelope.get("ok"):
            error = parsed_envelope.get("error", {})
            message = error.get("message", "unknown")
            event = append_fetch_failure(
                fetch_log_path,
                stage=stage,
                error_type=classify_api_error(error.get("code"), message),
                message=message,
                cmd=cmd,
                source_name=source_name,
                list_id=list_id,
                returncode=result.returncode,
                stderr=result.stderr,
                stdout_preview=result.stdout,
            )
            update_error_info(error_info, event)
            print(f"{error_prefix}: API error ({message})", file=sys.stderr)
            return []

        detail = result.stderr.strip() or f"exit code {result.returncode}"
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type="rate_limited"
            if is_rate_limited_message(detail, result.stdout)
            else "nonzero_exit",
            message=detail,
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
            returncode=result.returncode,
            stderr=result.stderr,
            stdout_preview=result.stdout,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: {detail}", file=sys.stderr)
        return []

    if json_error is not None:
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type="invalid_json",
            message=str(json_error),
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
            returncode=result.returncode,
            stderr=result.stderr,
            stdout_preview=result.stdout,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: invalid JSON ({json_error})", file=sys.stderr)
        return []

    if not isinstance(parsed_envelope, dict):
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type="invalid_json",
            message="missing JSON object envelope",
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
            returncode=result.returncode,
            stderr=result.stderr,
            stdout_preview=result.stdout,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: invalid JSON (missing JSON object envelope)", file=sys.stderr)
        return []

    if not parsed_envelope.get("ok", False):
        error = parsed_envelope.get("error", {})
        message = error.get("message", "unknown")
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type=classify_api_error(error.get("code"), message),
            message=message,
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
            returncode=result.returncode,
            stderr=result.stderr,
            stdout_preview=result.stdout,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: API error ({message})", file=sys.stderr)
        return []

    data = parsed_envelope.get("data", [])
    if not isinstance(data, list):
        event = append_fetch_failure(
            fetch_log_path,
            stage=stage,
            error_type="invalid_json",
            message="'data' must be a JSON array",
            cmd=cmd,
            source_name=source_name,
            list_id=list_id,
            returncode=result.returncode,
            stderr=result.stderr,
            stdout_preview=result.stdout,
        )
        update_error_info(error_info, event)
        print(f"{error_prefix}: invalid JSON ('data' must be a JSON array)", file=sys.stderr)
        return []

    return [item for item in data if isinstance(item, dict)]


def format_author(author: dict) -> str:
    """Render the author in the same flat string form expected by downstream stages."""
    screen_name = author.get("screenName", "")
    name = author.get("name", "")
    if screen_name and name:
        return f"@{screen_name} ({name})"
    if screen_name:
        return f"@{screen_name}"
    return name


def metric_value(metrics: dict, key: str) -> int:
    """Return an integer metric value with a safe 0 fallback."""
    value = metrics.get(key, 0)
    return value if isinstance(value, int) else 0


def preprocess_tweet(raw: dict, source_name: str) -> dict:
    """Flatten twitter-cli raw payloads into the raw.json schema expected downstream."""
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    screen_name = author.get("screenName", "")
    tweet_id = raw.get("id", "")
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    quoted = raw.get("quotedTweet") if isinstance(raw.get("quotedTweet"), dict) else None
    urls = raw.get("urls") if isinstance(raw.get("urls"), list) else []
    media = raw.get("media") if isinstance(raw.get("media"), list) else []
    text = raw.get("text", "")

    tweet = {
        "id": tweet_id,
        "url": f"https://x.com/{screen_name}/status/{tweet_id}"
        if screen_name and tweet_id
        else raw.get("url", ""),
        "author": format_author(author),
        "time": raw.get("createdAtISO", raw.get("createdAt", "")),
        "text": text,
        "likes": metric_value(metrics, "likes"),
        "views": metric_value(metrics, "views"),
        "retweets": metric_value(metrics, "retweets"),
        "replies": metric_value(metrics, "replies"),
        "quotes": metric_value(metrics, "quotes"),
        "bookmarks": metric_value(metrics, "bookmarks"),
        "source": source_name,
    }

    if raw.get("isRetweet"):
        tweet["is_retweet"] = True
    if raw.get("retweetedBy"):
        tweet["retweeted_by"] = f"@{raw['retweetedBy']}"
    if isinstance(text, str) and re.match(r"^@\w", text):
        tweet["likely_reply"] = True
    if quoted:
        quoted_author = quoted.get("author") if isinstance(quoted.get("author"), dict) else {}
        quoted_screen_name = quoted_author.get("screenName", "")
        quoted_id = quoted.get("id", "")
        quoted_text = quoted.get("text", "")
        if quoted_screen_name or quoted_text:
            tweet["quoted"] = f"@{quoted_screen_name}: {quoted_text}".rstrip(": ")
        if quoted_id:
            tweet["quoted_id"] = quoted_id
        if quoted_screen_name and quoted_id:
            tweet["quoted_url"] = f"https://x.com/{quoted_screen_name}/status/{quoted_id}"
        if quoted_author:
            tweet["quoted_author"] = format_author(quoted_author)
        if quoted_text:
            tweet["quoted_text"] = quoted_text
    if urls:
        tweet["links"] = [url for url in urls if isinstance(url, str)]
    if media:
        tweet["media"] = media

    return tweet


def fetch_list_tweets(
    list_id: str,
    max_tweets: int,
    *,
    source_name: str | None = None,
    fetch_log_path: Path | None = None,
    error_info: dict | None = None,
) -> list[dict]:
    """Fetch raw tweets from a single X List via twitter-cli."""
    tweets = run_twitter_json(
        ["twitter", "list", list_id, "--json", "--full-text", "--max", str(max_tweets)],
        timeout=120,
        error_prefix=f"Error fetching list {list_id}",
        fetch_log_path=fetch_log_path,
        stage="list_fetch",
        source_name=source_name,
        list_id=list_id,
        error_info=error_info,
    )
    return tweets


def fetch_all_lists(
    config: dict,
    hours: int,
    until: datetime,
    fetch_log_path: Path | None,
) -> tuple[list[dict], list[dict]]:
    """Fetch, preprocess, and time-filter tweets from every configured list."""
    fetch_log_path = prepare_fetch_log(fetch_log_path)

    defaults = config.get("defaults", {})
    max_default = defaults.get("max", 50)

    sources = config.get("sources", [])
    if not sources:
        print("Warning: no sources in config, nothing to fetch", file=sys.stderr)
        return [], []

    all_tweets: list[dict] = []
    fetch_errors: list[dict] = []
    window_start = until - timedelta(hours=hours)

    for source in sources:
        list_id = source.get("id")
        name = source.get("name", "unknown")
        max_tweets = source.get("max", max_default)

        if not list_id:
            fetch_errors.append(
                append_fetch_failure(
                    fetch_log_path,
                    stage="list_fetch",
                    error_type="invalid_config",
                    message="missing list_id",
                    cmd=["twitter", "list", ""],
                    source_name=name,
                )
            )
            continue

        error_info: dict = {}
        raw_tweets = fetch_list_tweets(
            list_id,
            max_tweets,
            source_name=name,
            fetch_log_path=fetch_log_path,
            error_info=error_info,
        )

        if error_info:
            fetch_errors.append(dict(error_info))
            continue

        if not raw_tweets:
            fetch_errors.append(
                append_fetch_failure(
                    fetch_log_path,
                    stage="list_fetch",
                    error_type="empty_data",
                    message="no tweets returned",
                    cmd=[
                        "twitter",
                        "list",
                        list_id,
                        "--json",
                        "--full-text",
                        "--max",
                        str(max_tweets),
                    ],
                    source_name=name,
                    list_id=list_id,
                )
            )
            continue

        for raw_tweet in raw_tweets:
            tweet = preprocess_tweet(raw_tweet, name)
            tweet_time_str = tweet.get("time", "")
            if not tweet_time_str:
                continue
            try:
                tweet_time = parse_iso(tweet_time_str)
            except (TypeError, ValueError):
                continue
            if window_start <= tweet_time < until:
                all_tweets.append(tweet)

    return all_tweets, fetch_errors


def deduplicate_tweets(tweets: list[dict]) -> list[dict]:
    """Deduplicate tweets by id, preserving order."""
    seen: set[str] = set()
    result = []
    for tweet in tweets:
        tweet_id = tweet.get("id", "")
        if tweet_id and tweet_id not in seen:
            seen.add(tweet_id)
            result.append(tweet)
    return result


def sort_tweets_desc(tweets: list[dict]) -> list[dict]:
    """Sort tweets newest-first, keeping malformed timestamps at the end."""

    def sort_key(tweet: dict) -> datetime:
        try:
            return parse_iso(tweet.get("time", ""))
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(tweets, key=sort_key, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch tweets from X Lists")
    parser.add_argument("--config", type=Path, required=True, help="Path to SOURCE_CONFIG JSON")
    parser.add_argument("--hours", type=int, required=True, help="Backfill window in hours")
    parser.add_argument(
        "--until",
        type=str,
        required=True,
        help="Cutoff time ISO 8601 (tweets at or after this time are excluded)",
    )
    parser.add_argument(
        "--fetch-log",
        type=Path,
        default=None,
        help="Path to write fetch errors as JSONL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write raw JSON output (recommended; bypasses stdout)",
    )
    args = parser.parse_args()
    daily_dir = resolve_daily_dir(args.fetch_log)
    append_run_log(
        skill="x-news-data-pipeline",
        script="x_list_fetch.py",
        event="step_start",
        message="starting x_list_fetch",
        meta={
            "config": args.config,
            "hours": args.hours,
            "until": args.until,
            "fetch_log": args.fetch_log,
        },
        daily_dir=daily_dir,
    )

    try:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        append_run_log(
            skill="x-news-data-pipeline",
            script="x_list_fetch.py",
            event="step_failed",
            status="error",
            message="invalid config",
            meta={"config": args.config, "error": str(e)},
            daily_dir=daily_dir,
        )
        print(f"Error: invalid config: {e}", file=sys.stderr)
        return 2

    try:
        until = parse_iso(args.until)
    except (ValueError, TypeError) as e:
        append_run_log(
            skill="x-news-data-pipeline",
            script="x_list_fetch.py",
            event="step_failed",
            status="error",
            message="invalid until timestamp",
            meta={"until": args.until, "error": str(e)},
            daily_dir=daily_dir,
        )
        print(f"Error: invalid --until time: {e}", file=sys.stderr)
        return 2

    tweets, fetch_errors = fetch_all_lists(config, args.hours, until, args.fetch_log)

    if not tweets:
        append_run_log(
            skill="x-news-data-pipeline",
            script="x_list_fetch.py",
            event="step_failed",
            status="error",
            message="no tweets fetched",
            meta={
                "source_count": len(config.get("sources", [])),
                "fetch_errors": len(fetch_errors),
            },
            daily_dir=daily_dir,
        )
        print("Error: no tweets fetched", file=sys.stderr)
        return 1

    tweets = sort_tweets_desc(deduplicate_tweets(tweets))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(tweets, f, ensure_ascii=False)
            f.write("\n")
    else:
        json.dump(tweets, sys.stdout, ensure_ascii=False)
        print()

    total = len(tweets)
    errors = len(fetch_errors)
    print(
        f"[x_list_fetch] fetched {total} tweets from {len(config.get('sources', []))} sources, "
        f"{errors} fetch errors"
        + (f", logged to {args.fetch_log}" if args.fetch_log and errors else ""),
        file=sys.stderr,
    )
    append_run_log(
        skill="x-news-data-pipeline",
        script="x_list_fetch.py",
        event="step_complete",
        message="fetched raw tweets",
        meta={
            "tweet_count": total,
            "source_count": len(config.get("sources", [])),
            "fetch_errors": errors,
            "output_path": os.environ.get("RAW_PATH", ""),
            "fetch_log": args.fetch_log,
        },
        daily_dir=daily_dir,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
