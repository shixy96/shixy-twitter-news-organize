#!/usr/bin/env python3
"""
Render post.json to post.md for x-news-to-daily-post.

Usage:
    python3 render_md.py --input <path> --output <path>

Exit codes:
    0 - Success
    1 - Invalid arguments or rendering error
"""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log


def split_body_paragraphs(body: str) -> list[str]:
    """Split body text into display paragraphs."""
    paragraphs = []
    for paragraph in body.split("\n\n"):
        normalized = paragraph.strip()
        if normalized:
            paragraphs.append(normalized)
    return paragraphs


def render_media_block(item: dict) -> list[str]:
    """Render item media lines."""
    lines: list[str] = []
    title = item.get("title", "配图")
    media = item.get("media", [])
    for media_file in media:
        if media_file.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
            lines.append(f"![{title}]({media_file})")
        elif media_file.endswith((".mp4", ".mov", ".webm")):
            lines.append(f'<video src="{media_file}" controls></video>')
    return lines


def render_related_links_block(item: dict) -> list[str]:
    """Render related links as plain-text URL bullets."""
    rendered_links: list[str] = []

    # Primary link (X tweet URL)
    primary_link = (item.get("link") or "").strip()
    if primary_link:
        rendered_links.append(f"- 原文：{primary_link}")

    # Related links (external: GitHub, arXiv, etc.)
    related_links = item.get("related_links", [])
    for rel_link in related_links:
        if isinstance(rel_link, dict):
            text = (rel_link.get("text") or rel_link.get("url") or "").strip()
            url = (rel_link.get("url") or "").strip()
        else:
            text = url = str(rel_link).strip()

        if not url:
            continue

        if text and text != url:
            rendered_links.append(f"- {text}：{url}")
        else:
            rendered_links.append(f"- {url}")

    if not rendered_links:
        return []

    return ["相关链接：", *rendered_links]


def render_item_heading(item: dict, display_index: int | None = None) -> str:
    """Render a single item heading in sample output format."""
    # Strip newlines — title must be a single line in the heading
    title = " ".join((item.get("title") or "无标题").split())
    link = (item.get("link") or "").strip()
    # Use display_index (global sequential) if provided, otherwise fall back to original index
    index = display_index if display_index is not None else item.get("index")

    if link:
        heading = f"### [{title}]({link})"
    else:
        heading = f"### {title}"

    if index is not None:
        heading += f" `#{index}`"

    return heading


def render_item(item: dict, display_index: int | None = None) -> str:
    """Render a single news item."""
    sections = [render_item_heading(item, display_index)]

    body = item.get("body", "")
    paragraphs = split_body_paragraphs(body)
    if paragraphs:
        sections.append("\n\n".join(paragraphs))

    media_lines = render_media_block(item)
    if media_lines:
        sections.append("\n".join(media_lines))

    related_links_block = render_related_links_block(item)
    if related_links_block:
        sections.append("\n".join(related_links_block))

    return "\n\n".join(sections)


def render_category_section(category: dict, start_index: int = 1) -> tuple[str, int]:
    """Render a single category section to markdown.

    Args:
        category: Category dict with name and items.
        start_index: Global sequential index for the first item in this category.

    Returns:
        Tuple of (rendered markdown string, next available global index).
    """
    cat_name = category.get("name", "未分类")
    items = category.get("items", [])

    lines = [f"## {cat_name}"]
    current_index = start_index
    for item in items:
        lines.append(render_item(item, display_index=current_index))
        current_index += 1

    return "\n\n".join(lines), current_index


def yaml_escape(value: str) -> str:
    """Escape a string for a YAML double-quoted scalar."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def render_frontmatter(post: dict) -> str:
    """Render YAML frontmatter from post metadata.

    Args:
        post: Post dict

    Returns:
        Frontmatter string
    """
    lines = ["---"]

    # Required fields
    title = yaml_escape(post.get("title", ""))
    lines.append(f'title: "{title}"')

    description = yaml_escape(post.get("description", ""))
    lines.append(f'description: "{description}"')

    pub_date = post.get("pubDate", "")
    lines.append(f"pubDate: {pub_date}")

    tags = post.get("tags", [])
    tags_str = json.dumps(tags, ensure_ascii=False)
    lines.append(f"tags: {tags_str}")

    slug = yaml_escape(post.get("slug", ""))
    lines.append(f'slug: "{slug}"')

    lines.append("---")
    return "\n".join(lines)


def render_post(input_path: Path, output_path: Path) -> None:
    """Render post.json to post.md.

    Args:
        input_path: Path to post.json
        output_path: Path to write post.md
    """
    with open(input_path, encoding="utf-8") as f:
        post = json.load(f)

    sections = [render_frontmatter(post)]

    title = post.get("title", "")
    if title:
        sections.append(f"# {title}")

    categories = post.get("categories", [])
    global_index = 1
    for category in categories:
        rendered_cat, global_index = render_category_section(category, start_index=global_index)
        sections.append(rendered_cat)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(sections).rstrip() + "\n")

    print(f"[render_md] Wrote {output_path}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render post.json to post.md")
    parser.add_argument("--input", type=Path, required=True, help="Path to post.json")
    parser.add_argument("--output", type=Path, required=True, help="Path to write post.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.output.expanduser().parent
    append_run_log(
        skill="x-news-to-daily-post",
        script="render_md.py",
        event="step_start",
        message="starting render_md",
        meta={"input": args.input, "output": args.output},
        daily_dir=daily_dir,
    )

    if not args.input.exists():
        append_run_log(
            skill="x-news-to-daily-post",
            script="render_md.py",
            event="step_failed",
            status="error",
            message="post.json not found",
            meta={"input": args.input},
            daily_dir=daily_dir,
        )
        print(f"Error: post.json not found: {args.input}", file=sys.stderr)
        return 1

    render_post(args.input, args.output)
    append_run_log(
        skill="x-news-to-daily-post",
        script="render_md.py",
        event="write_output",
        message="wrote post.md",
        meta={"input": args.input, "output": args.output},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-to-daily-post",
        script="render_md.py",
        event="step_complete",
        message="finished render_md",
        meta={"output": args.output},
        daily_dir=daily_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
