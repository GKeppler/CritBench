# CritBench tasksv2 bias audit

**Historical assessment:** the seven priority rows below have since been addressed. See [the ordered repair record](REPAIRS.md) for changes, tests and remaining limits.

Reviewed every v2 definition using the Arp et al. P1–P10 methodology adapted in [RUBRIC.md](RUBRIC.md): **53 tasks — 19 SCL, 16 PCAP, 10 VM, and 8 hardware awaiting baseline**. All 45 label-backed tasks received offline grader probes; all 35 static tasks received independent fixture checks. Hardware was reviewed prospectively, without inventing labels or running devices. No production inputs were changed; 112 input hashes were checked.

V2 materially improves the original corpus: structured relations penalize omissions and fabricated entities; independent static answers pass; prompt/empty probes fail; all six VM actions reject unchanged initial state. Explicit development-only scope, separated hint treatments and pending hardware labels are useful safeguards. V1 and v2 scores are not comparable.

## Findings that merit repair first

| Finding | Demonstrated result | Consequence |
|---|---|---|
| PTP identifier loses integer precision | Incorrect adjacent 64-bit clock identity receives 1.0 | False positive in pcap_time_source_dependency |
| SCL APPID interpreted in wrong base | Correct 0x4000 scores 0.9; wrong 0x0FA0 scores 1.0 | Penalizes a valid protocol representation |
| VM discovery baseline incomplete | Source-derived model including LPHD1 scores 0.8; incomplete baseline scores 1.0 | Rewards omission of a real modeled node |
| Generic normalization erases type/reference distinctions | Boolean accepted as integer/instance; explicitly wrong FC accepted | Structured formatting alone does not guarantee semantic correctness |
| Task framing overstates configuration evidence | SBO treated as an authentication barrier; VLAN 0 treated as proof of no switching isolation | Correct extraction can reward an unsupported security conclusion |
| Some action requirements remain ungraded | Prior reads lack chronology evidence; requested written fields can be wrong/absent | Success covers less than the stated action/report contract |
| Shared measurement safeguards are incomplete | 35 static tasks expose sibling fixtures; default metrics lack declared floor exclusion/fixture clustering | Environment and reported aggregate need alignment with ADR |

Other task-specific findings include a subscription graph that merges distinct source logical devices, planning tasks that assess headers without receiver acceptance prerequisites, incomplete fixture metadata, and prospective hardware capture/evidence problems. These are documented individually, with mitigations.

## Read the results

- [Task matrix](TASK_MATRIX.md): every task, every pitfall; [CSV](TASK_MATRIX.csv) for analysis.
- [Full records](all_task_reviews.json): individual rationale, source evidence, exact probes, severity, limitations and remedies.
- [SCL review](SCL_REVIEW.md), [PCAP review](PCAP_REVIEW.md), [VM and hardware review](DYNAMIC_REVIEW.md).
- [Shared harness/environment review](HARNESS_REVIEW.md): applies alongside task-local ratings and contains reproduction commands.
- [Coverage verification](coverage_check.json), [input hashes](input_manifest.json), [secondary adjudications](secondary_review_changes.json).

The rubric was fixed before family assessment. Delegated reviewers independently investigated separate families; root checked the evidence and harmonized final ratings. PCAP/dynamic primary records are preserved. The SCL reviewer completed independent extraction/probes but was interrupted before writing ratings; root completed that report. This is an agent-assisted source audit, not the paper's independent human expert panel or an inter-rater reliability study. The adjudicated matrix/full records take precedence over primary family ratings: VM P1 credits the bounded dev claim, and PCAP P4 remains unclear without model perturbation experiments.

P/PP indicate evidenced mismatches or partial safeguards; U means unavailable evidence, not proven bias; NP is limited to the inspected claim; NA identifies inapplicability. Ratings are not summed. Shared findings are recorded separately to avoid mistaking a task-local NP for a globally clean experiment.

These results establish potential measurement bias and reproducible oracle counterexamples, **not measured model bias or ranking changes**. Next, repair the confirmed semantic defects, freeze configurations and run paired original/repaired and semantics-preserving fixture variants with equal budgets, reporting full success, partial score, tool evidence and fixture-cluster uncertainty. Hardware remains excluded until an actual reviewed baseline and integration checks exist.
