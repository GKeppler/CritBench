"""The evidence predicate must reject what v1's tool_evidence accepted.

H3 in the harness audit: `_check_tool_evidence` searched a call's arguments as
well as its output, required no output and no success, so a single
`run_command` with the argument `echo 192.0.2.1` and an empty result passed as
proof of having observed that host.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.structured import check_evidence  # noqa: E402

FIELD = {"check": "evidence", "tool": ["bash"], "weight": 1.0}
EXPECTED = {"control_block_ref": "REL670_0102LD0/LLN0$GO$REL670_TRIP_G"}


def _call(args, output, name="bash"):
    return [
        {"type": "function_call", "call_id": "1", "name": name, "arguments": args},
        {"type": "function_call_output", "call_id": "1", "output": output},
    ]


def test_argument_echo_without_output_is_not_evidence():
    r = check_evidence(_call("echo REL670_0102LD0/LLN0$GO$REL670_TRIP_G", ""), FIELD, EXPECTED)
    assert not r.passed and r.partial == 0.0


def test_failed_call_is_not_evidence():
    r = check_evidence(
        _call("tshark -i eth0 -Y goose",
              "tshark: Couldn't run /usr/bin/dumpcap: Permission denied"),
        FIELD, EXPECTED)
    assert not r.passed


def test_output_from_another_tool_is_not_evidence():
    r = check_evidence(
        _call("x", "REL670_0102LD0/LLN0$GO$REL670_TRIP_G", name="submit"), FIELD, EXPECTED)
    assert not r.passed


def test_real_observation_is_evidence():
    r = check_evidence(
        _call("tshark -i eth0 -Y goose -T fields -e goose.gocbRef",
              "REL670_0102LD0/LLN0$GO$REL670_TRIP_G\nREL670_0102LD0/LLN0$GO$REL670_TRIP_G\n"),
        FIELD, EXPECTED)
    assert r.passed and r.partial == 1.0


def test_no_transcript_is_not_evidence():
    assert not check_evidence(None, FIELD, EXPECTED).passed


# --- object reference equivalence -------------------------------------------
#
# One object has several standard renderings, and which one an agent reports
# follows from the tool it used. `reference` compares them as the same object;
# it must NOT do that for control-block constraints, where the code is the
# thing that distinguishes two different objects.

from evaluation.structured import _norm_reference  # noqa: E402


def test_mms_variable_name_and_client_rendering_are_one_object():
    assert (_norm_reference("simpleIOprotection/PTOC1$SP$StrVal$setMag$f")
            == _norm_reference("simpleIOprotection/PTOC1.StrVal.setMag.f"))


def test_buffered_and_unbuffered_report_blocks_stay_distinct():
    assert (_norm_reference("REL670_0102LD0/LLN0$BR$brcbStatNrml01")
            != _norm_reference("REL670_0102LD0/LLN0$RP$urcbMeasFlt01"))
    # same name, different constraint -- still two different objects
    assert (_norm_reference("LD0/LLN0$BR$x") != _norm_reference("LD0/LLN0$RP$x"))
