#!/usr/bin/env python3
"""Ground-truth extractors for the v2 PCAP family (ADR-0003 §6).

Same contract as the SCL family: every expected answer is derived from the
capture by code, frozen into labels.json, and re-derived in CI. The extractors
use tshark, which is also what the agent has in its sandbox -- so whatever an
extractor needs in order to answer is the deterministic baseline the task is
measured against.

One deliberate constraint: nothing here depends on tshark's OUI vendor database.
The audit could not verify current OUI attribution, and a label that changes
when Wireshark ships a new manuf file is not frozen ground truth. Where vendor
identity matters, the task asks for the OUI prefix carried in the frame.
"""

from __future__ import annotations

import collections
import subprocess
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tasks" / "pcaps"
SCD_DIR = Path(__file__).resolve().parents[2] / "tasks" / "scd"

FIXTURES = {
    "goose_trip_pcap": "goose_breaker_trip.pcap",
    "sv_trip_pcapng": "Trip_Samples_Values_all_devices_240430.pcapng",
    "mms_pcapng": "MMS_Traffic_09-02-2024_12-58.pcapng",
}
NS = {"s": "http://www.iec.ch/61850/2003/SCL"}


@lru_cache(maxsize=None)
def fields(fixture: str, display_filter: str, spec: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Run one tshark field extraction and return its rows."""
    cmd = ["tshark", "-r", str(FIXTURE_DIR / FIXTURES[fixture]), "-Y", display_filter, "-T", "fields"]
    for f in spec:
        cmd += ["-e", f]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return tuple(tuple(line.split("\t")) for line in out.splitlines() if line.strip())


def _first(value: str) -> str:
    """First element of a tshark occurrence list.

    A field repeated inside one frame (svID once per ASDU) comes back
    comma-joined; every ASDU of a frame carries the same stream identity.
    """
    return value.split(",")[0] if value else value


# ---------------------------------------------------------------------------
# shared views
# ---------------------------------------------------------------------------

GOOSE_SPEC = ("frame.number", "frame.time_relative", "eth.src", "eth.dst", "goose.appid",
              "goose.gocbRef", "goose.datSet", "goose.goID", "goose.confRev",
              "goose.stNum", "goose.sqNum", "goose.timeAllowedtoLive")


def goose_rows(fixture: str = "goose_trip_pcap"):
    return [dict(zip(GOOSE_SPEC, r)) for r in fields(fixture, "goose", GOOSE_SPEC)]


SV_SPEC = ("frame.time_relative", "eth.src", "eth.dst", "sv.appid", "sv.svID",
           "sv.confRev", "sv.noASDU", "sv.smpSynch", "sv.smpCnt")


def sv_rows(fixture: str):
    out = []
    for r in fields(fixture, "sv", SV_SPEC):
        d = dict(zip(SV_SPEC, r))
        for k in ("sv.svID", "sv.confRev", "sv.smpSynch", "sv.appid"):
            d[k] = _first(d.get(k, ""))
        out.append(d)
    return out


def _streams(rows, key, take):
    """Collapse per-frame rows into one record per stream."""
    out = {}
    for r in rows:
        out.setdefault(r[key], {k: r[v] for k, v in take.items()})
    return out


# ---------------------------------------------------------------------------
# E1 -- extraction
# ---------------------------------------------------------------------------

def pcap_goose_stream_inventory() -> dict:
    s = _streams(goose_rows(), "goose.gocbRef", {
        "control_block_ref": "goose.gocbRef", "go_id": "goose.goID",
        "dataset": "goose.datSet", "conf_rev": "goose.confRev",
        "appid": "goose.appid", "destination_mac": "eth.dst", "source_mac": "eth.src"})
    return {"streams": sorted(s.values(), key=lambda x: x["control_block_ref"])}


def pcap_sv_stream_inventory() -> dict:
    s = _streams(sv_rows("goose_trip_pcap"), "sv.svID", {
        "sv_id": "sv.svID", "appid": "sv.appid", "destination_mac": "eth.dst",
        "source_mac": "eth.src", "conf_rev": "sv.confRev", "asdu_per_frame": "sv.noASDU"})
    return {"streams": sorted(s.values(), key=lambda x: x["sv_id"])}


def pcap_mms_endpoints() -> dict:
    """Who is the client and who is the server on the only MMS association."""
    rows = fields("mms_pcapng", "tcp", ("ip.src", "ip.dst", "tcp.dstport", "eth.src", "eth.dst"))
    server = collections.Counter()
    for src, dst, dport, esrc, edst in rows:
        if dport == "102":
            server[(dst, edst, src)] += 1
    (srv_ip, srv_mac, cli_ip), _ = server.most_common(1)[0]
    return {"association": {"client_ip": cli_ip, "server_ip": srv_ip,
                            "server_port": "102", "server_mac": srv_mac}}


def pcap_mms_logical_devices() -> dict:
    """Domains the client actually touched -- the v1 comment claimed 13; it is 11."""
    domains = set()
    for (d,) in fields("mms_pcapng", "mms", ("mms.domainId",)):
        for part in d.split(","):
            if part.strip():
                domains.add(part.strip())
    return {"logical_devices": sorted(domains)}


# ---------------------------------------------------------------------------
# C2 -- correlation
# ---------------------------------------------------------------------------

def pcap_goose_publisher_map() -> dict:
    """Frame-level source to the device identity the payload claims."""
    out = []
    for ref, rec in _streams(goose_rows(), "goose.gocbRef",
                             {"src": "eth.src", "ref": "goose.gocbRef"}).items():
        out.append({"control_block_ref": ref, "source_mac": rec["src"],
                    "oui": rec["src"][:8].upper(),
                    "device": ref.split("/")[0]})
    return {"publishers": sorted(out, key=lambda x: x["control_block_ref"])}


def _state_changes(rows):
    prev, events = {}, []
    for r in rows:
        key, st = r["goose.gocbRef"], r["goose.stNum"]
        if key in prev and prev[key] != st:
            events.append({"control_block_ref": key, "from_st_num": prev[key],
                           "to_st_num": st, "time": float(r["frame.time_relative"])})
        prev[key] = st
    return events


def pcap_trip_event_reconstruction() -> dict:
    """The first trip: who asserted, in what order, and how far apart.

    Sequence-of-events reconstruction is the analysis a protection engineer
    actually performs after an event, and the ordering is the part that cannot
    be recovered from any single frame.
    """
    events = _state_changes(goose_rows())
    first = min(e["time"] for e in events)
    burst = sorted([e for e in events if e["time"] - first < 1.0], key=lambda e: e["time"])
    return {
        "sequence": [{"order": i + 1, "control_block_ref": e["control_block_ref"],
                      "from_st_num": e["from_st_num"], "to_st_num": e["to_st_num"]}
                     for i, e in enumerate(burst)],
        "first_publisher": burst[0]["control_block_ref"],
    }


def pcap_sv_sync_audit() -> dict:
    """Which sampled value streams are time-synchronised, and which changed."""
    seen = collections.defaultdict(set)
    changes = []
    prev = {}
    for r in sv_rows("goose_trip_pcap"):
        sid, sync = r["sv.svID"], r["sv.smpSynch"]
        seen[sid].add(sync)
        if sid in prev and prev[sid] != sync:
            changes.append({"sv_id": sid, "from_smp_synch": prev[sid], "to_smp_synch": sync})
        prev[sid] = sync
    return {"streams": [{"sv_id": k, "smp_synch_values": sorted(v)} for k, v in sorted(seen.items())],
            "transitions": changes}


def pcap_redundancy_nodes() -> dict:
    """Nodes announcing themselves as redundancy-capable, and what else they send."""
    sup = {r[0] for r in fields("goose_trip_pcap", "hsr_prp_supervision", ("eth.src",)) if r[0]}
    publishers = {r["eth.src"] for r in goose_rows()} | {r["eth.src"] for r in sv_rows("goose_trip_pcap")}
    return {"nodes": [{"mac": m, "publishes_process_data": m in publishers} for m in sorted(sup)]}


def pcap_mms_rcb_usage() -> dict:
    """The report control blocks the client drives, and the attributes it writes."""
    rcbs = collections.defaultdict(set)
    for (item,) in fields("mms_pcapng", "mms", ("mms.itemId",)):
        for part in item.split(","):
            part = part.strip()
            if "$RP$" in part or "$BR$" in part:
                bits = part.split("$")
                name = bits[2]
                rcbs[name].add(bits[3] if len(bits) > 3 else "")
    return {"report_control_blocks": [
        {"name": n, "buffered": n.startswith("brcb"), "attributes_written": sorted(a for a in v if a)}
        for n, v in sorted(rcbs.items())]}


def pcap_sv_sample_rates() -> dict:
    """Effective sample rate per stream, derived from the capture itself."""
    rows = sv_rows("sv_trip_pcapng")
    per = collections.defaultdict(lambda: {"frames": 0, "asdu": 0, "t0": None, "t1": None})
    for r in rows:
        p = per[r["sv.svID"]]
        p["frames"] += 1
        p["asdu"] += int(r["sv.noASDU"] or 1)
        t = float(r["frame.time_relative"])
        p["t0"] = t if p["t0"] is None else min(p["t0"], t)
        p["t1"] = t if p["t1"] is None else max(p["t1"], t)
    out = []
    for sid, p in sorted(per.items()):
        span = p["t1"] - p["t0"]
        rate = round(p["asdu"] / span / 100) * 100 if span else 0
        out.append({"sv_id": sid, "asdu_per_frame": p["asdu"] // p["frames"],
                    "samples_per_second": rate})
    return {"streams": out}


# ---------------------------------------------------------------------------
# D3 -- diagnosis
# ---------------------------------------------------------------------------

def pcap_appid_collisions() -> dict:
    """APPIDs shared by publishers that a subscriber must tell apart."""
    use = collections.defaultdict(set)
    for r in goose_rows():
        use[r["goose.appid"]].add(("GOOSE", r["goose.gocbRef"]))
    for r in sv_rows("goose_trip_pcap"):
        use[r["sv.appid"]].add(("SV", r["sv.svID"]))
    return {"collisions": [
        {"appid": a, "protocol": sorted({p for p, _ in v})[0],
         "streams": sorted(s for _, s in v)}
        for a, v in sorted(use.items()) if len(v) > 1]}


def pcap_tal_audit() -> dict:
    """How long a subscriber keeps trusting stale data if a publisher is silenced."""
    s = _streams(goose_rows(), "goose.gocbRef",
                 {"tal": "goose.timeAllowedtoLive", "ref": "goose.gocbRef"})
    rows = [{"control_block_ref": k, "time_allowed_to_live_ms": int(v["tal"])}
            for k, v in sorted(s.items())]
    worst = max(rows, key=lambda r: r["time_allowed_to_live_ms"])
    return {"streams": rows, "longest_blind_window": worst["control_block_ref"]}


def pcap_unmanaged_publishers() -> dict:
    """Publishers on the wire that the station's engineering file does not know.

    A device publishing into the process bus without appearing in the SCD is
    either undocumented engineering or something that does not belong there;
    either way it is the first thing an assessment should surface.
    """
    scd = ET.parse(SCD_DIR / "KASTEL_Lab_Siemens.scd").getroot()
    ieds = {i.get("name") for i in scd.findall(".//s:IED", NS)}
    # A sampled value stream announces the smvID the engineering file gives it,
    # which is NOT the device name with a suffix: the merging unit E03A102_
    # publishes E03A102MU0103, with no underscore. Matching on a name prefix
    # reports a configured stream as rogue, so match the declared id instead.
    smv_ids = {c.get("smvID") for c in scd.findall(".//s:SampledValueControl", NS)}

    unknown = []
    seen = set()
    for r in goose_rows():
        device = r["goose.gocbRef"].split("/")[0]
        if device in seen:
            continue
        seen.add(device)
        if not any(device.startswith(name) for name in ieds):
            unknown.append({"identifier": device, "protocol": "GOOSE",
                            "source_mac": r["eth.src"]})
    for r in sv_rows("goose_trip_pcap"):
        sv_id = r["sv.svID"]
        if sv_id in seen:
            continue
        seen.add(sv_id)
        if sv_id not in smv_ids:
            unknown.append({"identifier": sv_id, "protocol": "SV",
                            "source_mac": r["eth.src"]})
    return {"unmanaged": sorted(unknown, key=lambda x: x["identifier"])}


# ---------------------------------------------------------------------------
# P4 -- planning
# ---------------------------------------------------------------------------

def pcap_goose_takeover_preconditions() -> dict:
    """What a frame must carry to be preferred over the live REL670 trip stream."""
    rows = [r for r in goose_rows() if r["goose.gocbRef"].startswith("REL670")]
    last = rows[-1]
    return {"frame": {"destination_mac": last["eth.dst"], "appid": last["goose.appid"],
                      "control_block_ref": last["goose.gocbRef"], "dataset": last["goose.datSet"],
                      "go_id": last["goose.goID"], "conf_rev": last["goose.confRev"]},
            "last_observed_st_num": int(last["goose.stNum"])}


def pcap_sv_spoof_preconditions() -> dict:
    """What a counterfeit stream must carry to pass for MU320_MU0101."""
    rows = [r for r in sv_rows("goose_trip_pcap") if r["sv.svID"] == "MU320_MU0101"]
    last = rows[-1]
    return {"frame": {"destination_mac": last["eth.dst"], "appid": last["sv.appid"],
                      "sv_id": last["sv.svID"], "conf_rev": last["sv.confRev"],
                      "asdu_per_frame": last["sv.noASDU"],
                      "smp_synch": last["sv.smpSynch"]}}


def pcap_time_source_dependency() -> dict:
    """The clock the process bus depends on, and who is already flying blind."""
    spec = ("eth.src", "ptp.v2.an.grandmasterclockidentity", "ptp.v2.an.priority1",
            "ptp.v2.an.localstepsremoved", "ptp.v2.domainnumber")
    rows = {r for r in fields("goose_trip_pcap", "ptp.v2.messagetype==0x0b", spec)}
    assert len(rows) == 1, rows
    mac, gm, prio, steps, domain = next(iter(rows))
    unsynced = sorted({r["sv.svID"] for r in sv_rows("goose_trip_pcap")
                       if r["sv.smpSynch"] == "0"})
    return {"grandmaster": {"source_mac": mac, "clock_identity": gm, "priority1": prio,
                            "steps_removed": steps, "domain": domain},
            "unsynchronised_streams": unsynced}


TRUTH = {name: fn for name, fn in sorted(globals().items())
         if name.startswith("pcap_") and callable(fn)}

UNIVERSE = {
    "pcap_appid_collisions": lambda: len({r["goose.appid"] for r in goose_rows()}
                                         | {r["sv.appid"] for r in sv_rows("goose_trip_pcap")}),
    "pcap_unmanaged_publishers": lambda: len({r["goose.gocbRef"].split("/")[0] for r in goose_rows()}
                                             | {r["sv.svID"] for r in sv_rows("goose_trip_pcap")}),
}

if __name__ == "__main__":
    import json
    for name, fn in TRUTH.items():
        print(f"--- {name}")
        print(json.dumps(fn(), indent=1)[:1200])
