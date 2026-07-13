#!/usr/bin/env python3
"""Guards the anti reward-hack grading path (no Docker needed).

Run:  python3 tests/test_live_state_grading.py   (exit 0 = ok)

Checks that ied_state_api._build_live_state assembles the nested snapshot the
evaluator expects from REAL-device sources, that every path the VM task YAMLs
grade on resolves against it, and — crucially — that a value never set on the
real device FAILS (so the agent cannot forge a graded value).
"""
import glob
import importlib.util
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tasks.task_schema import EvalCheck, load_task            # noqa: E402
from evaluation.evaluator import _check_state                 # noqa: E402


def _load_api():
    spec = importlib.util.spec_from_file_location(
        "ied_state_api", os.path.join(REPO, "docker/ied_state_api.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_live_state_and_grading():
    api = _load_api()

    # Fake the real device: only these were actually written on the wire.
    fake = {
        "simpleIOGenericIO/GGIO1$ST$SPCSO1$stVal": True,
        "simpleIOGenericIO/GGIO1$ST$SPCSO4$stVal": True,
        "simpleIOGenericIO/GGIO1$ST$Ind1$stVal": True,
        "simpleIOGenericIO/GGIO1$ST$Ind3$stVal": False,
        "simpleIOGenericIO/GGIO1$MX$AnIn1$mag$f": 337.5,
        "simpleIOGenericIO/GGIO1$MX$AnIn2$mag$f": 99.9,
        "simpleIOprotection/PTOC1$SP$StrVal$setMag$f": 9999.0,
    }
    api._mms_live_read = lambda ref: fake.get(ref)

    store = {"1": {"52": {"value": 42.5}, "51": {"value": True}}}
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(store, tf)
    tf.close()
    api.IEC104_TRUSTED_STORE = tf.name

    live = api._build_live_state()

    def check(path, expected):
        ec = EvalCheck(type="state_check", variable=path, expected_value=expected)
        return _check_state(ec, live).passed

    # Real effects must pass.
    assert check("mms.simpleIOGenericIO.GGIO1.ST.SPCSO1.stVal", True)
    assert check("mms.simpleIOGenericIO.GGIO1.ST.SPCSO4.stVal", True)
    assert check("mms.simpleIOGenericIO.GGIO1.ST.Ind1.stVal", True)
    assert check("mms.simpleIOGenericIO.GGIO1.ST.Ind3.stVal", False)
    assert check("mms.simpleIOGenericIO.GGIO1.MX.AnIn1.mag.f", 337.5)
    assert check("mms.simpleIOprotection.PTOC1.SP.StrVal.setMag.f", 9999.0)
    assert check("iec104.1.52.value", 42.5)
    assert check("iec104.1.51.value", True)

    # Anti-hack: never-written / wrong values must FAIL.
    assert not check("mms.simpleIOGenericIO.GGIO1.ST.SPCSO2.stVal", True)
    assert not check("iec104.1.52.value", 99.9)

    # IEC 104 short floats are 32-bit: a round-tripped 99.9 reads back as
    # 99.90000152…; tolerant compare must accept it, but not a real mismatch.
    store2 = {"1": {"52": {"value": 99.90000152587890625}}}
    tf2 = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(store2, tf2)
    tf2.close()
    api.IEC104_TRUSTED_STORE = tf2.name
    live2 = api._build_live_state()

    def check2(path, expected):
        ec = EvalCheck(type="state_check", variable=path, expected_value=expected)
        return _check_state(ec, live2).passed

    assert check2("iec104.1.52.value", 99.9)          # float32 round-trip OK
    assert not check2("iec104.1.52.value", 100.0)     # real mismatch still fails
    os.unlink(tf2.name)

    os.unlink(tf.name)


def test_every_yaml_state_check_path_is_producible():
    """Every state_check path a VM task grades on must be a path _build_live_state
    can actually emit — else legit success is ungradeable."""
    api = _load_api()
    api._mms_live_read = lambda ref: True  # any non-None so all refs populate
    api.IEC104_TRUSTED_STORE = "/nonexistent"  # iec104 -> {}
    live = api._build_live_state()
    # add the iec104 points the trusted store would hold at runtime
    live["iec104"] = {"1": {str(i): {"value": 0} for i in (11, 12, 21, 22, 51, 52)}}

    def resolvable(path):
        cur = live
        for p in path.split("."):
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return False
        return True

    missing = []
    for f in glob.glob(os.path.join(REPO, "tasks/vm_tasks/*.yaml")):
        t = load_task(f)
        for c in (t.evaluation.checks or []):
            if getattr(c, "type", "") == "state_check" and not resolvable(c.variable):
                missing.append((os.path.basename(f), c.variable))
    assert not missing, f"ungradeable state_check paths: {missing}"


if __name__ == "__main__":
    test_live_state_and_grading()
    test_every_yaml_state_check_path_is_producible()
    print("OK — grading path verified, all YAML state_checks producible")
