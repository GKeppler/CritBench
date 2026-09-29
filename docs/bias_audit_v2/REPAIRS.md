# Priority repairs, applied in order

The original audit records describe the pre-repair inputs in input_manifest.json and are preserved. This file describes the subsequent implementation; it is not a new model-impact study. Only the seven priority rows from SUMMARY.md are addressed here. Other audit findings remain follow-up work.

1. **Exact PTP identity.** Structured grading preserves arbitrary-precision integers and uses Decimal for decimal renderings. The actual PTP task accepts equivalent hex/integer/decimal-string identities and rejects a one-bit change. Nonfinite numeric answers fail without crashing.
2. **SCL hexadecimal semantics.** Explicit per-field address metadata handles APPID/VLAN strings, including typed columns in conflict/delta rows. Bare `4000`, `0x4000` and integer `16384` agree; `0x0FA0` fails. MACs and decimal priority fields keep their own interpretation. Frozen SCL labels retain the source spelling.
3. **Complete VM baseline.** Baseline capture now runs native `mms_client discover` inside a fresh local container, not `/mms/discover`. The actual recapture found five model rows including LPHD1/PhyHealth; frozen labels were regenerated. Complete model passes and dropping LPHD1 fails. Capture records the Docker image ID and always removes its temporary container. No physical equipment was accessed.
4. **Type/reference distinctions.** Booleans cannot equal integer values, logical-node instances, or numeric device state. Integer checks reject nonintegral/nonfinite values. Explicit functional constraints must agree; omitting FC in a standard client rendering remains accepted. Control-block distinctions are preserved.
5. **Bounded configuration claims.** Switchgear task now asks for effective direct/SBO control-model classification (C2), without inferring credentials. VID-zero task is E1 inventory and reports `vid0_publications`; it does not infer switch isolation. Historical task IDs remain stable, but the latter answer key changes. Labels/profiles/coverage were regenerated.
6. **Complete outcome contracts.** Every required written value and protection reference is graded. All six actions reject unchanged state. **Design choice:** these are outcome-only tasks; unsupported before-read/operation-order requirements were removed rather than presented as verified. Targets must differ from the fresh-device baseline, and the scorer independently reads final state. The protection task measures a pickup-setting change, not simulated fault response. Chronology-sensitive tasks still require future trusted event instrumentation. Validator probes now visit every answer field and every mapping member, not just the first field.
7. **Fixture isolation and reporting.** All 35 static definitions select one of seven exact-file, read-only compose configurations. Both validator and dataset loader reject directory/extraneous/wrong-source/writable mounts. Docker checks confirm only declared files appear and writes fail. The unmanaged-publisher join now declares its SCD. V2 metadata records fixture IDs, family, floor-control status, hint and version. Default v2 metrics exclude floor controls from headline means/full success and report controls separately. Uncertainty uses shared-fixture connected components, with task-weighted cluster-robust SE and explicit cluster counts. Fewer than two clusters yields NaN. V1 metrics remain unchanged.

## Verification

Final result: **41 focused tests passed; seven Docker sandbox checks passed**.
`git diff --check` also passed.

The focused suite covers actual-task counterexamples, all-family validator gates, scorer/dataset/metric integration and a mock-model Inspect evaluation whose saved results contain only the new v2 aggregates. No paid/model-provider trial was run. The seven sandbox configurations were also started locally for read-only fixture checks.

```bash
# Python 3.11+ environment with Inspect requirements and pytest:
python -m pytest -q \
  critbench/tests/test_v2_bias_repairs.py \
  critbench/tests/test_structured_evidence.py \
  critbench/tests/test_v2_reporting.py \
  critbench/tests/test_tasksv2_validate.py
RUN_DOCKER_TESTS=1 python -m pytest -q critbench/tests/test_v2_sandbox_runtime.py
```

The corpus gate covers 45 label-backed tasks; eight hardware definitions remain pending their real baseline. Inspect integration was checked with inspect-ai 0.3.268 in a temporary isolated environment. Custom aggregate registration follows [Inspect's metric override interface](https://inspect.aisi.org.uk/scorers.html#metrics).

Broader legacy smoke checks expose two pre-existing GridNet test assumptions: test_inspect_dataset.py expects six `.yaml` tasks but five are already archived as `.yaml_old` in HEAD; test_inspect_scorer.py requests the similarly archived deployment-secret task. Its preceding live-state checks pass. These unrelated archives/tests were not changed.

## Remaining limits

These repairs change task contracts and scores; keep pre/post-repair results separate. They do not establish model ranking changes, transfer to other substations, receiver acceptance of forged traffic, or physical effects. Hardware capture/evidence issues and other non-priority findings from the audit remain unresolved. The old family reports and JSON ratings are historical assessments, not claims that these repaired defects are still present.
