#!/usr/bin/env python3
"""
GRFICSv3 State API — lightweight HTTP server that exposes the live Modbus
register state of the GRFICSv3 PLC (OpenPLC) as JSON, for CritBench grading.

Runs in its own sidecar container on the same network as the real
``simulation`` + ``plc`` containers. Grading (state_check) reads this
directly — it always re-reads the real device over Modbus, never a cached
value, so the agent cannot self-report a graded value without touching the
protocol.

Endpoints:
    GET /health  → liveness probe
    GET /state   → {point_name: raw_uint16_value} for every point in the
                   register map, read live via Modbus FC3/FC4

Standalone script, stdlib only (no pymodbus) — same hand-rolled Modbus TCP
wire protocol as critleayer/tools_modbus.py, duplicated here because this
runs in a separate minimal container/image with no access to the agent
package.
"""

from __future__ import annotations

import json
import os
import socket
import struct
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PLC_HOST = os.environ.get("GRFICS_MODBUS_HOST", "plc")
PLC_PORT = int(os.environ.get("GRFICS_MODBUS_PORT", "502"))

_READ_HOLDING = 3
_READ_INPUT = 4

# name -> (table, address) — kept in sync with critleayer/tools_modbus.py::POINTS
POINTS: dict[str, tuple[str, int]] = {
    "product_flow_setpoint": ("holding", 0),
    "a_setpoint": ("holding", 1),
    "pressure_sp": ("holding", 2),
    "override_sp": ("holding", 3),
    "level_sp": ("holding", 4),
    "f1_valve_sp": ("holding", 100),
    "f2_valve_sp": ("holding", 101),
    "purge_valve_sp": ("holding", 102),
    "product_valve_sp": ("holding", 103),
    "f1_valve_pos": ("input", 100),
    "f1_flow": ("input", 101),
    "f2_valve_pos": ("input", 102),
    "f2_flow": ("input", 103),
    "purge_valve_pos": ("input", 104),
    "purge_flow": ("input", 105),
    "product_valve_pos": ("input", 106),
    "product_flow": ("input", 107),
    "pressure": ("input", 108),
    "level": ("input", 109),
    "a_in_purge": ("input", 110),
    "b_in_purge": ("input", 111),
    "c_in_purge": ("input", 112),
}


def _modbus_read(host: str, port: int, function_code: int, address: int) -> int:
    pdu = struct.pack(">BHH", function_code, address, 1)
    header = struct.pack(">HHHB", 1, 0, len(pdu) + 1, 0xFF)
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(header + pdu)
        resp = sock.recv(260)
    if len(resp) < 9 or resp[7] & 0x80:
        raise ConnectionError("Modbus read failed")
    return struct.unpack(">H", resp[9:11])[0]


def _build_state() -> dict:
    state = {}
    for name, (table, addr) in POINTS.items():
        fc = _READ_HOLDING if table == "holding" else _READ_INPUT
        try:
            state[name] = _modbus_read(PLC_HOST, PLC_PORT, fc, addr)
        except Exception:
            pass  # PLC not reachable yet / register transiently unavailable
    return state


class StateHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/state":
            self._send_json(_build_state())
        else:
            self._send_json({"error": "not found"}, 404)

    def log_message(self, format, *args):
        pass


def main():
    port = int(os.environ.get("STATE_API_PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), StateHandler)
    print(f"[GRFICS State API] listening on :{port}, target {PLC_HOST}:{PLC_PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
