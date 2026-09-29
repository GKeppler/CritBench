# Shared environment and measurement findings

These findings supplement every applicable task-local record. Ratings concern potential validity problems under the stated claim, not measured effects on model rankings. Evidence is from the current working tree, captured in input_manifest.json. Supported v2 execution is the Inspect path named in tasksv2/README.md; v1 runner defects are not automatically attributed to v2.

## H1 — Type and identity normalization (P2/P7 partly present; high confidence)

`critbench/evaluation/structured.py:79` coerces integers and hex strings to float, case-folds strings, and permits Python equality between booleans and numbers. The actual tasks demonstrate incorrect adjacent 64-bit PTP clock IDs accepted, boolean true accepted for common_address 1 and LN instance 1, and SCL hexadecimal APPID 4000 confused with decimal 4000. `structured.py:115` removes any recognized functional constraint, so explicitly wrong MX is accepted for an SP reference. These are field-dependent problems; they do not mean every task has incorrect frozen labels. Preserve arbitrary-precision integers, enforce types and field-specific hexadecimal/identifier semantics, and validate an explicit functional constraint rather than discarding it. Parsing embedded JSON and ignoring ungraded extra keys are separately documented contract-tolerance issues, not proof of accepting wrong graded relation content.

## H2 — Fixture mounting exceeds declarations (P3 partly present opportunity; high confidence)

All 35 static tasks have undeclared sibling fixtures accessible through full-directory mounts. `inspect_critbench/compose/scl_only.yaml:28` and `pcaps_only.yaml:28` narrow family access but mount complete fixture directories. Cross-family tasks use both directories. `tasksv2/validate.py:272` compares destination parent directories, so its strict gate does not enforce file-level declarations. The harness probe lists actual extra files per task. No label/grader files are mounted by these definitions; no LLM exploitation or pretraining contamination was measured. Mount explicit files or declare the full available evidence and align complexity metadata. Treat paired access-restricted trials as a follow-up experiment.

## H3 — Reported aggregate differs from declared design (P7 partly present; high confidence)

`inspect_critbench/dataset.py:81` carries yaml_path metadata, without floor-control or fixture annotations. `evals.py:118`, `:158`, `:273` load whole families. `scorer.py:222` reports ordinary mean, stderr and full success. This code does not exclude floor controls from headline means or cluster uncertainty by fixture as ADR-0003 describes. Default output therefore must not be presented as that proposed analysis. External postprocessing is unknown. Preserve per-task results, separate floor controls, and compute family/fixture-cluster summaries with explicit weights. Do not pool v1 and v2.

## H4 — Validator is a consistency gate, not independent validity (P2/P7 partly present; high confidence)

Read-only strict checks pass all 45 label-backed definitions; eight hardware definitions are pending. Label regeneration compares the extractor with itself. `tasksv2/validate.py:159` mutates the first answer field only, while :243 checks schema membership as a text substring. This misses secondary-field and semantic issues found here. Prompt-token checks remove paths and allowed targets and exclude short/numeric labels; passing does not prove no shortcut. Add independent semantic extraction and per-field, boundary-value, association and equivalent-representation checks. Use the audit scripts instead of the validator CLI to reproduce this review without rewriting production coverage/profiles.

## H5 — Development scope and incomplete experiment evidence (P1/P9 generally mitigated; P3/P4/P5/P6 unclear)

ADR-0003 explicitly bounds claims to these development configurations. Narrow diversity alone is not a demonstrated sampling or lab-only error under that scope. Independent parser/tshark/script baselines exist, but comparative model runs, historical tuning, contamination and transfer are not supplied. Static prompt-only failures do not establish absence of spurious correlations in models. Freeze model/tool/budget/hint settings; use paired renamed/repaired fixtures and held-out sites for broader claims. Keep capability label P4 (planning) distinct from paper pitfall P4 (spurious correlation).

## H6 — VM outcome checks improved; chronology remains partial (P7 partly present; high confidence)

All six actions reject untouched initial state. Inspect fetches live state and raises after repeated API acquisition failure (`scorer.py:123`), so blanket v1 missing-state criticism does not apply. However fixed before-value reports are not timestamped prior observations; copied values plus supplied target snapshots pass offline. This demonstrates an oracle coverage gap, not runtime ability to forge the host snapshot. The MMS API can relay changes to the native device, so final state does not distinguish native client use from the relay. Required report fields in indication/protection tasks are not graded. LPHD1 is absent from the static discovery API used for baseline capture, although present in C server source. The measurement hold behavior is supported by C source; protection trip/pickup dynamics are not. Require trusted read/write event evidence when chronology/protocol route matters, and derive model inventory by native discovery. Actual built-container/image identity was not verified live.

## H7 — Hardware correctly pending, with prospective blockers (P2/P9 unclear; P7/P10 partly present)

Eight tasks have no reviewed baseline and no Inspect entrypoint. They are neither passing nor failing hardware trials. Capture leaves asset/MMS sections for manual completion, ignores tshark failure status, and chooses the first sorted PTP announcer rather than establishing selected grandmaster context. Mocks confirm capture logic only; no mock was installed as a baseline.

`structured.py:230` requires matching tool outputs, improving over tool-name-only evidence. But :258 retains only strings of length at least four, dropping numeric/boolean facts and field bindings. A successful shell echo of expected strings satisfies the evidence predicate; this does not require forged host logs. Empty/numeric-only expected facts cannot establish evidence. Current hardware evidence tool allowlists also differ from Inspect's bash-to-run_command transcript mapping; hardware is not yet ported, so this is a future integration issue. Validator answer-field code excludes live_state but not evidence fields, then accesses missing path keys; the pending early return currently masks this prospective baseline-validation failure. Before enabling hardware, fix that path, require protocol-grounded structured observations and contemporaneous baseline review, handle tool failures explicitly, and confirm topology/domain/time context.

## Reproduction and limits

Run from repository root:

```bash
python3 docs/bias_audit_v2/harness_probes.py
python3 docs/bias_audit_v2/scl_checks.py
python3 docs/bias_audit_v2/pcap_probe.py
python3 docs/bias_audit_v2/dynamic_probe.py
python3 docs/bias_audit_v2/build_report.py
```

Scripts write audit outputs only. PCAP requires tshark; Python dependencies are those of the existing repository plus lxml. The probes exercise actual graders and independently inspected artifacts/source. There were no new model evaluations, live device actions or container launches, so no model ranking, operational prevalence or physical impact estimate follows from these results.
