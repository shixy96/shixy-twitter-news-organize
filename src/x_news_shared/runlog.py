"""Structured run logging helpers for pipeline skills."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_iso(value: str) -> datetime:
    normalized = value.strip()
    if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def current_timestamp() -> str:
    """Return an ISO timestamp, preferring REPORT_BOUNDARY timezone when available."""
    boundary = os.environ.get("REPORT_BOUNDARY")
    if boundary:
        try:
            tzinfo = _parse_iso(boundary).tzinfo
            return datetime.now(tzinfo).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_run_log_path(
    *,
    explicit: str | Path | None = None,
    daily_dir: str | Path | None = None,
) -> Path | None:
    """Resolve the JSONL run log path from explicit input, daily dir, or env."""
    if explicit:
        return Path(explicit).expanduser()

    env_path = os.environ.get("RUN_LOG_PATH")
    if env_path:
        return Path(env_path).expanduser()

    if daily_dir:
        return Path(daily_dir).expanduser() / "run.log.jsonl"

    run_root = os.environ.get("RUN_ROOT")
    report_date = os.environ.get("REPORT_DATE")
    if run_root and report_date:
        return Path(run_root).expanduser() / "daily" / report_date / "run.log.jsonl"

    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def append_run_log(
    *,
    skill: str,
    script: str,
    event: str,
    status: str = "info",
    message: str = "",
    meta: dict[str, Any] | None = None,
    run_log_path: str | Path | None = None,
    daily_dir: str | Path | None = None,
) -> Path | None:
    """Append one structured event to run.log.jsonl.

    Returns the resolved log path, or None when logging is disabled because no
    path could be resolved.
    """
    path = resolve_run_log_path(explicit=run_log_path, daily_dir=daily_dir)
    if path is None:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    event_row = {
        "ts": current_timestamp(),
        "run_id": os.environ.get("RUN_ID", ""),
        "report_date": os.environ.get("REPORT_DATE", ""),
        "skill": skill,
        "script": script,
        "event": event,
        "status": status,
        "message": message,
        "meta": _json_safe(meta or {}),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event_row, ensure_ascii=False) + "\n")
    return path
