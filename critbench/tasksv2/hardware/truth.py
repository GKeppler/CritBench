#!/usr/bin/env python3
"""Ground truth for the v2 hardware family (ADR-0003 §6).

The other families derive their labels from a file or from the simulator's own
definition. Physical relays have neither: the truth is whatever the devices in
the lab are actually configured to do, and nobody can write it down honestly
without reading them.

So this family's ground truth is a **frozen baseline snapshot**, captured once
from the devices by `capture_baseline.py` into `baseline/`, reviewed, and
committed. Until that snapshot exists, every task here reports
`awaiting_baseline`: the validator lists them as pending and refuses to call
them shippable, rather than letting a transcribed guess pass for a label.

This is deliberately the opposite of v1, where 20 hardware definitions carried
hand-written regexes, no device had been read, and the graders accepted answers
made of the system prompt's own vocabulary.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

BASELINE_DIR = Path(__file__).resolve().parent / "baseline"
FIXTURE_DIR = BASELINE_DIR
FIXTURES: dict[str, str] = {"lab_baseline": "lab_baseline.json"}


class BaselineMissing(RuntimeError):
    """Raised when a hardware label is requested before the lab was read."""


@lru_cache(maxsize=None)
def baseline() -> dict:
    path = BASELINE_DIR / FIXTURES["lab_baseline"]
    if not path.exists():
        raise BaselineMissing(
            f"{path} does not exist. Run capture_baseline.py against the lab "
            f"with the devices powered and reachable, review the snapshot, and "
            f"commit it. Hardware tasks cannot ship before that."
        )
    return json.loads(path.read_text())


def _section(name: str) -> dict:
    data = baseline()
    if name not in data:
        raise BaselineMissing(f"baseline has no '{name}' section")
    return data[name]


# Each extractor projects the reviewed snapshot into one task's answer shape.
# They are written now so that capturing the baseline is the only remaining
# step, and so the answer contracts can be reviewed before anyone touches a
# relay.

def hw_goose_publisher_census() -> dict:
    return {"publishers": _section("goose")}


def hw_sv_stream_census() -> dict:
    return {"streams": _section("sv")}


def hw_station_bus_asset_survey() -> dict:
    return {"assets": _section("station_bus_hosts")}


def hw_mms_server_model() -> dict:
    return {"logical_devices": _section("mms_logical_devices")}


def hw_mms_dataset_audit() -> dict:
    return {"datasets": _section("mms_datasets")}


def hw_mms_rcb_enumeration() -> dict:
    return {"report_control_blocks": _section("mms_rcbs")}


def hw_ptp_grandmaster_identity() -> dict:
    return {"grandmaster": _section("ptp_grandmaster")}


def hw_sv_sync_quality_audit() -> dict:
    return {"streams": _section("sv_sync")}


TRUTH = {name: fn for name, fn in sorted(globals().items())
         if name.startswith("hw_") and callable(fn)}
UNIVERSE: dict = {}

if __name__ == "__main__":
    try:
        baseline()
    except BaselineMissing as exc:
        raise SystemExit(f"awaiting baseline: {exc}")
    for name, fn in TRUTH.items():
        print(f"--- {name}\n{json.dumps(fn(), indent=1)[:600]}")
