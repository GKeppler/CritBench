#!/usr/bin/env python3
"""
Minimal IEC 104 server using c104 Python bindings.
Runs inside the IED server container on port 2404.
Pre-populates a few monitored and controllable points.
"""

from __future__ import annotations

import time
import c104


def main():
    # --- Server -----------------------------------------------------------
    server = c104.Server(
        ip="0.0.0.0",
        port=2404,
        tick_rate_ms=1000,
        max_connections=5,
    )

    station = server.add_station(common_address=1)

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

    server.start()
    print(f"[IEC104 Server] listening on :2404  (station CA=1)")

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
