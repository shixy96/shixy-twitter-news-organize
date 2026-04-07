#!/usr/bin/env python3
"""Unit tests for eval/live_runner.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root / "eval"))
sys.path.insert(0, str(sys_path_root / "skills" / "x-news-digest" / "scripts"))


class TestRunSingleJsonParseFailure(unittest.TestCase):
    @patch("subprocess.run")
    def test_json_parse_failure_writes_metrics(self, mock_run):
        """JSON parse failure should write metrics.json before returning FAIL."""
        from live_runner import run_single

        # Mock subprocess to return non-JSON output
        mock_result = MagicMock()
        mock_result.stdout = "This is not JSON output"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-001"
            filtered_path = Path(tmpdir) / "filtered.json"
            filtered_path.write_text("[]", encoding="utf-8")

            # Mock the file reads for editorial_rules, skill_md, etc.
            with patch.object(Path, "read_text", side_effect=lambda *args, **kwargs: ""):
                with patch("live_runner.EDITORIAL_RULES", Path(tmpdir) / "rules.md"):
                    with patch("live_runner.SKILL_MD", Path(tmpdir) / "skill.md"):
                        Path(tmpdir, "rules.md").write_text("", encoding="utf-8")
                        Path(tmpdir, "skill.md").write_text("", encoding="utf-8")

                        # Mock the evaluation to avoid side effects
                        with patch("live_runner.evaluate_digest") as mock_eval:
                            mock_eval.return_value = {"status": "PASS", "item_count": 1}

                            result = run_single(
                                "2026-04-06",
                                run_dir,
                                filtered_path,
                                "sonnet",
                                False,
                                1,
                            )

            # Should return FAIL
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("JSON parse error", result["errors"][0])

            # metrics.json should be written even on parse failure
            metrics_path = run_dir / "results" / "run-001" / "metrics.json"
            self.assertTrue(
                metrics_path.exists(),
                f"metrics.json not written at {metrics_path}",
            )
            metrics = json.loads(metrics_path.read_text())
            self.assertEqual(metrics["status"], "FAIL")

    def test_nonexistent_filtered_path_returns_error(self):
        """Nonexistent --filtered path should return error, not raise FileNotFoundError."""
        from live_runner import run_live_eval

        result = run_live_eval(
            date="2026-04-06",
            runs=1,
            model="sonnet",
            filtered_path=Path("/nonexistent/path/filtered.json"),
        )

        self.assertIn("error", result)
        self.assertIn("filtered", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
