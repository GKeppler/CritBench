"""Build Inspect datasets from CritBench task YAMLs."""

from __future__ import annotations

from pathlib import Path

import yaml
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.util import SandboxEnvironmentSpec
from inspect_ai.model import ChatMessageSystem, ChatMessageUser
from jinja2 import Environment, StrictUndefined

from tasks.task_schema import load_task, render_objective, ssh_key_paths, template_vars

# StrictUndefined matches ot_agent.py: an unresolved {{ var }} is a hard error,
# never a silently empty prompt.
_JINJA = Environment(undefined=StrictUndefined)

_TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"
_COMPOSE_DIR = Path(__file__).resolve().parent / "compose"


def critbench_dataset(family: str, hint: bool | str = False) -> MemoryDataset:
    """Load one CritBench task family (a directory under ``tasks/``).

    The YAML path and v2 reporting strata travel in ``Sample.metadata`` -- never the parsed
    ``evaluation`` block. The scorer re-loads the full task host-side, so
    ground truth reaches neither the model's context nor the sandbox. This is
    what ``run_experiments.py::_create_sanitised_task_yaml`` had to strip by
    hand; under Inspect the task definition simply never travels.
    """
    # "scd_tasks" resolves under tasks/; "../tasksv2/scl" (or any path with a
    # separator) lets the v2 corpus sit in its own tree while v1 stays frozen.
    directory = (_TASKS_ROOT / family).resolve()
    samples: list[Sample] = []

    for path in sorted(directory.glob("*.y*ml")):
        task = load_task(path)
        variables = template_vars(task)
        system_prompt = _JINJA.from_string(task.system_prompt).render(**variables)
        objective = _JINJA.from_string(task.objective).render(**variables)

        # `hint` and `answer_schema` are real YAML fields but are not on the
        # Task dataclass, so they are read from the raw mapping -- same as
        # run_experiments.py does for the hint. `hint=True` means H1 for a v2
        # task and the single unlevelled hint for a v1 one; pass "h2" for the
        # locator treatment.
        raw = yaml.safe_load(path.read_text()) or {}
        level = "h1" if hint is True else (hint or "")
        objective = render_objective(raw, objective, level)

        # Tasks that authenticate over SSH (the gridnet family) name a private
        # key on the host and where they expect it inside the container. Copy
        # it per sample rather than bind-mounting in the compose file: the six
        # gridnet tasks use two different keys at two different paths.
        files, setup = {}, None
        key_host, key_container = ssh_key_paths(task)
        if key_host and key_container:
            files[str(key_container)] = str(key_host)
            # OpenSSH refuses a key with group/world-readable permissions, and
            # Inspect copies files in without preserving mode.
            setup = f"chmod 600 {key_container}"

        # A v2 task names the compose file carrying exactly the fixtures it
        # declares, so a discovery task cannot read its own answer out of a
        # neighbouring family's fixture. Absent (every v1 task), the @task's
        # own sandbox applies unchanged.
        sandbox = None
        if raw.get("sandbox"):
            if raw.get("version") == 2 and raw.get("type") in ("scl_analysis", "pcap_analysis"):
                from tasksv2.static_fixtures import mount_problems
                problems = mount_problems(raw, _COMPOSE_DIR / raw["sandbox"])
                if problems:
                    raise ValueError(f"{task.id}: {'; '.join(problems)}")
            sandbox = SandboxEnvironmentSpec(
                "docker", str(_COMPOSE_DIR / raw["sandbox"]))

        metadata = {"yaml_path": str(path.resolve())}
        if raw.get("version") == 2:
            metadata.update({
                "benchmark_version": 2,
                "floor_control": raw.get("control") == "floor",
                "fixture_ids": ([raw["fixture"]["id"]] if isinstance(raw["fixture"]["id"], str)
                                else raw["fixture"]["id"]),
                "family": path.parent.name,
                "hint_level": level or "h0",
            })

        samples.append(
            Sample(
                id=task.id,
                sandbox=sandbox,
                input=[
                    ChatMessageSystem(content=system_prompt),
                    ChatMessageUser(content=objective),
                ],
                metadata=metadata,
                files=files or None,
                setup=setup,
            )
        )

    if not samples:
        raise ValueError(f"No task YAMLs found in {directory}")
    return MemoryDataset(samples, name=family)
