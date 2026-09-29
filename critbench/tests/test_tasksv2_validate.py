"""The v2 corpus is only as good as its gate, so the gate runs in CI.

`validate.py` regenerates every label from its fixture, re-renders every prompt,
and runs the real grader against a correct answer, an equivalent rendering, an
omission, a fabrication, the echoed prompt, the hint alone and an empty
submission. A task that stops satisfying any of that stops shipping.
"""

import sys
from pathlib import Path

CRITBENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CRITBENCH))
sys.path.insert(0, str(CRITBENCH / "tasksv2"))

import validate  # noqa: E402


import pytest  # noqa: E402


@pytest.mark.parametrize("family", ["scl", "pcap", "vm", "hardware"])
def test_v2_corpus_passes_its_gate(monkeypatch, family):
    monkeypatch.setattr(sys, "argv", ["validate.py", "--family", family])
    assert validate.main() == 0
