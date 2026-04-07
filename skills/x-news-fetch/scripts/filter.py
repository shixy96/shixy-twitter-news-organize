#!/usr/bin/env python3
"""
Filter raw tweets by engagement signal strength.

Usage:
    python3 filter.py <raw.json> [--config SOURCE_CONFIG] [--output <path>]

Output: JSON with strong/medium/backfill buckets.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

X_DOMAINS = {"x.com", "twitter.com"}


def normalize_domain(value: str) -> str:
    domain = value.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.rstrip(".").split(":")[0]


def normalize_x_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    domain = normalize_domain(parsed.netloc)
    if domain not in X_DOMAINS:
        return None
    path = parsed.path.rstrip("/")
    if not path:
        return None
    return f"https://x.com{path}"


def normalize_external_url(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    domain = normalize_domain(parsed.netloc)
    path = parsed.path.rstrip("/")
    normalized = f"https://{domain}{path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    if parsed.fragment:
        normalized = f"{normalized}#{parsed.fragment}"
    return normalized


# --- Signal thresholds ---
DEFAULT_STRONG = {"conditions": 2, "likes": 200, "bookmarks": 80, "interaction_rate": 0.015}
DEFAULT_MEDIUM = {"conditions": 1, "likes": 50, "bookmarks": 20}

TIER_RANK = {None: 0, "medium": 1, "strong": 2}

# --- Link classification ---
HIGH_VALUE_HOSTS = {
    "github.com": ("github", 100),
    "gist.github.com": ("github", 100),
    "arxiv.org": ("arxiv", 95),
    "huggingface.co": ("huggingface", 90),
    "hf.co": ("huggingface", 90),
    "paperswithcode.com": ("paper", 85),
    "openreview.net": ("paper", 85),
}
OFFICIAL_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "claude.com",
    "ai.google.dev",
    "deepmind.google",
    "github.blog",
    "mistral.ai",
    "cohere.com",
    "together.ai",
    "groq.com",
    "nvidia.com",
    "developer.nvidia.com",
    "meta.com",
    "ai.meta.com",
    "vercel.com",
}


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
            normalized = f"{normalized[:-2]}:{normalized[-2:]}"
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def score(p: dict) -> int:
    return p.get("likes", 0) + p.get("bookmarks", 0) * 2 + p.get("quotes", 0) * 3


def signal_tier(likes: int, bookmarks: int, views: int, strong: dict, medium: dict) -> str | None:
    ir = likes / views if views > 0 else 0.0
    sc = (
        (likes >= strong["likes"])
        + (bookmarks >= strong["bookmarks"])
        + (ir >= strong["interaction_rate"])
    )
    if sc >= strong["conditions"]:
        return "strong"
    mc = (likes >= medium["likes"]) + (bookmarks >= medium["bookmarks"])
    if mc >= medium["conditions"]:
        return "medium"
    return None


def classify_link(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)
    domain = normalize_domain(parsed.netloc)
    if domain in {"x.com", "twitter.com"}:
        return None
    if domain in HIGH_VALUE_HOSTS:
        return HIGH_VALUE_HOSTS[domain]
    if any(domain == d or domain.endswith(f".{d}") for d in OFFICIAL_DOMAINS):
        return ("official", 88)
    return ("external", 10)


def collect_links(members: list[dict]) -> tuple[list[dict], list[dict]]:
    by_url: dict[str, dict] = {}
    for p in members:
        for raw_url in p.get("links") or []:
            normalized = normalize_external_url(raw_url)
            if not normalized:
                continue
            cls = classify_link(normalized)
            if cls is None:
                continue
            kind, priority = cls
            entry = by_url.setdefault(
                normalized,
                {
                    "url": normalized,
                    "domain": normalize_domain(urlparse(normalized).netloc),
                    "kind": kind,
                    "mentions": 0,
                    "_pri": priority,
                    "_best": 0,
                },
            )
            entry["mentions"] += 1
            entry["_pri"] = max(entry["_pri"], priority)
            entry["_best"] = max(entry["_best"], p["_base_score"])
            if entry["kind"] == "external" and kind != "external":
                entry["kind"] = kind

    ranked = sorted(by_url.values(), key=lambda x: (-x["_pri"], -x["mentions"], -x["_best"]))
    external = [
        {"url": e["url"], "domain": e["domain"], "kind": e["kind"], "mentions": e["mentions"]}
        for e in ranked[:8]
    ]
    strong = [e for e in external if e["kind"] != "external"][:5]
    return external, strong


def canonical_key(p: dict) -> str:
    return p.get("source_id") or p.get("quoted_id") or p["id"]


def canonical_url(p: dict) -> str:
    return p.get("source_url") or p.get("quoted_url") or p["url"]


def canonical_author(p: dict) -> str:
    return p.get("source_author") or p.get("quoted_author") or p["author"]


def canonical_text(p: dict) -> str:
    return p.get("source_text") or p.get("quoted_text") or p["text"]


def build_candidate(
    p: dict, now: datetime, fresh_h: float, backfill_h: float, st: dict, mt: dict
) -> dict | None:
    tt = parse_time(p.get("time", ""))
    if tt is None:
        return None
    age = now - tt
    if age < timedelta(0):
        window = "fresh"
    elif age < timedelta(hours=fresh_h):
        window = "fresh"
    elif age < timedelta(hours=backfill_h):
        window = "backfill"
    else:
        return None

    c = dict(p)
    c["_tweet_time"] = tt
    c["_window"] = window
    c["_canonical_key"] = canonical_key(p)
    c["_base_signal"] = signal_tier(
        p.get("likes", 0), p.get("bookmarks", 0), p.get("views", 0), st, mt
    )
    c["_base_score"] = score(p)
    c["_interaction_rate"] = round(
        p.get("likes", 0) / p.get("views", 1) if p.get("views", 0) > 0 else 0.0, 4
    )
    return c


def group_candidates(posts: list[dict], st: dict, mt: dict) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        groups[p["_canonical_key"]].append(p)

    result = []
    for key, members in groups.items():
        rep = max(
            members, key=lambda p: (p["id"] == key, TIER_RANK[p["_base_signal"]], p["_base_score"])
        )
        source_posts = [p for p in members if p["id"] == key]
        canonical = max(source_posts, key=lambda p: p["_base_score"]) if source_posts else rep
        anchor_time = (
            canonical["_tweet_time"] if source_posts else max(p["_tweet_time"] for p in members)
        )

        al = sum(p.get("likes", 0) for p in members)
        av = sum(p.get("views", 0) for p in members)
        ab = sum(p.get("bookmarks", 0) for p in members)
        aq = sum(p.get("quotes", 0) for p in members)
        a_score = sum(p["_base_score"] for p in members)
        agg_sig = signal_tier(al, ab, av, st, mt)
        max_sig = max((p["_base_signal"] for p in members), key=lambda t: TIER_RANK[t])
        final_sig = max((agg_sig, max_sig), key=lambda t: TIER_RANK[t])

        item = dict(rep)
        item.update(
            {
                "_signal": final_sig,
                "_score": a_score,
                "_window": canonical["_window"] if source_posts else rep["_window"],
                "_group_size": len(members),
                "_source_proxy": rep["id"] != key,
                "_aggregate_likes": al,
                "_aggregate_views": av,
                "_aggregate_bookmarks": ab,
                "_aggregate_quotes": aq,
                "_aggregate_score": a_score,
                "_aggregate_interaction_rate": round(al / av if av > 0 else 0.0, 4),
                "_canonical_id": key,
                "_canonical_url": canonical_url(canonical),
                "_canonical_author": canonical_author(canonical),
                "_canonical_text": canonical_text(canonical),
                "_anchor_time": anchor_time.isoformat(),
            }
        )
        item["_external_links"], item["_strong_links"] = collect_links(members)

        related: list[str] = []
        seen: set[str] = set()
        for p in sorted(members, key=lambda p: -p["_base_score"]):
            cu = normalize_x_url(p["url"])
            if cu and cu != normalize_x_url(rep["url"]) and cu not in seen:
                seen.add(cu)
                related.append(cu)
        item["_related_urls"] = related[:5]
        result.append(item)
    return result


def filter_posts(
    raw: list[dict],
    now: datetime,
    fresh_h: float = 24,
    backfill_h: float = 48,
    config: dict | None = None,
) -> dict:
    thresholds = (config or {}).get("signal_thresholds", {})
    st = thresholds.get("strong", DEFAULT_STRONG)
    mt = thresholds.get("medium", DEFAULT_MEDIUM)

    seen_ids: set[str] = set()
    posts: list[dict] = []
    skipped = Counter()
    for p in raw:
        if p["id"] in seen_ids:
            skipped["duplicate_id"] += 1
            continue
        seen_ids.add(p["id"])
        posts.append(p)

    candidates = []
    for p in posts:
        if p.get("likes", 0) < 10 and p.get("bookmarks", 0) < 5:
            skipped["noise"] += 1
            continue
        c = build_candidate(p, now, fresh_h, backfill_h, st, mt)
        if c is None:
            skipped["outside_window"] += 1
            continue
        candidates.append(c)

    grouped = [g for g in group_candidates(candidates, st, mt) if g["_signal"] is not None]

    strong = sorted(
        [g for g in grouped if g["_window"] == "fresh" and g["_signal"] == "strong"],
        key=lambda g: -g["_score"],
    )
    medium = sorted(
        [g for g in grouped if g["_window"] == "fresh" and g["_signal"] == "medium"],
        key=lambda g: -g["_score"],
    )
    backfill = sorted(
        [
            g
            for g in grouped
            if g["_window"] == "backfill"
            and (
                g["_signal"] == "strong"
                or g["_aggregate_likes"] >= 500
                or g["_aggregate_bookmarks"] >= 200
            )
        ],
        key=lambda g: -g["_score"],
    )

    # Author cap: max 2 per author per bucket
    author_counts: Counter[str] = Counter()
    capped = {"strong": [], "medium": [], "backfill": []}
    for name, items in (("strong", strong), ("backfill", backfill), ("medium", medium)):
        for item in items:
            a = item.get("author", "")
            if author_counts[a] < 2:
                author_counts[a] += 1
                capped[name].append(item)

    def strip(item: dict) -> dict:
        c = dict(item)
        for k in ("_tweet_time", "_canonical_key", "_base_signal", "_base_score"):
            c.pop(k, None)
        return c

    return {
        "stats": {
            "total_raw": len(raw),
            "unique": len(posts),
            "within_window": len(candidates),
            "grouped_candidates": len(grouped),
            "strong": len(capped["strong"]),
            "medium": len(capped["medium"]),
            "backfill": len(capped["backfill"]),
            "skipped": sum(skipped.values()),
            "skipped_breakdown": dict(skipped),
        },
        "strong": [strip(i) for i in capped["strong"]],
        "medium": [strip(i) for i in capped["medium"]],
        "backfill": [strip(i) for i in capped["backfill"]],
    }


def main():
    parser = argparse.ArgumentParser(description="Filter raw tweets by engagement")
    parser.add_argument("input", help="Raw JSON file")
    parser.add_argument("--config", help="SOURCE_CONFIG with signal_thresholds")
    parser.add_argument("--fresh-hours", type=float, default=24)
    parser.add_argument("--backfill-hours", type=float, default=48)
    parser.add_argument("--now", default=None, help="Reference time ISO 8601")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)
    if args.backfill_hours <= args.fresh_hours:
        print("Error: --backfill-hours must be > --fresh-hours", file=sys.stderr)
        sys.exit(1)

    config = {}
    if args.config:
        try:
            with open(args.config, encoding="utf-8") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    raw = json.loads(input_path.read_text(encoding="utf-8"))
    now = parse_time(args.now) or datetime.now(timezone.utc)
    result = filter_posts(
        raw, now=now, fresh_h=args.fresh_hours, backfill_h=args.backfill_hours, config=config
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    s = result["stats"]
    print(
        f"[filter] {s['total_raw']} raw → {s['unique']} unique → strong={s['strong']} medium={s['medium']} backfill={s['backfill']}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
