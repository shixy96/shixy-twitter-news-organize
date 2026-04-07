#!/usr/bin/env python3
"""Unit tests for skills/x-news-digest/scripts/render_md.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root / "skills/x-news-digest/scripts"))

from render_md import (
    render_frontmatter,
    render_item,
    render_links,
    render_media,
    render_post,
    split_paragraphs,
    yaml_escape,
)


class TestSplitParagraphs(unittest.TestCase):
    def test_basic(self):
        result = split_paragraphs("para1\n\npara2\n\npara3")
        self.assertEqual(result, ["para1", "para2", "para3"])

    def test_empty_paragraphs_removed(self):
        result = split_paragraphs("para1\n\n\n\npara2")
        self.assertEqual(result, ["para1", "para2"])

    def test_whitespace_stripped(self):
        result = split_paragraphs("  para1  \n\n  para2  ")
        self.assertEqual(result, ["para1", "para2"])

    def test_empty_string(self):
        result = split_paragraphs("")
        self.assertEqual(result, [])

    def test_single_paragraph(self):
        result = split_paragraphs("single")
        self.assertEqual(result, ["single"])


class TestYamlEscape(unittest.TestCase):
    def test_backslash(self):
        result = yaml_escape("path\\to\\file")
        self.assertEqual(result, "path\\\\to\\\\file")

    def test_double_quote(self):
        result = yaml_escape('say "hello"')
        self.assertEqual(result, 'say \\"hello\\"')

    def test_newline(self):
        result = yaml_escape("line1\nline2")
        self.assertEqual(result, "line1\\nline2")

    def test_carriage_return(self):
        result = yaml_escape("line1\rline2")
        self.assertEqual(result, "line1\\rline2")

    def test_mixed(self):
        # Input string with backslash-quote-backslash-quote pairs: path\"to\"file
        # yaml_escape replaces \ with \\ and " with \" sequentially
        # So: path\"to\"file -> path\\"to\\"file (doubles backslashes) -> path\\\"to\\\"file (escapes quotes)
        # The output has \\ (escaped backslash) and \" (escaped quote) for each original
        result = yaml_escape('path\\"to\\"file')
        self.assertEqual(result, 'path\\\\\\"to\\\\\\"file')


class TestRenderMedia(unittest.TestCase):
    def test_image(self):
        item = {"title": "测试图片", "media": ["https://example.com/image.jpg"]}
        result = render_media(item)
        self.assertEqual(result, ["![测试图片](https://example.com/image.jpg)"])

    def test_video(self):
        item = {"media": ["https://example.com/video.mp4"]}
        result = render_media(item)
        self.assertEqual(result, ['<video src="https://example.com/video.mp4" controls></video>'])

    def test_multiple_media(self):
        item = {
            "title": "多图",
            "media": ["https://example.com/1.jpg", "https://example.com/2.png"],
        }
        result = render_media(item)
        self.assertEqual(len(result), 2)

    def test_unsupported_format(self):
        item = {"media": ["https://example.com/file.txt"]}
        result = render_media(item)
        self.assertEqual(result, [])

    def test_empty_media(self):
        item = {}
        result = render_media(item)
        self.assertEqual(result, [])


class TestRenderLinks(unittest.TestCase):
    def test_primary_link(self):
        item = {"link": "https://example.com/article"}
        result = render_links(item)
        self.assertIn("- 原文：https://example.com/article", result)

    def test_related_links(self):
        item = {
            "link": "https://example.com/article",
            "related_links": [{"text": "相关项目", "url": "https://example.com/project"}],
        }
        result = render_links(item)
        self.assertIn("相关链接：", result)
        self.assertIn("- 相关项目：https://example.com/project", result)

    def test_related_links_string(self):
        item = {"related_links": ["https://example.com/1", "https://example.com/2"]}
        result = render_links(item)
        self.assertEqual(len(result), 3)  # header + 2 links

    def test_empty_links(self):
        item = {}
        result = render_links(item)
        self.assertEqual(result, [])

    def test_related_same_as_url(self):
        item = {"related_links": [{"url": "https://example.com/same"}]}
        result = render_links(item)
        self.assertIn("- https://example.com/same", result)


class TestRenderItem(unittest.TestCase):
    def test_with_link(self):
        item = {
            "title": "测试标题",
            "link": "https://x.com/test/1",
            "body": "第一段\n\n第二段",
        }
        result = render_item(item, 1)
        self.assertIn("### [测试标题](https://x.com/test/1)", result)
        self.assertIn("#1", result)
        self.assertIn("第一段", result)

    def test_without_link(self):
        item = {"title": "无链接标题", "body": "正文内容"}
        result = render_item(item, 2)
        self.assertIn("### 无链接标题", result)
        self.assertIn("#2", result)

    def test_no_body(self):
        item = {"title": "标题"}
        result = render_item(item, 1)
        self.assertIn("### 标题", result)

    def test_with_media(self):
        item = {
            "title": "标题",
            "link": "https://x.com/test/1",
            "body": "正文",
            "media": ["https://example.com/img.jpg"],
        }
        result = render_item(item, 1)
        self.assertIn("![标题](https://example.com/img.jpg)", result)

    def test_with_related_links(self):
        item = {
            "title": "标题",
            "link": "https://x.com/test/1",
            "body": "正文",
            "related_links": [{"text": "链接", "url": "https://example.com"}],
        }
        result = render_item(item, 1)
        self.assertIn("相关链接", result)


class TestRenderFrontmatter(unittest.TestCase):
    def test_basic(self):
        post = {
            "title": "AI 资讯日报",
            "description": "每日精选",
            "pubDate": "2026-04-06",
            "tags": ["AI", "新闻"],
            "slug": "ai-news",
        }
        result = render_frontmatter(post)
        self.assertIn('title: "AI 资讯日报"', result)
        self.assertIn("pubDate: 2026-04-06", result)
        self.assertIn('slug: "ai-news"', result)

    def test_categories_description(self):
        post = {
            "title": "日报",
            "categories": [{"name": "模型发布"}, {"name": "开发生态"}],
            "pubDate": "2026-04-06",
            "tags": [],
            "slug": "test",
        }
        result = render_frontmatter(post)
        self.assertIn("模型发布", result)
        self.assertIn("开发生态", result)


class TestRenderPost(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        fixture_path = Path(__file__).resolve().parent.parent / "fixtures/render/post.json"
        with open(fixture_path, encoding="utf-8") as f:
            self.post_data = json.load(f)
        self.input_path = Path(self.temp_dir) / "post.json"
        with open(self.input_path, "w", encoding="utf-8") as f:
            json.dump(self.post_data, f)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_render_post(self):
        output_path = Path(self.temp_dir) / "output.md"
        render_post(self.input_path, output_path)
        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("---", content)
        self.assertIn("# AI 资讯日报 2026-04-06", content)
        self.assertIn("模型发布", content)


if __name__ == "__main__":
    unittest.main()
