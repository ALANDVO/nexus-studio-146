#!/usr/bin/env python3
"""Evaluate how reliably a skill description triggers a skill.

Each query is isolated in its own temporary project directory so that parallel
runs never see a sibling worker's command file. Cross-matching between workers
was the cause of near-zero trigger rates in earlier versions.

The ``claude`` CLI is invoked through an injectable runner so the measurement
logic can be tested without a network round trip or a model.
"""

import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

TRIGGER_MARKER = "SKILL_TRIGGERED"


class EvalError(RuntimeError):
    """Raised when the eval input is invalid."""


def build_command_content(skill_name, description, query_idx):
    """Build the markdown command file handed to the skill loader."""
    return (
        f"# Skill: {skill_name}\n\n"
        f"Description: {description}\n\n"
        "## Auto-generated for evaluation\n\n"
        f"Query: {query_idx}\n\n"
        f"Trigger marker: {TRIGGER_MARKER}\n"
    )


def claude_runner(command_text, project_root, timeout=30):
    """Default runner: invoke the ``claude`` CLI inside ``project_root``."""
    return subprocess.run(
        ["claude", "-p", command_text],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(os.environ),
    )


def parse_output(stdout):
    """Return True when the output shows the skill was invoked."""
    return TRIGGER_MARKER in (stdout or "")


def run_single_query(query_idx, skill_name, description, should_trigger, runner=None):
    """Run one query in a fresh temp project; return a result dict."""
    runner = runner or claude_runner
    iso_root = Path(tempfile.mkdtemp(prefix="trigeval-"))
    try:
        commands_dir = iso_root / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        clean_name = f"{skill_name}-skill-{query_idx}"
        command_file = commands_dir / f"{clean_name}.md"
        command_file.write_text(
            build_command_content(skill_name, description, query_idx), encoding="utf-8"
        )

        completed = runner(description, iso_root)
        stdout = getattr(completed, "stdout", "") or ""
        triggered = parse_output(stdout)

        return {
            "query_idx": query_idx,
            "skill_name": skill_name,
            "description": description,
            "should_trigger": should_trigger,
            "triggered": triggered,
            "expected": "positive" if should_trigger else "negative",
            "verdict": (
                "correct"
                if triggered == should_trigger
                else "false-negative"
                if should_trigger
                else "false-positive"
            ),
            "output_snippet": stdout[-200:],
            "returncode": getattr(completed, "returncode", None),
        }
    finally:
        shutil.rmtree(iso_root, ignore_errors=True)


def run_eval(
    skill_name,
    descriptions,
    should_trigger_list=None,
    num_workers=4,
    runner=None,
):
    """Run all queries, optionally in parallel, and summarize the outcome."""
    if not skill_name:
        raise EvalError("skill_name is required")
    if not descriptions:
        raise EvalError("descriptions must not be empty")
    if should_trigger_list is None:
        should_trigger_list = [True] * len(descriptions)
    if len(should_trigger_list) != len(descriptions):
        raise EvalError("should_trigger_list length must match descriptions")

    num_workers = max(1, min(int(num_workers), len(descriptions)))

    results = [None] * len(descriptions)
    if num_workers == 1 or runner is not None:
        for idx, (desc, should) in enumerate(zip(descriptions, should_trigger_list)):
            results[idx] = run_single_query(idx, skill_name, desc, should, runner)
    else:
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(
                    run_single_query, idx, skill_name, desc, should, None
                ): idx
                for idx, (desc, should) in enumerate(
                    zip(descriptions, should_trigger_list)
                )
            }
            for future, idx in futures.items():
                results[idx] = future.result()

    positives = [r for r in results if r["should_trigger"]]
    negatives = [r for r in results if not r["should_trigger"]]
    triggered_positives = sum(1 for r in positives if r["triggered"])
    triggered_negatives = sum(1 for r in negatives if r["triggered"])

    return {
        "skill_name": skill_name,
        "total_queries": len(results),
        "triggered_count": triggered_positives,
        "trigger_rate": (triggered_positives / len(positives)) if positives else None,
        "false_positive_count": triggered_negatives,
        "false_negative_count": len(positives) - triggered_positives,
        "results": results,
    }


if __name__ == "__main__":
    result = run_eval(
        "test-skill",
        [
            "I need to use the skill right now",
            "Can you help me with this task?",
            "Run the skill please",
        ],
        [True, False, True],
    )
    print(json.dumps(result, indent=2))
