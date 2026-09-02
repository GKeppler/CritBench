"""Build Inspect datasets from CritBench task YAMLs."""

from __future__ import annotations

from pathlib import Path

import yaml
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageUser
from jinja2 import Environment, StrictUndefined

from tasks.task_schema import load_task, template_vars

# StrictUndefined matches ot_agent.py: an unresolved {{ var }} is a hard error,
# never a silently empty prompt.
_JINJA = Environment(undefined=StrictUndefined)

_TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


def critbench_dataset(family: str, hint: bool = False) -> MemoryDataset:
    """Load one CritBench task family (a directory under ``tasks/``).

    Only the YAML *path* travels in ``Sample.metadata`` -- never the parsed
    ``evaluation`` block. The scorer re-loads the full task host-side, so
    ground truth reaches neither the model's context nor the sandbox. This is
    what ``run_experiments.py::_create_sanitised_task_yaml`` had to strip by
    hand; under Inspect the task definition simply never travels.
    """
    directory = _TASKS_ROOT / family
    samples: list[Sample] = []

    for path in sorted(directory.glob("*.y*ml")):
        task = load_task(path)
        variables = template_vars(task)
        system_prompt = _JINJA.from_string(task.system_prompt).render(**variables)
        objective = _JINJA.from_string(task.objective).render(**variables)

        # `hint` is a real YAML field but is not on the Task dataclass, so it
        # is read from the raw mapping -- same as run_experiments.py does.
        if hint:
            raw = yaml.safe_load(path.read_text()) or {}
            if raw.get("hint"):
                objective = f"{objective}\n\nHint: {raw['hint']}"

        # Tasks that authenticate over SSH (the gridnet family) name a private
        # key on the host and where they expect it inside the container. Copy
        # it per sample rather than bind-mounting in the compose file: the six
        # gridnet tasks use two different keys at two different paths.
        files, setup = {}, None
        key_host = task.environment.extra.get("ssh_key_host_path")
        key_container = task.environment.extra.get("ssh_key_container_path")
        if key_host and key_container:
            files[str(key_container)] = str(key_host)
            # OpenSSH refuses a key with group/world-readable permissions, and
            # Inspect copies files in without preserving mode.
            setup = f"chmod 600 {key_container}"

        samples.append(
            Sample(
                id=task.id,
                input=[
                    ChatMessageSystem(content=system_prompt),
                    ChatMessageUser(content=objective),
                ],
                metadata={"yaml_path": str(path.resolve())},
                files=files or None,
                setup=setup,
            )
        )

    if not samples:
        raise ValueError(f"No task YAMLs found in {directory}")
    return MemoryDataset(samples, name=family)
