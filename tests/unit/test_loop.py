#!/usr/bin/env python3
"""Unit tests for improve/loop.py."""

import subprocess
import sys
import unittest
import json
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

    @patch("loop.score_digest")
    @patch("loop.run_single")
    def test_no_judge_score_when_structurally_failed(self, mock_run_single, mock_score_digest):
        """score_digest must NOT be called when run_single returns status==FAIL.

        Bug: FAIL runs still feed post.json into score_digest and add editorial points,
        which can inflate scores and corrupt Pareto comparisons.
        The loop should set e_score=0 when status==FAIL, so composite=0.
        """
        import loop as loop_module
        import tempfile
        import shutil

        old_eval_dir = loop_module.EVAL_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        loop_module.EVAL_DIR = tmpdir

        mock_run_single.return_value = {"status": "FAIL", "errors": ["missing title"]}

        result = loop_module.evaluate_candidate(
            dates=["2026-04-06"],
            runs_per_iter=1,
            digest_model="sonnet",
            judge_model="opus",
            runs_dir=tmpdir / "runs",
        )

        mock_score_digest.assert_not_called()
        self.assertTrue(result["any_fail"])
        self.assertEqual(result["scores_by_date"]["2026-04-06"], 0)
        self.assertEqual(result["fail_count"], 1)
        self.assertEqual(result["fail_reasons"], ["missing title"])

        loop_module.EVAL_DIR = old_eval_dir
        shutil.rmtree(tmpdir)

    @patch("loop.score_digest")
    @patch("loop.run_single")
    def test_run_scores_by_date_includes_per_run_scores(self, mock_run_single, mock_score_digest):
        """Per-run structural/editorial/composite scores should be returned for logging."""
        import loop as loop_module
        import tempfile
        import shutil

        old_eval_dir = loop_module.EVAL_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        loop_module.EVAL_DIR = tmpdir

        mock_run_single.return_value = {"status": "PASS"}
        mock_score_digest.return_value = {"total": 55, "scores": {}, "major_issues": []}

        artifacts_dir = tmpdir / "runs" / "2026-04-06" / "iter-000" / "run-001" / "results" / "artifacts"
        artifacts_dir.mkdir(parents=True)
        (artifacts_dir / "post.json").write_text("{}", encoding="utf-8")

        result = loop_module.evaluate_candidate(
            dates=["2026-04-06"],
            runs_per_iter=1,
            digest_model="sonnet",
            judge_model="opus",
            runs_dir=tmpdir / "runs",
        )

        self.assertIn("run_scores_by_date", result)
        self.assertIn("2026-04-06", result["run_scores_by_date"])
        self.assertEqual(
            result["run_scores_by_date"]["2026-04-06"],
            [
                {
                    "run": 1,
                    "status": "PASS",
                    "structural_score": 30,
                    "editorial_score": 55,
                    "composite_score": 85,
                }
            ],
        )

        loop_module.EVAL_DIR = old_eval_dir
        shutil.rmtree(tmpdir)

    @patch("loop._git_discard_rules")
    @patch("loop._git_commit_rules")
    def test_no_change_not_accepted(self, mock_commit, mock_discard):
        """No-change commit_hash should not increment accepted_count.

        Bug: when _git_commit_rules returns 'no-change' (rules unchanged),
        accepted_count is still incremented if _pareto_improved is True (e.g. random
        score variance). This corrupts the accepted/rejected counter.
        """
        import loop as loop_module
        import tempfile
        import shutil
        from unittest.mock import patch as mock_patch

        old_eval_dir = loop_module.EVAL_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        rules_content = "# editorial rules\n"
        rules_file = tmpdir / "editorial-rules.md"
        rules_file.write_text(rules_content, encoding="utf-8")
        experiments_log = tmpdir / "experiments.jsonl"
        runs_root = tmpdir / "tmp_runs"
        loop_module.EVAL_DIR = tmpdir
        loop_module.EDITORIAL_RULES = rules_file

        # Simulate: _git_commit_rules returns "no-change" (rules unchanged)
        mock_commit.return_value = "no-change"

        # evaluate_candidate returns Pareto-improved scores so accept=True is reached,
        # ensuring the no-change guard is what prevents accepted_count from incrementing
        eval_call_count = [0]

        def fake_evaluate(dates, runs, digest, judge, runs_dir, iter_num=0, **_kwargs):
            eval_call_count[0] += 1
            score = 50 if eval_call_count[0] == 1 else 60  # baseline=50, iter=60 → Pareto
            return {
                "scores_by_date": {"2026-04-06": score},
                "judge_feedback": [],
                "any_fail": False,
            }

        with mock_patch.object(
            loop_module, "propose_change", MagicMock(return_value=rules_content)
        ):
            with mock_patch.object(loop_module, "evaluate_candidate", side_effect=fake_evaluate):
                result = loop_module.run_auto_improve(
                    dates=["2026-04-06"],
                    max_iters=1,
                    runs_per_iter=1,
                    digest_model="sonnet",
                    judge_model="opus",
                    proposer_model="opus",
                    experiments_log=experiments_log,
                    runs_root=runs_root,
                )

        # accepted_count must be 0 since no actual change was made
        self.assertEqual(result["accepted"], 0)

        loop_module.EVAL_DIR = old_eval_dir
        loop_module.EDITORIAL_RULES = (
            loop_module.REPO_ROOT / "skills" / "x-news-digest" / "reference" / "editorial-rules.md"
        )
        shutil.rmtree(tmpdir)

    @patch("loop._git_discard_rules")
    @patch("loop._git_commit_rules")
    def test_no_change_accepted_when_pareto_true(self, mock_commit, mock_discard):
        """accepted_count incremented even when commit_hash='no-change' and pareto improved.

        Bug: when _pareto_improved(new_scores, best_scores) is True (score noise) but
        _git_commit_rules returns 'no-change' (rules unchanged), accepted_count is
        STILL incremented. This corrupts the counter and the hill-climbing trajectory.
        """
        import loop as loop_module
        import tempfile
        import shutil
        from unittest.mock import patch as mock_patch

        old_eval_dir = loop_module.EVAL_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        rules_content = "# editorial rules\n"
        rules_file = tmpdir / "editorial-rules.md"
        rules_file.write_text(rules_content, encoding="utf-8")
        experiments_log = tmpdir / "experiments.jsonl"
        runs_root = tmpdir / "tmp_runs"
        loop_module.EVAL_DIR = tmpdir
        loop_module.EDITORIAL_RULES = rules_file

        mock_commit.return_value = "no-change"

        # Track which call is baseline vs iteration to return different scores
        eval_call_count = [0]

        def fake_evaluate(dates, runs, digest, judge, runs_dir, iter_num=0, **_kwargs):
            eval_call_count[0] += 1
            if eval_call_count[0] == 1:
                # baseline: score = 50
                return {
                    "scores_by_date": {"2026-04-06": 50},
                    "judge_feedback": [],
                    "any_fail": False,
                }
            else:
                # iteration: score = 60 > 50 → Pareto-improved, but rules unchanged
                return {
                    "scores_by_date": {"2026-04-06": 60},
                    "judge_feedback": [],
                    "any_fail": False,
                }

        with mock_patch.object(
            loop_module, "propose_change", MagicMock(return_value=rules_content)
        ):
            with mock_patch.object(loop_module, "evaluate_candidate", side_effect=fake_evaluate):
                result = loop_module.run_auto_improve(
                    dates=["2026-04-06"],
                    max_iters=1,
                    runs_per_iter=1,
                    digest_model="sonnet",
                    judge_model="opus",
                    proposer_model="opus",
                    experiments_log=experiments_log,
                    runs_root=runs_root,
                )

        # accepted_count must be 0 — no actual rules change was committed.
        # Bug would set accepted=1 because accept=True (Pareto improved) but
        # commit_hash='no-change' should prevent counting as accepted.
        self.assertEqual(result["accepted"], 0)

        loop_module.EVAL_DIR = old_eval_dir
        loop_module.EDITORIAL_RULES = (
            loop_module.REPO_ROOT / "skills" / "x-news-digest" / "reference" / "editorial-rules.md"
        )
        shutil.rmtree(tmpdir)

    @patch("loop._git_discard_rules")
    @patch("loop._git_commit_rules")
    def test_fail_metadata_logged_to_experiments_jsonl(self, mock_commit, mock_discard):
        """experiments.jsonl should include fail_count and fail_reasons for failed evaluations."""
        import loop as loop_module
        import tempfile
        import shutil
        from unittest.mock import patch as mock_patch

        old_eval_dir = loop_module.EVAL_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        rules_file = tmpdir / "editorial-rules.md"
        rules_file.write_text("# editorial rules\n", encoding="utf-8")
        experiments_log = tmpdir / "experiments.jsonl"
        runs_root = tmpdir / "tmp_runs"
        loop_module.EVAL_DIR = tmpdir
        loop_module.EDITORIAL_RULES = rules_file
        mock_commit.return_value = "no-change"

        eval_call_count = [0]

        def fake_evaluate(dates, runs, digest, judge, runs_dir, iter_num=0, **_kwargs):
            eval_call_count[0] += 1
            if eval_call_count[0] == 1:
                return {
                    "scores_by_date": {"2026-04-06": 50},
                    "judge_feedback": [],
                    "any_fail": False,
                    "fail_count": 0,
                    "fail_reasons": [],
                }
            return {
                "scores_by_date": {"2026-04-06": 0},
                "judge_feedback": [{"major_issues": ["missing title"]}],
                "any_fail": True,
                "fail_count": 1,
                "fail_reasons": ["missing title"],
            }

        with mock_patch.object(
            loop_module, "propose_change", MagicMock(return_value="# editorial rules\n# changed\n")
        ):
            with mock_patch.object(loop_module, "evaluate_candidate", side_effect=fake_evaluate):
                loop_module.run_auto_improve(
                    dates=["2026-04-06"],
                    max_iters=1,
                    runs_per_iter=1,
                    digest_model="sonnet",
                    judge_model="opus",
                    proposer_model="opus",
                    experiments_log=experiments_log,
                    runs_root=runs_root,
                )

        lines = [json.loads(line) for line in experiments_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertIn("run_scores_by_date", lines[0])
        self.assertIn("run_scores_by_date", lines[1])
        self.assertEqual(lines[0]["fail_count"], 0)
        self.assertEqual(lines[0]["fail_reasons"], [])
        self.assertEqual(lines[1]["fail_count"], 1)
        self.assertEqual(lines[1]["fail_reasons"], ["missing title"])
        self.assertTrue(lines[1]["any_fail"])

        loop_module.EVAL_DIR = old_eval_dir
        loop_module.EDITORIAL_RULES = (
            loop_module.REPO_ROOT / "skills" / "x-news-digest" / "reference" / "editorial-rules.md"
        )
        shutil.rmtree(tmpdir)

    @patch("loop._git_discard_rules")
    @patch("loop._git_commit_rules")
    def test_tmp_run_dir_created_with_timestamp(self, mock_commit, mock_discard):
        """tmp_runs/<timestamp>/ directory and experiments.jsonl are created during a session."""
        import loop as loop_module
        import tempfile
        import shutil
        from unittest.mock import patch as mock_patch

        old_eval_dir = loop_module.EVAL_DIR
        old_improve_dir = loop_module.IMPROVE_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        rules_file = tmpdir / "editorial-rules.md"
        rules_file.write_text("# editorial rules\n", encoding="utf-8")
        improve_dir = tmpdir / "improve"
        improve_dir.mkdir()

        loop_module.EVAL_DIR = tmpdir
        loop_module.EDITORIAL_RULES = rules_file
        loop_module.IMPROVE_DIR = improve_dir
        mock_commit.return_value = "no-change"

        fixed_ts = "20260407_120000"

        def fake_evaluate(dates, runs, digest, judge, runs_dir, iter_num=0, **_kwargs):
            return {"scores_by_date": {"2026-04-06": 50}, "judge_feedback": [], "any_fail": False}

        with mock_patch.object(
            loop_module, "propose_change", MagicMock(return_value="# editorial rules\n")
        ):
            with mock_patch.object(loop_module, "evaluate_candidate", side_effect=fake_evaluate):
                with mock_patch("loop.datetime") as mock_dt:
                    mock_dt.now.return_value.strftime.return_value = fixed_ts
                    mock_dt.now.return_value.isoformat.return_value = "2026-04-07T12:00:00"
                    result = loop_module.run_auto_improve(
                        dates=["2026-04-06"],
                        max_iters=1,
                        runs_per_iter=1,
                        digest_model="sonnet",
                        judge_model="opus",
                        proposer_model="opus",
                    )

        expected_runs_dir = improve_dir / "tmp_runs" / fixed_ts
        self.assertTrue(expected_runs_dir.exists(), f"Expected {expected_runs_dir} to exist")
        # experiments.jsonl is now global (improve/experiments.jsonl), not per-run
        expected_log = improve_dir / "experiments.jsonl"
        self.assertTrue(expected_log.exists(), f"Expected {expected_log} to exist")
        # log should have exactly two entries: baseline (iter=0) + one iteration
        lines = [l for l in expected_log.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)

        loop_module.EVAL_DIR = old_eval_dir
        loop_module.IMPROVE_DIR = old_improve_dir
        loop_module.EDITORIAL_RULES = (
            loop_module.REPO_ROOT / "skills" / "x-news-digest" / "reference" / "editorial-rules.md"
        )
        shutil.rmtree(tmpdir)

    @patch("loop.run_single")
    def test_exception_feedback_included_in_judge_feedback(self, mock_run):
        """Exception-run feedback should be included in all_judge_feedback."""
        import loop as loop_module
        import tempfile
        import shutil

        old_eval_dir = loop_module.EVAL_DIR

        tmpdir = Path(tempfile.mkdtemp())
        fixtures_dir = tmpdir / "fixtures" / "2026-04-06"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "filtered.json").write_text("[]", encoding="utf-8")
        runs_dir = tmpdir / "tmp_runs" / "20260407_120000"
        loop_module.EVAL_DIR = tmpdir
        mock_run.side_effect = RuntimeError("crash")

        with patch.object(loop_module, "propose_change", MagicMock(return_value="# unchanged")):
            result = loop_module.evaluate_candidate(
                dates=["2026-04-06"],
                runs_per_iter=1,
                digest_model="sonnet",
                judge_model="opus",
                runs_dir=runs_dir,
            )

        feedback = result["judge_feedback"]
        self.assertEqual(len(feedback), 1)
        self.assertTrue(any("crash" in "".join(f.get("major_issues", [])) for f in feedback))

        loop_module.EVAL_DIR = old_eval_dir
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    unittest.main()
