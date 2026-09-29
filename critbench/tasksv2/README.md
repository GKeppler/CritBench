# CritBench v2 tasks

Built to the construct, coverage and measurement rules of
[ADR-0003](../../docs/adr/0003-tasks-v2-construct-and-coverage.md), which is the
document to read first. v1 (`critbench/tasks/`) is frozen and still runnable;
**v2 scores are not comparable with v1 scores** and must never be pooled with
them.

| family | tasks | what it is | Inspect task |
|---|---|---|---|
| `scl/` | 19 | IEC 61850 engineering files | `@critbench_scl_v2` |
| `pcap/` | 16 | GOOSE / SV / MMS / PTP captures | `@critbench_pcap_v2` |
| `vm/` | 10 | live MMS + IEC 104 device, six with verified device-state outcomes | `@critbench_iec61850_v2` |
| `hardware/` | 8 | physical relays -- **pending a lab baseline, do not run for score** | none yet |

```bash
python3 critbench/tasksv2/validate.py --family scl   # the gate: labels, prompts, probes
python3 critbench/tasksv2/validate.py --family scl --freeze   # after changing truth.py or a fixture

cd critbench
inspect eval inspect_critbench/evals.py@critbench_scl_v2 --model openai/gpt-4o
inspect eval inspect_critbench/evals.py@critbench_scl_v2 --model openai/gpt-4o -T hint=h1
```

The hardware family needs its ground truth read off the equipment before it can
grade anything:

```bash
python3 critbench/tasksv2/hardware/capture_baseline.py --interface eth0   # read-only
#   review baseline/lab_baseline.json by hand, then:
python3 critbench/tasksv2/validate.py --family hardware --freeze
```

A family directory holds the task YAMLs plus three files that make the corpus
auditable:

| file | what it is |
|---|---|
| `truth.py` | derives every expected answer from the fixture (for `vm/`, from a fresh-container native MMS/live-state capture); also the deterministic baseline |
| `labels.json` | those answers, frozen; the YAMLs contain no expected values |
| `COVERAGE.md`, `profiles.json` | generated: grid occupancy and the computed complexity vector per task |

Adding a task means writing the extractor first, then the YAML, then running the
validator until it is green. It refuses a task whose labels are stale, whose
prompt contains an answer token, whose sandbox mounts a fixture the task does
not declare, or whose grader accepts a fabrication, an omission, an action never
taken, the echoed prompt, the hint alone or an empty submission.

What it cannot refuse is an answer contract with two defensible readings, since
it builds its "correct" answer from the labels and so only ever tests your own
rendering. The first model run is what finds those. Treat a calibration run as
part of authoring, and expect to reword.

## Measurement contract after the v2 audit

Action tasks check the final device state and every requested written-value or
reference field. They do not claim to verify prior-read chronology or simulated
fault/breaker response. Initial labels remain for no-action regression checks.
VM baseline capture browses native MMS (including LPHD1), records the image ID,
and samples values repeatedly; recapture after rebuilding the simulator.

SCL APPID/VLAN strings use hexadecimal semantics; numeric JSON values denote
integers. Boolean and integer values are distinct. Explicit functional
constraints must agree; standard reference renderings omitting FC still work.

Every v2 static sandbox mounts only the declared fixture files. Inspect reports
`headline_mean` and `headline_full_success` excluding floor controls, with
separate `floor_*` metrics. `fixture_cluster_stderr` groups overlapping fixture
sets; one cluster yields NaN, not zero uncertainty. `fixture_clusters`,
`headline_n` and `floor_n` expose the sample sizes. Keep family/hint runs separate.

See [the repair record](../../docs/bias_audit_v2/REPAIRS.md) for changes and tests.
