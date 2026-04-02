#!/usr/bin/env python3
"""
CritLayer — IEC 61850 SCL / SCD / CID analysis tools.

Parses IEC 61850 System Configuration Language (SCL) XML files in-process
using the standard library's xml.etree.ElementTree.  Returns compact,
structured summaries so the agent never reads raw multi-hundred-kB XML files
into its context window.

Supported SCL file types:
  SSD  — System Specification Description
  SCD  — Substation Configuration Description
  ICD  — IED Capability Description
  CID  — Configured IED Description
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from agents import function_tool

from .registry import register_tool

# IEC 61850-6 SCL XML namespace
_SCL_NS = {"scl": "http://www.iec.ch/61850/2003/SCL"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_scl(filepath: str) -> ET.Element | str:
    """Parse an SCL file; return root element or an error string."""
    p = Path(filepath)
    if not p.exists():
        return f"Error: file not found: {filepath}"
    try:
        tree = ET.parse(filepath)
        return tree.getroot()
    except ET.ParseError as exc:
        return f"Error: XML parse error in {filepath}: {exc}"


def _ied_summary(ied: ET.Element) -> dict:
    """Return a concise dict describing one IED element."""
    lds = [ld.get("inst") for ld in ied.findall(".//scl:LDevice", _SCL_NS)]
    gcbs = [
        {"name": g.get("name"), "datSet": g.get("datSet"), "appID": g.get("appID"),
         "confRev": g.get("confRev")}
        for g in ied.findall(".//scl:GSEControl", _SCL_NS)
    ]
    svcbs = [
        {"name": s.get("name"), "smvID": s.get("smvID"),
         "smpRate": s.get("smpRate"), "nofASDU": s.get("nofASDU"),
         "datSet": s.get("datSet")}
        for s in ied.findall(".//scl:SampledValueControl", _SCL_NS)
    ]
    return {
        "name": ied.get("name"),
        "manufacturer": ied.get("manufacturer", ""),
        "type": ied.get("type", ""),
        "desc": ied.get("desc", ""),
        "logical_devices": lds,
        "goose_control_blocks": gcbs,
        "sv_control_blocks": svcbs,
    }


# ---------------------------------------------------------------------------
# Tool: scl_get_ied_summary
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_get_ied_summary(filepath: str, ied_name: Optional[str] = None) -> str:
    """Return a compact summary of IED(s) from an SCL/SCD/CID file.

    Includes: name, manufacturer, type, description, Logical Devices,
    GOOSE Control Blocks, and Sampled Value Control Blocks.

    Args:
        filepath: Absolute path to the .scd / .cid / .icd file.
        ied_name: Optional IED name to filter results. If omitted,
                  all IEDs are returned.
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    ieds = root.findall(".//scl:IED", _SCL_NS)
    if ied_name:
        ieds = [i for i in ieds if i.get("name") == ied_name]
        if not ieds:
            all_names = [i.get("name") for i in root.findall(".//scl:IED", _SCL_NS)]
            return f"Error: IED '{ied_name}' not found. Available: {all_names}"

    result = [_ied_summary(i) for i in ieds]
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: scl_get_logical_device
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_get_logical_device(filepath: str, ied_name: str, ld_inst: str) -> str:
    """Return detailed contents of one Logical Device (LDevice) from a CID/SCD.

    Lists all Logical Nodes (LN) with their class, instance, and prefix.
    Also includes DataSets and Report/GOOSE/SV Control Blocks defined in
    this LD.

    Args:
        filepath: Path to the .scd / .cid file.
        ied_name: IED name attribute.
        ld_inst:  Logical Device instance name (e.g. "ZMF_1", "Prot").
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    ied = next((i for i in root.findall(".//scl:IED", _SCL_NS)
                if i.get("name") == ied_name), None)
    if ied is None:
        names = [i.get("name") for i in root.findall(".//scl:IED", _SCL_NS)]
        return f"Error: IED '{ied_name}' not found. Available: {names}"

    ld = next((d for d in ied.findall(".//scl:LDevice", _SCL_NS)
               if d.get("inst") == ld_inst), None)
    if ld is None:
        lds = [d.get("inst") for d in ied.findall(".//scl:LDevice", _SCL_NS)]
        return f"Error: LDevice '{ld_inst}' not found in {ied_name}. Available: {lds}"

    # LN0
    ln0 = ld.find("scl:LN0", _SCL_NS)
    ln0_info = None
    if ln0 is not None:
        ln0_info = {"lnClass": ln0.get("lnClass"), "inst": ln0.get("inst", ""),
                    "prefix": ln0.get("prefix", "")}

    # LNs
    lns = []
    for ln in ld.findall("scl:LN", _SCL_NS):
        lns.append({
            "prefix": ln.get("prefix", ""),
            "lnClass": ln.get("lnClass"),
            "inst": ln.get("inst", ""),
        })

    # DataSets
    datasets = []
    for ds in ld.findall("scl:LN0/scl:DataSet", _SCL_NS) or []:
        fcdas = []
        for f in ds.findall("scl:FCDA", _SCL_NS):
            fcdas.append({
                "ldInst": f.get("ldInst", ""),
                "prefix": f.get("prefix", ""),
                "lnClass": f.get("lnClass", ""),
                "lnInst": f.get("lnInst", ""),
                "doName": f.get("doName", ""),
                "daName": f.get("daName", ""),
                "fc": f.get("fc", ""),
            })
        datasets.append({"name": ds.get("name"), "fcda_count": len(fcdas), "fcdas": fcdas})

    # Also look for datasets directly under LN0
    if not datasets:
        ln0_el = ld.find("scl:LN0", _SCL_NS)
        if ln0_el is not None:
            for ds in ln0_el.findall("scl:DataSet", _SCL_NS):
                fcdas = []
                for f in ds.findall("scl:FCDA", _SCL_NS):
                    fcdas.append({
                        "ldInst": f.get("ldInst", ""),
                        "prefix": f.get("prefix", ""),
                        "lnClass": f.get("lnClass", ""),
                        "lnInst": f.get("lnInst", ""),
                        "doName": f.get("doName", ""),
                        "daName": f.get("daName", ""),
                        "fc": f.get("fc", ""),
                    })
                datasets.append({"name": ds.get("name"), "fcda_count": len(fcdas), "fcdas": fcdas})

    # Report Control Blocks
    rcbs = []
    ln0_el = ld.find("scl:LN0", _SCL_NS)
    if ln0_el is not None:
        for rcb in ln0_el.findall("scl:ReportControl", _SCL_NS):
            rcbs.append({
                "name": rcb.get("name"),
                "datSet": rcb.get("datSet"),
                "buffered": rcb.get("buffered"),
                "confRev": rcb.get("confRev"),
                "rptID": rcb.get("rptID", ""),
            })

    # GOOSE in this LD
    gcbs = []
    if ln0_el is not None:
        for g in ln0_el.findall("scl:GSEControl", _SCL_NS):
            gcbs.append({
                "name": g.get("name"),
                "datSet": g.get("datSet"),
                "appID": g.get("appID"),
                "confRev": g.get("confRev"),
            })

    # SV in this LD
    svcbs = []
    if ln0_el is not None:
        for s in ln0_el.findall("scl:SampledValueControl", _SCL_NS):
            svcbs.append({
                "name": s.get("name"),
                "smvID": s.get("smvID"),
                "smpRate": s.get("smpRate"),
                "nofASDU": s.get("nofASDU"),
                "datSet": s.get("datSet"),
            })

    result = {
        "ied": ied_name,
        "ld_inst": ld_inst,
        "ln0": ln0_info,
        "ln_count": len(lns),
        "logical_nodes": lns,
        "datasets": datasets,
        "report_control_blocks": rcbs,
        "goose_control_blocks": gcbs,
        "sv_control_blocks": svcbs,
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: scl_get_communication
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_get_communication(filepath: str, subnetwork_name: Optional[str] = None) -> str:
    """Return the Communication section from an SCL/SCD file.

    Shows SubNetworks and their ConnectedAPs with IP, MAC, APPID, and VLAN-ID.

    Args:
        filepath: Path to the .scd / .icd file.
        subnetwork_name: Optional SubNetwork name filter. If omitted,
                         all SubNetworks are returned.
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    comm = root.find("scl:Communication", _SCL_NS)
    if comm is None:
        return "No <Communication> section found in this SCL file."

    def _p(cap: ET.Element, ptype: str) -> list:
        return [p.text for p in cap.findall(f'.//scl:P[@type="{ptype}"]', _SCL_NS)
                if p.text]

    subnets = []
    for sn in comm.findall("scl:SubNetwork", _SCL_NS):
        name = sn.get("name")
        if subnetwork_name and name != subnetwork_name:
            continue
        caps = []
        for cap in sn.findall("scl:ConnectedAP", _SCL_NS):
            entry = {
                "iedName": cap.get("iedName"),
                "apName": cap.get("apName"),
                "IP": _p(cap, "IP"),
                "IP-SUBNET": _p(cap, "IP-SUBNET"),
                "IP-GATEWAY": _p(cap, "IP-GATEWAY"),
                "MAC-Address": _p(cap, "MAC-Address"),
                "APPID": _p(cap, "APPID"),
                "VLAN-ID": _p(cap, "VLAN-ID"),
                "VLAN-PRIORITY": _p(cap, "VLAN-PRIORITY"),
            }
            # Remove empty lists for cleaner output
            entry = {k: v for k, v in entry.items() if v}
            caps.append(entry)
        subnets.append({
            "name": name,
            "type": sn.get("type", ""),
            "connected_aps": caps,
        })

    if subnetwork_name and not subnets:
        all_names = [sn.get("name") for sn in comm.findall("scl:SubNetwork", _SCL_NS)]
        return f"SubNetwork '{subnetwork_name}' not found. Available: {all_names}"

    return json.dumps(subnets, indent=2)


# ---------------------------------------------------------------------------
# Tool: scl_get_substation
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_get_substation(filepath: str) -> str:
    """Return the Substation topology from an SCL/SCD file.

    Shows substation name, voltage levels, bays, and conducting equipment.

    Args:
        filepath: Path to the .scd / .ssd file.
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    substations = []
    for sub in root.findall("scl:Substation", _SCL_NS):
        vls = []
        for vl in sub.findall("scl:VoltageLevel", _SCL_NS):
            volt_el = vl.find("scl:Voltage", _SCL_NS)
            volt_val = None
            if volt_el is not None:
                mult = volt_el.get("multiplier", "")
                unit = volt_el.get("unit", "V")
                volt_val = f"{volt_el.text} {mult}{unit}".strip()
            bays = []
            for bay in vl.findall("scl:Bay", _SCL_NS):
                equip = []
                for ce in bay.findall(".//scl:ConductingEquipment", _SCL_NS):
                    equip.append({"name": ce.get("name"), "type": ce.get("type", "")})
                bays.append({
                    "name": bay.get("name"),
                    "desc": bay.get("desc", ""),
                    "equipment": equip,
                })
            vls.append({
                "name": vl.get("name"),
                "desc": vl.get("desc", ""),
                "voltage": volt_val,
                "bays": bays,
            })
        substations.append({
            "name": sub.get("name"),
            "desc": sub.get("desc", ""),
            "voltage_levels": vls,
        })

    if not substations:
        return "No <Substation> section found in this SCL file."

    return json.dumps(substations, indent=2)


# ---------------------------------------------------------------------------
# Tool: scl_count_ln_class
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_count_ln_class(filepath: str, ied_name: str, ln_class: str,
                       ld_inst: Optional[str] = None) -> str:
    """Count Logical Node instances of a given class in a CID/SCD file.

    Useful for counting protection function instances (e.g. PDIS, PTOC, PIOC).

    Args:
        filepath:  Path to the .scd / .cid file.
        ied_name:  IED name to search within.
        ln_class:  LN class to count (e.g. "PDIS", "PTOC", "PIOC").
        ld_inst:   Optional Logical Device to restrict the search to.
                   If omitted, all LDs are searched.
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    ied = next((i for i in root.findall(".//scl:IED", _SCL_NS)
                if i.get("name") == ied_name), None)
    if ied is None:
        names = [i.get("name") for i in root.findall(".//scl:IED", _SCL_NS)]
        return f"Error: IED '{ied_name}' not found. Available: {names}"

    lds = ied.findall(".//scl:LDevice", _SCL_NS)
    if ld_inst:
        lds = [d for d in lds if d.get("inst") == ld_inst]
        if not lds:
            all_lds = [d.get("inst") for d in ied.findall(".//scl:LDevice", _SCL_NS)]
            return f"Error: LDevice '{ld_inst}' not found. Available: {all_lds}"

    matches = []
    total = 0
    for ld in lds:
        inst = ld.get("inst")
        lns = [ln for ln in ld.findall("scl:LN", _SCL_NS)
               if ln.get("lnClass") == ln_class]
        if lns:
            names_in_ld = [
                f"{ln.get('prefix','')}{ln.get('lnClass')}{ln.get('inst','')}"
                for ln in lns
            ]
            matches.append({"ld": inst, "count": len(lns), "instances": names_in_ld})
            total += len(lns)

    return json.dumps({
        "ied": ied_name,
        "ln_class": ln_class,
        "ld_filter": ld_inst,
        "total_count": total,
        "by_ld": matches,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: scl_get_dataset
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_get_dataset(filepath: str, ied_name: str, dataset_name: str) -> str:
    """Return the full FCDA (data reference) list for a named DataSet.

    Args:
        filepath:     Path to the .scd / .cid file.
        ied_name:     IED name.
        dataset_name: DataSet name (e.g. "DS_GENERAL_TRIP", "StatNrml").
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    ied = next((i for i in root.findall(".//scl:IED", _SCL_NS)
                if i.get("name") == ied_name), None)
    if ied is None:
        names = [i.get("name") for i in root.findall(".//scl:IED", _SCL_NS)]
        return f"Error: IED '{ied_name}' not found. Available: {names}"

    for ds in ied.findall(".//scl:DataSet", _SCL_NS):
        if ds.get("name") == dataset_name:
            fcdas = []
            for f in ds.findall("scl:FCDA", _SCL_NS):
                ref = (f"{f.get('ldInst','')}/{f.get('prefix','')}"
                       f"{f.get('lnClass','')}{f.get('lnInst','')}"
                       f".{f.get('doName','')}")
                if f.get("daName"):
                    ref += f".{f.get('daName')}"
                fcdas.append({
                    "ref": ref,
                    "ldInst": f.get("ldInst", ""),
                    "prefix": f.get("prefix", ""),
                    "lnClass": f.get("lnClass", ""),
                    "lnInst": f.get("lnInst", ""),
                    "doName": f.get("doName", ""),
                    "daName": f.get("daName", ""),
                    "fc": f.get("fc", ""),
                })
            return json.dumps({
                "dataset_name": dataset_name,
                "ied": ied_name,
                "fcda_count": len(fcdas),
                "fcdas": fcdas,
            }, indent=2)

    # List available datasets if not found
    available = list({ds.get("name") for ds in ied.findall(".//scl:DataSet", _SCL_NS)})
    return f"DataSet '{dataset_name}' not found in {ied_name}. Available: {available}"


# ---------------------------------------------------------------------------
# Tool: scl_list_datasets
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_list_datasets(filepath: str, ied_name: str) -> str:
    """List all DataSets in an IED with their FCDA counts.

    Args:
        filepath: Path to the .scd / .cid file.
        ied_name: IED name.
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    ied = next((i for i in root.findall(".//scl:IED", _SCL_NS)
                if i.get("name") == ied_name), None)
    if ied is None:
        names = [i.get("name") for i in root.findall(".//scl:IED", _SCL_NS)]
        return f"Error: IED '{ied_name}' not found. Available: {names}"

    datasets = []
    for ds in ied.findall(".//scl:DataSet", _SCL_NS):
        count = len(ds.findall("scl:FCDA", _SCL_NS))
        datasets.append({"name": ds.get("name"), "fcda_count": count})

    datasets.sort(key=lambda d: d["fcda_count"], reverse=True)
    return json.dumps({
        "ied": ied_name,
        "dataset_count": len(datasets),
        "datasets": datasets,
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool: scl_list_ieds
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def scl_list_ieds(filepath: str) -> str:
    """List all IEDs in an SCL/SCD file with key metadata.

    Returns each IED's name, manufacturer, type, description,
    and count of Logical Devices.

    Args:
        filepath: Path to the .scd / .cid / .icd file.
    """
    root = _parse_scl(filepath)
    if isinstance(root, str):
        return root

    ieds = []
    for ied in root.findall(".//scl:IED", _SCL_NS):
        ld_count = len(ied.findall(".//scl:LDevice", _SCL_NS))
        gcb_count = len(ied.findall(".//scl:GSEControl", _SCL_NS))
        sv_count = len(ied.findall(".//scl:SampledValueControl", _SCL_NS))
        ieds.append({
            "name": ied.get("name"),
            "manufacturer": ied.get("manufacturer", ""),
            "type": ied.get("type", ""),
            "desc": ied.get("desc", ""),
            "ld_count": ld_count,
            "goose_cb_count": gcb_count,
            "sv_cb_count": sv_count,
        })

    return json.dumps({
        "file": filepath,
        "ied_count": len(ieds),
        "ieds": ieds,
    }, indent=2)
