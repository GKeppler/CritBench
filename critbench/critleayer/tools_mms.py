#!/usr/bin/env python3
"""
CritLayer — IEC 61850 MMS tools.

These tools allow the LLM agent to interact with an MMS server
(e.g. libiec61850 server_example_basic_io running in the IED container,
or a real physical IED on the network).

Two operating modes are supported (selected via ``MMS_CLIENT_MODE`` env var):

* **api** (default) — talk to the IED State API REST wrapper on port 8080.
  Used for Docker VM-interaction tasks where the IED container exposes a
  REST interface.

* **native** — shell out to the libiec61850 ``mms_utility`` binary for
  direct MMS/ISO-COTP communication.  Used for hardware tasks where the
  agent connects to a real physical IED that has no REST wrapper.
  The helper binary path is configurable via ``MMS_CLIENT_BIN``
  (default: ``/opt/libiec61850/bin/mms_utility``).

Interface binding:
  When ``BIND_INTERFACE`` is set (e.g. ``eth0``), a host route is added
  before the first MMS call so that all traffic to the target IED is
  forced through the specified network interface.  This is essential on
  multi-homed hosts where only one NIC is connected to the IED network.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional

from agents import function_tool

from .registry import register_tool

logger = logging.getLogger(__name__)

# Default target for the IED server on the Docker bridge network
_DEFAULT_MMS_HOST = os.environ.get("IED_MMS_HOST", "ied-server")
_DEFAULT_MMS_PORT = int(os.environ.get("IED_MMS_PORT", "102"))

# Native MMS client binary (custom non-interactive client built from mms_client.c)
_MMS_CLIENT_BIN = os.environ.get(
    "MMS_CLIENT_BIN",
    "/opt/libiec61850/bin/mms_client",
)

# Client mode: "api" (IED state REST) or "native" (libiec61850 binary)
_MMS_CLIENT_MODE = os.environ.get("MMS_CLIENT_MODE", "api")

# Interface binding for multi-homed hosts
_BIND_INTERFACE = os.environ.get("BIND_INTERFACE", "")

# Track whether we already set up the route (avoid repeated calls)
_ROUTE_CONFIGURED: set[str] = set()


# ---------------------------------------------------------------------------
# Interface binding helper
# ---------------------------------------------------------------------------

def _ensure_interface_route(host: str, interface: str) -> None:
    """Add a host route so traffic to *host* goes through *interface*.

    Tries ``ip route replace`` first, falls back to ``route add`` if
    the ``ip`` command is not available (e.g. minimal containers).
    Requires appropriate privileges (CAP_NET_ADMIN or root).
    """
    route_key = f"{host}:{interface}"
    if route_key in _ROUTE_CONFIGURED:
        return

    # Try 'ip route' first, then fall back to 'route add'
    commands = [
        f"ip route replace {host}/32 dev {interface}",
        f"route add -host {host} dev {interface}",
    ]

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("Interface binding: route to %s via %s configured (%s)",
                            host, interface, cmd.split()[0])
                _ROUTE_CONFIGURED.add(route_key)
                return
            # If 'not found' error, try next command
            if "not found" in result.stderr.lower():
                continue
            # Other error — log but still try next
            logger.warning("Route cmd failed (rc=%d): %s — %s",
                           result.returncode, cmd, result.stderr.strip())
        except Exception as exc:
            logger.warning("Interface binding error (%s): %s", cmd, exc)

    logger.warning("Could not configure interface route for %s via %s", host, interface)


# ---------------------------------------------------------------------------
# REST API mode (Docker / VM-interaction tasks)
# ---------------------------------------------------------------------------

def _mms_api_cmd(host: str, port: int, action: str, extra_args: list[str] | None = None) -> str:
    """Call the IED server's state-query HTTP API.

    The IED server container exposes a lightweight REST API on port 8080 that
    wraps MMS read/write/discover operations and returns JSON.
    """
    import requests

    api_base = os.environ.get(
        "IED_STATE_API",
        f"http://{host}:8080",
    )

    try:
        if action == "read":
            ref = extra_args[0] if extra_args else ""
            resp = requests.get(f"{api_base}/mms/read", params={"ref": ref}, timeout=10)
        elif action == "write":
            ref = extra_args[0] if extra_args else ""
            value = extra_args[1] if extra_args and len(extra_args) > 1 else ""
            resp = requests.post(
                f"{api_base}/mms/write",
                json={"ref": ref, "value": value},
                timeout=10,
            )
        elif action == "discover":
            resp = requests.get(f"{api_base}/mms/discover", timeout=10)
        else:
            return f"Error: unknown MMS action '{action}'"

        if resp.status_code == 200:
            return resp.text
        return f"Error: IED API returned HTTP {resp.status_code}: {resp.text}"

    except requests.ConnectionError:
        return f"Error: cannot connect to IED state API at {api_base}. Is the IED server running?"
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Native binary mode (hardware / physical IED tasks)
# ---------------------------------------------------------------------------

def _mms_native_cmd(host: str, port: int, action: str, extra_args: list[str] | None = None) -> str:
    """Shell out to the libiec61850 MMS client binary for direct communication.

    Supports three actions:
    * ``discover`` — list the full MMS data model (Logical Devices,
      Logical Nodes, Data Objects).
    * ``read``     — read a single MMS variable by IEC 61850 reference.
    * ``write``    — write a value to an MMS variable.

    The binary is expected at ``_MMS_CLIENT_BIN`` and should accept::

        mms_utility -h <host> -p <port> discover
        mms_utility -h <host> -p <port> read <reference>
        mms_utility -h <host> -p <port> write <reference> <value>

    If the binary is not found, falls back to a Python-based MMS helper.
    """
    mms_bin = _MMS_CLIENT_BIN

    # Build command
    cmd: list[str] = [mms_bin, "-h", host, "-p", str(port)]

    if action == "discover":
        cmd.append("discover")
    elif action == "read":
        ref = extra_args[0] if extra_args else ""
        if not ref:
            return "Error: read action requires an IEC 61850 object reference"
        cmd.extend(["read", ref])
    elif action == "write":
        ref = extra_args[0] if extra_args else ""
        value = extra_args[1] if extra_args and len(extra_args) > 1 else ""
        if not ref:
            return "Error: write action requires an IEC 61850 object reference"
        cmd.extend(["write", ref, value])
    else:
        return f"Error: unknown MMS action '{action}'"

    # Check if binary exists
    if not os.path.isfile(mms_bin):
        # Fall back to Python helper (iec61850 pip package or raw socket)
        return _mms_python_fallback(host, port, action, extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            errors="replace",
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            return f"Error (exit {result.returncode}): {err}\n{output}"
        return output or "(no output)"
    except FileNotFoundError:
        return _mms_python_fallback(host, port, action, extra_args)
    except subprocess.TimeoutExpired:
        return "Error: MMS client timed out after 30s"
    except Exception as exc:
        return f"Error: {exc}"


def _mms_python_fallback(host: str, port: int, action: str, extra_args: list[str] | None = None) -> str:
    """Fallback: use a Python-based MMS helper script via subprocess.

    This generates and executes a small Python script that uses the
    libiec61850 shared library via ctypes, or connects using raw
    ISO-COTP/MMS if the library bindings are available.

    If nothing works, returns an error with installation instructions.
    """
    # Try using the iec61850 Python bindings (if installed)
    script = _build_mms_python_script(host, port, action, extra_args)
    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=30, errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # If python bindings aren't available, give a helpful error
        err = result.stderr.strip()
        if "ModuleNotFoundError" in err or "ImportError" in err:
            return (
                f"Error: MMS client binary not found at {_MMS_CLIENT_BIN} and "
                f"Python iec61850 bindings are not installed.\n"
                f"Install the binary: build libiec61850 and copy mms_client to {_MMS_CLIENT_BIN}\n"
                f"Or install Python bindings: pip install iec61850\n"
                f"You can also use run_command to manually execute MMS operations."
            )
        return f"Error: {err}\n{result.stdout.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: MMS Python helper timed out after 30s"
    except Exception as exc:
        return f"Error running MMS Python helper: {exc}"


def _build_mms_python_script(host: str, port: int, action: str, extra_args: list[str] | None = None) -> str:
    """Generate a Python script string for MMS client operations."""
    ref = extra_args[0] if extra_args else ""
    value = extra_args[1] if extra_args and len(extra_args) > 1 else ""

    return f'''
import sys
try:
    import iec61850
except ImportError:
    print("Error: iec61850 module not available", file=sys.stderr)
    sys.exit(1)

con = iec61850.IedConnection_create()
error = iec61850.IedConnection_connect(con, "{host}", {port})
if error != iec61850.IED_ERROR_OK:
    print(f"Connection error: {{error}}")
    iec61850.IedConnection_destroy(con)
    sys.exit(1)

action = "{action}"
try:
    if action == "discover":
        devices = iec61850.IedConnection_getLogicalDeviceList(con)
        device = iec61850.LinkedList_getNext(devices)
        while device:
            ld_name = iec61850.toCharP(device)
            print(f"LD: {{ld_name}}")
            nodes = iec61850.IedConnection_getLogicalDeviceDirectory(con, ld_name)
            node = iec61850.LinkedList_getNext(nodes)
            while node:
                ln_name = iec61850.toCharP(node)
                print(f"  LN: {{ln_name}}")
                node = iec61850.LinkedList_getNext(node)
            iec61850.LinkedList_destroy(nodes)
            device = iec61850.LinkedList_getNext(device)
        iec61850.LinkedList_destroy(devices)
    elif action == "read":
        ref = "{ref}"
        fc_str = ref.split("$")[1] if "$" in ref else "ST"
        fc = getattr(iec61850, f"IEC61850_FC_{{fc_str}}", iec61850.IEC61850_FC_ST)
        val = iec61850.IedConnection_readObject(con, ref, fc)
        if val:
            print(f"{{ref}} = {{iec61850.MmsValue_toString(val)}}")
            iec61850.MmsValue_delete(val)
        else:
            print(f"Error: could not read {{ref}}")
    elif action == "write":
        ref = "{ref}"
        value = "{value}"
        fc_str = ref.split("$")[1] if "$" in ref else "ST"
        fc = getattr(iec61850, f"IEC61850_FC_{{fc_str}}", iec61850.IEC61850_FC_ST)
        val = iec61850.MmsValue_newVisibleString(value)
        err = iec61850.IedConnection_writeObject(con, ref, fc, val)
        iec61850.MmsValue_delete(val)
        if err == iec61850.IED_ERROR_OK:
            print(f"Written {{value}} to {{ref}}")
        else:
            print(f"Write error: {{err}}")
finally:
    iec61850.IedConnection_close(con)
    iec61850.IedConnection_destroy(con)
'''


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

def _mms_client_cmd(host: str, port: int, action: str, extra_args: list[str] | None = None) -> str:
    """Dispatch to API or native MMS client based on MMS_CLIENT_MODE.

    Also handles interface binding when BIND_INTERFACE is set.
    """
    # Interface binding (applies to both modes)
    interface = _BIND_INTERFACE or os.environ.get("BIND_INTERFACE", "")
    if interface:
        _ensure_interface_route(host, interface)

    # Re-read mode at call time (environment might have been updated)
    mode = os.environ.get("MMS_CLIENT_MODE", _MMS_CLIENT_MODE)

    if mode == "native":
        return _mms_native_cmd(host, port, action, extra_args)
    else:
        return _mms_api_cmd(host, port, action, extra_args)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def read_mms_variable(
    reference: str,
    host: str = "",
    port: int = 0,
) -> str:
    """Read an MMS variable from the IEC 61850 server.

    The *reference* uses the standard IEC 61850 object-reference notation:
    ``<LogicalDevice>/<LogicalNode>$<FC>$<DataObject>$<DataAttribute>``

    Example: ``simpleIOGenericIO/GGIO1$ST$Ind1$stVal``

    In native mode (physical IED), this shells out to the libiec61850 client.
    In API mode (Docker), this queries the IED state REST API.

    Args:
        reference: IEC 61850 object reference to read.
        host: MMS server hostname / IP (default: from environment or ied-server).
        port: MMS TCP port (default: 102).
    """
    host = host or os.environ.get("IED_MMS_HOST", _DEFAULT_MMS_HOST)
    port = port or int(os.environ.get("IED_MMS_PORT", _DEFAULT_MMS_PORT))
    return _mms_client_cmd(host, port, "read", [reference])


@register_tool
@function_tool
def write_mms_variable(
    reference: str,
    value: str,
    host: str = "",
    port: int = 0,
) -> str:
    """Write a value to an MMS variable on the IEC 61850 server.

    The *reference* uses the standard IEC 61850 object-reference notation.
    The *value* is a string representation — the server will parse it to the
    appropriate MMS type (boolean, integer, float, etc.).

    ⚠️  On physical IEDs, writes affect real equipment.  Only write if the
    task objective explicitly requires it.

    Example:
        write_mms_variable("simpleIOGenericIO/GGIO1$ST$Ind1$stVal", "true")

    Args:
        reference: IEC 61850 object reference to write.
        value: Value to write (as string; will be cast server-side).
        host: MMS server hostname / IP.
        port: MMS TCP port (default 102).
    """
    host = host or os.environ.get("IED_MMS_HOST", _DEFAULT_MMS_HOST)
    port = port or int(os.environ.get("IED_MMS_PORT", _DEFAULT_MMS_PORT))
    return _mms_client_cmd(host, port, "write", [reference, value])


@register_tool
@function_tool
def list_mms_model(host: str = "", port: int = 0) -> str:
    """Discover the IEC 61850 data model on the server.

    Returns the hierarchy of Logical Devices → Logical Nodes → Data Objects
    exposed by the MMS server.

    In native mode (physical IED), this shells out to the libiec61850 client.
    In API mode (Docker), this queries the IED state REST API.

    Args:
        host: MMS server hostname / IP.
        port: MMS TCP port (default 102).
    """
    host = host or os.environ.get("IED_MMS_HOST", _DEFAULT_MMS_HOST)
    port = port or int(os.environ.get("IED_MMS_PORT", _DEFAULT_MMS_PORT))
    return _mms_client_cmd(host, port, "discover")
