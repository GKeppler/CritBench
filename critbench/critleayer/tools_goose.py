#!/usr/bin/env python3
"""
CritLayer — IEC 61850 GOOSE tools.

GOOSE operates at Layer 2 (raw Ethernet), so these tools use *scapy* to
craft and capture GOOSE frames.  The agent container must have
``CAP_NET_RAW`` for live capture / injection.

For the initial version the actual GOOSE encoding is simplified; full
ASN.1 BER encoding can be added later.
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
import time
from typing import List, Optional

from agents import function_tool

from .registry import register_tool

logger = logging.getLogger(__name__)

_DEFAULT_INTERFACE = os.environ.get("GOOSE_INTERFACE", "eth0")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def inject_goose_packet(
    gocb_ref: str,
    app_id: int,
    st_num: int,
    sq_num: int,
    dataset_values: str,
    interface: str = "",
    dst_mac: str = "01:0c:cd:01:00:01",
) -> str:
    """Craft and inject a GOOSE frame onto the network.

    This sends a single GOOSE Ethernet frame with the provided parameters.
    Requires CAP_NET_RAW capability.

    Args:
        gocb_ref: GOOSE Control Block Reference (e.g. "simpleIOGenericIO/LLN0$GO$gcb01").
        app_id: GOOSE APPID (uint16).
        st_num: State number.
        sq_num: Sequence number.
        dataset_values: Comma-separated list of boolean/integer values (e.g. "true,false,42").
        interface: Network interface to inject on (default: eth0).
        dst_mac: Destination MAC address (default: 01:0c:cd:01:00:01).
    """
    iface = interface or _DEFAULT_INTERFACE

    try:
        from scapy.all import Ether, sendp, Raw
    except ImportError:
        return "Error: scapy not installed. Install with: pip install scapy"

    try:
        # Build a minimal GOOSE Ethernet frame
        # EtherType 0x88B8 = GOOSE
        # Real GOOSE uses ASN.1 BER; here we embed a simplified payload
        # that libiec61850's GOOSE receiver can still decode for testing
        goose_payload = _build_goose_payload(gocb_ref, app_id, st_num, sq_num, dataset_values)

        frame = Ether(dst=dst_mac, type=0x88B8) / Raw(load=goose_payload)
        sendp(frame, iface=iface, verbose=False)

        return (
            f"GOOSE frame injected on {iface}:\n"
            f"  gocbRef={gocb_ref}, appId={app_id}, stNum={st_num}, sqNum={sq_num}\n"
            f"  dataset={dataset_values}, dst_mac={dst_mac}"
        )
    except PermissionError:
        return "Error: permission denied — container needs CAP_NET_RAW"
    except Exception as exc:
        return f"Error injecting GOOSE frame: {exc}"


@register_tool
@function_tool
def subscribe_goose(
    interface: str = "",
    gocb_ref_filter: str = "",
    timeout: int = 10,
    max_frames: int = 20,
) -> str:
    """Listen for GOOSE frames on a network interface.

    Captures GOOSE Ethernet frames (EtherType 0x88B8) and returns a
    summary of received messages.

    Args:
        interface: Network interface (default: eth0).
        gocb_ref_filter: Optional gocbRef to filter on.
        timeout: Capture timeout in seconds (default 10).
        max_frames: Maximum frames to capture (default 20).
    """
    iface = interface or _DEFAULT_INTERFACE

    try:
        from scapy.all import sniff
    except ImportError:
        return "Error: scapy not installed."

    try:
        # Capture raw Ethernet frames with GOOSE EtherType
        frames = sniff(
            iface=iface,
            filter="ether proto 0x88b8",
            timeout=timeout,
            count=max_frames,
        )

        if not frames:
            return f"No GOOSE frames captured on {iface} within {timeout}s"

        lines = []
        for i, pkt in enumerate(frames):
            raw = bytes(pkt.payload) if hasattr(pkt, "payload") else b""
            lines.append(f"Frame {i+1}: {len(raw)} bytes, src={pkt.src}, dst={pkt.dst}")

        return f"Captured {len(frames)} GOOSE frames on {iface}:\n\n" + "\n".join(lines)

    except PermissionError:
        return "Error: permission denied — container needs CAP_NET_RAW"
    except Exception as exc:
        return f"Error capturing GOOSE: {exc}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_goose_payload(
    gocb_ref: str,
    app_id: int,
    st_num: int,
    sq_num: int,
    dataset_values: str,
) -> bytes:
    """Build a simplified GOOSE PDU.

    This is a minimal representation — NOT full ASN.1 BER encoding.
    It is sufficient for testing the framework plumbing; swap in a proper
    ASN.1 encoder (or shell out to the libiec61850 goose_publisher) for
    production use.
    """
    # GOOSE header: APPID (2 bytes) + Length (2 bytes) + Reserved (4 bytes)
    payload_body = gocb_ref.encode("utf-8") + b"\x00"
    payload_body += struct.pack(">II", st_num, sq_num)

    # Encode dataset values (extremely simplified)
    for val in dataset_values.split(","):
        val = val.strip().lower()
        if val in ("true", "1"):
            payload_body += b"\x01"
        elif val in ("false", "0"):
            payload_body += b"\x00"
        else:
            try:
                payload_body += struct.pack(">i", int(val))
            except ValueError:
                payload_body += val.encode("utf-8") + b"\x00"

    total_len = 4 + 4 + len(payload_body)  # header(4) + reserved(4) + body
    header = struct.pack(">HH", app_id, total_len) + b"\x00" * 4
    return header + payload_body
