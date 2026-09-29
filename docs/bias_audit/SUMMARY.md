# CritBench task bias audit

**The corpus has confirmed measurement defects and experiment-design risks that should be addressed before interpreting scores as general OT capability.** The strongest evidence concerns grading, answer-bearing prompts, and trial isolation. This audit does **not** establish that evaluated LLMs exploited these defects, that any particular model ranking is wrong, or that public tasks contaminated model training.

The file-based corpus contains **104 current YAML definitions and 5 archived `.yaml_old` definitions**. The legacy `alltasks.txt` snapshot contains another 81 entries: 60 identical static tasks, 18 older VM variants and 3 GOOSE tasks absent from the standalone files. These are reviewed separately in the [snapshot supplement](SNAPSHOT_REVIEW.md), giving **112 distinct task IDs** across all sources. “Current” includes 20 explicitly untested hardware definitions; it does not mean all 104 have been validated in their intended runtime. The README's 81-task total is stale.

| Family | Current | Archived | What was checked |
|---|---:|---:|---|
| PCAP | 30 | 0 | All objectives/oracles; local tshark extraction from the three captures; actual-grader counterexamples |
| SCL/SCD/CID | 30 | 0 | All objectives/oracles; independent XML extraction from four files; actual-grader correct/incorrect answer probes |
| VM IED | 18 | 0 | Every objective/oracle; C/Python simulator and state API source; offline state/answer probes |
| GRFICSv3 | 5 | 0 | Every objective/oracle; compose, tool and Modbus sidecar source; offline probes |
| GridNet | 1 | 5 | Current milestones/reset implementation, archived objectives/oracles and available local fixtures; offline probes |
| Hardware, untested | 20 | 0 | Every objective/oracle, tool-evidence predicate and execution path; fabricated-observation rejection probes |
| **Total** | **104** | **5** | **109 individual P1–P10 assessments** |

Start with the [all-task matrix](TASK_MATRIX.md), or filter [the CSV](task_matrix.csv). Detailed findings, evidence and remedies are in [PCAP](PCAP_REVIEW.md), [SCL](SCL_REVIEW.md), [dynamic/hardware](DYNAMIC_REVIEW.md), and [shared harness findings](HARNESS_REVIEW.md). [Combined JSON](all_task_reviews.json) retains the 109 file-based records; [snapshot records](snapshot_records.json) cover the 21 distinct legacy versions, and the [snapshot comparison](alltasks_snapshot_comparison.json) accounts for all 81 entries without counting exact duplicates as new tasks.

## Method adapted from the supplied paper

The [rubric](RUBRIC.md) was written before task reviews, following Arp et al., *Dos and Don'ts of Machine Learning in Computer Security*, arXiv:2010.09470v2, sections 2–4 and Appendix A, as supplied by the user. The ten pitfalls are assessed categorically: present, partly present, not present in inspected scope, unclear, or not applicable. Ratings are not summed into a “bias score.” Each assessment distinguishes the bounded task claim from broad deployment claims.

Three family reviewers performed primary source/fixture reviews. The root reviewer assessed every record, inspected the relevant objective/oracle/source evidence, reran all four probe suites, and reconciled scope differences. Primary records and adjudication notes are retained. This is an **adapted agent review**, not a reproduction of the paper's two independent human expert reviews plus third-party adjudication. The second review had access to primary findings; no independence or inter-rater reliability statistic is claimed. No author survey was conducted.

The paper's impact-analysis idea is applied here through controlled offline changes to answers/evidence while keeping the task and actual grader fixed. These tests demonstrate false acceptance/rejection and omitted requirements. They do not replace paired LLM trials for measuring score/ranking effects. Classification-specific P8 is NA for bounded extraction/action completion; unequal task-family counts are discussed under P1/P7 instead.

## Confirmed findings to prioritize

| Priority | Evidence | Consequence | Repair |
|---|---|---|---|
| 1 | Original harness mounts the entire output base; host reports placed there include expected answers. | Later runs can access earlier labels and answers. Current-task YAML sanitization does not close this route. | Fresh per-run agent mount; keep grade reports outside agent-visible paths. See H1. |
| 1 | Original batch starts IED/GRFICS/GridNet once and iterates tasks/models/repetitions without per-run reset. | Later trials may inherit success conditions or interfering changes; model order becomes a confound. | Reprovision and assert a clean baseline for every trial. Inspect's isolation/reset differs and deserves separate treatment. See H7/H8. |
| 1 | Correct answers to `scd_cross_goose_confrev` and `scd_rtu_client` cannot reach full success: nested `contains_any` is unsupported. | Valid answers score at most 2/3 and 3/4 respectively. | Implement/validate nested check types, then test independent correct answers before inclusion. |
| 1 | `vm_mms_rapid_toggle` scores 1.0 at its initial false state with an answer explicitly reporting zero successful writes. | Final-state equality does not demonstrate toggling. | Trusted transition history/count and initial/final reads; define the required rate if “rapid” is measured. |
| 1 | Hardware tool evidence accepts a target substring in a permitted call with no output or successful observation. All 20 hardware definitions accept offline keyword answers plus such synthetic calls. | A tool-shaped record is treated as proof of observing a device. | Trusted completed tool results and parsed target-specific observations; reject echo/missing-output/unrelated calls. See H3. |
| 2 | Repeating the **rendered system prompt and objective** earns full success on **12 current tasks**: 9 PCAP, 1 SCL, 2 VM. | The grader can reward restating the assignment without answering it. | Remove answer-bearing examples for discovery tasks; require structured facts/associations and appropriate evidence. See H4. |
| 2 | All 30 PCAP graders accept a negated expected answer; 22 SCL graders do too. | Lexical matching can reward incorrect conclusions or incomplete lists. | Typed values, set equality and entity/value associations, with contradiction and equivalent-answer probes. |
| 2 | `cid_protection_lds` omits `CTRL` from its six expected LDs; XML contains the seventh qualifying LD with `SMPPTRC1`. | Incomplete protection inventory earns full credit. | Independently derive the seven-element set and validate exclusivity/completeness. |
| 2 | `grfics_modbus_recon` accepts arbitrary integers after `pressure=` and `pressure_sp=`. | No live numeric correctness is measured. | Compare reported values against trusted timestamped observations with tolerances. |
| 2 | GRFICS persistence tasks check one snapshot; manual override checks a valve command register, not measured valve position. `vm_mms_ptoc_blinding` never exercises a fault/trip model. | Register changes do not establish all requested persistence or physical effects. | Add time-separated observations and process outcomes, or narrow the objective to register modification. |

These findings are about the implemented predicates and experiment setup. A deliberately fabricated offline transcript is **not** evidence that a deployed model can forge Inspect's host-recorded history. Likewise, supplying expected state to a unit probe does **not** demonstrate control over the trusted state API. The family reports preserve those distinctions.

## What is supported, and what remains uncertain

- **Positive controls:** six SCL tasks explicitly request a single integer and use exact matching; independent XML counts match and wrong/negated answers are rejected. They still inherit whole-experiment provenance/isolation risks when applicable.
- **Existing mitigations:** selective image copying and YAML sanitization protect current labels; Inspect keeps grading data host-side; live IED and GRFICS reads improve final-state validation; current Inspect GridNet uses stronger milestones, complete reset and readiness checks. These should be retained.
- **P1:** 60 static questions reuse three captures and four SCL files, often the same site/device. This limits independent coverage, but representativeness cannot be determined without a declared target population. Do not treat 60 questions as 60 independent deployments.
- **P3/P5/P6:** pretraining contamination, final held-out evaluation/tuning history and published model/parser comparisons cannot be established from task files alone. They remain unclear. Evidence of task revision after model testing is a development-history signal, not sufficient proof of invalid final evaluation.
- **P9/P10:** controlled offline and simulated tasks are legitimate under explicit bounded claims. Physical transfer, hardware liveness, current OUI attribution and standards-specific ambiguities not independently verified are marked as limitations, not silently assumed.

## Reproduce and extend

From the repository root, run:

```bash
python3 docs/bias_audit/audit_harness.py
python3 docs/bias_audit/pcap_probe.py
python3 docs/bias_audit/scl_checks.py
python3 docs/bias_audit/dynamic_probe.py
python3 docs/bias_audit/snapshot_probe.py
python3 docs/bias_audit/build_audit_index.py
```

The environment used Python with PyYAML, requests and Jinja2, plus local tshark. The probe scripts executed successfully during review; the index validates complete coverage, all ten ratings, unique IDs and unchanged task hashes. They perform offline file/grader checks, not LLM calls or device interactions. [Input hashes and repository revision](audit_manifest.json) identify the reviewed working tree; pre-existing uncommitted changes were preserved.

For a publication-quality impact study, freeze model/configuration choices, introduce independently verified structured oracles and clean resets, and compare original/repaired conditions with equal budgets across repeated paired trials. Include deterministic XML/tshark/protocol-script baselines, prompt-only model baselines, held-out sites/devices/captures, and semantics-preserving identifier/prompt variants. Report full success, partial score, false acceptance/rejection, resource use and infrastructure failures separately, with uncertainty clustered by shared fixture/site. Do not silently discard hard, unavailable or failed tasks from the denominator.

**Work performed:** review artifacts and reproducible tests were added. Task definitions, graders and environments were not changed; no new containers, physical actions or paid model trials were run. Existing model-score effect sizes and physical-world generalization remain unmeasured.
