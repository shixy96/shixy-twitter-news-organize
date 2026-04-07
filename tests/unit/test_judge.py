#!/usr/bin/env python3
"""Unit tests for improve/judge.py."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root / "improve"))

from judge import DIMENSIONS, _validate_judge_output, score_digest


class TestValidateJudgeOutput(unittest.TestCase):
    def test_valid_empty_dict(self):
        """Empty dict should be accepted and dimensions filled with zeros."""
        data = {}
        _validate_judge_output(data)
        self.assertIsInstance(data, dict)
        self.assertEqual(len(data["scores"]), 7)  # all DIMENSIONS filled
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["major_issues"], [])

    def test_valid_full_dict(self):
        """Full valid dict should pass through with totals computed."""
        data = {
            "scores": {
                "selection_relevance": {"score": 8, "reason": "good"},
                "selection_dedup": {"score": 7, "reason": "ok"},
                "title_quality": {"score": 9, "reason": "great"},
                "body_quality": {"score": 6, "reason": "fair"},
                "link_quality": {"score": 8, "reason": "good"},
                "editorial_judgment": {"score": 7, "reason": "ok"},
                "overall_coherence": {"score": 9, "reason": "great"},
            },
            "major_issues": [],
        }
        _validate_judge_output(data)
        self.assertEqual(data["total"], 54)
        for dim in data["scores"]:
            self.assertIn("score", data["scores"][dim])
            self.assertIn("reason", data["scores"][dim])

    def test_non_dict_list_raises(self):
        """Non-dict input should raise AttributeError."""
        with self.assertRaises(AttributeError) as ctx:
            _validate_judge_output([])
        self.assertIn("expected dict", str(ctx.exception))

    def test_non_dict_string_raises(self):
        """String input should raise AttributeError."""
        with self.assertRaises(AttributeError) as ctx:
            _validate_judge_output("string")
        self.assertIn("expected dict", str(ctx.exception))

    def test_non_dict_int_raises(self):
        """Integer input should raise AttributeError."""
        with self.assertRaises(AttributeError) as ctx:
            _validate_judge_output(42)
        self.assertIn("expected dict", str(ctx.exception))

    def test_scores_list_coerced_to_empty(self):
        """scores as list should be treated as empty dict, not crash."""
        data = {"scores": []}
        _validate_judge_output(data)
        # scores should be replaced with empty dict, then filled with DIMENSIONS
        self.assertEqual(len(data["scores"]), 7)
        self.assertEqual(data["total"], 0)

    @patch("subprocess.run")
    def test_score_digest_file_not_found_returns_zero(self, mock_run):
        """FileNotFoundError from missing claude binary should return zero-score fallback."""
        from judge import score_digest

        mock_run.side_effect = FileNotFoundError("claude not found")
        result = score_digest("[]", "{}")
        self.assertEqual(result["total"], 0)
        self.assertIn("major_issues", result)
        # Should contain error info about the failure
        error_text = " ".join(str(e) for e in result["major_issues"]).lower()
        self.assertTrue(
            "judge failed" in error_text or "not found" in error_text,
            f"Expected 'judge failed' or 'not found' in major_issues, got: {result['major_issues']}",
        )

    def test_scores_string_coerced_to_empty(self):
        """scores as string should be treated as empty dict."""
        data = {"scores": "invalid"}
        _validate_judge_output(data)
        self.assertEqual(len(data["scores"]), 7)
        self.assertEqual(data["total"], 0)

    def test_missing_scores_dimensions_filled(self):
        """Missing dimension scores should be filled with zeros."""
        data = {"scores": {}}
        _validate_judge_output(data)
        for dim in DIMENSIONS:
            self.assertIn(dim, data["scores"])
            self.assertEqual(data["scores"][dim]["score"], 0)
            self.assertEqual(data["scores"][dim]["reason"], "missing")

    def test_invalid_score_types_fixed(self):
        """Non-numeric scores should be converted to 0."""
        data = {
            "scores": {
                "selection_relevance": {"score": "bad", "reason": "invalid"},
                "selection_dedup": {"score": None, "reason": "null"},
                "title_quality": {"score": 5.5, "reason": "float ok"},
                "body_quality": {"score": -10, "reason": "negative clamped"},
                "link_quality": {"score": 15, "reason": "over max clamped"},
                "editorial_judgment": {"score": 0, "reason": "zero ok"},
                "overall_coherence": {"score": 10, "reason": "max ok"},
            },
        }
        _validate_judge_output(data)
        self.assertEqual(data["scores"]["selection_relevance"]["score"], 0)
        self.assertEqual(data["scores"]["selection_dedup"]["score"], 0)
        self.assertEqual(data["scores"]["title_quality"]["score"], 5)
        self.assertEqual(data["scores"]["body_quality"]["score"], 0)
        self.assertEqual(data["scores"]["link_quality"]["score"], 10)
        self.assertEqual(data["scores"]["editorial_judgment"]["score"], 0)
        self.assertEqual(data["scores"]["overall_coherence"]["score"], 10)


if __name__ == "__main__":
    unittest.main()
