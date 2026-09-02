"""Inspect (https://inspect.aisi.org.uk) front-end for CritBench.

Additive: ``run_experiments.py`` and ``agent_runner/ot_agent.py`` remain the
original harness and are untouched. This package re-uses their two pure pieces
-- ``tasks.task_schema`` for loading task YAMLs and ``evaluation.evaluator``
for grading -- and supplies only the glue Inspect needs.

Run from the ``critbench/`` directory::

    inspect eval inspect_critbench/evals.py@critbench_scl --model openai/gpt-4o
"""

from __future__ import annotations

import sys
from pathlib import Path

# The git root is not the package root: `tasks`, `evaluation` and `critleayer`
# are importable as top-level packages only with `critbench/` on sys.path.
# run_experiments.py and ot_agent.py do the same thing for the same reason.
_CRITBENCH_ROOT = Path(__file__).resolve().parent.parent
if str(_CRITBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_CRITBENCH_ROOT))
