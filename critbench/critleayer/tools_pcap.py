#!/usr/bin/env python3
"""
CritLayer — PCAP analysis tools.

Uses *pyshark* (wraps tshark) so we get Wireshark's built-in dissectors for
MMS, GOOSE, SV, and IEC 104 for free.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from agents import function_tool

from .registry import register_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_tshark(pcap_path: str, display_filter: str, fields: List[str],
                max_rows: int = 200) -> str:
    """Run tshark and return tab-separated field output.

    NOTE: We do NOT use tshark's ``-c`` flag here because ``-c`` limits
    the number of *packets read from the file*, not the number of packets
    that *match the display filter*.  For protocols like GOOSE that may
    appear deep into a large capture, ``-c`` would stop reading before
    reaching any matching frames.  Instead we read the full capture and
    truncate the output to ``max_rows`` lines afterwards.
    """
    cmd = [
        "tshark", "-r", pcap_path,
        "-T", "fields",
    ]
    # Only add display filter if non-empty
    if display_filter:
        cmd.extend(["-Y", display_filter])
    for f in fields:
        cmd.extend(["-e", f])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return f"tshark error: {result.stderr.strip()}"
        # Truncate to max_rows lines
        lines = result.stdout.strip().split("\n")
        return "\n".join(lines[:max_rows]) + "\n"
    except FileNotFoundError:
        return "Error: tshark not installed. Install wireshark-common / tshark."
    except subprocess.TimeoutExpired:
        return "Error: tshark timed out (increase timeout or narrow your filter)"
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@register_tool
@function_tool
def parse_pcap(filepath: str, protocol_filter: str = "", max_packets: int = 100) -> str:
    """Parse a PCAP file and return a summary of packets.

    Args:
        filepath: Path to the .pcap / .pcapng file.
        protocol_filter: Optional Wireshark display filter (e.g. "mms", "goose",
                         "iec60870_104", "tcp.port==102").
        max_packets: Maximum packets to return (default 100).
    """
    p = Path(filepath)
    if not p.exists():
        return f"Error: file not found: {filepath}"

    display_filter = protocol_filter or ""

    # General summary: frame number, time, src/dst, protocol, info.
    # Use both IP and Ethernet address fields so the tool works for
    # Layer-2 protocols (GOOSE, SV) as well as IP-based ones (MMS, 104).
    fields = [
        "frame.number", "frame.time_relative",
        "eth.src", "eth.dst",
        "ip.src", "ip.dst",
        "frame.protocols", "_ws.col.Info",
    ]
    output = _run_tshark(filepath, display_filter, fields, max_packets)
    if output.startswith("Error"):
        return output

    lines = output.strip().split("\n")
    header = "Frame\tTime\tEthSrc\tEthDst\tIPSrc\tIPDst\tProtocols\tInfo"
    return f"Parsed {len(lines)} packets from {filepath}:\n\n{header}\n" + "\n".join(lines[:max_packets])


@register_tool
@function_tool
def extract_goose_frames(filepath: str, max_frames: int = 50) -> str:
    """Extract IEC 61850 GOOSE frames from a PCAP file.

    Returns gocbRef, stNum, sqNum, and allData for each GOOSE message.

    Args:
        filepath: Path to the pcap file.
        max_frames: Maximum frames to return (default 50).
    """
    p = Path(filepath)
    if not p.exists():
        return f"Error: file not found: {filepath}"

    fields = [
        "goose.gocbRef",
        "goose.stNum",
        "goose.sqNum",
        "goose.timeAllowedtoLive",
        "goose.datSet",
        "goose.allData",
    ]
    output = _run_tshark(filepath, "goose", fields, max_frames)
    if output.startswith("Error"):
        return output

    lines = output.strip().split("\n")
    header = "gocbRef\tstNum\tsqNum\ttimeAllowed\tdatSet\tallData"
    return f"Extracted {len(lines)} GOOSE frames:\n\n{header}\n" + "\n".join(lines[:max_frames])


@register_tool
@function_tool
def extract_mms_operations(filepath: str, max_packets: int = 100) -> str:
    """Extract MMS (IEC 61850-8-1) operations from a PCAP file.

    Returns domain IDs, item IDs, and confirmed service types.

    Args:
        filepath: Path to the pcap file.
        max_packets: Maximum packets to return (default 100).
    """
    p = Path(filepath)
    if not p.exists():
        return f"Error: file not found: {filepath}"

    fields = [
        "mms.domainId",
        "mms.itemId",
        "mms.confirmedServiceRequest",
        "mms.confirmedServiceResponse",
    ]
    output = _run_tshark(filepath, "mms", fields, max_packets)
    if output.startswith("Error"):
        return output

    lines = output.strip().split("\n")
    header = "domainId\titemId\tserviceReq\tserviceResp"
    return f"Extracted {len(lines)} MMS operations:\n\n{header}\n" + "\n".join(lines[:max_packets])


@register_tool
@function_tool
def extract_iec104_traffic(filepath: str, max_packets: int = 100) -> str:
    """Extract IEC 60870-5-104 traffic from a PCAP file.

    Returns ASDU type, cause of transmission, IOA, and values.

    Args:
        filepath: Path to the pcap file.
        max_packets: Maximum packets to return (default 100).
    """
    p = Path(filepath)
    if not p.exists():
        return f"Error: file not found: {filepath}"

    fields = [
        "iec60870_104.type",
        "iec60870_asdu.typeid",
        "iec60870_asdu.causetx",
        "iec60870_asdu.addr",
        "iec60870_asdu.ioa",
    ]
    output = _run_tshark(filepath, "iec60870_104", fields, max_packets)
    if output.startswith("Error"):
        return output

    lines = output.strip().split("\n")
    header = "104type\tasduType\tcauseTx\tasduAddr\tIOA"
    return f"Extracted {len(lines)} IEC 104 packets:\n\n{header}\n" + "\n".join(lines[:max_packets])
