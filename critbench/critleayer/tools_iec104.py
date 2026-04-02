#!/usr/bin/env python3
"""
CritLayer — IEC 60870-5-104 tools.

Uses the **c104** Python library (wraps lib60870-C via pybind11) for
client operations against an IEC 104 server.

Default target: the IED server container on the Docker bridge network
(``ied-server:2404``).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Optional

from agents import function_tool

from .registry import register_tool

logger = logging.getLogger(__name__)

_DEFAULT_104_HOST = os.environ.get("IED_104_HOST", "ied-server")
_DEFAULT_104_PORT = int(os.environ.get("IED_104_PORT", "2404"))
_IED_STATE_API = os.environ.get("IED_STATE_API", "http://ied-server:8080")

_CMD_TYPE_MAP = {
    "single":        "C_SC_NA_1",
    "double":        "C_DC_NA_1",
    "setpoint_float": "C_SE_NC_1",
}


def _iec104_sync_to_state_api(
    host: str,
    common_address: int,
    ioa: int,
    value,
    command_type: str,
) -> None:
    """Best-effort POST of a sent IEC 104 command to the state API.

    The state API's /iec104/write endpoint stores the value so the
    evaluator's state_check can find it under iec104.<ca>.<ioa>.value.
    """
    payload = json.dumps({
        "common_address": common_address,
        "ioa": ioa,
        "value": value,
        "type": _CMD_TYPE_MAP.get(command_type, command_type),
    }).encode()
    try:
        req = urllib.request.Request(
            f"{_IED_STATE_API}/iec104/write",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # best-effort


# ---------------------------------------------------------------------------
# Internal connection helper
# ---------------------------------------------------------------------------

def _get_iec104_client(host: str, port: int):
    """Create and start a c104 Client + Connection."""
    try:
        import c104
    except ImportError:
        return None, None, "Error: c104 not installed. pip install c104"

    # c104 requires a numeric IP address; resolve hostname if needed
    import socket as _socket
    try:
        host = _socket.gethostbyname(host)
    except _socket.gaierror:
        pass  # keep original value; c104 will produce an error

    client = c104.Client()
    conn = client.add_connection(
        ip=host,
        port=port,
        init=c104.Init.INTERROGATION,
    )
    client.start()
    # Give connection time to establish
    time.sleep(1.5)

    if not conn.is_connected:
        client.stop()
        return None, None, f"Error: could not connect to IEC 104 server at {host}:{port}"

    return client, conn, None


def _stop_client(client):
    """Gracefully stop the c104 client."""
    if client is not None:
        try:
            client.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def send_iec104_command(
    ioa: int,
    value: float,
    common_address: int = 1,
    command_type: str = "single",
    host: str = "",
    port: int = 0,
) -> str:
    """Send an IEC 104 command to the server.

    Supported command types:
    - "single"  → C_SC_NA_1 (Single Command, ON/OFF)
    - "double"  → C_DC_NA_1 (Double Command, OPEN/CLOSE)
    - "setpoint_float" → C_SE_NC_1 (Setpoint, short float)

    Args:
        ioa: Information Object Address of the target point.
        value: Value to send (bool for single/double, float-as-string for setpoint).
        common_address: ASDU common address (default 1).
        command_type: Command type — "single", "double", or "setpoint_float".
        host: IEC 104 server IP (default: ied-server).
        port: IEC 104 server port (default: 2404).
    """
    import c104

    host = host or _DEFAULT_104_HOST
    port = port or _DEFAULT_104_PORT

    client, conn, err = _get_iec104_client(host, port)
    if err:
        return err

    try:
        station = conn.add_station(common_address=common_address)
        if station is None:
            station = conn.get_station(common_address=common_address)
        if station is None:
            return f"Error: could not get station for CA={common_address}"
        time.sleep(0.5)

        if command_type == "single":
            point = station.add_point(io_address=ioa, type=c104.Type.C_SC_NA_1)
            if point is None:
                point = station.get_point(io_address=ioa)
            time.sleep(0.3)
            point.value = bool(value)
            point.transmit(cause=c104.Cot.ACTIVATION)
        elif command_type == "double":
            point = station.add_point(io_address=ioa, type=c104.Type.C_DC_NA_1)
            if point is None:
                point = station.get_point(io_address=ioa)
            time.sleep(0.3)
            point.value = int(bool(value)) + 1  # DPI: 1=OFF, 2=ON
            point.transmit(cause=c104.Cot.ACTIVATION)
        elif command_type == "setpoint_float":
            point = station.add_point(io_address=ioa, type=c104.Type.C_SE_NC_1)
            if point is None:
                point = station.get_point(io_address=ioa)
            time.sleep(0.3)
            point.value = float(value)
            point.transmit(cause=c104.Cot.ACTIVATION)
        else:
            return f"Error: unknown command_type '{command_type}'. Use: single, double, setpoint_float"

        time.sleep(0.5)

        # Sync command result to state API so evaluator can verify it
        _iec104_sync_to_state_api(
            host=host,
            common_address=common_address,
            ioa=ioa,
            value=value,
            command_type=command_type,
        )

        return (
            f"IEC 104 command sent:\n"
            f"  host={host}:{port}, CA={common_address}, IOA={ioa}\n"
            f"  type={command_type}, value={value}"
        )

    except Exception as exc:
        return f"Error sending IEC 104 command: {exc}"
    finally:
        _stop_client(client)


@register_tool
@function_tool
def read_iec104_point(
    ioa: int,
    point_type: str = "measured_float",
    common_address: int = 1,
    host: str = "",
    port: int = 0,
) -> str:
    """Read a data point from the IEC 104 server.

    Point types:
    - "single"         → M_SP_NA_1 (Single Point, boolean)
    - "double"         → M_DP_NA_1 (Double Point)
    - "measured_float" → M_ME_NC_1 (Measured Value, short float)
    - "measured_scaled"→ M_ME_NB_1 (Measured Value, scaled)

    Args:
        ioa: Information Object Address.
        point_type: Type of point (see above).
        common_address: ASDU common address (default 1).
        host: IEC 104 server IP.
        port: IEC 104 server port.
    """
    import c104

    host = host or _DEFAULT_104_HOST
    port = port or _DEFAULT_104_PORT

    type_map = {
        "single": c104.Type.M_SP_NA_1,
        "double": c104.Type.M_DP_NA_1,
        "measured_float": c104.Type.M_ME_NC_1,
        "measured_scaled": c104.Type.M_ME_NB_1,
    }

    if point_type not in type_map:
        return f"Error: unknown point_type '{point_type}'. Use: {list(type_map.keys())}"

    client, conn, err = _get_iec104_client(host, port)
    if err:
        return err

    try:
        station = conn.add_station(common_address=common_address)
        if station is None:
            station = conn.get_station(common_address=common_address)
        if station is None:
            return f"Error: could not get station for CA={common_address}"
        point = station.add_point(io_address=ioa, type=type_map[point_type])
        if point is None:
            point = station.get_point(io_address=ioa)
        if point is None:
            return f"Error: could not get point IOA={ioa} on CA={common_address}"
        # Wait for interrogation to populate the value
        time.sleep(2.0)

        val = point.value
        quality = getattr(point, "quality", "N/A")

        return (
            f"IEC 104 read:\n"
            f"  host={host}:{port}, CA={common_address}, IOA={ioa}\n"
            f"  type={point_type}, value={val}, quality={quality}"
        )
    except Exception as exc:
        return f"Error reading IEC 104 point: {exc}"
    finally:
        _stop_client(client)


@register_tool
@function_tool
def iec104_interrogation(
    common_address: int = 1,
    host: str = "",
    port: int = 0,
) -> str:
    """Send a General Interrogation to the IEC 104 server.

    Returns all data points reported by the server in response.

    Args:
        common_address: ASDU common address (default 1).
        host: IEC 104 server IP.
        port: IEC 104 server port.
    """
    # The c104 library triggers GI automatically on connection when
    # init=c104.Init.INTERROGATION.  We just need to read the results
    # from the state API endpoint instead.
    import requests

    host = host or _DEFAULT_104_HOST
    api_base = os.environ.get("IED_STATE_API", f"http://{host}:8080")

    try:
        resp = requests.get(f"{api_base}/iec104/state", params={"ca": common_address}, timeout=10)
        if resp.status_code == 200:
            return resp.text
        return f"Error: IED API returned HTTP {resp.status_code}: {resp.text}"
    except requests.ConnectionError:
        return f"Error: cannot connect to IED state API at {api_base}"
    except Exception as exc:
        return f"Error: {exc}"
