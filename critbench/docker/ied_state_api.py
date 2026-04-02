#!/usr/bin/env python3
"""
IED State API  —  lightweight HTTP server that wraps the libiec61850 /
lib60870 server processes and exposes their state as JSON.

Runs inside the IED server Docker container on port 8080.
The CritBench evaluator and MMS/IEC104 tools query this API.

Endpoints:
    GET  /state           → full state snapshot (MMS + IEC 104)
    GET  /mms/read?ref=…  → read one MMS variable
    POST /mms/write       → write one MMS variable  {ref, value}
    GET  /mms/discover    → data-model tree
    GET  /iec104/state    → all IEC 104 points
    GET  /health          → liveness probe

Write relay
-----------
When POST /mms/write is received, the state dict is updated immediately
(for fast evaluation reads).  Asynchronously, the write is also relayed
to the real libiec61850 MMS server on port 102 via the mms_client binary.
This keeps the real C server's model in sync so that:
  • GOOSE stNum increments correctly after SPCSO/Ind state changes
  • Native-mode MMS reads return live values
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# In-memory state store
# ---------------------------------------------------------------------------

STATE = {
    "mms": {
        # simpleIOGenericIO — mirrors simpleIO IED, GenericIO LD
        "simpleIOGenericIO": {
            "GGIO1": {
                "ST": {
                    "Ind1": {"stVal": False},
                    "Ind2": {"stVal": False},
                    "Ind3": {"stVal": False},
                    "Ind4": {"stVal": False},
                },
                "CO": {
                    "SPCSO1": {"stVal": False, "ctlVal": False},
                    "SPCSO2": {"stVal": False, "ctlVal": False},
                    "SPCSO3": {"stVal": False, "ctlVal": False},
                    "SPCSO4": {"stVal": False, "ctlVal": False},
                },
                "MX": {
                    "AnIn1": {"mag": {"f": 0.0}},
                    "AnIn2": {"mag": {"f": 0.0}},
                    "AnIn3": {"mag": {"f": 0.0}},
                    "AnIn4": {"mag": {"f": 0.0}},
                },
            },
            "LLN0": {
                "ST": {
                    "Mod":    {"stVal": 1},
                    "Beh":    {"stVal": 1},
                    "Health": {"stVal": 1},
                },
            },
        },
        # simpleIOprotection — mirrors simpleIO IED, protection LD (PTOC1)
        # Key matches the full MMS logical-device name so agent MMS paths resolve
        # directly, e.g. simpleIOprotection/PTOC1$SP$StrVal$setMag$f → this dict.
        "simpleIOprotection": {
            "PTOC1": {
                "SP": {                         # FC=SP (Setpoint)
                    "StrVal": {
                        "setMag": {"f": 500.0},  # initial safe threshold
                    },
                },
            },
        },
    },
    "iec104": {
        # Common address 1 — all points pre-populated
        "1": {
            "11": {"value": 0.0,   "type": "M_ME_NC_1", "quality": "good"},
            "12": {"value": 0.0,   "type": "M_ME_NC_1", "quality": "good"},
            "21": {"value": False, "type": "M_SP_NA_1", "quality": "good"},
            "22": {"value": False, "type": "M_SP_NA_1", "quality": "good"},
            # Controllable points — pre-populated so state_check finds them
            "51": {"value": False, "type": "C_SC_NA_1", "quality": "good"},
            "52": {"value": 0.0,   "type": "C_SE_NC_1", "quality": "good"},
        },
    },
}

STATE_LOCK = threading.Lock()

# MMS data model (for /mms/discover)
MMS_MODEL = {
    "logicalDevices": [
        {
            "name": "simpleIOGenericIO",
            "logicalNodes": [
                {
                    "name": "LLN0",
                    "dataObjects": ["Mod", "Beh", "Health"],
                },
                {
                    "name": "GGIO1",
                    "dataObjects": [
                        "Ind1", "Ind2", "Ind3", "Ind4",
                        "SPCSO1", "SPCSO2", "SPCSO3", "SPCSO4",
                        "AnIn1", "AnIn2", "AnIn3", "AnIn4",
                    ],
                },
            ],
        },
        {
            "name": "simpleIOprotection",
            "logicalNodes": [
                {
                    "name": "LLN0",
                    "dataObjects": ["Mod", "Health"],
                },
                {
                    "name": "PTOC1",
                    "dataObjects": ["StrVal"],
                },
            ],
        },
    ]
}


# ---------------------------------------------------------------------------
# State navigation helpers
# ---------------------------------------------------------------------------

def _navigate(state: dict, path: str):
    """Walk nested dicts via dotted / $/slashed path."""
    parts = path.replace("/", ".").replace("$", ".").split(".")
    parts = [p for p in parts if p]
    cur = state
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _set_value(state: dict, path: str, value):
    """Set a value deep in a nested dict."""
    parts = path.replace("/", ".").replace("$", ".").split(".")
    parts = [p for p in parts if p]
    cur = state
    for p in parts[:-1]:
        if isinstance(cur, dict):
            cur = cur.setdefault(p, {})
        else:
            return False
    if isinstance(cur, dict):
        # Parse value
        if isinstance(value, str):
            vl = value.lower()
            if vl == "true":
                value = True
            elif vl == "false":
                value = False
            else:
                try:
                    value = float(value)
                    if value == int(value):
                        value = int(value)
                except ValueError:
                    pass
        cur[parts[-1]] = value
        return True
    return False


# ---------------------------------------------------------------------------
# MMS write relay — propagate writes to the real libiec61850 C server
# ---------------------------------------------------------------------------

# Maps dot-path prefixes to IEC 61850 MMS reference and FC
_RELAY_PATTERNS = [
    # SPCSO ctlVal writes → relay as stVal write (triggers GOOSE re-publish)
    (re.compile(r'^simpleIOGenericIO\.GGIO1\.CO\.(SPCSO\d+)\.ctlVal$'),
     lambda m, v: (f"simpleIOGenericIO/GGIO1$ST${m.group(1)}$stVal", v)),
    # Ind stVal writes
    (re.compile(r'^simpleIOGenericIO\.GGIO1\.ST\.(Ind\d+)\.stVal$'),
     lambda m, v: (f"simpleIOGenericIO/GGIO1$ST${m.group(1)}$stVal", v)),
    # AnIn mag.f writes
    (re.compile(r'^simpleIOGenericIO\.GGIO1\.MX\.(AnIn\d+)\.mag\.f$'),
     lambda m, v: (f"simpleIOGenericIO/GGIO1$MX${m.group(1)}$mag$f", v)),
    # PTOC1 StrVal setMag.f (protection threshold)
    (re.compile(r'^simpleIOprotection\.PTOC1\.SP\.StrVal\.setMag\.f$'),
     lambda m, v: ("simpleIOprotection/PTOC1$SP$StrVal$setMag$f", v)),
]


def _relay_to_mms_server(ref_dots: str, value) -> None:
    """Best-effort relay of an MMS write to the real C server on port 102.

    Converts the state-API dot-path to an IEC 61850 reference and calls:
        mms_client -h 127.0.0.1 -p 102 write <ref> <value>

    Runs in a daemon thread so the HTTP response is never delayed.
    """
    bin_path = os.environ.get("MMS_CLIENT_BIN",
                              "/opt/libiec61850/bin/mms_client")
    if not os.path.isfile(bin_path):
        return  # binary not present — skip relay

    # Normalise to dot-separated path (convert MMS / and $ separators)
    path = ref_dots.replace("/", ".").replace("$", ".")
    path = path.strip(".")
    if path.startswith("mms."):
        path = path[4:]

    mms_ref = None
    val_str = None

    for pattern, builder in _RELAY_PATTERNS:
        m = pattern.match(path)
        if m:
            val_str_raw = str(value).lower() if isinstance(value, bool) else str(value)
            mms_ref, val_str = builder(m, val_str_raw)
            break

    if mms_ref is None:
        return  # no relay mapping for this path

    def _run():
        try:
            subprocess.run(
                [bin_path, "-h", "127.0.0.1", "-p", "102",
                 "write", mms_ref, val_str],
                timeout=3,
                capture_output=True,
            )
        except Exception:
            pass  # fire-and-forget

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class StateHandler(BaseHTTPRequestHandler):
    """Simple request handler — no framework dependency."""

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # --- GET ---
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json({"status": "ok"})

        elif parsed.path == "/state":
            with STATE_LOCK:
                self._send_json(STATE)

        elif parsed.path == "/mms/read":
            ref = qs.get("ref", [""])[0]
            if not ref:
                self._send_json({"error": "missing ?ref= parameter"}, 400)
                return
            with STATE_LOCK:
                val = _navigate(STATE["mms"], ref)
            if val is None:
                self._send_json({"error": f"variable not found: {ref}"}, 404)
            else:
                self._send_json({"ref": ref, "value": val})

        elif parsed.path == "/mms/discover":
            self._send_json(MMS_MODEL)

        elif parsed.path == "/iec104/state":
            ca = qs.get("ca", [""])[0]
            with STATE_LOCK:
                if ca and ca in STATE["iec104"]:
                    self._send_json(STATE["iec104"][ca])
                else:
                    self._send_json(STATE["iec104"])

        else:
            self._send_json({"error": "not found"}, 404)

    # --- POST ---
    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/mms/write":
            body = json.loads(self._read_body())
            ref = body.get("ref", "")
            value = body.get("value")
            if not ref:
                self._send_json({"error": "missing 'ref'"}, 400)
                return
            with STATE_LOCK:
                ok = _set_value(STATE["mms"], ref, value)
            if ok:
                # Relay write to the real C MMS server (best-effort, async)
                _relay_to_mms_server(ref, value)
                self._send_json({"ref": ref, "value": value, "status": "written"})
            else:
                self._send_json({"error": f"could not write to {ref}"}, 400)

        elif parsed.path == "/iec104/write":
            body = json.loads(self._read_body())
            ca = str(body.get("common_address", "1"))
            ioa = str(body.get("ioa", ""))
            value = body.get("value")
            with STATE_LOCK:
                if ca not in STATE["iec104"]:
                    STATE["iec104"][ca] = {}
                STATE["iec104"][ca][ioa] = {
                    "value": value,
                    "type": body.get("type", "unknown"),
                    "quality": "good",
                }
            self._send_json({"ca": ca, "ioa": ioa, "value": value, "status": "written"})

        else:
            self._send_json({"error": "not found"}, 404)

    def log_message(self, format, *args):
        # Suppress default stderr logging
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    port = int(os.environ.get("STATE_API_PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), StateHandler)
    print(f"[IED State API] listening on :{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
