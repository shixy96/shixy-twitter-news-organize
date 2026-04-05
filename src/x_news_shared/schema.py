#!/usr/bin/env python3
"""JSON Schema definitions for x-news pipeline artifacts."""

# Raw tweet schema - individual tweet object in raw.json array
RAW_SCHEMA = {
    "type": "object",
    "required": ["id", "url", "author", "text", "time"],
    "properties": {
        "id": {"type": "string"},
        "url": {"type": "string"},
        "author": {"type": "string"},
        "text": {"type": "string"},
        "time": {"type": "string"},
        "likes": {"type": "integer", "minimum": 0},
        "views": {"type": "integer", "minimum": 0},
        "bookmarks": {"type": "integer", "minimum": 0},
        "quotes": {"type": "integer", "minimum": 0},
        "replies": {"type": "integer", "minimum": 0},
        "retweets": {"type": "integer", "minimum": 0},
        "links": {"type": "array", "items": {"type": "string"}},
        "media": {"type": "array"},
        "source_id": {"type": "string"},
        "source_url": {"type": "string"},
        "source_author": {"type": "string"},
        "source_text": {"type": "string"},
        "quoted_id": {"type": "string"},
        "quoted_url": {"type": "string"},
        "quoted_author": {"type": "string"},
        "quoted_text": {"type": "string"},
        "thread_reply_ids": {"type": "array", "items": {"type": "string"}},
        "thread_text": {"type": "string"},
        "has_thread_context": {"type": "boolean"},
        "detail_fetched": {"type": "boolean"},
        "detail_reply_count": {"type": "integer"},
    },
}

# Filtered result schema - output of filter.py
FILTERED_SCHEMA = {
    "type": "object",
    "required": ["stats", "strong", "medium", "backfill"],
    "properties": {
        "stats": {
            "type": "object",
            "required": ["total_raw", "unique", "within_window", "grouped_candidates",
                         "strong", "medium", "backfill", "skipped"],
            "properties": {
                "total_raw": {"type": "integer"},
                "unique": {"type": "integer"},
                "within_window": {"type": "integer"},
                "grouped_candidates": {"type": "integer"},
                "strong": {"type": "integer"},
                "medium": {"type": "integer"},
                "backfill": {"type": "integer"},
                "skipped": {"type": "integer"},
                "skipped_breakdown": {"type": "object"},
            },
        },
        "strong": {"type": "array", "items": {"type": "object"}},
        "medium": {"type": "array", "items": {"type": "object"}},
        "backfill": {"type": "array", "items": {"type": "object"}},
    },
}

# Companion JSON schema - editorial output replacing report.md
COMPANION_SCHEMA = {
    "type": "object",
    "required": ["generated_at", "report_date", "title", "description", "stats",
                 "categories", "items"],
    "properties": {
        "generated_at": {"type": "string"},
        "report_date": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "stats": {
            "type": "object",
            "required": ["strong", "medium", "backfill", "total", "selected"],
            "properties": {
                "strong": {"type": "integer"},
                "medium": {"type": "integer"},
                "backfill": {"type": "integer"},
                "total": {"type": "integer"},
                "selected": {"type": "integer"},
            },
        },
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "items"],
                "properties": {
                    "name": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "object"}},
                },
            },
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["index", "canonical_id", "title", "author",
                             "author_screen_name", "category", "is_highlight",
                             "summary", "metrics", "primary_url", "strong_links",
                             "external_links", "related_urls", "is_backfill", "is_followup"],
                "properties": {
                    "index": {"type": "integer"},
                    "canonical_id": {"type": "string"},
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                    "author_screen_name": {"type": "string"},
                    "category": {"type": "string"},
                    "is_highlight": {"type": "boolean"},
                    "summary": {"type": "string"},
                    "metrics": {
                        "type": "object",
                        "properties": {
                            "likes": {"type": "integer"},
                            "views": {"type": "integer"},
                            "bookmarks": {"type": "integer"},
                        },
                    },
                    "primary_url": {"type": "string"},
                    "strong_links": {"type": "array", "items": {"type": "string"}},
                    "external_links": {"type": "array", "items": {"type": "string"}},
                    "related_urls": {"type": "array", "items": {"type": "string"}},
                    "is_backfill": {"type": "boolean"},
                    "is_followup": {"type": "boolean"},
                },
            },
        },
    },
}

# Dedup result schema - output of dedup.py
DEDUP_RESULT_SCHEMA = {
    "type": "object",
    "required": ["auto_resolved", "history_prior_match", "require_decision"],
    "properties": {
        "auto_resolved": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["canonical_id", "dedup_type", "reason"],
                "properties": {
                    "canonical_id": {"type": "string"},
                    "dedup_type": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "history_prior_match": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["canonical_id", "prior_item", "has_new_content_delta",
                             "delta_summary", "reason"],
                "properties": {
                    "canonical_id": {"type": "string"},
                    "prior_item": {"type": "object"},
                    "has_new_content_delta": {"type": "boolean"},
                    "delta_summary": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "require_decision": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["canonical_id", "candidates", "reason"],
                "properties": {
                    "canonical_id": {"type": "string"},
                    "candidates": {"type": "array", "items": {"type": "object"}},
                    "reason": {"type": "string"},
                },
            },
        },
        "by_author": {"type": "object"},
    },
}

# Enrichment schema - output of enrich.py
ENRICHMENT_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["index", "fetch_status"],
                "properties": {
                    "index": {"type": "integer"},
                    "fetch_status": {
                        "type": "object",
                        "properties": {
                            "primary_url": {"type": "string"},
                            "related_urls": {"type": "string"},
                            "link_fetches": {"type": "string"},
                            "media": {"type": "string"},
                        },
                    },
                    "primary_url_fetch": {"type": "object"},
                    "related_url_fetches": {"type": "array", "items": {"type": "object"}},
                    "link_fetches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "type": {"type": "string"},
                                "data": {"type": "object"},
                                "fetch_status": {"type": "string"},
                            },
                        },
                    },
                    "selected_context_facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "source_url": {"type": "string"},
                                "source_type": {"type": "string"},
                            },
                        },
                    },
                    "media_files": {"type": "array", "items": {"type": "string"}},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

# Editorial categories - used across editorial, quality-audit, and daily-post skills
ALLOWED_CATEGORIES = {
    "模型发布",
    "开发生态",
    "技术洞察",
    "产品动态",
    "安全事件",
    "行业观点",
}

# Post JSON schema - output of assemble.py
POST_SCHEMA = {
    "type": "object",
    "required": ["title", "description", "pubDate", "tags", "slug", "categories"],
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "pubDate": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "slug": {"type": "string"},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "items"],
                "properties": {
                    "name": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["index", "title", "link", "body"],
                            "properties": {
                                "index": {"type": "integer"},
                                "title": {"type": "string"},
                                "link": {"type": "string"},
                                "body": {"type": "string"},
                                "media": {"type": "array", "items": {"type": "string"}},
                                "related_links": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "text": {"type": "string"},
                                            "url": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}
