#!/usr/bin/env python3
"""
Render post.json to post.md.

Usage:
    python3 render_md.py --input <path> --output <path>
"""

import argparse
import json
import sys
from pathlib import Path


def split_paragraphs(body: str) -> list[str]:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def render_media(item: dict) -> list[str]:
    lines = []
    title = item.get("title", "配图")
    for f in item.get("media", []):
        if f.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
            lines.append(f"![{title}]({f})")
        elif f.endswith((".mp4", ".mov", ".webm")):
            lines.append(f'<video src="{f}" controls></video>')
    return lines


def render_links(item: dict) -> list[str]:
    rendered = []
    primary = (item.get("link") or "").strip()
    if primary:
        rendered.append(f"- 原文：{primary}")
    for rel in item.get("related_links", []):
        if isinstance(rel, dict):
            text = (rel.get("text") or rel.get("url") or "").strip()
            url = (rel.get("url") or "").strip()
        else:
            text = url = str(rel).strip()
        if not url:
            continue
        rendered.append(f"- {text}：{url}" if text and text != url else f"- {url}")
    return ["相关链接：", *rendered] if rendered else []


def render_item(item: dict, index: int) -> str:
    title = " ".join((item.get("title") or "无标题").split())
    link = (item.get("link") or "").strip()
    heading = f"### [{title}]({link})" if link else f"### {title}"
    heading += f" `#{index}`"

    sections = [heading]
    paragraphs = split_paragraphs(item.get("body", ""))
    if paragraphs:
        sections.append("\n\n".join(paragraphs))
    media = render_media(item)
    if media:
        sections.append("\n".join(media))
    links = render_links(item)
    if links:
        sections.append("\n".join(links))
    return "\n\n".join(sections)


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def render_frontmatter(post: dict) -> str:
    category_names = [c["name"] for c in post.get("categories", []) if c.get("name")]
    if category_names:
        description = "每日 AI 领域精选资讯：" + "、".join(category_names)
    else:
        description = post.get("description", "每日 AI 领域精选资讯")
    lines = ["---"]
    lines.append(f'title: "{yaml_escape(post.get("title", ""))}"')
    lines.append(f'description: "{yaml_escape(description)}"')
    lines.append(f"pubDate: {post.get('pubDate', '')}")
    lines.append(f"tags: {json.dumps(post.get('tags', []), ensure_ascii=False)}")
    lines.append(f'slug: "{yaml_escape(post.get("slug", ""))}"')
    lines.append("---")
    return "\n".join(lines)


def render_post(input_path: Path, output_path: Path) -> None:
    with open(input_path, encoding="utf-8") as f:
        post = json.load(f)

    sections = [render_frontmatter(post)]
    title = post.get("title", "")
    if title:
        sections.append(f"# {title}")

    idx = 1
    for cat in post.get("categories", []):
        cat_lines = [f"## {cat.get('name', '未分类')}"]
        for item in cat.get("items", []):
            cat_lines.append(render_item(item, idx))
            idx += 1
        sections.append("\n\n".join(cat_lines))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(sections).rstrip() + "\n")
    print(f"[render_md] Wrote {output_path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render post.json to post.md")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        return 1

    render_post(args.input, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
