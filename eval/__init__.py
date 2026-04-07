"""x-news eval package."""

from .eval_lib import (
    EVAL_ROOT,
    EVAL_RUNS_ROOT,
    REPO_ROOT,
    build_benchmark,
    ensure_dir,
    evaluate_digest,
    load_json,
    pairwise_jaccard,
    short_id,
    timestamp_token,
    write_json,
)

__all__ = [
    "EVAL_ROOT",
    "EVAL_RUNS_ROOT",
    "REPO_ROOT",
    "build_benchmark",
    "ensure_dir",
    "evaluate_digest",
    "load_json",
    "pairwise_jaccard",
    "short_id",
    "timestamp_token",
    "write_json",
]
