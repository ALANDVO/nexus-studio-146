import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_eval


class FakeCompleted:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def make_runner(trigger_predicate, recorder=None):
    """Synthetic runner: no network, no external model."""

    def runner(command_text, project_root, timeout=30):
        if recorder is not None:
            recorder.append(str(project_root))
        return FakeCompleted(run_eval.TRIGGER_MARKER if trigger_predicate else "")

    return runner


class SingleQueryTest(unittest.TestCase):
    def test_isolated_project_is_removed(self):
        seen = {}

        def runner(command_text, project_root, timeout=30):
            seen["root"] = str(project_root)
            seen["exists"] = (project_root / ".claude" / "commands").is_dir()
            return FakeCompleted(run_eval.TRIGGER_MARKER)

        result = run_eval.run_single_query(0, "alpha", "do alpha", True, runner)
        self.assertTrue(seen["exists"])
        self.assertFalse(Path(seen["root"]).exists())
        self.assertTrue(result["triggered"])
        self.assertEqual(result["verdict"], "correct")

    def test_command_content_includes_description_and_marker(self):
        content = run_eval.build_command_content("alpha", "do alpha", 3)
        self.assertIn("do alpha", content)
        self.assertIn(run_eval.TRIGGER_MARKER, content)

    def test_negative_query_not_triggered(self):
        result = run_eval.run_single_query(1, "alpha", "ignore", False, make_runner(False))
        self.assertFalse(result["triggered"])
        self.assertEqual(result["verdict"], "correct")


class EvalSummaryTest(unittest.TestCase):
    def test_trigger_rate_and_counters(self):
        descriptions = ["a", "b", "c"]
        should = [True, False, True]
        runner = make_runner(lambda: True)

        summary = run_eval.run_eval("alpha", descriptions, should, num_workers=1, runner=runner)

        self.assertEqual(summary["total_queries"], 3)
        self.assertEqual(summary["triggered_count"], 2)
        self.assertAlmostEqual(summary["trigger_rate"], 1.0)
        self.assertEqual(summary["false_positive_count"], 1)
        self.assertEqual(summary["false_negative_count"], 0)

    def test_results_are_index_aligned(self):
        runner = make_runner(lambda: False)
        summary = run_eval.run_eval("alpha", ["a", "b"], [True, False], num_workers=1, runner=runner)
        self.assertEqual([r["query_idx"] for r in summary["results"]], [0, 1])

    def test_mismatched_should_trigger_list_raises(self):
        with self.assertRaises(run_eval.EvalError):
            run_eval.run_eval("alpha", ["a", "b"], [True], num_workers=1, runner=make_runner(False))

    def test_empty_descriptions_raises(self):
        with self.assertRaises(run_eval.EvalError):
            run_eval.run_eval("alpha", [], num_workers=1, runner=make_runner(False))



    def test_parallel_with_runner_forces_sequential(self):
        """Verify that num_workers > 1 with runner not None forces sequential execution."""
        runner = make_runner(True)

        descriptions = ["desc1", "desc2", "desc3"]
        should_trigger = [True, False, True]

        summary = run_eval.run_eval(
            "test-skill", descriptions, should_trigger, num_workers=4, runner=runner
        )

        self.assertEqual(summary["total_queries"], 3)
        self.assertEqual(summary["triggered_count"], 2)
        self.assertAlmostEqual(summary["trigger_rate"], 1.0)
        self.assertEqual(summary["false_positive_count"], 1)
        self.assertEqual(summary["false_negative_count"], 0)
        self.assertEqual([r["verdict"] for r in summary["results"]], ["correct", "false-positive", "correct"])
if __name__ == "__main__":
    unittest.main()
