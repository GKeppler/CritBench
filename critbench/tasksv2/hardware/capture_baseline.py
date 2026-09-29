#!/usr/bin/env python3
"""Record the lab's ground truth, once, so hardware tasks can be graded.

    python3 capture_baseline.py --interface eth0 --mms 10.0.19.35 10.0.19.36 \
        --out baseline/lab_baseline.json

Read-only by construction: it captures traffic and browses MMS models, and
issues no write, no control and no device restart. Run it with the lab in its
normal operating state, review the JSON it produces, and commit it. The review
matters -- whatever ends up in that file becomes the answer key, and a relay
that was in a strange state when it was captured makes a wrong key.

Re-run it after any engineering change to the lab; `validate.py --freeze`
then moves the labels and CI shows exactly which answers changed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _tshark(interface: str, display_filter: str, spec: list[str], seconds: int) -> list[dict]:
    cmd = ["tshark", "-i", interface, "-a", f"duration:{seconds}", "-Y", display_filter,
           "-T", "fields"]
    for f in spec:
        cmd += ["-e", f]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    rows = [dict(zip(spec, line.split("\t"))) for line in out.splitlines() if line.strip()]
    return rows


def _unique(rows: list[dict], key: str) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in rows:
        seen.setdefault(r.get(key, ""), r)
    return [v for k, v in sorted(seen.items()) if k]


def capture(interface: str, seconds: int) -> dict:
    goose = _unique(_tshark(interface, "goose",
                            ["goose.gocbRef", "goose.appid", "goose.datSet",
                             "goose.confRev", "eth.src", "eth.dst"], seconds),
                    "goose.gocbRef")
    sv = _unique(_tshark(interface, "sv",
                         ["sv.svID", "sv.appid", "sv.confRev", "sv.noASDU",
                          "eth.src", "eth.dst"], seconds), "sv.svID")
    sv_sync = _tshark(interface, "sv", ["sv.svID", "sv.smpSynch"], seconds)
    ptp = _unique(_tshark(interface, "ptp.v2.messagetype==0x0b",
                          ["eth.src", "ptp.v2.an.grandmasterclockidentity",
                           "ptp.v2.an.priority1", "ptp.v2.an.localstepsremoved",
                           "ptp.v2.domainnumber"], seconds), "eth.src")
    sync: dict[str, set] = {}
    for r in sv_sync:
        sync.setdefault(r["sv.svID"].split(",")[0], set()).add(r["sv.smpSynch"].split(",")[0])
    return {
        "goose": [{"control_block_ref": g["goose.gocbRef"], "appid": g["goose.appid"],
                   "dataset": g["goose.datSet"], "conf_rev": g["goose.confRev"],
                   "source_mac": g["eth.src"], "destination_mac": g["eth.dst"]} for g in goose],
        "sv": [{"sv_id": s["sv.svID"].split(",")[0], "appid": s["sv.appid"].split(",")[0],
                "conf_rev": s["sv.confRev"].split(",")[0],
                "asdu_per_frame": s["sv.noASDU"], "source_mac": s["eth.src"],
                "destination_mac": s["eth.dst"]} for s in sv],
        "sv_sync": [{"sv_id": k, "smp_synch_values": sorted(v)} for k, v in sorted(sync.items())],
        "ptp_grandmaster": ({"source_mac": ptp[0]["eth.src"],
                             "clock_identity": ptp[0]["ptp.v2.an.grandmasterclockidentity"],
                             "priority1": ptp[0]["ptp.v2.an.priority1"],
                             "steps_removed": ptp[0]["ptp.v2.an.localstepsremoved"],
                             "domain": ptp[0]["ptp.v2.domainnumber"]} if ptp else {}),
        # Filled by the operator from a reviewed MMS browse of each relay; kept
        # separate because browsing a live relay's model is not a passive
        # capture and must be a deliberate, logged action.
        "station_bus_hosts": [],
        "mms_logical_devices": [],
        "mms_datasets": [],
        "mms_rcbs": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interface", required=True)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--out", default=str(Path(__file__).parent / "baseline" / "lab_baseline.json"))
    args = ap.parse_args()
    snapshot = capture(args.interface, args.seconds)
    Path(args.out).write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out}; review it before committing")
    for key, value in snapshot.items():
        print(f"  {key}: {len(value) if isinstance(value, list) else 'dict'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
