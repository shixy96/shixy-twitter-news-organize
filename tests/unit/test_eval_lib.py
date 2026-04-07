#!/usr/bin/env python3
"""Unit tests for eval/eval_lib.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root))

from eval.eval_lib import (
    ALLOWED_CATEGORIES,
    _mean,
    _std,
    build_benchmark,
    contains_cjk,
    evaluate_digest,
    pairwise_jaccard,
)


class TestContainsCjk(unittest.TestCase):
    def test_chinese(self):
        self.assertTrue(contains_cjk("你好世界"))

    def test_english(self):
        self.assertFalse(contains_cjk("hello world"))

    def test_mixed(self):
        self.assertTrue(contains_cjk("hello你好world"))

    def test_empty(self):
        self.assertFalse(contains_cjk(""))

    def test_none_input(self):
        self.assertFalse(contains_cjk(None))

    def test_japanese(self):
        self.assertTrue(contains_cjk("日本語"))

    def test_korean(self):
        # Korean Hangul is not in the CJK Unified Ideographs range (U+4E00-U+9FFF)
        self.assertFalse(contains_cjk("한글"))


class TestPairwiseJaccard(unittest.TestCase):
    def test_identical_sets(self):
        result = pairwise_jaccard([{"a", "b"}, {"a", "b"}])
        self.assertAlmostEqual(result, 1.0)

    def test_disjoint_sets(self):
        result = pairwise_jaccard([{"a"}, {"b"}])
        self.assertAlmostEqual(result, 0.0)

    def test_partial_overlap(self):
        result = pairwise_jaccard([{"a", "b"}, {"b", "c"}])
        self.assertAlmostEqual(result, 1.0 / 3.0)

    def test_single_set(self):
        self.assertIsNone(pairwise_jaccard([{"a"}]))

    def test_empty_list(self):
        self.assertIsNone(pairwise_jaccard([]))

    def test_three_sets(self):
        result = pairwise_jaccard([{"a", "b"}, {"b", "c"}, {"c", "d"}])
        # pairs: (ab,bc)=1/3, (ab,cd)=0, (bc,cd)=1/3
        expected = (1.0 / 3.0 + 0.0 + 1.0 / 3.0) / 3.0
        self.assertAlmostEqual(result, expected)


class TestMeanStd(unittest.TestCase):
    def test_mean_basic(self):
        self.assertAlmostEqual(_mean([1.0, 2.0, 3.0]), 2.0)

    def test_mean_single(self):
        self.assertAlmostEqual(_mean([42.0]), 42.0)

    def test_mean_empty(self):
        self.assertAlmostEqual(_mean([]), 0.0)

    def test_std_basic(self):
        # Sample std dev using n-1 denominator (Bessel's correction)
        result = _std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        self.assertAlmostEqual(result, 2.138, places=3)

    def test_std_single(self):
        self.assertEqual(_std([42.0]), 0.0)

    def test_std_empty(self):
        self.assertEqual(_std([]), 0.0)


class TestEvaluateDigest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.artifacts_dir = Path(self.temp_dir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def _write_post(self, post_data):
        post_path = self.artifacts_dir / "post.json"
        with open(post_path, "w", encoding="utf-8") as f:
            json.dump(post_data, f, ensure_ascii=False, indent=2)
        return post_path

    def _valid_post(self):
        return {
            "title": "AI 资讯日报",
            "description": "每日 AI 领域精选资讯",
            "pubDate": "2026-04-06",
            "tags": ["AI"],
            "slug": "ai-news-2026-04-06",
            "categories": [
                {
                    "name": "模型发布",
                    "items": [
                        {
                            "canonical_id": "id-001",
                            "title": "测试标题",
                            "link": "https://x.com/test/1",
                            "body": "这是测试正文内容，包含足够长的中文文本以满足长度要求。本测试数据用于验证评估函数的各项检查逻辑是否正常工作，确保能够正确识别和处理各种边界情况。".ljust(
                                100
                            ),
                        }
                    ],
                }
            ],
        }

    def test_missing_post_json(self):
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("post.json missing", result["errors"])

    def test_invalid_json(self):
        post_path = self.artifacts_dir / "post.json"
        post_path.write_text("not json", encoding="utf-8")
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("invalid JSON" in e for e in result["errors"]))

    def test_not_object(self):
        post_path = self.artifacts_dir / "post.json"
        post_path.write_text("[1,2,3]", encoding="utf-8")
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("not an object", result["errors"])

    def test_missing_frontmatter_field(self):
        post = self._valid_post()
        del post["title"]
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing 'title'", result["errors"])

    def test_invalid_category(self):
        post = self._valid_post()
        post["categories"][0]["name"] = "非法分类"
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("invalid category: 非法分类", result["errors"])

    def test_title_not_chinese(self):
        post = self._valid_post()
        post["categories"][0]["items"][0]["title"] = "English Only"
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        issues = result["item_checks"][0]["issues"]
        self.assertIn("title_not_chinese", issues)

    def test_title_too_long(self):
        post = self._valid_post()
        post["categories"][0]["items"][0]["title"] = "这" * 55  # exceeds 50 char limit
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "WARN")
        issues = result["item_checks"][0]["issues"]
        self.assertIn("title_too_long", issues)

    def test_body_too_short(self):
        post = self._valid_post()
        post["categories"][0]["items"][0]["body"] = "短"
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "WARN")
        issues = result["item_checks"][0]["issues"]
        self.assertIn("body_too_short", issues)

    def test_has_placeholder(self):
        post = self._valid_post()
        post["categories"][0]["items"][0]["body"] = "TODO: 待补充内容，需要填写完整信息。"
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        issues = result["item_checks"][0]["issues"]
        self.assertIn("has_placeholder", issues)

    def test_fail_preserved_over_item_warn(self):
        """Frontmatter FAIL should not be downgraded by item-level WARN issues."""
        post = self._valid_post()
        del post["title"]  # causes frontmatter FAIL
        post["categories"][0]["items"][0]["title"] = "x" * 55  # only WARN-level issue
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing 'title'", result["errors"])

    def test_missing_canonical_id_flagged(self):
        """Item without canonical_id should be flagged and NOT use index as stable ID."""
        post = self._valid_post()
        # Remove canonical_id but keep index (the problematic fallback)
        del post["categories"][0]["items"][0]["canonical_id"]
        post["categories"][0]["items"][0]["index"] = 0
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        # Missing canonical_id should be a FAIL-level issue
        issues = result["item_checks"][0]["issues"]
        self.assertIn("missing_canonical_id", issues)
        # selected_ids should NOT contain the numeric index as a pseudo-stable ID
        self.assertNotIn("0", result["selected_ids"])

    def test_missing_canonical_id_no_aliasing(self):
        """Multiple items missing canonical_id should not collapse to same ID."""
        post = self._valid_post()
        # Add a second item also missing canonical_id
        post["categories"][0]["items"].append(
            {
                "title": "第二个标题",
                "body": "这是第二个测试正文内容，需要足够长才能通过长度检查。本测试验证多个缺失 canonical_id 的项不会相互混淆。".ljust(
                    100
                ),
                "link": "https://x.com/test/2",
            }
        )
        del post["categories"][0]["items"][0]["canonical_id"]
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        # Each missing canonical_id should produce distinct placeholder IDs
        selected = result["selected_ids"]
        self.assertEqual(len(selected), 2)
        # They should be distinct (not both "missing-0")
        self.assertNotEqual(selected[0], selected[1])

    def test_string_category_item_handled(self):
        """String items in categories (malformed JSON) should not cause AttributeError."""
        post = self._valid_post()
        post["categories"][0]["items"] = ["not a dict"]
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        # Should return FAIL, not raise AttributeError
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["item_checks"][0]["issues"], ["item_not_dict"])

    def test_categories_null_does_not_raise(self):
        """Null categories should be treated as empty list, not raise TypeError."""
        post = self._valid_post()
        post["categories"] = None
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("missing 'categories'", result["errors"])

    def test_items_null_does_not_raise(self):
        """Null items in a category should be treated as empty, not raise TypeError."""
        post = self._valid_post()
        post["categories"][0]["items"] = None
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("items is null" in e for e in result["errors"]))

    def test_non_string_title_does_not_raise(self):
        """Non-string title (e.g., number/object) should not raise TypeError."""
        post = self._valid_post()
        post["categories"][0]["items"][0]["title"] = 12345  # number instead of string
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any(
                "title_not_string" in str(ic.get("issues", []))
                for ic in result.get("item_checks", [])
            )
        )

    def test_non_string_body_does_not_raise(self):
        """Non-string body should not raise TypeError."""
        post = self._valid_post()
        post["categories"][0]["items"][0]["body"] = {
            "text": "some content"
        }  # object instead of string
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(
            any(
                "body_not_string" in str(ic.get("issues", []))
                for ic in result.get("item_checks", [])
            )
        )

    def test_valid_post(self):
        post = self._valid_post()
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["item_count"], 1)

    def test_item_count_warn_too_few(self):
        post = self._valid_post()
        self._write_post(post)
        result = evaluate_digest(self.artifacts_dir)
        self.assertEqual(result["status"], "PASS")
        self.assertIn("only 1 items", result["warnings"][0])


class TestBuildBenchmark(unittest.TestCase):
    def test_basic(self):
        case = {"id": "test-case", "report_date": "2026-04-06"}
        metrics = [
            {"status": "PASS", "selected_ids": ["a", "b"]},
            {"status": "PASS", "selected_ids": ["a", "b"]},
        ]
        result = build_benchmark("x-news-digest", case, metrics)
        self.assertEqual(result["skill"], "x-news-digest")
        self.assertEqual(result["case_id"], "test-case")
        self.assertEqual(result["runs"], 2)
        self.assertEqual(result["pass_count"], 2)
        self.assertEqual(result["fail_count"], 0)


if __name__ == "__main__":
    unittest.main()
