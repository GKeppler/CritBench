"""Inspect task entry points for CritBench.

Run from the ``critbench/`` directory::

    inspect eval inspect_critbench/evals.py@critbench_scl       --model openai/gpt-4o
    inspect eval inspect_critbench/evals.py@critbench_pcap      --model openai/gpt-4o
    inspect eval inspect_critbench/evals.py@critbench_iec61850  --model openai/gpt-4o
    inspect eval inspect_critbench/evals.py@critbench_grfics    --model openai/gpt-4o --max-sandboxes 1

Named ``evals.py`` rather than ``tasks.py`` on purpose: ``critbench/`` is on
sys.path, so a top-level module called ``tasks`` would shadow the ``tasks``
package that ``task_schema`` lives in.

One @task per family rather than one combined task: each needs its own compose
file and its own grading source, and GRFICS additionally needs serialising.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `inspect eval` loads this file BY PATH rather than as a member of the
# inspect_critbench package, so __init__.py never runs and relative imports are
# unavailable. Bootstrap sys.path here, before importing anything local, so
# both `inspect_critbench.*` and the top-level `tasks` / `evaluation` packages
# resolve. (`inspect list tasks` only scans source for @task and so does not
# catch this -- the failure appears at eval time.)
_CRITBENCH_ROOT = Path(__file__).resolve().parent.parent
if str(_CRITBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_CRITBENCH_ROOT))

from inspect_ai import Task, task
from inspect_ai.agent import AgentSubmit, react
from inspect_ai.tool import bash

from inspect_critbench.dataset import critbench_dataset
from inspect_critbench.scorer import critbench_scorer

_COMPOSE = Path(__file__).resolve().parent / "compose"

# Tool surface: bash + submit only. Not a reduction -- run_experiments.py
# declares --notools as `default=True, action="store_true"`, so it cannot be
# switched off from the CLI and every run of the original harness is already
# `run_command` + `submit_solution`. The critleayer protocol tools remain
# available for a later port.
#
# answer_only=True makes the graded completion exactly the string passed to
# submit(), matching CritBench's `submit_solution(answer=...)`. Inspect's
# default appends the answer to whatever else the model wrote in that turn,
# which would give every `contains` check extra text to match against and
# silently inflate scores relative to the original harness.
_SUBMIT = AgentSubmit(answer_only=True)


def _critbench_task(
    family: str,
    compose: str,
    state_source: str | None,
    *,
    hint: bool,
    turn_limit: int,
    token_limit: int,
    time_limit: int,
    bash_timeout: int,
) -> Task:
    return Task(
        dataset=critbench_dataset(family, hint=hint),
        solver=react(tools=[bash(timeout=bash_timeout)], submit=_SUBMIT),
        scorer=critbench_scorer(state_source=state_source),
        sandbox=("docker", str(_COMPOSE / compose)),
        # Limits are task-level because Sample carries none, and because the
        # per-task max_turns/token_budget/timeout in the YAMLs are already dead
        # config: _create_sanitised_task_yaml overwrites all three with
        # run-level CLI values before the agent ever sees them.
        turn_limit=turn_limit,
        token_limit=token_limit,
        time_limit=time_limit,
        version=1,
    )


@task
def critbench_scl(
    hint: bool = False,
    turn_limit: int = 50,
    token_limit: int = 1_000_000,
    time_limit: int = 600,
    bash_timeout: int = 180,
) -> Task:
    """30 IEC 61850 SCL/SCD static-analysis tasks. Graded on the answer text."""
    return _critbench_task(
        "scd_tasks", "static.yaml", None,
        hint=hint, turn_limit=turn_limit, token_limit=token_limit,
        time_limit=time_limit, bash_timeout=bash_timeout,
    )


@task
def critbench_pcap(
    hint: bool = False,
    turn_limit: int = 50,
    token_limit: int = 1_000_000,
    time_limit: int = 600,
    bash_timeout: int = 180,
) -> Task:
    """30 packet-capture analysis tasks (GOOSE/MMS/IEC 104). Answer-text graded."""
    return _critbench_task(
        "pcaps_tasks", "static.yaml", None,
        hint=hint, turn_limit=turn_limit, token_limit=token_limit,
        time_limit=time_limit, bash_timeout=bash_timeout,
    )


@task
def critbench_iec61850(
    hint: bool = False,
    turn_limit: int = 50,
    token_limit: int = 1_000_000,
    time_limit: int = 600,
    bash_timeout: int = 180,
) -> Task:
    """18 live IEC 61850 MMS/GOOSE tasks against a real IED server.

    Half carry `state_check` grading: the scorer re-reads /live_state on the
    IED after the agent finishes, so a claimed breaker flip has to have
    actually happened.
    """
    return _critbench_task(
        "vm_tasks", "iec61850.yaml", "iec61850",
        hint=hint, turn_limit=turn_limit, token_limit=token_limit,
        time_limit=time_limit, bash_timeout=bash_timeout,
    )


@task
def critbench_gridnet(
    hint: bool = False,
    turn_limit: int = 80,
    token_limit: int = 10_000_000,
    time_limit: int = 1800,
    bash_timeout: int = 300,
) -> Task:
    """6 multi-stage IT->OT kill-chain tasks on the GridNet substation range.

    REQUIRES AN EXTERNALLY MANAGED ENVIRONMENT. CritBench does not start these
    targets: a nested-KVM guest (see ssh_key_host_path in the task YAMLs) must
    already be up, exposing SSH on host ports 2221-2225 and the milestone API on
    18090. With it down, every sample fails on connection errors.

    Run with `--max-sandboxes 1`: all samples share that one live guest.

    Five of six grade via `tool_evidence` (verified against the agent's real
    tool calls); `gridnet_full_chain_it_to_ot` grades against the guest-side
    milestone API.
    """
    return _critbench_task(
        "gridnet", "gridnet.yaml", "gridnet",
        hint=hint, turn_limit=turn_limit, token_limit=token_limit,
        time_limit=time_limit, bash_timeout=bash_timeout,
    )


@task
def critbench_grfics(
    hint: bool = False,
    turn_limit: int = 50,
    token_limit: int = 1_000_000,
    time_limit: int = 900,
    bash_timeout: int = 180,
) -> Task:
    """5 GRFICSv3 Modbus/OpenPLC process-tampering tasks.

    Run with `--max-sandboxes 1`: the task prompts hardcode 192.168.95.2, so
    the compose file pins that subnet and concurrent samples would collide.
    """
    return _critbench_task(
        "GRFICSv3", "grfics.yaml", "grfics",
        hint=hint, turn_limit=turn_limit, token_limit=token_limit,
        time_limit=time_limit, bash_timeout=bash_timeout,
    )
