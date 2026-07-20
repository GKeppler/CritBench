#!/usr/bin/env python3
"""
run_experiments.py  —  CritBench batch experiment runner.

Orchestrates multiple agent runs across tasks, models, and repetitions.
Handles Docker lifecycle for VM-interaction tasks and collects results.

Usage:
    python run_experiments.py --tasks tasks/definitions/ --models gpt-4o claude-sonnet-4-20250514 --runs 3
    python run_experiments.py --task tasks/definitions/vm_mms_breaker_flip.yaml --model gpt-4o
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure critbench packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from tasks.task_schema import Task, TaskType, load_task, load_all_tasks
from evaluation.evaluator import evaluate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_experiments")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class ExperimentConfig:
    task_paths: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=lambda: ["gpt-4o"])
    runs_per_combo: int = 1
    output_base: str = "output"
    parallel: int = 1
    docker_compose_file: str = "docker-compose.yaml"
    timeout: int = 600  # seconds per run (Docker wall-clock)
    token_budget: int = 200000  # max input tokens per run
    max_turns: int = 50  # max agent turns per run
    dry_run: bool = False
    notools: bool = False  # restrict agent to run_command + submit_solution only
    hint: bool = False  # append hint field to objective text


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _docker_compose_cmd(compose_file: str) -> list[str]:
    """Return the docker compose base command."""
    # Try 'docker compose' (v2) first, fall back to 'docker-compose'
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, check=True,
        )
        return ["docker", "compose", "-f", compose_file]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose", "-f", compose_file]


def _compose_services(compose_file: str) -> set[str]:
    """Return the set of service names defined in a compose file."""
    cmd = _docker_compose_cmd(compose_file)
    result = subprocess.run([*cmd, "config", "--services"], capture_output=True, text=True)
    if result.returncode != 0:
        return set()
    return {s.strip() for s in result.stdout.splitlines() if s.strip()}


def _task_is_grfics(task: Task) -> bool:
    """A task belongs to the GRFICSv3 (Modbus/OpenPLC) family, not the
    IEC 61850 ied-server family — it targets a different compose topology
    and a different host-side grading endpoint."""
    return str(task.environment.extra.get("state_api", "")).startswith("http://grfics-state-api")


def _check_docker_images(compose_file: str = "docker-compose.yaml") -> None:
    """Verify the required Docker images exist before running experiments.

    Raises RuntimeError with build instructions if any image is missing.
    The ied-server image is only required when the compose file actually
    defines an ``ied-server`` service (the GRFICSv3 compose doesn't — its
    upstream images are pulled and its state-api sidecar is built
    automatically by ``docker compose up``).
    """
    services = _compose_services(compose_file)
    required = ["critbench-agent:latest"]
    if "ied-server" in services:
        required.append("critbench-ied:latest")

    missing = []
    for img in required:
        result = subprocess.run(
            ["docker", "image", "inspect", img],
            capture_output=True,
        )
        if result.returncode != 0:
            missing.append(img)

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Docker image(s) not found: {names}\n"
            f"Build them first with:\n"
            f"  docker build -t critbench-agent:latest -f docker/Dockerfile.agent .\n"
            f"  docker build -t critbench-ied:latest   -f docker/Dockerfile.ied_server .\n"
            f"See README.md for details."
        )
    log.info("Docker images present ✓")


def start_ied_server(compose_file: str) -> None:
    """Start the IED server container and wait until it responds."""
    cmd = _docker_compose_cmd(compose_file)
    log.info("Starting IED server …")
    subprocess.run(
        [*cmd, "up", "-d", "ied-server"],
        check=True, capture_output=True, text=True,
    )
    # Probe the health API from the HOST side (port 18080 → container 8080).
    # This avoids depending on curl/wget being installed inside the container.
    import urllib.request
    import urllib.error

    health_url = "http://localhost:18080/health"
    for attempt in range(30):
        try:
            with urllib.request.urlopen(health_url, timeout=3) as resp:
                if resp.status == 200:
                    log.info("IED server healthy ✓")
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    raise RuntimeError(
        f"IED server did not become healthy in time "
        f"(checked {health_url} for 60 s)"
    )


def stop_ied_server(compose_file: str) -> None:
    """Stop and remove the IED server container."""
    cmd = _docker_compose_cmd(compose_file)
    log.info("Stopping IED server …")
    subprocess.run(
        [*cmd, "down", "--volumes", "--remove-orphans"],
        capture_output=True, text=True,
    )


def start_grfics_stack(compose_file: str) -> None:
    """Start the GRFICSv3 process stack (simulation + plc + state-api sidecar)
    and wait until the state API responds. Mirrors start_ied_server(), but
    for the Modbus/OpenPLC compose topology (no single 'ied-server' service)."""
    cmd = _docker_compose_cmd(compose_file)
    log.info("Starting GRFICSv3 stack (simulation + plc + grfics-state-api) …")
    subprocess.run(
        [*cmd, "up", "-d", "--build", "simulation", "plc", "grfics-state-api"],
        check=True, capture_output=True, text=True,
    )
    import urllib.request
    import urllib.error

    health_url = "http://localhost:18081/health"
    for attempt in range(60):
        try:
            with urllib.request.urlopen(health_url, timeout=3) as resp:
                if resp.status == 200:
                    log.info("GRFICSv3 state API healthy ✓")
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(3)
    raise RuntimeError(
        f"GRFICSv3 state API did not become healthy in time "
        f"(checked {health_url} for 180 s — plc/simulation may still be booting "
        f"or the fortiphyd images may still be pulling)"
    )


def stop_grfics_stack(compose_file: str) -> None:
    """Stop and remove the GRFICSv3 stack."""
    cmd = _docker_compose_cmd(compose_file)
    log.info("Stopping GRFICSv3 stack …")
    subprocess.run(
        [*cmd, "down", "--volumes", "--remove-orphans"],
        capture_output=True, text=True,
    )


def run_agent_in_docker(
    compose_file: str,
    model: str,
    task_yaml: str,
    output_dir: str,
    timeout: int,
    output_base: str = "output",
    needs_ied: bool = False,
    env_overrides: dict | None = None,
    host_network: bool = False,
) -> int:
    """Run the agent container with specified config. Returns exit code.

    Args:
        output_base: Host-side output base directory (mounted as /output in container).
        needs_ied: If False, passes --no-deps to skip the ied-server dependency.
        host_network: If True, run with ``--network host`` so the container
            can reach physical devices on the host's LAN interfaces.
    """
    cmd = _docker_compose_cmd(compose_file)
    env = os.environ.copy()
    env["CRITBENCH_MODEL"] = model
    env["CRITBENCH_TASK"] = task_yaml
    env["CRITBENCH_OUTPUT"] = output_dir
    # Tell docker-compose which host directory to mount as /output
    env["CRITBENCH_OUTPUT_MOUNT"] = os.path.abspath(output_base)
    if env_overrides:
        env.update(env_overrides)

    log.info(f"Running agent in Docker: model= {model}, task= {task_yaml}, ied={needs_ied}, host_net={host_network}")
    try:
        if host_network:
            # 'docker compose run' does not support --network host.
            # Use plain 'docker run' with the same image, volumes, caps,
            # and environment variables that docker-compose.yaml defines.
            compose_dir = os.path.dirname(os.path.abspath(compose_file))
            output_mount = os.path.abspath(output_base)
            pcaps_mount = os.path.join(compose_dir, "tasks", "pcaps")
            scd_mount = os.path.join(compose_dir, "tasks", "scd")

            run_cmd = [
                "docker", "run", "--rm",
                "--network", "host",
                "--cap-add", "NET_RAW",
                "--cap-add", "NET_ADMIN",
                "-v", f"{output_mount}:/output",
                "-v", f"{pcaps_mount}:/code/tasks/pcaps:ro",
                "-v", f"{scd_mount}:/code/tasks/scd:ro",
                "-e", f"CRITBENCH_MODEL={model}",
                "-e", f"CRITBENCH_TASK={task_yaml}",
                "-e", f"CRITBENCH_OUTPUT={output_dir}",
            ]
            print("Docker is run: ",run_cmd)
            # Forward API keys from the host environment
            for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "KITOOLBOX_API_KEY", "SFT_AGENT_BASE_URL", "SFT_AGENT_API_KEY"):
                val = os.environ.get(key)
                if val:
                    run_cmd.extend(["-e", f"{key}={val}"])
            # Forward any extra env vars (hardware interface, MMS config, etc.)
            if env_overrides:
                for k, v in env_overrides.items():
                    run_cmd.extend(["-e", f"{k}={v}"])
            run_cmd.append("critbench-agent:latest")
        else:
            run_cmd = [*cmd, "run", "--rm"]
            if not needs_ied:
                run_cmd.append("--no-deps")
            run_cmd.extend([
                "-e", f"CRITBENCH_MODEL={model}",
                "-e", f"CRITBENCH_TASK={task_yaml}",
                "-e", f"CRITBENCH_OUTPUT={output_dir}",
            ])
            # Forward any extra env vars (e.g. CRITBENCH_EVAL_TASK)
            if env_overrides:
                for k, v in env_overrides.items():
                    run_cmd.extend(["-e", f"{k}={v}"])
            run_cmd.append("agent")
        result = subprocess.run(
            run_cmd,
            env=env, capture_output=True, text=True, timeout=timeout,
        )
        if result.stdout:
            log.info(f"stdout (last 500): {result.stdout[-500:]}")
        if result.returncode != 0:
            log.warning(f"Agent exited with code {result.returncode}")
            log.warning(f"stderr: {result.stderr[-500:]}")
        return result.returncode
    except subprocess.TimeoutExpired:
        log.error(f"Agent timed out after {timeout}s")
        # Kill the agent container — use compose kill for reliability
        subprocess.run(
            [*_docker_compose_cmd(compose_file), "kill", "agent"],
            capture_output=True,
        )
        subprocess.run(
            [*_docker_compose_cmd(compose_file), "rm", "-f", "agent"],
            capture_output=True,
        )
        # Also try the named container as a fallback
        subprocess.run(
            ["docker", "rm", "-f", "critbench-agent"],
            capture_output=True,
        )
        return -1


# ---------------------------------------------------------------------------
# Task YAML sanitiser  — strip evaluation section before mounting
# ---------------------------------------------------------------------------

def _create_sanitised_task_yaml(
    task_path: str,
    output_dir: str,
    notools: bool = False,
    hint: bool = False,
    token_budget: int = 200000,
    max_turns: int = 50,
    timeout: int = 600,
) -> str:
    """Copy the task YAML to output_dir with the evaluation section removed.

    This prevents the agent from reading the expected answer.
    If notools=True, overrides allowed_tools to [run_command, submit_solution].
    If hint=True, appends the task's hint field to the objective text.
    token_budget, max_turns, and timeout are injected into the sanitised YAML.
    Returns the path to the sanitised copy.
    """
    import yaml as _yaml  # lazy to keep top-level imports light

    with open(task_path) as f:
        data = _yaml.safe_load(f)

    # Strip evaluation / grading sections
    for key in ("evaluation", "grading", "expected_answer", "expected"):
        data.pop(key, None)

    # Handle hint field: append to objective if --hint is set, then remove
    hint_text = data.pop("hint", None)
    if hint and hint_text:
        objective = data.get("objective", "")
        data["objective"] = f"{objective}\nHint: {hint_text.strip()}"

    # Set allowed_tools based on task type and flags
    if notools:
        run_cmd_tool = "run_command_hardware" if data.get("type") == "hardware" else "run_command"
        data["allowed_tools"] = [run_cmd_tool, "submit_solution"]
    elif data.get("type") == "pcap_analysis":
        data["allowed_tools"] = [
            "parse_pcap",
            "extract_goose_frames",
            "extract_mms_operations",
            "extract_iec104_traffic",
            "run_command",
            "submit_solution",
        ]
    elif data.get("type") == "scl_analysis":
        data["allowed_tools"] = [
            "scl_list_ieds",
            "scl_get_ied_summary",
            "scl_get_logical_device",
            "scl_get_communication",
            "scl_get_substation",
            "scl_count_ln_class",
            "scl_get_dataset",
            "scl_list_datasets",
            "run_command",
            "submit_solution",
        ]
    elif data.get("type") == "vm_interaction" and not str(
        data.get("environment", {}).get("state_api", "")
    ).startswith("http://grfics-state-api"):
        # GRFICSv3 (Modbus) tasks are also vm_interaction but target a
        # different toolset (tools_modbus, not MMS/GOOSE/IEC104) — keep
        # whatever allowed_tools their own YAML defines instead of
        # overwriting with the IEC 61850 tool list below.
        data["allowed_tools"] = [
            'extract_goose_frames',
            'extract_mms_operations',
            'extract_iec104_traffic',
            'read_mms_variable',
            'write_mms_variable',
            'list_mms_model',
            'inject_goose_packet',
            'subscribe_goose',
            'send_iec104_command',
            'read_iec104_point',
            'iec104_interrogation',
            "run_command",
            "submit_solution",
        ]
    else:
        # For other task types, keep whatever allowed_tools the YAML defines
        # (already stripped of evaluation; notools not set)
        pass

    # Inject run-level parameters (override any task-level values)
    data["token_budget"] = token_budget
    data["max_turns"] = max_turns
    data["timeout"] = timeout

    sanitised_path = os.path.join(output_dir, "_task_sanitised.yaml")
    with open(sanitised_path, "w") as f:
        _yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return sanitised_path


# ---------------------------------------------------------------------------
# Host-side evaluation (runs AFTER the agent container exits)
# ---------------------------------------------------------------------------

def _fetch_hardware_state_from_host(task: Task) -> dict | None:
    """Independently re-read state_check targets straight from the real IED.

    Hardware tasks have no REST sidecar to poll (unlike ied-server/
    grfics-state-api) — the device itself IS the ground truth. For every
    ``state_check`` the task declares, shell out to the already-compiled
    native ``mms_client`` binary (same one the agent container uses) from
    the HOST, after the agent has exited, and read the reference fresh.
    Never trusts anything the agent itself reported.
    """
    refs = [c.variable for c in (task.evaluation.checks or []) if c.type == "state_check"]
    if not refs:
        return None

    host = str(task.environment.extra.get("ied_host", ""))
    port = str(task.environment.extra.get("ied_mms_port", "102"))
    values: dict[str, Any] = {}

    for full_path in refs:
        # variable is "hardware.<LD>/<LN>$<FC>$<DO>$<DA>" — strip the
        # "hardware." prefix to get the raw MMS reference for mms_client.
        ref = full_path.split(".", 1)[1] if full_path.startswith("hardware.") else full_path
        cmd = ["docker", "run", "--rm", "--network", "host",
               "critbench-agent:latest",
               "/opt/libiec61850/bin/mms_client", "-h", host, "-p", port, "read", ref]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            # do_read() prints "<reference> = <value>"
            line = next((l for l in result.stdout.splitlines() if " = " in l), None)
            if result.returncode == 0 and line:
                value = line.split(" = ", 1)[1].strip().strip('"')
                parts = ref.replace("/", ".").replace("$", ".").split(".")
                cur = values
                for p in parts[:-1]:
                    cur = cur.setdefault(p, {})
                cur[parts[-1]] = value
            else:
                log.warning("Live MMS re-read failed for %s: %s", ref, result.stderr.strip())
        except Exception as exc:
            log.warning("Could not run native mms_client for %s: %s", ref, exc)

    return {"hardware": values}


def _fetch_ied_state_from_host(task: Task) -> dict | None:
    """Fetch live grading state from the HOST side (via a mapped port).

    This is the host-side counterpart of what the old agent-side
    _fetch_ied_state() did, but uses the host-mapped port instead of
    the Docker-internal address. Dispatches between the IEC 61850
    ied-server (port 18080, /live_state) and the GRFICSv3 state-api
    sidecar (port 18081, /state) depending on the task's family — each
    is a different compose stack with a different container topology.
    """
    if task.type in (TaskType.PCAP_ANALYSIS, TaskType.SCL_ANALYSIS):
        return None

    if _task_is_grfics(task):
        api_url, path = "http://localhost:18081", "/state"
    else:
        api_url, path = "http://localhost:18080", "/live_state"

    try:
        import urllib.request
        import urllib.error

        # /live_state (ied-server) and /state (grfics-state-api) both read
        # the REAL device — never an agent-writable dict — so grading can't
        # be reward-hacked by writing to the state API directly.
        req = urllib.request.Request(f"{api_url}{path}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
            log.warning("State API returned %d", resp.status)
    except Exception as exc:
        log.warning("Could not fetch live state from host: %s", exc)
    return None


def _run_host_side_evaluation(
    task: Task,
    agent_output: dict,
    output_dir: str,
    notools: bool = False,
    hint: bool = False,
) -> dict:
    """Run evaluation on the host using the full task YAML and agent output.

    Reads agent_output.json (written by the agent container), runs the
    evaluator with the full task (including ground truth), and writes
    result.json.

    Returns the result dict.
    """
    agent_answer = agent_output.get("agent_answer", "")
    ied_state = (
        _fetch_hardware_state_from_host(task) if task.type == TaskType.HARDWARE
        else _fetch_ied_state_from_host(task)
    )

    transcript = None
    transcript_file = os.path.join(output_dir, "transcript.json")
    if os.path.exists(transcript_file):
        try:
            with open(transcript_file) as f:
                transcript = json.load(f)
        except Exception as exc:
            log.warning("Could not load transcript for evaluation: %s", exc)

    eval_result = evaluate(task, agent_answer, ied_state, transcript)

    log.info(
        "Host evaluation: success=%s, score=%.2f, answer=%s",
        eval_result.success, eval_result.score, agent_answer[:200],
    )

    # Build result.json combining agent output + evaluation
    from datetime import datetime as _dt

    start_time = None
    end_time = None
    if agent_output.get("start_time"):
        try:
            start_time = _dt.fromisoformat(agent_output["start_time"])
        except (ValueError, TypeError):
            pass
    if agent_output.get("end_time"):
        try:
            end_time = _dt.fromisoformat(agent_output["end_time"])
        except (ValueError, TypeError):
            pass

    duration = 0.0
    if start_time and end_time:
        duration = (end_time - start_time).total_seconds()

    result = {
        "success": eval_result.success,
        "exit_reason": agent_output.get("exit_reason", "unknown"),
        "task_id": agent_output.get("task_id", task.id),
        "task_type": agent_output.get("task_type", task.type.value),
        "model": agent_output.get("model", ""),
        "token_budget": agent_output.get("token_budget", task.token_budget),
        "total_loops": agent_output.get("total_loops", 0),
        "tool_errors": agent_output.get("tool_errors", 0),
        "duration_seconds": round(duration, 2),
        "start_time": agent_output.get("start_time", ""),
        "end_time": agent_output.get("end_time", ""),
        "evaluation": eval_result.to_dict(),
        "metrics": agent_output.get("metrics", {}),
        "prompts": {
            "system_prompt": agent_output.get("system_prompt", ""),
            "initial_prompt": agent_output.get("initial_prompt", ""),
        },
        "transcript_path": agent_output.get("transcript_path", ""),
        "agent_answer": agent_answer,
        "agent_reasoning": agent_output.get("agent_reasoning", ""),
        "notools": notools,
        "hint": hint,
    }

    result_path = os.path.join(output_dir, "result.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    log.info("Wrote result.json to %s", result_path)

    return result


# ---------------------------------------------------------------------------
# Single experiment
# ---------------------------------------------------------------------------

def run_single_experiment(
    task: Task,
    task_path: str,
    model: str,
    run_idx: int,
    config: ExperimentConfig,
) -> dict:
    """Execute one (task, model, run) combination. Returns summary dict."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{task.id}__{model.replace('/', '_')}__{run_idx}__{timestamp}"
    output_dir = os.path.join(config.output_base, run_id)
    os.makedirs(output_dir, exist_ok=True)

    summary = {
        "run_id": run_id,
        "task_id": task.id,
        "model": model,
        "run_index": run_idx,
        "timestamp": timestamp,
        "task_type": task.type.value,
        "status": "pending",
        "notools": config.notools,
        "hint": config.hint,
    }

    if config.dry_run:
        summary["status"] = "dry_run"
        log.info(f"[DRY RUN] {run_id}")
        return summary

    try:
        # Create a sanitised copy of the task YAML (evaluation stripped)
        sanitised_host_path = _create_sanitised_task_yaml(
            task_path, output_dir,
            notools=config.notools,
            hint=config.hint,
            token_budget=config.token_budget,
            max_turns=config.max_turns,
            timeout=config.timeout,
        )
        # output_dir on host = <output_base>/<run_id>
        # Docker mount: ./output → /output  (output_base must be "output")
        rel_output = os.path.relpath(output_dir, config.output_base)
        # Agent writes results to per-run subdirectory inside container
        container_output = f"/output/{rel_output}"
        # Sanitised task YAML lives in the same per-run directory
        container_task_path = f"{container_output}/_task_sanitised.yaml"

        needs_ied = task.type == TaskType.VM_INTERACTION
        is_hardware = task.type == TaskType.HARDWARE

        # Use the CLI timeout as the Docker wall-clock limit
        effective_timeout = config.timeout

        # Hardware tasks need host networking + interface/MMS env vars
        hw_env: dict[str, str] = {}
        if is_hardware:
            if task.environment.network_interface:
                hw_env["BIND_INTERFACE"] = task.environment.network_interface
            if task.environment.mms_client_mode:
                hw_env["MMS_CLIENT_MODE"] = task.environment.mms_client_mode
            if "ied_host" in task.environment.extra:
                hw_env["IED_MMS_HOST"] = str(task.environment.extra["ied_host"])
            if "ied_mms_port" in task.environment.extra:
                hw_env["IED_MMS_PORT"] = str(task.environment.extra["ied_mms_port"])

        rc = run_agent_in_docker(
            compose_file=config.docker_compose_file,
            model=model,
            task_yaml=container_task_path,
            output_dir=container_output,
            timeout=effective_timeout,
            output_base=config.output_base,
            needs_ied=needs_ied,
            env_overrides=hw_env if hw_env else None,
            host_network=is_hardware,
        )
        summary["exit_code"] = rc
        summary["status"] = "completed" if rc == 0 else "failed"

    except Exception as e:
        log.error(f"Experiment {run_id} failed: {e}")
        summary["status"] = "error"
        summary["error"] = str(e)

    # ---- Host-side evaluation ----
    # Read agent_output.json, run evaluation with full task YAML, write result.json
    agent_output_file = os.path.join(output_dir, "agent_output.json")
    if os.path.exists(agent_output_file):
        try:
            with open(agent_output_file) as f:
                agent_output = json.load(f)
            result_data = _run_host_side_evaluation(task, agent_output, output_dir, notools=config.notools, hint=config.hint)
            summary["result"] = result_data

            # If Docker timed out (-1) but the agent actually wrote output,
            # recover status from the evaluation.
            if summary["status"] == "failed" and summary.get("exit_code") == -1:
                eval_data = result_data.get("evaluation", {})
                if isinstance(eval_data, dict) and eval_data.get("success"):
                    summary["status"] = "completed"
                    summary["note"] = "Docker process timed out but agent evaluation succeeded"
                    log.info("Recovered successful result from timed-out run: %s", run_id)
                elif isinstance(eval_data, dict) and "score" in eval_data:
                    summary["status"] = "completed"
                    summary["note"] = "Docker process timed out but agent evaluation was performed"
                    log.info("Recovered evaluated (unsuccessful) result from timed-out run: %s", run_id)
        except Exception as e:
            log.error(f"Host-side evaluation failed for {run_id}: {e}")
            summary["eval_error"] = str(e)
    else:
        log.warning("No agent_output.json found in %s — agent may have crashed", output_dir)

        # Fallback: check for legacy result.json (pre-restructuring runs)
        result_file = os.path.join(output_dir, "result.json")
        if os.path.exists(result_file):
            with open(result_file) as f:
                summary["result"] = json.load(f)
            summary["note"] = "Legacy result.json (pre-restructuring, agent-side eval)"

    # Write per-run summary
    summary_file = os.path.join(output_dir, "summary.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


# ---------------------------------------------------------------------------
# Batch orchestrator
# ---------------------------------------------------------------------------

def run_experiments(config: ExperimentConfig) -> list[dict]:
    """Run all (task × model × repetition) experiments."""
    # Load tasks
    tasks: list[tuple[Task, str]] = []
    for tp in config.task_paths:
        p = Path(tp)
        if p.is_dir():
            for task in load_all_tasks(str(p)):
                # Find the YAML path
                for yaml_file in p.glob("*.yaml"):
                    t = load_task(str(yaml_file))
                    if t.id == task.id:
                        tasks.append((task, str(yaml_file)))
                        break
        elif p.is_file():
            task = load_task(str(p))
            tasks.append((task, str(p)))

    if not tasks:
        log.error("No tasks found!")
        return []

    log.info(f"Loaded {len(tasks)} task(s), {len(config.models)} model(s), "
             f"{config.runs_per_combo} run(s) each")

    # Check which tasks need a live environment stack, and which one —
    # GRFICSv3 tasks and classic IEC 61850 vm_interaction tasks are both
    # TaskType.VM_INTERACTION but need different compose stacks.
    vm_tasks = [t for t, _ in tasks if t.type == TaskType.VM_INTERACTION]
    grfics_tasks = [t for t in vm_tasks if _task_is_grfics(t)]
    ied_tasks = [t for t in vm_tasks if not _task_is_grfics(t)]
    ied_running = False
    grfics_running = False

    results: list[dict] = []

    try:
        # Verify Docker images exist (they must be built beforehand)
        if not config.dry_run:
            _check_docker_images(config.docker_compose_file)

        if ied_tasks and not config.dry_run:
            start_ied_server(config.docker_compose_file)
            ied_running = True
        if grfics_tasks and not config.dry_run:
            start_grfics_stack(config.docker_compose_file)
            grfics_running = True

        # Build experiment list
        experiments = []
        for task, tpath in tasks:
            for model in config.models:
                for run_idx in range(config.runs_per_combo):
                    experiments.append((task, tpath, model, run_idx))

        log.info(f"Total experiments: {len(experiments)}")

        # Run (sequential or parallel for non-VM tasks)
        if config.parallel > 1:
            # Only parallelize PCAP/hardware; VM tasks are sequential
            vm_exps = [(t, tp, m, r) for t, tp, m, r in experiments
                       if t.type == TaskType.VM_INTERACTION]
            other_exps = [(t, tp, m, r) for t, tp, m, r in experiments
                          if t.type != TaskType.VM_INTERACTION]

            # Parallel for non-VM
            with ThreadPoolExecutor(max_workers=config.parallel) as pool:
                futures = [
                    pool.submit(run_single_experiment, t, tp, m, r, config)
                    for t, tp, m, r in other_exps
                ]
                for f in futures:
                    results.append(f.result())

            # Sequential for VM (shared IED server)
            for t, tp, m, r in vm_exps:
                results.append(run_single_experiment(t, tp, m, r, config))
        else:
            for t, tp, m, r in experiments:
                results.append(run_single_experiment(t, tp, m, r, config))

    finally:
        if ied_running:
            stop_ied_server(config.docker_compose_file)
        if grfics_running:
            stop_grfics_stack(config.docker_compose_file)

    # Write aggregate results
    os.makedirs(config.output_base, exist_ok=True)
    agg_path = os.path.join(
        config.output_base,
        f"aggregate_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(agg_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Aggregate results → {agg_path}")

    # Print summary table
    _print_summary(results)

    return results


def _print_summary(results: list[dict]) -> None:
    """Print a human-readable summary table."""
    print("\n" + "=" * 72)
    print("CritBench Experiment Summary")
    print("=" * 72)

    header = f"{'Task':<30} {'Model':<25} {'Run':<5} {'Status':<12} {'Score'}"
    print(header)
    print("-" * len(header))

    for r in results:
        score = ""
        if "result" in r and isinstance(r["result"], dict):
            eval_data = r["result"].get("evaluation", {})
            if isinstance(eval_data, dict):
                score = f"{eval_data.get('score', 'N/A')}"
        print(f"{r['task_id']:<30} {r['model']:<25} {r['run_index']:<5} "
              f"{r['status']:<12} {score}")

    print("=" * 72)

    # Aggregate stats
    completed = [r for r in results if r["status"] == "completed"]
    failed = [r for r in results if r["status"] == "failed"]
    errored = [r for r in results if r["status"] == "error"]
    print(f"\nTotal: {len(results)}  |  Completed: {len(completed)}  |  "
          f"Failed: {len(failed)}  |  Errors: {len(errored)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CritBench — OT Security LLM Evaluation Runner",
    )
    parser.add_argument(
        "--tasks", "-t", nargs="+", required=True,
        help="Task YAML file(s) or directory containing them",
    )
    parser.add_argument(
        "--models", "-m", nargs="+", default=["kit.qwen3.5-397b-A17"],
        help="Model name(s) to evaluate",
    )
    parser.add_argument(
        "--runs", "-r", type=int, default=1,
        help="Number of runs per (task, model) combination",
    )
    parser.add_argument(
        "--output", "-o", default="output",
        help="Base output directory",
    )
    parser.add_argument(
        "--parallel", "-p", type=int, default=1,
        help="Max parallel runs (for PCAP/hardware tasks only)",
    )
    parser.add_argument(
        "--compose", default="docker-compose.yaml",
        help="Path to docker-compose.yaml",
    )
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Docker wall-clock timeout per run in seconds (default: 600)",
    )
    parser.add_argument(
        "--token-budget", type=int, default=1000000,
        help="Max input tokens per run (default: 1000000)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=50,
        help="Max agent turns per run (default: 50)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List experiments without running them",
    )
    parser.add_argument(
        "--notools", default=True, action="store_true",
        help="Restrict agent to run_command and submit_solution only (ignore task-specific tools)",
    )
    parser.add_argument(
        "--hint", action="store_true", default=False,
        help="Append the task's hint field to the objective text (as 'Hint: ...')",
    )

    args = parser.parse_args()

    config = ExperimentConfig(
        task_paths=args.tasks,
        models=args.models,
        runs_per_combo=args.runs,
        output_base=args.output,
        parallel=args.parallel,
        docker_compose_file=args.compose,
        timeout=args.timeout,
        token_budget=args.token_budget,
        max_turns=args.max_turns,
        dry_run=args.dry_run,
        notools=args.notools,
        hint=args.hint,
    )

    run_experiments(config)


if __name__ == "__main__":
    main()
