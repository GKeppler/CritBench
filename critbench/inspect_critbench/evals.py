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
from collections.abc import Awaitable, Callable
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
from inspect_ai.solver import Solver, TaskState
from inspect_ai.tool import bash

from inspect_critbench.dataset import critbench_dataset
from inspect_critbench.gridnet_range import gridnet_release, gridnet_reset
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
    setup: Solver | None = None,
    cleanup: Callable[[TaskState], Awaitable[None]] | None = None,
) -> Task:
    return Task(
        dataset=critbench_dataset(family, hint=hint),
        # Task.setup, not the head of the solver chain: Inspect documents it as
        # the step that "should not be substituted when another solver is used
        # with the task", i.e. it still runs under `inspect eval --solver ...`.
        # Environment preparation is exactly that -- an agent swapped in from
        # the CLI must not silently inherit the previous sample's range.
        setup=setup,
        solver=react(tools=[bash(timeout=bash_timeout)], submit=_SUBMIT),
        # Runs in a `finally` after solvers AND scorers, cancellation-shielded,
        # so a resource claimed in `setup` is given back on every path -- error,
        # limit and interrupt included.
        cleanup=cleanup,
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
    # 150, measured rather than guessed. The first full-chain run at 80 hit the
    # turn limit at turn 81 with the agent connected to the IED, its data model
    # enumerated, one functional-constraint argument away from the control
    # action -- it scored 0.60 for a chain it had effectively solved. Roughly
    # half its turns went into discovering what the perimeter answers on, which
    # is real work the old flat topology did not charge for. A limit that
    # truncates mid-action measures the budget, not the agent.
    turn_limit: int = 150,
    token_limit: int = 10_000_000,
    # The sample-level time limit covers the WHOLE solver chain, and the first
    # step of every sample is a full range reset -- 7.6 min of the 55.9 min that
    # first run took. 7200 leaves ~110 min of actual agent time at ~36 s/turn
    # measured, which is what 150 turns needs.
    time_limit: int = 7200,
    bash_timeout: int = 300,
    reset_timeout: int = 1800,
) -> Task:
    """The multi-stage IT->OT kill chain on the GridNet substation range.

    ONE task at present. The other five (`*.yaml_old` in tasks/gridnet/) were
    parked in 42e874c: they graded via `tool_evidence` against the agent's own
    tool calls, which the enforced per-sample reset makes redundant and the
    milestone API makes weaker. Re-enable one by renaming it back; the dataset
    loader picks up `*.yaml` and nothing else.

    The range itself is ~56 containers on the host Docker daemon rather than a
    compose file, so Inspect does not *provision* it -- bring it up once:

        gridnet_env/bring_up_host.sh          # up   (idempotent)
        gridnet_env/bring_up_host.sh --down   # down

    but every sample then RE-CREATES it in `Task.setup`, because three of the
    four graded milestones survive a run and would otherwise be scored as the
    next agent's work (see gridnet_range.py). That costs ~10 min per sample and
    is not optional: the reset also asserts the range came back ready and clean,
    and raises rather than letting a sample start from a used one.

    Run with `--max-sandboxes 1`. That is what serialises the samples: the
    sandbox semaphore is held for the whole sample (solvers *and* scorers), and
    Inspect documents that "when a max_sandboxes is applied this effectively
    creates a global max_samples limit that is equal to the max_sandboxes".

    Forgetting it is no longer silent. gridnet_reset claims the range for the
    sample's whole lifetime and gridnet_release (Task.cleanup) hands it back, so
    a second concurrent sample is refused with that instruction instead of
    tearing the range down under the first one's agent. The claim deliberately
    does NOT queue: `time_limit` is wall clock over the entire sample, so a
    sample waiting out its predecessor would reach its agent phase with its
    budget already spent and score low for a reason nothing in the log records.

    `gridnet_full_chain_it_to_ot` grades against the milestone API, read
    host-side -- never the agent's answer text and never a value the agent's own
    tool call could have written.
    """
    script = _CRITBENCH_ROOT / "gridnet_env" / "bring_up_host.sh"
    if not script.exists():
        raise FileNotFoundError(
            f"{script} not found -- gridnet_env is a submodule: "
            "`git submodule update --init`"
        )
    return _critbench_task(
        "gridnet", "gridnet.yaml", "gridnet",
        hint=hint, turn_limit=turn_limit, token_limit=token_limit,
        time_limit=time_limit, bash_timeout=bash_timeout,
        setup=gridnet_reset(str(script), timeout=reset_timeout),
        cleanup=gridnet_release,
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
