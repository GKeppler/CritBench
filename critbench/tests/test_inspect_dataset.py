#!/usr/bin/env python3
"""Ground truth must not reach the model. Run directly; exit 0 = pass.

The original harness enforced this by stripping `evaluation` and `hint` out of
a copied task YAML before mounting it into the agent container
(run_experiments.py::_create_sanitised_task_yaml). The Inspect front-end
enforces it structurally instead -- only the YAML *path* travels in
Sample.metadata -- and this asserts that structure actually holds.

Note what is deliberately NOT asserted: that a check's `expected` value is
absent from the prompt. Task authors put target values in objectives on purpose
("force the setpoint to the raw value 5000"), so that assertion would fail on
correct tasks. The leak that matters is the `hint` field -- several are
step-by-step walkthroughs of the full answer.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inspect_critbench.dataset import critbench_dataset  # noqa: E402

FAMILIES = ["pcaps_tasks", "scd_tasks", "vm_tasks", "GRFICSv3", "gridnet"]
EXPECTED_COUNTS = {"pcaps_tasks": 30, "scd_tasks": 30, "vm_tasks": 18,
                   "GRFICSv3": 5, "gridnet": 6}

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


for family in FAMILIES:
    samples = list(critbench_dataset(family, hint=False))
    check(
        len(samples) == EXPECTED_COUNTS[family],
        f"{family}: expected {EXPECTED_COUNTS[family]} samples, got {len(samples)}",
    )

    for sample in samples:
        text = "\n".join(str(m.content) for m in sample.input)
        raw = yaml.safe_load(Path(sample.metadata["yaml_path"]).read_text())

        # 1. Only the path travels -- no parsed evaluation rides in metadata.
        check(
            set(sample.metadata) == {"yaml_path"},
            f"{sample.id}: metadata leaked extra keys {set(sample.metadata) - {'yaml_path'}}",
        )

        # 2. Ground truth must not ride in Sample.target either.
        check(not sample.target, f"{sample.id}: Sample.target is non-empty: {sample.target!r}")

        # 3. The hint is a walkthrough of the answer; it must be absent unless
        #    explicitly requested via -T hint=true.
        hint = (raw.get("hint") or "").strip()
        if hint:
            check(
                hint not in text,
                f"{sample.id}: hint text leaked into the prompt with hint=False",
            )

        # 4. Every prompt must be fully rendered -- no unsubstituted Jinja.
        check("{{" not in text, f"{sample.id}: unrendered Jinja left in prompt")

        # 5. A private key is copied into the sandbox for SSH tasks; its
        #    CONTENTS must never appear in the prompt (only its path may).
        for host_path in (sample.files or {}).values():
            key = Path(host_path)
            if key.is_file():
                body = key.read_text(errors="ignore")
                secret = "".join(body.split())[:200]
                check(
                    bool(secret) and secret not in "".join(text.split()),
                    f"{sample.id}: private key material leaked into the prompt",
                )

# The hint flag must actually work when asked for.
hinted = {s.id: s for s in critbench_dataset("vm_tasks", hint=True)}
for sample in critbench_dataset("vm_tasks", hint=False):
    raw = yaml.safe_load(Path(sample.metadata["yaml_path"]).read_text())
    hint = (raw.get("hint") or "").strip()
    if hint:
        text = "\n".join(str(m.content) for m in hinted[sample.id].input)
        check(hint in text, f"{sample.id}: hint=True did not append the hint")
        break
else:
    failures.append("no vm_task carries a hint -- the hint=True path is untested")

if failures:
    print(f"FAIL ({len(failures)}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)

print(f"PASS: {sum(EXPECTED_COUNTS.values())} samples across {len(FAMILIES)} families; "
      "no evaluation data, target, or hint reaches the prompt")
