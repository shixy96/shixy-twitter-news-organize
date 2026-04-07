#!/usr/bin/env python3
"""Unit tests for improve/loop.py."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root / "improve"))


class TestGitCommitRules(unittest.TestCase):
    @patch("subprocess.run")
    def test_git_commit_rules_no_diff(self, mock_run):
        """git commit should be skipped when editorial-rules.md has no changes."""
        from loop import _git_commit_rules

        # Simulate: git add succeeds, git diff --staged returns empty (no changes)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git add
            MagicMock(returncode=0, stdout="", stderr=""),  # git diff --staged (empty)
        ]

        result = _git_commit_rules("test: no change")

        # commit should not be called
        commit_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "git" and c[0][0][1] == "commit"
        ]
        self.assertEqual(len(commit_calls), 0)
        self.assertEqual(result, "no-change")

    @patch("subprocess.run")
    def test_git_commit_rules_with_diff(self, mock_run):
        """git commit should run when there are staged changes."""
        from loop import _git_commit_rules

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # git add
            MagicMock(
                returncode=0, stdout="1 file changed, 10 insertions(+)", stderr=""
            ),  # git diff --staged
            MagicMock(returncode=0, stdout="", stderr=""),  # git commit
            MagicMock(returncode=0, stdout="abc1234\n", stderr=""),  # git rev-parse
        ]

        result = _git_commit_rules("test: with change")

        # commit should be called once
        commit_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "git" and c[0][0][1] == "commit"
        ]
        self.assertEqual(len(commit_calls), 1)
        self.assertEqual(result, "abc1234")

    def test_pareto_improved_false_when_scores_equal(self):
        """_pareto_improved should return False when new_scores == best_scores."""
        from loop import _pareto_improved

        best = {"2026-04-06": 50}
        equal = {"2026-04-06": 50}
        self.assertFalse(_pareto_improved(equal, best))

    def test_no_judge_score_when_structurally_failed(self):
        """Structurally failed runs (FAIL status) should not contribute editorial points.

        Bug: FAIL runs still feed post.json into score_digest and add editorial points,
        which can inflate scores and corrupt Pareto comparisons.
        The loop should set e_score=0 when status==FAIL, so composite=0.
        """
        from loop import composite_score, structural_score

        # FAIL status → structural score = 0
        fail_metrics = {"status": "FAIL", "errors": ["missing title"]}
        s = structural_score(fail_metrics)
        self.assertEqual(s, 0)

        # FAIL run: e_score should be 0, so composite = 0
        self.assertEqual(composite_score(s, 0), 0)

    @patch("loop.run_single")
    def test_exception_feedback_included_in_judge_feedback(self, mock_run):
        """Exception-run feedback should be included in all_judge_feedback."""
        import loop as loop_module
        import tempfile
        import shutil

        old_eval_dir = loop_module.EVAL_DIR
        old_exp_log = loop_module.EXPERIMENTS_LOG

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        exp_log = tmpdir / "experiments.jsonl"
        exp_log.touch()

        loop_module.EVAL_DIR = tmpdir
        loop_module.EXPERIMENTS_LOG = exp_log
        mock_run.side_effect = RuntimeError("crash")

        with patch.object(loop_module, "propose_change", MagicMock(return_value="# unchanged")):
            result = loop_module.evaluate_candidate(
                dates=["2026-04-06"],
                runs_per_iter=1,
                digest_model="sonnet",
                judge_model="opus",
            )

        feedback = result["judge_feedback"]
        self.assertEqual(len(feedback), 1)
        self.assertTrue(any("crash" in "".join(f.get("major_issues", [])) for f in feedback))

        loop_module.EVAL_DIR = old_eval_dir
        loop_module.EXPERIMENTS_LOG = old_exp_log
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    unittest.main()
