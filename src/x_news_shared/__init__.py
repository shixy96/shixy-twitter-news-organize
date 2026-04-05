"""x_news_shared - shared utilities for x-news pipeline skills."""

from .normalize import (
    normalize_domain,
    normalize_external_url,
    normalize_link,
    normalize_x_url,
)
from .runlog import append_run_log, resolve_run_log_path
from .schema import (
    ALLOWED_CATEGORIES,
    COMPANION_SCHEMA,
    DEDUP_RESULT_SCHEMA,
    ENRICHMENT_SCHEMA,
    FILTERED_SCHEMA,
    POST_SCHEMA,
    RAW_SCHEMA,
)
from .validate import validate_json_schema

__all__ = [
    "ALLOWED_CATEGORIES",
    "normalize_domain",
    "normalize_external_url",
    "normalize_link",
    "normalize_x_url",
    "append_run_log",
    "resolve_run_log_path",
    "RAW_SCHEMA",
    "FILTERED_SCHEMA",
    "COMPANION_SCHEMA",
    "POST_SCHEMA",
    "DEDUP_RESULT_SCHEMA",
    "ENRICHMENT_SCHEMA",
    "validate_json_schema",
]
