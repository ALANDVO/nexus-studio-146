# Product development plan

Each round completes one feature or repair. Future items are planned, not implemented claims.

## Current round

fix-skill-creator-parallel-eval

## Roadmap

### fix-skill-creator-parallel-eval — Isolate eval queries per temporary project to avoid cross-matching

Status: done

Acceptance:
- Each query command file is isolated in its own temporary directory
- Parallel runs do not interfere; each claude -p invocation sees only its own command

Implementation: `skill-creator/scripts/run_eval.py`

Tests: `python -m py_compile skill-creator/scripts/run_eval.py`

---

Alan Vo · [alanvo.net](https://alanvo.net) · [X: @alanvoasi](https://x.com/alanvoasi)
