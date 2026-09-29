# Shared harness findings

Read alongside the individual family reviews and [rubric](RUBRIC.md). Evidence is the working tree, not just committed HEAD. No model runs or live device actions were performed. Existing running GRFICS containers were left alone.

## H1 — Previous results disclose labels to later original-harness runs

**P3 present conditionally; P10 trust-boundary concern. High severity, high source confidence.** The original Docker compose binds the entire output base into `/output` (`critbench/docker-compose.yaml:77`; `run_experiments.py:329–355`). Each run uses a subdirectory of that same base (`run_experiments.py:720–756`). Host grading writes `result.json` after a run, including `evaluation.checks[].expected` (`run_experiments.py:685–700`, `evaluation/metrics.py:134–148`). Thus later runs sharing that base have filesystem access to earlier labels and answers. A fresh isolated first run has no such prior results. Repeated tasks/models make the exposure especially relevant. We did not observe an LLM reading those files and did not test an actual container exploit.

The selective Docker image copy (`docker/Dockerfile.agent:54–63`) and task sanitizer (`run_experiments.py:445–450`) correctly remove current task evaluation material. They do not close this separate cross-run output path. Inspect's static sandbox mounts fixtures, not original output directories (`inspect_critbench/compose/static.yaml:21–23`), and its dataset passes only rendered prompts to the agent (`dataset.py:33–66`); do not attribute H1 to Inspect without another route.

**Repair/test:** mount only a fresh per-run scratch directory; store host grading reports outside all agent mounts. Before each run assert that sentinel labels from a prior run cannot be listed or read. Keep full grade details in a host-only result store. Treat earlier results collected with shared output visibility as exposed evaluations, not automatically as proven contaminated trajectories.

## H2 — Same grader does not make front-ends equivalent experiments

**P7 comparison risk; P5 tuning history unclear. Medium/high severity, high source confidence.** The original sanitizer replaces family tool lists and overrides all task budgets (`run_experiments.py:455–515`); default run settings are 50 turns, 200,000 tokens and 600 seconds (`:49–63`). Inspect uses `react(tools=[bash(...)])` and task-level run limits (`inspect_critbench/evals.py:73–95`), with its own solver/system behavior. A label such as `--notools` in the original means shell-only, not no tools. Hints are a separate treatment, disabled by default. Task YAML budgets and allowed-tools fields alone are not the complete experiment specification.

**Repair/test:** publish rendered prompts, actual tool schemas, solver version, model version, effective limits, hint treatment and termination accounting for every run. Compare front-ends only in an explicitly matched experimental condition. Do not infer biased tuning simply from configurable budgets.

## H3 — Tool evidence accepts an argument string without a successful observation

**P2/P7/P10 present where tool evidence is relied on. High severity, high confidence from executed offline probe.** `_check_tool_evidence` (`evaluation/evaluator.py:143–201`) searches a permitted function call's arguments plus output for a target substring, rejects only several error phrases, and does not require output, a network operation, a successful exit code, or a parsed protocol response. An offline transcript consisting only of `run_command` with argument `echo 192.0.2.1`, no output, passes a check demanding evidence for `192.0.2.1`. See [probe results](harness_probe_results.json). This establishes a grader predicate defect, not that a real model fabricated a transcript. The original harness additionally reads `transcript.json` from the agent-writable output directory (`run_experiments.py:637–644`); Inspect constructs tool history host-side, which improves provenance but still calls this permissive predicate.

**Repair/test:** use host-recorded tool results with command exit status and validated observations tied to target, protocol, object and timestamp. For live outcomes prefer an independent trusted read. A legitimate attempt yielding no target data must not count as successful observation. Add rejection probes for echo, missing output, wrong target, connection failure and unrelated successful command.

## H4 — Prompt text can earn full credit without observations

**P4 shortcut opportunity/P7 measurement defect; no measured model reliance.** Running the actual evaluator on each task's rendered system prompt plus objective, with no hint, empty state and empty transcript, yields full success on **12 of 104 current tasks** (9 PCAP, 1 SCL, 2 VM). None of the 5 archives passes fully this way. This is an intentionally wrong response: it repeats the assignment, not a submitted analysis. Many other tasks award partial credit. Exact IDs and check-level results are in [inventory](inventory.json); the test is reproducible with `python3 docs/bias_audit/audit_harness.py`.

Interpretation must be narrow: these are deterministic grader stress tests, not a no-tool LLM evaluation and not an estimated bias effect size. Some prompt vocabulary is legitimate scaffolding. The flaw is that the oracle treats repeating that vocabulary as completing the requested observation/analysis.

**Repair/test:** check structured requested facts and associations; remove answer-bearing examples when discovery is the intended construct. Keep knowledge-only tasks labeled separately. Evaluate task paraphrases and fixture variants with frozen models to determine actual reliance.

## H5 — Check implementation and literal wording can change rankings

`contains` accepts negated answers and numeric substrings; regex uses IGNORECASE and DOTALL globally (`evaluation/evaluator.py:52–80`). Exact match only strips whitespace (`:41–49`), which is appropriate where an exact single integer is explicitly requested, but not a semantic evaluator. Nested `contains_any` is not implemented in the `multi` dispatch (`:332–348`) even though top-level `contains_any` is supported. `_parse_eval_check` does not carry the YAML `case_sensitive` option into individual checks (`tasks/task_schema.py:131–151`). These are not automatically errors in every task; individual reviews identify where they violate an objective or make a check impossible.

**Repair/test:** validate check types at load time, support/check nested alternatives consistently, and verify each task with independently derived correct answers plus wrong/negated/reordered/unit-equivalent responses. Require associations, not just a bag of expected tokens. Report full success separately from weighted partial credit; neither should be labeled physical impact without appropriate evidence.

## H6 — Sampling and experimental provenance

The 60 current static tasks reuse **3 captures and 4 SCL files**, with many questions on the same device/site. This is a useful controlled OT fixture suite, but 60 answers are not 60 independent deployments. At whole-corpus level 60/104 current definitions are static tasks, 20 are explicitly untested hardware definitions, 18 are custom IED simulation tasks, 5 are GRFICS and 1 is an active GridNet chain. An unweighted overall mean is therefore a property of this chosen mix, not a deployment-frequency estimate. The README's 81-task claim and six-active-GridNet description do not match current loader inputs.

**P1:** limited coverage is observed, but population representativeness is U without a specified target distribution. **P3:** pretraining contamination and held-out split history are U. **P5/P6:** task files do not establish final-test tuning history or whether adequate model/parser baselines appeared in a separate publication. **P8:** NA for bounded completion tasks; unequal family counts are not the literal base-rate fallacy. **P9:** simulation is legitimate under bounded claims; physical/general OT transfer remains unmeasured here.

**Repair/test:** report family and shared-fixture clusters, split at site/device/capture/template level, publish data provenance and task revision history, use parser/script and prompt-only baselines, and evaluate untouched external fixtures for generalization. Avoid confidence intervals treating correlated questions as independent sites.

## H7 — Current reset mitigations deserve credit

Inspect GridNet now enforces a complete reset and readiness checks and prevents overlapping samples within one process (`inspect_critbench/gridnet_range.py:1–32,60–93,159` and `evals.py:173–218`). The original harness instead leaves GridNet running and documents a manual full reset (`run_experiments.py:229–290`); its batch path starts the range once (`:902–903`). This is a material difference for repeated-run independence. Older README statements and archived weak tasks should not be used to claim that the current Inspect path has no reset; the original path still requires separate reset control. Runtime determinism and coordination across separate evaluator processes were not validated. The lock is process-local, so independently launched jobs still require external exclusive scheduling. An existing implementation mitigation is evidence even without a fresh physical experiment; it is not proof that all reset problems are solved.

## H8 — Original batch runs reuse modified dynamic state

**P2/P3/P7 conditional carryover risk, high severity and high source confidence.** `run_experiments.py:899–906` starts each needed stack once before constructing/iterating the experiment list; `:910–939` runs task/model/repetition combinations against those same services, and `:941–945` stops IED/GRFICS only in the batch finalizer. No per-run reset occurs in that path. Later trials can inherit an earlier trial's successful target value or an interfering modification. Serial execution avoids simultaneous writes but does not restore initial state. This can inflate or depress later scores and confound model order. GridNet state persists beyond the batch as well. We did not measure this effect on existing model trajectories.

Inspect creates per-sample IEC/GRFICS compose sandboxes, and GridNet has the separate reset mitigation described in H7. Those paths must be reported separately. Repair the original path with per-run clean provisioning, a trusted initial-state assertion, and independent before/after observations. Test A→B and B→A model orders against identical initial snapshots. Record setup failures separately from capability failures.

## Reproduction and limits

`audit_harness.py` parses all 109 definitions and uses the repository's loader/evaluator. State is always supplied as `{}` so no state API is contacted. It stores task hashes, raw environment mapping, check types, prompt-only and empty-answer results. The forged tool test uses a documentation-only address and executes no shell command. Family scripts supply fixture checks and further task-specific counterexamples. No purchased API calls, new containers, hardware actions, or changes to task/grader code were needed. This audit establishes validity defects and testable risks; paired model trials remain necessary to measure their influence on model scores or rankings.
