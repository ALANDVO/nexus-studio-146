#!/usr/bin/env python3
# Skeleton for run_eval.py fix: isolate each query in its own temp directory.
# TODO: implement run_single_query with isolation.

import json
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor


def run_single_query(query_idx, skill_name, description, should_trigger, num_workers):
    """Run a single eval query with isolation in a temp directory."""
    # Create an isolated temporary project directory
    iso_root = Path(tempfile.mkdtemp(prefix="trigeval-"))
    try:
        project_commands_dir = iso_root / ".claude" / "commands"
        project_commands_dir.mkdir(parents=True, exist_ok=True)

        # Build command file content
        clean_name = f"{skill_name}-skill-{query_idx}"
        command_file = project_commands_dir / f"{clean_name}.md"
        command_file.write_text(f"# Skill: {skill_name}\n\nDescription: {description}\n\n## Auto-generated for evaluation\n")

        # Build environment pointing to the isolated commands dir
        env = dict(__import__("os").environ)

        # Run claude -p with the isolated project
        import subprocess
        result = subprocess.run(
            ["claude", "-p", description],
            cwd=str(iso_root),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        # Check if the skill was triggered by searching output for the clean_name
        triggered = clean_name in result.stdout or clean_name in result.stderr

        return {
            "query_idx": query_idx,
            "skill_name": skill_name,
            "description": description,
            "should_trigger": should_trigger,
            "triggered": triggered,
            "output_snippet": result.stdout[-200:] if result.stdout else "",
        }
    finally:
        shutil.rmtree(iso_root, ignore_errors=True)


def run_eval(skill_name, descriptions, should_trigger_list=None, num_workers=4):
    """Run eval with isolated temp directories per query."""
    if should_trigger_list is None:
        should_trigger_list = [True] * len(descriptions)

    positives = []
    negatives = []
    results = []

    for idx, (desc, should_trigger) in enumerate(zip(descriptions, should_trigger_list)):
        if should_trigger:
            positives.append(idx)
        else:
            negatives.append(idx)

    # Run queries in parallel with isolation
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for idx, (desc, should_trigger) in enumerate(zip(descriptions, should_trigger_list)):
            future = executor.submit(
                run_single_query, idx, skill_name, desc, should_trigger, num_workers
            )
            futures.append(future)

        for future in futures:
            result = future.result()
            results.append(result)
            if result["should_trigger"] and result["triggered"]:
                pass  # correct positive
            elif not result["should_trigger"] and not result["triggered"]:
                pass  # correct negative
            elif result["should_trigger"] and not result["triggered"]:
                pass  # false negative (should trigger but didn't)
            elif not result["should_trigger"] and result["triggered"]:
                pass  # false positive (triggered when shouldn't)

    triggered_count = sum(1 for r in results if r["should_trigger"] and r["triggered"])

    return {
        "skill_name": skill_name,
        "total_queries": len(results),
        "triggered_count": triggered_count,
        "results": results,
    }


if __name__ == "__main__":
    # Example usage
    skill_name = "test-skill"
    descriptions = [
        "I need to use the skill right now",
        "Can you help me with this task?",
        "Run the skill please",
    ]
    should_trigger_list = [True, False, True]

    result = run_eval(skill_name, descriptions, should_trigger_list, num_workers=4)
    print(json.dumps(result, indent=2))
