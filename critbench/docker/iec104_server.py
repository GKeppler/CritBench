#!/usr/bin/env python3
"""
Minimal IEC 104 server using c104 Python bindings.
Runs inside the IED server container on port 2404.
Pre-populates a few monitored and controllable points.

Verifiable state (anti reward-hack)
-----------------------------------
Command points (IOA 51, 52) register an on_receive handler so that a real
IEC 104 command actually *reflects* into the server point value.  The full
point table is mirrored to a trusted JSON store (TRUSTED_STORE) that ONLY
this server process writes.  The state API serves grading reads from that
store, so a graded value can only change if a real command reached the real
server — the agent (in a separate container) cannot write it directly.
"""

# NB: no `from __future__ import annotations` here — c104 validates the
# on_receive callback's REAL type annotations (c104.Point etc.), and the
# future import would stringify them and fail that check.

import json
import os
import tempfile
import threading
import time

import c104

# Trusted store — written only by this server, read by the state API.
TRUSTED_STORE = os.environ.get(
    "IEC104_TRUSTED_STORE", "/tmp/critbench_iec104_state.json"
)

_STORE_LOCK = threading.Lock()

# In-memory mirror: {common_address: {ioa: {"value":..,"type":..,"quality":..}}}
_STORE: dict = {}


def _persist() -> None:
    """Atomically write the mirror to the trusted store file."""
    with _STORE_LOCK:
        data = json.dumps(_STORE)
    d = os.path.dirname(TRUSTED_STORE) or "."
    try:
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.replace(tmp, TRUSTED_STORE)
    except OSError as exc:
        print(f"[IEC104 Server] could not persist trusted store: {exc}")


def _record(ca: int, ioa: int, value, type_name: str) -> None:
    with _STORE_LOCK:
        _STORE.setdefault(str(ca), {})[str(ioa)] = {
            "value": value,
            "type": type_name,
            "quality": "good",
        }
    _persist()


def _make_handler(ca: int, ioa: int, type_name: str):
    """Build an on_receive handler that reflects a received command.

    c104 validates the callback signature STRICTLY: it must be exactly
    (point, previous_info, message) -> ResponseState, with those parameter
    names. On receipt, point.value already holds the commanded value.
    """
    def _handler(point: c104.Point,
                 previous_info: c104.Information,
                 message: c104.IncomingMessage) -> c104.ResponseState:
        try:
            _record(ca, ioa, point.value, type_name)
        except Exception as exc:  # never let a handler crash the server
            print(f"[IEC104 Server] handler error IOA={ioa}: {exc}")
        return c104.ResponseState.SUCCESS

    return _handler


def main():
    # --- Server -----------------------------------------------------------
    server = c104.Server(
        ip="0.0.0.0",
        port=2404,
        tick_rate_ms=1000,
        max_connections=5,
    )

    ca = 1
    station = server.add_station(common_address=ca)

    # Monitored: measured floating-point values (M_ME_NC_1 = 13)
    p_anin1 = station.add_point(io_address=11, type=c104.Type.M_ME_NC_1)
    p_anin2 = station.add_point(io_address=12, type=c104.Type.M_ME_NC_1)

    # Monitored: single-point indications (M_SP_NA_1 = 1)
    p_sp1 = station.add_point(io_address=21, type=c104.Type.M_SP_NA_1)
    p_sp2 = station.add_point(io_address=22, type=c104.Type.M_SP_NA_1)

    # Controllable: single command (C_SC_NA_1 = 45)
    p_ctrl1 = station.add_point(io_address=51, type=c104.Type.C_SC_NA_1)

    # Controllable: setpoint float (C_SE_NC_1 = 50)
    p_ctrl2 = station.add_point(io_address=52, type=c104.Type.C_SE_NC_1)

    # Set initial values
    p_anin1.value = 0.0
    p_anin2.value = 0.0
    p_sp1.value = False
    p_sp2.value = False
    p_ctrl1.value = False
    p_ctrl2.value = 0.0

    # Seed the trusted store with the initial point table so /iec104/state
    # and grading reflect the real (pre-command) server state.
    _record(ca, 11, 0.0, "M_ME_NC_1")
    _record(ca, 12, 0.0, "M_ME_NC_1")
    _record(ca, 21, False, "M_SP_NA_1")
    _record(ca, 22, False, "M_SP_NA_1")
    _record(ca, 51, False, "C_SC_NA_1")
    _record(ca, 52, 0.0, "C_SE_NC_1")

    # Reflect real commands into the trusted store. on_receive is a METHOD
    # (register the callback), not a settable attribute.
    try:
        p_ctrl1.on_receive(callable=_make_handler(ca, 51, "C_SC_NA_1"))
        p_ctrl2.on_receive(callable=_make_handler(ca, 52, "C_SE_NC_1"))
    except Exception as exc:
        print(f"[IEC104 Server] WARNING: on_receive registration failed: {exc}")

    server.start()
    print(f"[IEC104 Server] listening on :2404  (station CA={ca})")
    print(f"[IEC104 Server] trusted store: {TRUSTED_STORE}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        print("[IEC104 Server] stopped")


if __name__ == "__main__":
    main()
