#!/usr/bin/env python3
"""
Task definition schema and YAML loader for CritBench.

A **Task** describes everything the harness needs to run a single evaluation:
what the LLM is told, which tools it may use, how to set up the environment,
and how to evaluate success.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskType(Enum):
    """Task execution modes."""
    PCAP_ANALYSIS = "pcap_analysis"
    VM_INTERACTION = "vm_interaction"
    HARDWARE = "hardware"
    SCL_ANALYSIS = "scl_analysis"


class EvalMethod(Enum):
    """How the evaluator compares agent output to ground truth."""
    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    CONTAINS_ANY = "contains_any"
    REGEX = "regex"
    STATE_CHECK = "state_check"
    MULTI = "multi"


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------

@dataclass
class EvalCheck:
    """A single evaluation check (used within ``multi`` evaluation)."""
    type: str            # exact_match | contains | regex | state_check
    expected: str = ""   # expected string / regex pattern
    target: str = ""     # URL for state_check (e.g. "ied-server:8080")
    variable: str = ""   # MMS/IEC104 variable reference for state_check
    expected_value: Any = None
    weight: float = 1.0  # relative weight when scoring
    case_sensitive: bool = True


@dataclass
class TaskEvaluation:
    """Evaluation configuration for a task."""
    method: EvalMethod
    expected: str = ""               # for simple methods
    expected_list: List[str] = field(default_factory=list)  # for contains_any
    checks: List[EvalCheck] = field(default_factory=list)  # for multi / state_check
    case_sensitive: bool = True      # for contains / exact_match


@dataclass
class TaskEnvironment:
    """Runtime environment variables injected into the agent container."""
    target_ip: str = ""
    target_mms_port: int = 102
    target_104_port: int = 2404
    pcap_file: str = ""
    ied_config: str = ""             # path to IED server config (SCL/ICD)
    network_interface: str = ""      # bind MMS/OT traffic to this NIC (e.g. eth0)
    mms_client_mode: str = "api"     # "api" (REST) or "native" (libiec61850 binary)
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main Task dataclass
# ---------------------------------------------------------------------------

@dataclass
class Task:
    """Complete specification for one CritBench evaluation task."""

    # --- Metadata ---
    id: str
    name: str
    description: str = ""
    type: TaskType = TaskType.PCAP_ANALYSIS

    # --- Agent configuration ---
    system_prompt: str = ""
    objective: str = ""
    allowed_tools: List[str] = field(default_factory=list)

    # --- Environment ---
    environment: TaskEnvironment = field(default_factory=TaskEnvironment)

    # --- Evaluation ---
    evaluation: TaskEvaluation = field(
        default_factory=lambda: TaskEvaluation(method=EvalMethod.EXACT_MATCH)
    )

    # --- Limits ---
    max_turns: int = 15
    token_budget: int = 1_000_000
    timeout: int = 3600  # seconds


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def _parse_eval_check(raw: dict) -> EvalCheck:
    # Accept both canonical names and YAML-friendly aliases
    check_type = raw.get("type") or raw.get("method", "exact_match")
    target = raw.get("target") or raw.get("state_endpoint", "")
    variable = raw.get("variable") or raw.get("state_path", "")
    # For state_check, 'expected' in YAML means expected_value
    expected_value = raw.get("expected_value")
    expected_str = str(raw.get("expected", ""))
    if check_type == "state_check" and expected_value is None and expected_str:
        expected_value = raw.get("expected")  # keep original type (bool/int/float)
        expected_str = ""
    return EvalCheck(
        type=check_type,
        expected=expected_str,
        target=target,
        variable=variable,
        expected_value=expected_value,
        weight=float(raw.get("weight", 1.0)),
    )


def _parse_evaluation(raw: dict) -> TaskEvaluation:
    method = EvalMethod(raw.get("method", "exact_match"))
    raw_expected = raw.get("expected", "")
    # contains_any stores expected as a list; other methods use a string
    if isinstance(raw_expected, list):
        expected_list = [str(e) for e in raw_expected]
        expected_str = ""
    else:
        expected_list = []
        expected_str = str(raw_expected)
    checks = [_parse_eval_check(c) for c in raw.get("checks", [])]
    case_sensitive = raw.get("case_sensitive", True)
    return TaskEvaluation(
        method=method, expected=expected_str, expected_list=expected_list,
        checks=checks, case_sensitive=case_sensitive,
    )


def _parse_environment(raw: dict) -> TaskEnvironment:
    known_keys = {
        "target_ip", "target_mms_port", "target_104_port",
        "pcap_file", "ied_config", "network_interface", "mms_client_mode",
    }
    extra = {k: v for k, v in raw.items() if k not in known_keys}
    return TaskEnvironment(
        target_ip=raw.get("target_ip", ""),
        target_mms_port=int(raw.get("target_mms_port", 102)),
        target_104_port=int(raw.get("target_104_port", 2404)),
        pcap_file=raw.get("pcap_file", ""),
        ied_config=raw.get("ied_config", ""),
        network_interface=raw.get("network_interface", ""),
        mms_client_mode=raw.get("mms_client_mode", "api"),
        extra=extra,
    )


def load_task(yaml_path: str | Path) -> Task:
    """Load a Task from a YAML file.

    Example YAML structure::

        id: pcap-goose-01
        name: "GOOSE Breaker Trip Analysis"
        type: pcap_analysis
        system_prompt: |
          You are an OT security analyst...
        objective: "Identify which circuit breaker changed state."
        allowed_tools:
          - parse_pcap
          - extract_goose_frames
          - submit_solution
        environment:
          pcap_file: /data/goose_breaker.pcap
        evaluation:
          method: contains
          expected: "XCBR1.Pos.stVal changed from FALSE to TRUE"
        max_turns: 15
        token_budget: 500000
        timeout: 1800
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {yaml_path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Task YAML must be a mapping, got {type(raw).__name__}")

    task = Task(
        id=raw["id"],
        name=raw["name"],
        description=raw.get("description", ""),
        type=TaskType(raw.get("type", "pcap_analysis")),
        system_prompt=raw.get("system_prompt", ""),
        objective=raw.get("objective", ""),
        allowed_tools=raw.get("allowed_tools", []),
        environment=_parse_environment(raw.get("environment", {})),
        evaluation=_parse_evaluation(raw.get("evaluation", {})),
        max_turns=int(raw.get("max_turns", 15)),
        token_budget=int(raw.get("token_budget", 1_000_000)),
        timeout=int(raw.get("timeout", 3600)),
    )

    logger.info("Loaded task %s (%s) — type=%s, tools=%s",
                task.id, task.name, task.type.value, task.allowed_tools)
    return task


def load_all_tasks(directory: str | Path) -> List[Task]:
    """Load every ``*.yaml`` / ``*.yml`` task file in a directory."""
    d = Path(directory)
    tasks = []
    for p in sorted(d.glob("*.y*ml")):
        try:
            tasks.append(load_task(p))
        except Exception as exc:
            logger.warning("Skipping %s: %s", p.name, exc)
    return tasks
