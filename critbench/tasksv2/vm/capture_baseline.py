#!/usr/bin/env python3
"""Record the live device's ground truth from the device itself.

    python3 capture_baseline.py

Start a fresh local simulator, enumerate its model over native MMS, and read
its live values repeatedly. Do not use the static /mms/discover convenience
mirror: it can omit real nodes. Stable/drifting classification and image
provenance are recorded with the snapshot.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

IMAGE = "critbench-ied:latest"
OUT = Path(__file__).resolve().parent / "baseline" / "live_baseline.json"


def _exec(container: str, script: str) -> str:
    return subprocess.run(["docker", "exec", "-i", container, "python3", "-"],
                          input=script, capture_output=True, text=True, check=True).stdout


def _get(container: str, path: str) -> dict:
    return json.loads(_exec(container, (
        "import urllib.request,json;"
        f"print(urllib.request.urlopen('http://localhost:8080{path}', timeout=25).read().decode())"
    )))


def _flatten(node, prefix=()) -> dict:
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_flatten(v, prefix + (k,)))
    else:
        out[".".join(prefix)] = node
    return out


def parse_native_model(output: str) -> list[dict]:
    """Read the native client's LD/LN/DO hierarchy, not the HTTP model mirror."""
    rows = []
    ld = None
    row = None
    for line in output.splitlines():
        match = re.fullmatch(r"LD: (\S+)", line)
        if match:
            ld, row = match[1], None
        elif match := re.fullmatch(r"  LN: (\S+)", line):
            if ld is None:
                raise ValueError("native browse returned LN before LD")
            row = {"logical_device": ld, "logical_node": match[1], "data_objects": []}
            rows.append(row)
        elif match := re.fullmatch(r"    DO: (\S+)", line):
            if row is None:
                raise ValueError("native browse returned DO before LN")
            row["data_objects"].append(match[1])
    if not rows or len({(r['logical_device'], r['logical_node']) for r in rows}) != len(rows):
        raise ValueError("empty or duplicate native model")
    for row in rows:
        row['data_objects'] = sorted(set(row['data_objects']))
    return sorted(rows, key=lambda r: (r['logical_device'], r['logical_node']))


def main() -> int:
    container = subprocess.run(
        ["docker", "run", "-d", "--rm", IMAGE], capture_output=True, text=True,
        check=True).stdout.strip()[:12]
    print(f"started fresh {IMAGE} as {container}")
    try:
        for _ in range(30):
            try:
                _get(container, "/health")
                break
            except Exception:
                time.sleep(2)

        native = subprocess.run(
            ["docker", "exec", container, "mms_client", "-h", "127.0.0.1", "-p", "102", "discover"],
            capture_output=True, text=True, check=True, timeout=60)
        model = parse_native_model(native.stdout)
        snapshots = []
        for i in range(3):
            if i:
                time.sleep(3)
            snapshots.append(_flatten(_get(container, "/live_state")))

        first = snapshots[0]
        stable = {k: v for k, v in first.items()
                  if all(s.get(k) == v for s in snapshots[1:])}
        drifting = sorted(set(first) - set(stable))

        snapshot = {
            "model": model,
            "provenance": {
                "model_source": "native MMS mms_client discover",
                "image_id": subprocess.run(
                    ["docker", "inspect", container, "--format", "{{.Image}}"],
                    capture_output=True, text=True, check=True).stdout.strip(),
            },
            "stable": dict(sorted(stable.items())),
            "drifting": drifting,
            "iec104": _get(container, "/iec104/state"),
        }
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
        print(f"wrote {OUT}")
        print(f"  model rows: {len(snapshot['model'])}")
        print(f"  stable values: {len(stable)}   drifting: {len(drifting)}")
        for d in drifting:
            print(f"    drifting: {d}")
    finally:
        subprocess.run(["docker", "kill", container], capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
