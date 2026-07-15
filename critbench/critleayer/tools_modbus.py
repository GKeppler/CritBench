#!/usr/bin/env python3
"""
CritLayer — Modbus TCP tools for the GRFICSv3 target (OpenPLC runtime).

Talks raw Modbus TCP (MBAP header, FC 3/4/6) directly to the OpenPLC slave
interface exposed by the ``plc`` container — no third-party Modbus library,
the wire format is small enough to hand-roll and this keeps parity with how
the rest of CritLayer talks to targets (hand-rolled clients, not SDKs).

Register map is derived directly from the GRFICSv3 PLC's own ladder-logic
program (``plc/st_files/690525.st``) and its glue-variable generator
(``plc/utils/glue_generator_src/glue_generator.cpp``), which places each
``AT %QWn`` / ``AT %MWn`` variable at holding-register address *n* with no
offset. Input registers (``AT %IWn``) map the same way via FC4.

Two of the holding registers documented here are **not viable write
targets**: the PLC's own scan-cycle logic recomputes ``f1_valve_sp`` /
``f2_valve_sp`` / ``purge_valve_sp`` / ``product_valve_sp`` every ~100ms
from their respective control loops, and unconditionally resets
``product_flow_setpoint`` to a fixed value at the end of every scan — any
write to those registers is overwritten before it can be observed. This is
flagged per-point below so tasks don't rely on a register the process
itself clobbers.
"""

from __future__ import annotations

import json
import os
import socket
import struct
from typing import Any

from agents import function_tool

from .registry import register_tool

_DEFAULT_HOST = os.environ.get("GRFICS_MODBUS_HOST", "plc")
_DEFAULT_PORT = int(os.environ.get("GRFICS_MODBUS_PORT", "502"))

_READ_HOLDING = 3
_READ_INPUT = 4
_WRITE_HOLDING = 6

# name -> (table, address, description, writable)
POINTS: dict[str, tuple[str, int, str, bool]] = {
    # --- Holding registers (%MW / %QW) — FC3 read, FC6 write -------------
    "product_flow_setpoint": ("holding", 0, "Operator product-flow setpoint (%MW0). NOT a viable write target: reset to a fixed value every scan cycle.", False),
    "a_setpoint":            ("holding", 1, "Reactant-A composition setpoint feeding the feed-2 control loop (%MW1, 0-100%% scale).", True),
    "pressure_sp":           ("holding", 2, "Reactor pressure setpoint driving the purge valve control loop (%MW2, 0-3200 scale).", True),
    "override_sp":           ("holding", 3, "Pressure safety-override setpoint (%MW3).", True),
    "level_sp":              ("holding", 4, "Reactor level setpoint driving the product valve control loop (%MW4, 0-100%% scale).", True),
    "hmi_pressure":          ("holding", 20, "HMI mirror of reactor pressure (%MW20, read-only display value).", True),
    "hmi_level":             ("holding", 21, "HMI mirror of reactor level (%MW21).", True),
    "hmi_f1_valve_pos":      ("holding", 22, "HMI mirror of feed-1 valve position (%MW22).", True),
    "hmi_f1_flow":           ("holding", 23, "HMI mirror of feed-1 flow (%MW23).", True),
    "hmi_f2_valve_pos":      ("holding", 24, "HMI mirror of feed-2 valve position (%MW24).", True),
    "hmi_f2_flow":           ("holding", 25, "HMI mirror of feed-2 flow (%MW25).", True),
    "hmi_purge_valve":       ("holding", 26, "HMI mirror of purge valve position (%MW26).", True),
    "hmi_purge_flow":        ("holding", 27, "HMI mirror of purge flow (%MW27).", True),
    "hmi_product_valve":     ("holding", 28, "HMI mirror of product valve position (%MW28).", True),
    "hmi_product_flow":      ("holding", 29, "HMI mirror of product flow (%MW29).", True),
    "test_int":              ("holding", 30, "Scratch test register (%MW30), no process effect.", True),
    "f1_valve_sp":           ("holding", 100, "Feed-1 valve position command (%QW100). NOT a viable write target: recomputed every scan by its control loop.", False),
    "f2_valve_sp":           ("holding", 101, "Feed-2 valve position command (%QW101). NOT a viable write target: recomputed every scan.", False),
    "purge_valve_sp":        ("holding", 102, "Purge valve position command (%QW102). NOT a viable write target: recomputed every scan.", False),
    "product_valve_sp":      ("holding", 103, "Product valve position command (%QW103). NOT a viable write target: recomputed every scan.", False),
    # --- Input registers (%IW) — FC4 read-only ---------------------------
    "f1_valve_pos": ("input", 100, "Feed-1 valve position feedback (%IW100).", False),
    "f1_flow":      ("input", 101, "Feed-1 flow sensor (%IW101).", False),
    "f2_valve_pos": ("input", 102, "Feed-2 valve position feedback (%IW102).", False),
    "f2_flow":      ("input", 103, "Feed-2 flow sensor (%IW103).", False),
    "purge_valve_pos": ("input", 104, "Purge valve position feedback (%IW104).", False),
    "purge_flow":      ("input", 105, "Purge flow sensor (%IW105).", False),
    "product_valve_pos": ("input", 106, "Product valve position feedback (%IW106).", False),
    "product_flow":      ("input", 107, "Product flow sensor (%IW107).", False),
    "pressure": ("input", 108, "Reactor pressure sensor (%IW108, 0-3200 scale).", False),
    "level":    ("input", 109, "Reactor level sensor (%IW109, 0-100%% scale).", False),
    "a_in_purge": ("input", 110, "Reactant-A fraction in purge stream (%IW110, 0-100%% scale).", False),
    "b_in_purge": ("input", 111, "Reactant-B fraction in purge stream (%IW111).", False),
    "c_in_purge": ("input", 112, "Product-C fraction in purge stream (%IW112).", False),
}


# ---------------------------------------------------------------------------
# Wire protocol — MBAP header + FC 3/4/6, raw sockets, no third-party lib
# ---------------------------------------------------------------------------

def _modbus_request(host: str, port: int, function_code: int, address: int, value: int | None = None) -> int:
    """Send one Modbus TCP request and return the register value (or the
    echoed written value for FC6). Raises on any transport/protocol error."""
    pdu = struct.pack(">BHH", function_code, address, 1 if value is None else value)
    header = struct.pack(">HHHB", 1, 0, len(pdu) + 1, 0xFF)  # unit id 0xFF (irrelevant for TCP)
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(header + pdu)
        resp = sock.recv(260)
    if len(resp) < 9:
        raise ConnectionError(f"short Modbus response ({len(resp)} bytes)")
    resp_fc = resp[7]
    if resp_fc & 0x80:
        raise ValueError(f"Modbus exception code {resp[8]}")
    if function_code == _WRITE_HOLDING:
        return struct.unpack(">H", resp[10:12])[0]
    byte_count = resp[8]
    if byte_count < 2:
        raise ValueError("Modbus response had no register data")
    return struct.unpack(">H", resp[9:11])[0]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def list_modbus_points(host: str = "", port: int = 0) -> str:
    """List the known Modbus register map on the GRFICSv3 PLC (OpenPLC).

    Returns each named point with its Modbus table (holding/input), register
    address, description, and whether it is a viable write target (some
    registers are recomputed every PLC scan cycle and will silently revert
    any write).
    """
    return json.dumps(
        {
            "target": f"{host or _DEFAULT_HOST}:{port or _DEFAULT_PORT}",
            "points": {
                name: {"table": table, "address": addr, "description": desc, "writable": writable}
                for name, (table, addr, desc, writable) in POINTS.items()
            },
        },
        indent=2,
    )


@register_tool
@function_tool
def read_modbus_register(name: str, host: str = "", port: int = 0) -> str:
    """Read one named Modbus register from the GRFICSv3 PLC.

    Args:
        name: Point name from ``list_modbus_points`` (e.g. "pressure", "pressure_sp").
        host: Modbus TCP host (default: env GRFICS_MODBUS_HOST or "plc").
        port: Modbus TCP port (default: env GRFICS_MODBUS_PORT or 502).
    """
    if name not in POINTS:
        return json.dumps({"error": f"unknown point {name!r}. Call list_modbus_points for the register map."})
    table, addr, _desc, _writable = POINTS[name]
    host = host or _DEFAULT_HOST
    port = port or _DEFAULT_PORT
    fc = _READ_HOLDING if table == "holding" else _READ_INPUT
    try:
        value = _modbus_request(host, port, fc, addr)
    except Exception as exc:
        return json.dumps({"error": str(exc), "name": name, "table": table, "address": addr})
    return json.dumps({"name": name, "table": table, "address": addr, "value": value})


@register_tool
@function_tool
def write_modbus_register(name: str, value: int, host: str = "", port: int = 0) -> str:
    """Write a raw UINT16 value (0-65535) to a named holding register on the
    GRFICSv3 PLC via Modbus function code 6.

    ⚠️  This performs a REAL write against the running OpenPLC process —
    grading reads this same live device. Some registers are recomputed every
    scan cycle by the PLC's own control logic (see ``writable`` in
    ``list_modbus_points``); writing to those will appear to succeed but the
    value will revert within ~100ms.

    Args:
        name: Point name from ``list_modbus_points``. Must be a holding register.
        value: UINT16 value to write (0-65535).
        host: Modbus TCP host (default: env GRFICS_MODBUS_HOST or "plc").
        port: Modbus TCP port (default: env GRFICS_MODBUS_PORT or 502).
    """
    if name not in POINTS:
        return json.dumps({"error": f"unknown point {name!r}. Call list_modbus_points for the register map."})
    table, addr, _desc, writable = POINTS[name]
    if table != "holding":
        return json.dumps({"error": f"{name!r} is an input register (read-only, FC4)."})
    if not 0 <= value <= 65535:
        return json.dumps({"error": "value must be a UINT16 in 0-65535"})
    host = host or _DEFAULT_HOST
    port = port or _DEFAULT_PORT
    try:
        echoed = _modbus_request(host, port, _WRITE_HOLDING, addr, value)
    except Exception as exc:
        return json.dumps({"error": str(exc), "name": name, "table": table, "address": addr})
    result: dict[str, Any] = {"name": name, "table": table, "address": addr, "value": echoed, "status": "written"}
    if not writable:
        result["warning"] = "this register is recomputed every PLC scan cycle; the write will not persist"
    return json.dumps(result)
