#!/usr/bin/env python3
"""
Self-check for the hand-rolled Modbus TCP wire protocol in
critleayer/tools_modbus.py (and its duplicate in docker/grfics_state_api.py).

Runs a minimal fake Modbus TCP slave in-process (no GRFICSv3 containers
needed) and asserts FC3/FC4 reads and FC6 writes round-trip correctly.

Usage: python3 docker/test/test_modbus_wire.py
"""

from __future__ import annotations

import socket
import struct
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from critleayer.tools_modbus import _modbus_request  # noqa: E402


def _fake_slave(sock: socket.socket, holding: dict[int, int], input_regs: dict[int, int]):
    # tools_modbus opens one fresh TCP connection per call, so accept in a loop.
    while True:
        try:
            conn, _ = sock.accept()
        except OSError:
            return
        with conn:
            req = conn.recv(260)
            if not req:
                continue
            addr, count = struct.unpack(">HH", req[8:12])
            fc = req[7]
            if fc == 6:  # write single holding register
                value = count  # third field is the value for FC6
                holding[addr] = value
                conn.sendall(req[:12])  # FC6 response echoes the request
            elif fc == 3:
                val = holding.get(addr, 0)
                conn.sendall(req[:8] + struct.pack(">BH", 2, val))
            elif fc == 4:
                val = input_regs.get(addr, 0)
                conn.sendall(req[:8] + struct.pack(">BH", 2, val))
            else:
                resp = bytearray(req[:9])
                resp[7] |= 0x80
                resp[8] = 0x01
                conn.sendall(bytes(resp))


def main() -> None:
    holding: dict[int, int] = {2: 55295}
    input_regs: dict[int, int] = {108: 1200}

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()

    t = threading.Thread(target=_fake_slave, args=(srv, holding, input_regs), daemon=True)
    t.start()

    assert _modbus_request(host, port, 3, 2) == 55295, "FC3 read of pressure_sp failed"
    assert _modbus_request(host, port, 4, 108) == 1200, "FC4 read of pressure failed"
    written = _modbus_request(host, port, 6, 2, 60000)
    assert written == 60000, f"FC6 write echo mismatch: {written}"
    assert _modbus_request(host, port, 3, 2) == 60000, "FC3 read-back after write failed"

    print("[PASS] Modbus TCP wire protocol: FC3 read, FC4 read, FC6 write + read-back")


if __name__ == "__main__":
    main()
