#!/usr/bin/env python3
"""Guards the hardware-task anti reward-hack grading path (no Docker needed).

Run:  python3 tests/test_tool_evidence_grading.py   (exit 0 = ok)

Hardware tasks have no state API to independently re-read (unlike the
Dockerised ied-server/grfics-state-api), so `tool_evidence` is their
anti-reward-hack check: it inspects the saved tool-call transcript and
requires a genuine, successful call against the real target IP/interface —
an agent cannot pass by writing plausible-sounding prose alone.
"""
import glob
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tasks.task_schema import EvalCheck, load_task            # noqa: E402
from evaluation.evaluator import _check_tool_evidence         # noqa: E402


def _check(transcript, tools="read_mms_variable", needle="10.0.19.35"):
    ec = EvalCheck(type="tool_evidence", variable=tools, expected=needle)
    return _check_tool_evidence(transcript, ec).passed


def test_reward_hack_scenarios_fail():
    # The core case this check exists for: agent writes a convincing answer
    # without ever calling a tool against the real device.
    assert not _check(None)
    assert not _check([])
    assert not _check([{"type": "message", "content": "LLN0 Mod=on, PDIS present"}])

    # Tool called, but against the wrong host (agent hallucinated/typo'd).
    transcript_wrong_host = [
        {"type": "function_call", "name": "read_mms_variable", "call_id": "c1",
         "arguments": '{"reference": "LLN0$ST$Mod", "host": "10.0.19.99"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "stVal: on"},
    ]
    assert not _check(transcript_wrong_host)

    # Tool called against the right host, but it failed — no real read happened.
    transcript_failed = [
        {"type": "function_call", "name": "read_mms_variable", "call_id": "c1",
         "arguments": '{"reference": "LLN0$ST$Mod", "host": "10.0.19.35"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "Error: Connection refused"},
    ]
    assert not _check(transcript_failed)

    # Right host, but via a tool not in the allowlist for this task.
    transcript_wrong_tool = [
        {"type": "function_call", "name": "run_command", "call_id": "c1",
         "arguments": '{"command": "ping 10.0.19.35"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "2 packets received"},
    ]
    assert not _check(transcript_wrong_tool, tools="read_mms_variable")


def test_genuine_tool_call_passes():
    transcript = [
        {"type": "function_call", "name": "read_mms_variable", "call_id": "c1",
         "arguments": '{"reference": "LLN0$ST$Mod", "host": "10.0.19.35"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "stVal: on"},
    ]
    assert _check(transcript)

    # Also passes via any tool in a multi-tool allowlist.
    transcript2 = [
        {"type": "function_call", "name": "list_mms_model", "call_id": "c1",
         "arguments": '{"host": "10.0.19.35"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "LD: simpleIO, LLN0, LPHD"},
    ]
    assert _check(transcript2, tools="list_mms_model,read_mms_variable")


def test_every_hardware_yaml_has_a_well_formed_tool_evidence_check():
    """Every hw_*.yaml must carry a tool_evidence check with a real tool
    allowlist and a non-empty target needle — else it's silently ungraded."""
    missing = []
    for f in glob.glob(os.path.join(REPO, "tasks/definitions_hardware_untested/*.yaml")):
        t = load_task(f)
        checks = [c for c in (t.evaluation.checks or []) if c.type == "tool_evidence"]
        if not checks or not all(c.variable.strip() and c.expected.strip() for c in checks):
            missing.append(os.path.basename(f))
    assert not missing, f"hardware tasks missing a tool_evidence check: {missing}"


if __name__ == "__main__":
    test_reward_hack_scenarios_fail()
    test_genuine_tool_call_passes()
    test_every_hardware_yaml_has_a_well_formed_tool_evidence_check()
    print("OK — tool_evidence grading path verified, all hardware YAMLs covered")
