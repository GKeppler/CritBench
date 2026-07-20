# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout gotcha

The git root (this directory) is *not* the Python package root. All code, tasks,
and commands below live under `critbench/` — `cd critbench` before running
anything. `critbench/__init__.py` plus `sys.path` manipulation in
`run_experiments.py` / `agent_runner/ot_agent.py` is what makes `critleayer`,
`tasks`, `evaluation` importable as top-level packages from that directory.

## Commands

```bash
cd critbench
pip install -r requirements.txt          # or use the repo-root .venv
```

Build the Docker images before running anything VM-related (not built automatically):

```bash
docker build -t critbench-agent:latest -f docker/Dockerfile.agent .
docker build -t critbench-ied:latest   -f docker/Dockerfile.ied_server .   # IEC 61850 tasks only
# GRFICSv3 tasks: grfics-state-api is built automatically by `docker compose up`;
# simulation/plc are pulled as-is from Docker Hub (fortiphyd/grfics-*), never rebuilt.
```

Run experiments (the only real entry point — no separate lint/build step exists):

```bash
python run_experiments.py --tasks tasks/vm_tasks/vm_mms_breaker_flip.yaml --models gpt-4o --runs 1 --output output/test
python run_experiments.py --tasks tasks/GRFICSv3 --models kit.qwen3.5-397b-A17b --runs 1 \
  --output output/test --compose docker/docker-compose.grfics.yml --notools
python run_experiments.py --tasks tasks/pcaps_tasks/ tasks/scd_tasks/ --models gpt-4o --dry-run   # preview, no Docker/API calls
```

Useful flags: `--notools` (restrict the agent to `run_command` + `submit_solution` only —
forces genuine protocol interaction instead of calling purpose-built tools; the primary way
to test whether a task is solvable without hand-holding), `--hint` (append the task's `hint:`
field to the objective — the standard way to confirm a task that failed is still solvable at
all, not just harder), `--compose <file>` (must point at `docker/docker-compose.grfics.yml`
for GRFICSv3 tasks, defaults to `docker-compose.yaml` for everything else), `--runs N`,
`--parallel N` (PCAP/SCD/hardware tasks only — VM-interaction tasks always run sequentially
against a shared live environment).

Tests are plain scripts, not a pytest suite — run directly, exit 0 = pass:

```bash
python3 tests/test_live_state_grading.py           # anti-reward-hack grading path, no Docker needed
python3 docker/test/test_modbus_wire.py             # Modbus TCP wire protocol, fake in-process slave
docker/test/run_tests.sh [ied-host]                  # requires a running critbench-ied container
```

`.env` in `critbench/` holds `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `KITOOLBOX_API_KEY`.
`run_experiments.py` and `agent_runner/ot_agent.py` both call `load_dotenv()` — if you add a
new host-side entry point that shells out to `docker compose run` with `env=os.environ.copy()`,
it needs `load_dotenv()` too, or compose's `${VAR:-}` substitutions silently resolve to empty
and the agent container gets a blank API key (a 401 loop, not an obvious "missing key" error).

## Architecture

**Flow**: a task YAML (`tasks/<family>/*.yaml`, schema in `tasks/task_schema.py`) declares a
system prompt, objective, `allowed_tools`, an `environment` block, and an `evaluation` block
with the ground truth. `run_experiments.py` copies the YAML into the run's output dir with
`evaluation` (and `hint`, unless `--hint`) stripped before mounting it into the agent
container — the agent image itself never ships task definitions or answers, only
`agent_runner/`, `critleayer/`, and `tasks/task_schema.py` (see `Dockerfile.agent`'s
"SELECTIVE COPY" comment). The agent runs to completion, host-side code then re-loads the
*full* task and grades `agent_output.json` against it in `evaluation/evaluator.py`.

**Anti-reward-hack grading is the load-bearing design principle.** `state_check` evaluation
must never trust anything the agent itself could have written. For IEC 61850 tasks this means
grading reads `/live_state` on the IED server (real libiec61850/c104 server state via a native
client binary), not `/state` (an agent-writable convenience dict used only for fast reads).
For GRFICSv3 tasks the same idea is simpler: `docker/grfics_state_api.py` does a fresh live
Modbus read for every `/state` request — there's no shadow dict to fool at all. When adding a
new state_check-graded task family, preserve this: the grading source must be a real,
independent re-read of the device, not a value the agent's own tool call cached.

**Two independent environment topologies**, selected via `--compose`:
- `docker-compose.yaml` (default) — IEC 61850: a custom `ied-server` container
  (`critbench_ied_server.c`, hand-rolled MMS+GOOSE, `mms_client.c` as the native read/write
  client) + `agent`. Lifecycle managed by `start_ied_server`/`stop_ied_server` in
  `run_experiments.py`.
- `docker/docker-compose.grfics.yml` — Modbus/OpenPLC: `simulation` + `plc` (real
  `fortiphyd/grfics-*` images from the [GRFICSv3](https://github.com/Fortiphyd/GRFICSv3) lab,
  unmodified — deliberately only these two of GRFICSv3's 8 containers are started, not the
  HMI/EWS/Kali/router/Caldera/Wazuh human-training infrastructure the agent doesn't use) +
  `grfics-state-api` (grading sidecar) + `agent`, on a bridge network that reuses GRFICSv3's
  own subnet/IPs (192.168.95.0/24, plc=.2, simulation=.45) so `simulation`'s own entrypoint
  script (which self-assigns six field-device IP aliases) keeps working unmodified. Lifecycle:
  `start_grfics_stack`/`stop_grfics_stack`.

`run_experiments.py` tells these apart at runtime via `_task_is_grfics()` (checks whether
`task.environment.extra["state_api"]` points at `grfics-state-api`) rather than task type —
GRFICSv3 tasks deliberately reuse `TaskType.VM_INTERACTION`, they're not a distinct enum value.
Anywhere `run_experiments.py` special-cases IEC 61850 specifics (image checks, the
`_create_sanitised_task_yaml` tool-list override for `vm_interaction`, the host-side
`/live_state` fetch), check whether it needs a GRFICSv3-family branch too before assuming
"vm_interaction" means IEC 61850.

**CritLayer tool registry** (`critleayer/`): every `tools_*.py` module registers its
`@function_tool`-decorated functions into a global dict via `@register_tool`, and
`critleayer/__init__.py` imports every module so the registry is populated on package import.
A task's `allowed_tools` list is resolved against this registry at agent-startup — adding a new
protocol's tools means a new `tools_<protocol>.py` plus one import line in `__init__.py`, no
other wiring. Protocol clients here are hand-rolled (raw sockets/structs), not third-party
SDKs — `tools_mms.py`'s MMS client, `tools_modbus.py`'s Modbus TCP client
(FC1/3/4/5/6 by hand, no pymodbus), and the IED server's own C binaries all follow this
pattern; match it rather than reaching for a library when adding another protocol.

**GRFICSv3 register/point map** (`critleayer/tools_modbus.py::POINTS`,
`docker/grfics_state_api.py::POINTS`, kept in sync manually) is ground-truthed against the
*live* container's own glue-variable boot dump (`docker logs <plc-container>`), not just the
static `.st` source — the actually-active ladder program is `plc/st_files/326339.st` inside
the upstream GRFICSv3 image; `690525.st` looks similar but is missing the
`manual_mode`/`run_bit`/`*_manual_sp` coils entirely. If GRFICSv3 ships a new image version,
re-verify this map against a live container before trusting it.
