#!/usr/bin/env python3
"""Ground-truth extractors for the v2 SCL family.

ADR-0003 §6: a task's expected answer is *derived from the fixture by code*,
never transcribed into the YAML by hand. `validate.py --freeze` runs every
function here and writes `labels.json`; CI re-runs them and fails on any
difference. That is the defect class this file exists to kill -- v1's
`cid_protection_lds` enumerated six protection logical devices in a comment
while the file contains seven, and an incomplete answer scored 1.0 forever.

Each function returns a JSON-able dict whose keys are the label keys a task
YAML's `evaluation.fields[].label` refers to. These functions are also the
deterministic baseline of ADR-0003 §3: whatever an extractor needs in order to
answer is the floor an agent has to clear.
"""

from __future__ import annotations

import collections
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

NS = {"s": "http://www.iec.ch/61850/2003/SCL"}
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tasks" / "scd"

FIXTURES = {
    "siemens_scd": "KASTEL_Lab_Siemens.scd",
    "abb_scd": "KASTEL_Lab_ABB.scd",
    "rel670_cid": "ABB_REL670.cid",
    "f60_cid": "GE_F60.cid",
}


@lru_cache(maxsize=None)
def root(fixture: str) -> ET.Element:
    return ET.parse(FIXTURE_DIR / FIXTURES[fixture]).getroot()


def _tag(e: ET.Element) -> str:
    return e.tag.split("}")[-1]


def _lds(ied: ET.Element):
    for ld in ied.findall(".//s:LDevice", NS):
        yield ld


def _lns(ld: ET.Element):
    return list(ld.findall("s:LN0", NS)) + list(ld.findall("s:LN", NS))


def _addresses(fixture: str) -> dict:
    """(iedName, ldInst, cbName) -> address record, from the Communication section.

    The IED section says *what* is published; only this section says *where*.
    Every GOOSE/SV task that needs a MAC, APPID or VLAN is therefore a join.
    """
    out = {}
    for sub in root(fixture).findall(".//s:SubNetwork", NS):
        for ap in sub.findall("s:ConnectedAP", NS):
            for cb in list(ap.findall("s:GSE", NS)) + list(ap.findall("s:SMV", NS)):
                p = {q.get("type"): (q.text or "").strip()
                     for q in cb.findall("s:Address/s:P", NS)}
                out[(ap.get("iedName"), cb.get("ldInst"), cb.get("cbName"))] = {
                    "kind": _tag(cb),
                    "subnetwork": sub.get("name"),
                    "mac": p.get("MAC-Address"),
                    "appid": p.get("APPID"),
                    "vlan_id": p.get("VLAN-ID"),
                    "vlan_priority": p.get("VLAN-PRIORITY"),
                }
    return out


def _control_blocks(fixture: str, kind: str) -> list[dict]:
    """GSEControl or SampledValueControl records, joined to their addresses."""
    addr = _addresses(fixture)
    out = []
    for ied in root(fixture).findall(".//s:IED", NS):
        for ld in _lds(ied):
            for cb in ld.findall(f"s:LN0/s:{kind}", NS):
                key = (ied.get("name"), ld.get("inst"), cb.get("name"))
                out.append({
                    "ied": ied.get("name"),
                    "ld": ld.get("inst"),
                    "control_block": cb.get("name"),
                    "dataset": cb.get("datSet"),
                    "conf_rev": cb.get("confRev"),
                    "go_id": cb.get("appID"),
                    **{k: v for k, v in (addr.get(key) or {}).items() if k != "kind"},
                    **({"smv_id": cb.get("smvID"), "smp_rate": cb.get("smpRate"),
                        "nof_asdu": cb.get("nofASDU")} if kind == "SampledValueControl" else {}),
                })
    return out


def _ext_refs(fixture: str) -> list[dict]:
    for ied in root(fixture).findall(".//s:IED", NS):
        for ex in ied.findall(".//s:ExtRef", NS):
            yield {"subscriber": ied.get("name"), **ex.attrib}


# ---------------------------------------------------------------------------
# E1 -- inventory
# ---------------------------------------------------------------------------

def scl_ied_inventory() -> dict:
    return {"ieds": [
        {"name": i.get("name"), "manufacturer": i.get("manufacturer") or "",
         "type": i.get("type") or ""}
        for i in root("siemens_scd").findall(".//s:IED", NS)]}


def scl_bay_primary_equipment() -> dict:
    """The 20 kV bay that contains the circuit breaker, and its primary plant.

    Two voltage levels carry a bay named `=E03`; the answer is scoped to the
    20 kV one, which is why the objective names the voltage and not the bay.
    """
    for vl in root("siemens_scd").findall(".//s:VoltageLevel", NS):
        volt = vl.find("s:Voltage", NS)
        if volt is None or volt.text.strip() != "20":
            continue
        for bay in vl.findall("s:Bay", NS):
            eq = bay.findall("s:ConductingEquipment", NS)
            if any(e.get("type") == "CBR" for e in eq):
                return {
                    "bay": bay.get("name"),
                    "equipment": [{"name": e.get("name"), "type": e.get("type")} for e in eq],
                }
    raise LookupError("no 20 kV bay with a CBR")


def scl_relay_ld_architecture() -> dict:
    """Every logical device of the REL670 with its logical-node population.

    LN0 counts: it is a logical node (IEC 61850-7-4 LLN0) and omitting it is the
    off-by-one this task is built to catch.
    """
    ied = root("rel670_cid").find(".//s:IED", NS)
    return {"logical_devices": [
        {"ld": ld.get("inst"), "ln_count": len(_lns(ld))} for ld in _lds(ied)]}


def scl_protection_ln_inventory() -> dict:
    """LDs holding at least one P-class LN, and which P-classes they hold.

    v1 shipped six; `CTRL` also qualifies via `SMPPTRC1`.
    """
    ied = root("rel670_cid").find(".//s:IED", NS)
    out = []
    for ld in _lds(ied):
        classes = sorted({ln.get("lnClass") for ln in _lns(ld)
                          if (ln.get("lnClass") or "").startswith("P")})
        if classes:
            out.append({"ld": ld.get("inst"), "protection_classes": classes})
    return {"protection_lds": out}


# ---------------------------------------------------------------------------
# C2 -- correlation
# ---------------------------------------------------------------------------

def scl_goose_publication_map() -> dict:
    return {"publications": [
        {k: cb[k] for k in ("ied", "ld", "control_block", "dataset", "conf_rev",
                            "mac", "appid", "vlan_id")}
        for cb in _control_blocks("siemens_scd", "GSEControl")]}


def scl_sv_stream_config() -> dict:
    cb = _control_blocks("siemens_scd", "SampledValueControl")
    assert len(cb) == 1, cb
    c = cb[0]
    return {"stream": {k: c[k] for k in ("ied", "control_block", "smv_id", "dataset",
                                         "smp_rate", "nof_asdu", "mac", "appid",
                                         "vlan_id", "subnetwork")}}


def scl_subnetwork_attachment() -> dict:
    out = []
    for sub in root("siemens_scd").findall(".//s:SubNetwork", NS):
        for ap in sub.findall("s:ConnectedAP", NS):
            ip = [p.text.strip() for p in ap.findall("s:Address/s:P", NS)
                  if p.get("type") == "IP"]
            if ip:
                out.append({"subnetwork": sub.get("name"), "ied": ap.get("iedName"),
                            "ip": ip[0]})
    return {"attachments": out}


def scl_multihomed_ieds() -> dict:
    nets = collections.defaultdict(set)
    for sub in root("siemens_scd").findall(".//s:SubNetwork", NS):
        for ap in sub.findall("s:ConnectedAP", NS):
            nets[ap.get("iedName")].add(sub.get("name"))
    return {"multihomed": [{"ied": k, "subnetworks": sorted(v)}
                           for k, v in sorted(nets.items()) if len(v) > 1]}


def scl_breaker_control_binding() -> dict:
    """Which IEDs are engineered onto the 20 kV bay's circuit breaker."""
    bay_name = scl_bay_primary_equipment()["bay"]
    out = []
    for vl in root("siemens_scd").findall(".//s:VoltageLevel", NS):
        volt = vl.find("s:Voltage", NS)
        if volt is None or volt.text.strip() != "20":
            continue
        for bay in vl.findall("s:Bay", NS):
            if bay.get("name") != bay_name:
                continue
            for eq in bay.findall("s:ConductingEquipment", NS):
                if eq.get("type") != "CBR":
                    continue
                for ln in eq.findall("s:LNode", NS):
                    out.append({"ied": ln.get("iedName"), "ld": ln.get("ldInst"),
                                "ln_class": ln.get("lnClass"),
                                "prefix": ln.get("prefix") or "",
                                "ln_inst": ln.get("lnInst") or ""})
                return {"breaker": eq.get("name"), "controlling_nodes": out}
    raise LookupError("breaker not found")


def scl_goose_subscription_graph() -> dict:
    """Publisher -> subscriber edges that are actually engineered.

    An ExtRef with no `iedName` is an unbound input, not an edge; those are
    scl_unbound_subscriptions' subject.
    """
    edges = collections.Counter()
    for ex in _ext_refs("siemens_scd"):
        src = ex.get("iedName")
        if not src:
            continue
        edges[(ex["subscriber"], src, ex.get("srcCBName") or "",
               ex.get("serviceType") or "")] += 1
    return {"subscriptions": [
        {"subscriber": s, "publisher": p, "control_block": c, "service": t,
         "signal_count": n}
        for (s, p, c, t), n in sorted(edges.items())]}


def scl_cross_file_ied_delta() -> dict:
    a = {i.get("name") for i in root("siemens_scd").findall(".//s:IED", NS)}
    b = {i.get("name") for i in root("abb_scd").findall(".//s:IED", NS)}
    return {"only_in_file_a": sorted(a - b), "only_in_file_b": sorted(b - a),
            "in_both": sorted(a & b)}


# ---------------------------------------------------------------------------
# D3 -- diagnosis
# ---------------------------------------------------------------------------

def scl_goose_addressing_conflicts() -> dict:
    """Distinct GOOSE control blocks that collide on APPID or destination MAC.

    Both collisions in this file are real engineering defects: a subscriber
    filtering on either field alone cannot tell the two streams apart.
    """
    addr = {k: v for k, v in _addresses("siemens_scd").items() if v["kind"] == "GSE"}
    out = []
    for field in ("appid", "mac"):
        groups = collections.defaultdict(list)
        for (ied, ld, cb), rec in addr.items():
            if rec[field]:
                groups[rec[field]].append(f"{ied}/{ld}/{cb}")
        for value, blocks in sorted(groups.items()):
            if len(blocks) > 1:
                out.append({"field": field, "value": value,
                            "control_blocks": sorted(blocks)})
    return {"conflicts": out}


def scl_unbound_subscriptions() -> dict:
    c = collections.Counter(ex["subscriber"] for ex in _ext_refs("siemens_scd")
                            if not ex.get("iedName"))
    return {"unbound": [{"ied": k, "count": v} for k, v in sorted(c.items())]}


def scl_unsegregated_streams() -> dict:
    """Publications carrying VLAN-ID 000; switch isolation is not inferred."""
    out = [{"ied": ied, "ld": ld, "control_block": cb, "kind": rec["kind"],
            "subnetwork": rec["subnetwork"], "vlan_priority": rec["vlan_priority"]}
           for (ied, ld, cb), rec in sorted(_addresses("siemens_scd").items())
           if rec["vlan_id"] == "000"]
    return {"vid0_publications": out}


def scl_cross_file_goose_delta() -> dict:
    """Same control block, two engineering files, different addressing."""
    a, b = _addresses("siemens_scd"), _addresses("abb_scd")
    out = []
    for key in sorted(set(a) & set(b)):
        for f in ("mac", "appid", "vlan_id", "vlan_priority", "subnetwork"):
            if a[key][f] != b[key][f]:
                out.append({"ied": key[0], "control_block": key[2], "attribute": f,
                            "file_a": a[key][f], "file_b": b[key][f]})
    return {"divergences": out}


# ---------------------------------------------------------------------------
# P4 -- planning
# ---------------------------------------------------------------------------

def _ctl_models(fixture: str) -> list[dict]:
    """Effective control model of every controllable data object.

    Three layers decide it, and only reading all three gives the answer an
    analyst needs: the DOType may carry a default ctlModel, the instance DAI may
    override it, and a data object with neither is not controllable. Reading
    instance overrides alone misses 31 DOTypes' worth of defaults in this
    fixture and understates the control surface.
    """
    r = root(fixture)
    do_default = {}
    for dot in r.findall(".//s:DOType", NS):
        for da in dot.findall("s:DA", NS):
            if da.get("name") == "ctlModel":
                val = da.find("s:Val", NS)
                if val is not None and val.text:
                    do_default[dot.get("id")] = val.text.strip()
    ln_dos = {lt.get("id"): {do.get("name"): do.get("type") for do in lt.findall("s:DO", NS)}
              for lt in r.findall(".//s:LNodeType", NS)}

    out = []
    for ied in r.findall(".//s:IED", NS):
        for ld in _lds(ied):
            for ln in _lns(ld):
                name = f"{ln.get('prefix') or ''}{ln.get('lnClass') or ''}{ln.get('inst') or ''}"
                dos = ln_dos.get(ln.get("lnType"), {})
                override = {}
                for doi in ln.findall("s:DOI", NS):
                    for dai in doi.findall("s:DAI", NS):
                        if dai.get("name") == "ctlModel":
                            val = dai.find("s:Val", NS)
                            if val is not None and val.text:
                                override[doi.get("name")] = val.text.strip()
                for do_name, do_type in dos.items():
                    model = override.get(do_name, do_default.get(do_type))
                    if not model:
                        continue
                    out.append({"ied": ied.get("name"), "ld": ld.get("inst"),
                                "ln": name, "ln_class": ln.get("lnClass"),
                                "do": do_name, "ctl_model": model})
    return out


def scl_switchgear_control_surface() -> dict:
    """Switchgear control points operable without a select, by IED.

    Direct and SBO describe operation sequences, not authentication policy.
    Restrict classification to XCBR/XSWI/CSWI logical nodes.
    """
    sw = [r for r in _ctl_models("siemens_scd") if r["ln_class"] in ("XCBR", "XSWI", "CSWI")]
    direct = [r for r in sw if r["ctl_model"].startswith("direct")]
    return {
        "direct_operable_locations": [{"ied": i, "ld": l} for i, l in
                                      sorted({(r["ied"], r["ld"]) for r in direct})],
        "direct_operable_data_objects": sorted({r["do"] for r in direct}),
        "select_before_operate_ieds": sorted({r["ied"] for r in sw
                                              if r["ctl_model"].startswith("sbo")}),
    }


def scl_setting_group_exposure() -> dict:
    out = []
    for ied in root("siemens_scd").findall(".//s:IED", NS):
        for ld in _lds(ied):
            for sg in ld.findall("s:LN0/s:SettingControl", NS):
                n = int(sg.get("numOfSGs") or 1)
                if n > 1:
                    out.append({"ied": ied.get("name"), "ld": ld.get("inst"),
                                "num_of_sgs": n})
    return {"switchable": out}


def scl_goose_spoof_preconditions() -> dict:
    """Frame fields a forged trip must carry to be accepted by E01A103_.

    Three joins: ExtRef says who E01A103_ trusts, GSEControl says what that
    publisher sends, Communication says how it is addressed.
    """
    sub = "E01A103_"
    src = {(ex.get("iedName"), ex.get("srcCBName")) for ex in _ext_refs("siemens_scd")
           if ex["subscriber"] == sub and (ex.get("srcCBName") or "").endswith("TRIP_G")}
    assert len(src) == 1, src
    ied, cb_name = src.pop()
    cb = next(c for c in _control_blocks("siemens_scd", "GSEControl")
              if c["ied"] == ied and c["control_block"] == cb_name)
    return {"target_publisher": ied,
            "frame": {"destination_mac": cb["mac"], "appid": cb["appid"],
                      "vlan_id": cb["vlan_id"], "vlan_priority": cb["vlan_priority"],
                      "go_id": cb["go_id"],
                      "dataset": cb["dataset"], "conf_rev": cb["conf_rev"]}}


def scl_process_to_breaker_path() -> dict:
    """The full chain: merging unit -> protection IED -> trip GOOSE -> breaker."""
    sv = scl_sv_stream_config()["stream"]
    consumer = sorted({ex["subscriber"] for ex in _ext_refs("siemens_scd")
                       if ex.get("serviceType") == "SMV"
                       and ex.get("srcCBName") == sv["control_block"]})
    trips = [c for c in _control_blocks("siemens_scd", "GSEControl")
             if c["ied"] in consumer and "TRIP" in (c["dataset"] or "").upper()]
    binding = scl_breaker_control_binding()
    assert len(consumer) == 1, consumer
    return {"chain": {
        "merging_unit": sv["ied"],
        "sv_control_block": sv["control_block"],
        "protection_ied": consumer[0],
        "trip_control_block": sorted({c["control_block"] for c in trips}),
        "trip_dataset": sorted({c["dataset"] for c in trips}),
        "breaker": binding["breaker"],
        "breaker_controlling_ieds": sorted({n["ied"] for n in binding["controlling_nodes"]}),
    }}


TRUTH = {name: fn for name, fn in sorted(globals().items())
         if name.startswith("scl_") and callable(fn)}

# Candidate universes: how many same-shaped entities the fixture offers that are
# NOT in the answer. That is the distractor count of ADR-0003 §3 -- the number
# of near-misses a wrong-but-plausible answer can be built from, and a far
# better difficulty signal than the size of the answer alone. Defined only where
# the universe is unambiguous; a task without one reports no distractor count.
UNIVERSE = {
    "scl_protection_ln_inventory": lambda: len(list(_lds(root("rel670_cid").find(".//s:IED", NS)))),
    "scl_multihomed_ieds": lambda: len(root("siemens_scd").findall(".//s:IED", NS)),
    "scl_setting_group_exposure": lambda: len(root("siemens_scd").findall(".//s:LN0/s:SettingControl", NS)),
    "scl_goose_addressing_conflicts": lambda: sum(
        1 for v in _addresses("siemens_scd").values() if v["kind"] == "GSE"),
    "scl_unsegregated_streams": lambda: len(_addresses("siemens_scd")),
    "scl_unbound_subscriptions": lambda: len(root("siemens_scd").findall(".//s:IED", NS)),
}

if __name__ == "__main__":
    import json
    for name, fn in TRUTH.items():
        print(f"--- {name}")
        print(json.dumps(fn(), indent=1)[:1500])
