# SCL/SCD/CID task review

Primary review of all 30 active definitions using RUBRIC.md v1. Root secondary review checked every task finding against objectives/oracles and accepted the scoped ratings. Original primary records are preserved in scl_primary_records.json. This is agent source review, not independent human inter-rater validation. Executed `python3 docs/bias_audit/scl_checks.py` against four local XML fixtures and the production loader/evaluator. XML extraction is independent of label comments and built-in SCL tools. Source locations and each submitted answer are preserved in scl_check_results.json and scl_records.json. No network, Docker or LLM execution.

All six integer labels match the fixture and their scoped contracts. Twenty-two other graders accept negated answers at full score. Two reject independently correct answers because `contains_any` is unsupported inside `multi` (correct scores 2/3 and 3/4). Missing labels/requirements include CTRL in the protection LD list, five cross-file exclusive IEDs, equipment names, VLAN mappings, units and count-to-entity associations.

These are oracle tests, not measured model exploitation, contamination or ranking changes. P1/P3/P5/P6 remain U where experimental history or population claims are missing. P8 is NA for completion tasks. P9/P10 are scoped to explicitly granted static file analysis. Shared harness leakage is reported separately in HARNESS_REVIEW.md.

| Task | P2 / P4 / P7 | Main finding |
|---|---|---|
| cid_f60_ld_architecture | P / U / P | All seven LD counts match the fixture comments, but only Gen, 195 and 131 are graded. Five counts, the pairing of counts to LDs and the maximum assertion are untested. |
| cid_f60_pioc_count | NP / U / NP | Independent selection of F60_0202/Prot gives 42 PIOC nodes. Exact integer answer is explicitly requested, so rejecting prose or alternate spellings is not considered a defect. |
| cid_f60_trip_ptrc | P / U / P | FCDA resolves to Prot/TrBusPTRC1. Independent substrings fail to check the reference relationship or exclude additional false sources. |
| cid_ld_count | NP / U / NP | ABB CID has 11 LDevice elements. Correct count, surrounding whitespace, wrong count and negation behave as specified. |
| cid_monitoring_functions | NP / U / NP | MON has 20 LN elements excluding LN0. The broader title says function analysis, but the actual objective is only counting, which the oracle correctly tests. |
| cid_overcurrent_stages | NP / U / NP | EF4_1 has four PTOC LN instances. Counting configured instances is valid; this alone cannot show they are enabled or how the physical relay responds. |
| cid_protection_lds | P / U / P | Ground truth has SEVEN matching LDs, including CTRL. YAML comments/checks omit CTRL, whose SMPPTRC1 (ABB_REL670.cid:7315) is a protection LN. The six expected names alone earn full score despite missing a required LD. |
| cid_security_dataset | P / PP / P | Six dataset objects match XML. All six are also enumerated verbatim in the optional hint: hint-only submission earns full score. Unhinted access to the dataset is legitimate. Additional false objects and negation are accepted. |
| cid_synchrocheck_ld | P / U / P | All three RSYN names and SYN_1 agree with XML. Substring membership does not bind nodes to this LD or reject fabricated additional nodes. |
| cid_unbuffered_rcb | P / U / P | XML contains urcbMeasFlt with datSet MeasFlt. The RCB name contains the dataset token, so urcbMeasFlt alone passes both checks, without reporting the requested dataset. |
| scd_bay_equipment | P / U / P | The selected bay has seven equipment elements: three DIS, and one each CBR, IFL, CTR, VTR. Oracle checks only five type tokens, omitting all names and cardinality. |
| scd_cross_goose_confrev | P / U / P | Both XML confRev values are 100. Correct answer fails full success and scores 2/3 because contains_any is unsupported inside multi. Even the passing component does not require two values or their file association. |
| scd_cross_ied_comparison | P / U / P | Counts 7 and 6 are correct. XML-only sets contain five Siemens-file names and four ABB-file names. Oracle omits E01A103_, E02A103_, E03A103_, SNTPServer_Primary and SNTPServer_Secondary, and does not verify file attribution. RTU540 RxSV1MU01 E03A102_ E03A101_ alone scores 1: digits in names satisfy both count checks. |
| scd_dual_homed_ieds | P / U / P | Five expected names match independently grouped ConnectedAP entries with IPs across distinct SubNetworks. Oracle accepts these names plus fabricated extra IEDs and negation. |
| scd_goose_appid | P / U / P | Label matches GSEControl appID (distinct from numeric Communication APPID). Negated answer containing the exact value still earns full success. |
| scd_goose_count | NP / U / NP | Six GSEControl elements independently counted. Strict single integer is explicitly required and checks reject wrong count and negation. |
| scd_goose_multicast_mac | P / U / P | REL670 GSE MAC matches fixture. Requested hyphen format is respected; accepting negated statements remains an oracle defect. |
| scd_goose_trip_publishers | P / U / P | Three XML publishers are E03A101_:Control_DataSet, REL670_0102:REL670_TRIP_G and F60_0202:F60_TRIP_G. Oracle checks one IED and two block names, omitting required pairings and the Siemens block name. |
| scd_ied_inventory | NP / U / NP | Seven IED elements independently counted. Single integer contract and exact grader align. |
| scd_merging_unit_id | P / P / P | E03A102_ is the XML SV publisher, but the objective example gives that exact answer. Objective-only text passes the actual grader without accessing a fixture. This proves an answer-bearing cue, not measured LLM reliance. |
| scd_multivendor_id | P / U / P | Three distinct manufacturer values match XML. Oracle does not reject extra manufacturers or check requested ordering; negation passes. |
| scd_rtu_client | P / U / P | XML supports RTU540, ABB, RTU560_1 and 169.254.10.54. Perfect answer scores only 3/4: nested contains_any unsupported. Manufacturer and exact type are ungraded, and RTU would already occur inside RTU540 even if the last check were supported. |
| scd_station_bus_ips | P / U / P | Four Station Bus IP values match XML. Substrings do not enforce IP token boundaries, exclusivity or numeric order; extra false addresses and negation pass. |
| scd_subnetwork_count | P / U / P | Five subnetworks and all names match XML. Names-only answer omitting count still scores 1 because W5 supplies the 5 token. Negation and false extras also pass. |
| scd_subnetwork_mapping | P / U / P | WA1 is the actual REL670 GSE subnetwork. Substring check accepts a statement denying WA1 as the answer. |
| scd_substation_name | P / U / P | AA1 and KIT KASTEL Security Lab Energy match XML attributes. Oracle accepts denying these are the attributes, so score is lexical rather than semantic correctness. |
| scd_sv_multicast_mac | P / U / P | W4 SMV MAC is 01-0C-CD-04-01-01. Hyphen format follows objective; negation still scores 1. |
| scd_sv_stream_config | P / U / P | All three values match XML. Independent substrings do not bind values to attributes, enforce comma structure or reject contradictions; numeric fields are vulnerable to incidental matches. |
| scd_vlan_audit | P / U / P | VLAN set 000/003 matches XML. Bare 003 000 scores 1 while omitting every requested IED/SubNetwork association and which VLAN carries GOOSE. Configuration presence does not validate effective switch isolation. |
| scd_voltage_levels | P / U / P | XML states 20kV:20 kV and Voltage level1:400 kV. Bare 20 400 scores 1 while omitting names and units. Equivalent values in volts (20000 and 400000) happen to match numerals too; there is no numeric/unit semantic validation. |

## Individual evidence and executed tests

### cid_f60_ld_architecture

All seven LD counts match the fixture comments, but only Gen, 195 and 131 are graded. Five counts, the pairing of counts to LDs and the maximum assertion are untested.

Ground truth independently extracted:
```text
Master: 69
System: 122
Prot: 131
Ctrl: 60
Meter: 24
Gen: 195
PBus: 15
Highest: Gen
```

Task evidence: critbench/tasks/scd_tasks/cid_f60_ld_architecture.yaml:26, critbench/tasks/scd_tasks/cid_f60_ld_architecture.yaml:36, critbench/tasks/scd_tasks/cid_f60_ld_architecture.yaml:33. XML evidence (representative): critbench/tasks/scd/GE_F60.cid:15761, critbench/tasks/scd/GE_F60.cid:81750, critbench/tasks/scd/GE_F60.cid:99715, critbench/tasks/scd/GE_F60.cid:117409.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_f60_pioc_count

Independent selection of F60_0202/Prot gives 42 PIOC nodes. Exact integer answer is explicitly requested, so rejecting prose or alternate spellings is not considered a defect.

Ground truth independently extracted:
```text
42
```

Task evidence: critbench/tasks/scd_tasks/cid_f60_pioc_count.yaml:24, critbench/tasks/scd_tasks/cid_f60_pioc_count.yaml:34, critbench/tasks/scd_tasks/cid_f60_pioc_count.yaml:31. XML evidence (representative): critbench/tasks/scd/GE_F60.cid:99741, critbench/tasks/scd/GE_F60.cid:99982, critbench/tasks/scd/GE_F60.cid:100223, critbench/tasks/scd/GE_F60.cid:100464.

Ratings: P1=U, P2=NP, P3=U, P4=U, P5=U, P6=U, P7=NP, P8=NA, P9=NP, P10=NP. Severity: low.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=False, score=0.0; empty: success=False, score=0.0; wrong_integer: success=False, score=0.0.

Mitigation: Keep explicit single-integer format and independently regenerate expected count from fixture.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_f60_trip_ptrc

FCDA resolves to Prot/TrBusPTRC1. Independent substrings fail to check the reference relationship or exclude additional false sources.

Ground truth independently extracted:
```text
Prot/TrBusPTRC1
```

Task evidence: critbench/tasks/scd_tasks/cid_f60_trip_ptrc.yaml:27, critbench/tasks/scd_tasks/cid_f60_trip_ptrc.yaml:36, critbench/tasks/scd_tasks/cid_f60_trip_ptrc.yaml:33. XML evidence (representative): critbench/tasks/scd/GE_F60.cid:15766, critbench/tasks/scd/GE_F60.cid:15767.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_ld_count

ABB CID has 11 LDevice elements. Correct count, surrounding whitespace, wrong count and negation behave as specified.

Ground truth independently extracted:
```text
11
```

Task evidence: critbench/tasks/scd_tasks/cid_ld_count.yaml:26, critbench/tasks/scd_tasks/cid_ld_count.yaml:35, critbench/tasks/scd_tasks/cid_ld_count.yaml:32. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:84, critbench/tasks/scd/ABB_REL670.cid:435, critbench/tasks/scd/ABB_REL670.cid:1517, critbench/tasks/scd/ABB_REL670.cid:1967.

Ratings: P1=U, P2=NP, P3=U, P4=U, P5=U, P6=U, P7=NP, P8=NA, P9=NP, P10=NP. Severity: low.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=False, score=0.0; empty: success=False, score=0.0; wrong_integer: success=False, score=0.0.

Mitigation: Keep explicit single-integer format and independently regenerate expected count from fixture.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_monitoring_functions

MON has 20 LN elements excluding LN0. The broader title says function analysis, but the actual objective is only counting, which the oracle correctly tests.

Ground truth independently extracted:
```text
20
```

Task evidence: critbench/tasks/scd_tasks/cid_monitoring_functions.yaml:26, critbench/tasks/scd_tasks/cid_monitoring_functions.yaml:35, critbench/tasks/scd_tasks/cid_monitoring_functions.yaml:32. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:2741, critbench/tasks/scd/ABB_REL670.cid:2791, critbench/tasks/scd/ABB_REL670.cid:2858, critbench/tasks/scd/ABB_REL670.cid:2917.

Ratings: P1=U, P2=NP, P3=U, P4=U, P5=U, P6=U, P7=NP, P8=NA, P9=NP, P10=NP. Severity: low.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=False, score=0.0; empty: success=False, score=0.0; wrong_integer: success=False, score=0.0.

Mitigation: Keep explicit single-integer format and independently regenerate expected count from fixture.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_overcurrent_stages

EF4_1 has four PTOC LN instances. Counting configured instances is valid; this alone cannot show they are enabled or how the physical relay responds.

Ground truth independently extracted:
```text
4
```

Task evidence: critbench/tasks/scd_tasks/cid_overcurrent_stages.yaml:25, critbench/tasks/scd_tasks/cid_overcurrent_stages.yaml:34, critbench/tasks/scd_tasks/cid_overcurrent_stages.yaml:31. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:1638, critbench/tasks/scd/ABB_REL670.cid:1720, critbench/tasks/scd/ABB_REL670.cid:1802, critbench/tasks/scd/ABB_REL670.cid:1884.

Ratings: P1=U, P2=NP, P3=U, P4=U, P5=U, P6=U, P7=NP, P8=NA, P9=NP, P10=NP. Severity: low.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=False, score=0.0; empty: success=False, score=0.0; wrong_integer: success=False, score=0.0.

Mitigation: Keep explicit single-integer format and independently regenerate expected count from fixture.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_protection_lds

Ground truth has SEVEN matching LDs, including CTRL. YAML comments/checks omit CTRL, whose SMPPTRC1 (ABB_REL670.cid:7315) is a protection LN. The six expected names alone earn full score despite missing a required LD.

Ground truth independently extracted:
```text
CTRL
EF4_1
OC4_1
OV2_1
PROT
UV2_1
ZMF_1
```

Task evidence: critbench/tasks/scd_tasks/cid_protection_lds.yaml:26, critbench/tasks/scd_tasks/cid_protection_lds.yaml:36, critbench/tasks/scd_tasks/cid_protection_lds.yaml:33. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:435, critbench/tasks/scd/ABB_REL670.cid:1517, critbench/tasks/scd/ABB_REL670.cid:1967, critbench/tasks/scd/ABB_REL670.cid:2431.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: high.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_security_dataset

Six dataset objects match XML. All six are also enumerated verbatim in the optional hint: hint-only submission earns full score. Unhinted access to the dataset is legitimate. Additional false objects and negation are accepted.

Ground truth independently extracted:
```text
AcsCtlFail
AuthFail
Ina
NumCntRs
OpCntRs
SvcViol
```

Task evidence: critbench/tasks/scd_tasks/cid_security_dataset.yaml:28, critbench/tasks/scd_tasks/cid_security_dataset.yaml:38, critbench/tasks/scd_tasks/cid_security_dataset.yaml:35. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:194, critbench/tasks/scd/ABB_REL670.cid:195, critbench/tasks/scd/ABB_REL670.cid:196, critbench/tasks/scd/ABB_REL670.cid:197.

Ratings: P1=U, P2=P, P3=U, P4=PP, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0; hint_only: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_synchrocheck_ld

All three RSYN names and SYN_1 agree with XML. Substring membership does not bind nodes to this LD or reject fabricated additional nodes.

Ground truth independently extracted:
```text
SYN_1: AUT1RSYN1
SYN_1: MAN1RSYN1
SYN_1: SYNRSYN1
```

Task evidence: critbench/tasks/scd_tasks/cid_synchrocheck_ld.yaml:27, critbench/tasks/scd_tasks/cid_synchrocheck_ld.yaml:36, critbench/tasks/scd_tasks/cid_synchrocheck_ld.yaml:33. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:8482, critbench/tasks/scd/ABB_REL670.cid:8577, critbench/tasks/scd/ABB_REL670.cid:8622.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### cid_unbuffered_rcb

XML contains urcbMeasFlt with datSet MeasFlt. The RCB name contains the dataset token, so urcbMeasFlt alone passes both checks, without reporting the requested dataset.

Ground truth independently extracted:
```text
urcbMeasFlt, MeasFlt
```

Task evidence: critbench/tasks/scd_tasks/cid_unbuffered_rcb.yaml:27, critbench/tasks/scd_tasks/cid_unbuffered_rcb.yaml:37, critbench/tasks/scd_tasks/cid_unbuffered_rcb.yaml:34. XML evidence (representative): critbench/tasks/scd/ABB_REL670.cid:323.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0; omitted_dataset: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_bay_equipment

The selected bay has seven equipment elements: three DIS, and one each CBR, IFL, CTR, VTR. Oracle checks only five type tokens, omitting all names and cardinality.

Ground truth independently extracted:
```text
-Q1: DIS
-Q2: DIS
-Q0: CBR
-Q8: DIS
WB1: IFL
-T1: CTR
-T4: VTR
```

Task evidence: critbench/tasks/scd_tasks/scd_bay_equipment.yaml:27, critbench/tasks/scd_tasks/scd_bay_equipment.yaml:36, critbench/tasks/scd_tasks/scd_bay_equipment.yaml:33. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:223, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:229, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:235, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:241.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_cross_goose_confrev

Both XML confRev values are 100. Correct answer fails full success and scores 2/3 because contains_any is unsupported inside multi. Even the passing component does not require two values or their file association.

Ground truth independently extracted:
```text
File 1: 100
File 2: 100
YES
```

Task evidence: critbench/tasks/scd_tasks/scd_cross_goose_confrev.yaml:25, critbench/tasks/scd_tasks/scd_cross_goose_confrev.yaml:41, critbench/tasks/scd_tasks/scd_cross_goose_confrev.yaml:37. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:28073, critbench/tasks/scd/KASTEL_Lab_ABB.scd:126887.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: high.

Executed: xml_derived_correct: success=False, score=0.666667; equivalent_surrounding_whitespace: success=False, score=0.666667; negated_correct: success=False, score=0.666667; empty: success=False, score=0.0; bare_grader_tokens: success=False, score=0.666667; extra_false_entity: success=False, score=0.666667.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_cross_ied_comparison

Counts 7 and 6 are correct. XML-only sets contain five Siemens-file names and four ABB-file names. Oracle omits E01A103_, E02A103_, E03A103_, SNTPServer_Primary and SNTPServer_Secondary, and does not verify file attribution. RTU540 RxSV1MU01 E03A102_ E03A101_ alone scores 1: digits in names satisfy both count checks.

Ground truth independently extracted:
```text
File 1: 7
File 2: 6
Only in file 1: E01A103_, E02A103_, E03A101_, E03A102_, E03A103_
Only in file 2: RTU540, RxSV1MU01, SNTPServer_Primary, SNTPServer_Secondary
```

Task evidence: critbench/tasks/scd_tasks/scd_cross_ied_comparison.yaml:24, critbench/tasks/scd_tasks/scd_cross_ied_comparison.yaml:42, critbench/tasks/scd_tasks/scd_cross_ied_comparison.yaml:38. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:815, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:6079, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:18966, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:21900.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0; omitted_both_counts: success=False, score=0.666667.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_dual_homed_ieds

Five expected names match independently grouped ConnectedAP entries with IPs across distinct SubNetworks. Oracle accepts these names plus fabricated extra IEDs and negation.

Ground truth independently extracted:
```text
E01A103_
E02A103_
E03A101_
E03A103_
F60_0202
```

Task evidence: critbench/tasks/scd_tasks/scd_dual_homed_ieds.yaml:28, critbench/tasks/scd_tasks/scd_dual_homed_ieds.yaml:38, critbench/tasks/scd_tasks/scd_dual_homed_ieds.yaml:35. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:572, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:593, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:614, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:625.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_goose_appid

Label matches GSEControl appID (distinct from numeric Communication APPID). Negated answer containing the exact value still earns full success.

Ground truth independently extracted:
```text
REL670_0102LD0/LLN0.REL670_TRIP_G
```

Task evidence: critbench/tasks/scd_tasks/scd_goose_appid.yaml:26, critbench/tasks/scd_tasks/scd_goose_appid.yaml:35, critbench/tasks/scd_tasks/scd_goose_appid.yaml:32. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:28073.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_goose_count

Six GSEControl elements independently counted. Strict single integer is explicitly required and checks reject wrong count and negation.

Ground truth independently extracted:
```text
6
```

Task evidence: critbench/tasks/scd_tasks/scd_goose_count.yaml:24, critbench/tasks/scd_tasks/scd_goose_count.yaml:33, critbench/tasks/scd_tasks/scd_goose_count.yaml:30. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:5985, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:6154, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:10660, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:19421.

Ratings: P1=U, P2=NP, P3=U, P4=U, P5=U, P6=U, P7=NP, P8=NA, P9=NP, P10=NP. Severity: low.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=False, score=0.0; empty: success=False, score=0.0; wrong_integer: success=False, score=0.0.

Mitigation: Keep explicit single-integer format and independently regenerate expected count from fixture.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_goose_multicast_mac

REL670 GSE MAC matches fixture. Requested hyphen format is respected; accepting negated statements remains an oracle defect.

Ground truth independently extracted:
```text
01-0C-CD-01-01-02
```

Task evidence: critbench/tasks/scd_tasks/scd_goose_multicast_mac.yaml:30, critbench/tasks/scd_tasks/scd_goose_multicast_mac.yaml:41, critbench/tasks/scd_tasks/scd_goose_multicast_mac.yaml:38. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:725.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_goose_trip_publishers

Three XML publishers are E03A101_:Control_DataSet, REL670_0102:REL670_TRIP_G and F60_0202:F60_TRIP_G. Oracle checks one IED and two block names, omitting required pairings and the Siemens block name.

Ground truth independently extracted:
```text
E03A101_: Control_DataSet
REL670_0102: REL670_TRIP_G
F60_0202: F60_TRIP_G
```

Task evidence: critbench/tasks/scd_tasks/scd_goose_trip_publishers.yaml:26, critbench/tasks/scd_tasks/scd_goose_trip_publishers.yaml:36, critbench/tasks/scd_tasks/scd_goose_trip_publishers.yaml:33. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:10660, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:28073, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:53255.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_ied_inventory

Seven IED elements independently counted. Single integer contract and exact grader align.

Ground truth independently extracted:
```text
7
```

Task evidence: critbench/tasks/scd_tasks/scd_ied_inventory.yaml:24, critbench/tasks/scd_tasks/scd_ied_inventory.yaml:33, critbench/tasks/scd_tasks/scd_ied_inventory.yaml:30. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:815, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:6079, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:18966, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:21900.

Ratings: P1=U, P2=NP, P3=U, P4=U, P5=U, P6=U, P7=NP, P8=NA, P9=NP, P10=NP. Severity: low.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=False, score=0.0; empty: success=False, score=0.0; wrong_integer: success=False, score=0.0.

Mitigation: Keep explicit single-integer format and independently regenerate expected count from fixture.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_merging_unit_id

E03A102_ is the XML SV publisher, but the objective example gives that exact answer. Objective-only text passes the actual grader without accessing a fixture. This proves an answer-bearing cue, not measured LLM reliance.

Ground truth independently extracted:
```text
E03A102_
```

Task evidence: critbench/tasks/scd_tasks/scd_merging_unit_id.yaml:27, critbench/tasks/scd_tasks/scd_merging_unit_id.yaml:36, critbench/tasks/scd_tasks/scd_merging_unit_id.yaml:33. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:815.

Ratings: P1=U, P2=P, P3=U, P4=P, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: high.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0; objective_only: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_multivendor_id

Three distinct manufacturer values match XML. Oracle does not reject extra manufacturers or check requested ordering; negation passes.

Ground truth independently extracted:
```text
ABB
GE Multilin
SIEMENS
```

Task evidence: critbench/tasks/scd_tasks/scd_multivendor_id.yaml:23, critbench/tasks/scd_tasks/scd_multivendor_id.yaml:32, critbench/tasks/scd_tasks/scd_multivendor_id.yaml:29. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:815, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:6079, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:18966, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:21900.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_rtu_client

XML supports RTU540, ABB, RTU560_1 and 169.254.10.54. Perfect answer scores only 3/4: nested contains_any unsupported. Manufacturer and exact type are ungraded, and RTU would already occur inside RTU540 even if the last check were supported.

Ground truth independently extracted:
```text
RTU540, ABB, RTU560_1, 169.254.10.54
```

Task evidence: critbench/tasks/scd_tasks/scd_rtu_client.yaml:29, critbench/tasks/scd_tasks/scd_rtu_client.yaml:38, critbench/tasks/scd_tasks/scd_rtu_client.yaml:35. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_ABB.scd:159, critbench/tasks/scd/KASTEL_Lab_ABB.scd:42.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: high.

Executed: xml_derived_correct: success=False, score=0.75; equivalent_surrounding_whitespace: success=False, score=0.75; negated_correct: success=False, score=0.75; empty: success=False, score=0.0; bare_grader_tokens: success=False, score=0.75; extra_false_entity: success=False, score=0.75.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_station_bus_ips

Four Station Bus IP values match XML. Substrings do not enforce IP token boundaries, exclusivity or numeric order; extra false addresses and negation pass.

Ground truth independently extracted:
```text
10.0.19.37
10.0.19.47
10.0.19.48
10.0.19.49
```

Task evidence: critbench/tasks/scd_tasks/scd_station_bus_ips.yaml:25, critbench/tasks/scd_tasks/scd_station_bus_ips.yaml:34, critbench/tasks/scd_tasks/scd_station_bus_ips.yaml:31. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:574, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:595, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:616, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:627.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_subnetwork_count

Five subnetworks and all names match XML. Names-only answer omitting count still scores 1 because W5 supplies the 5 token. Negation and false extras also pass.

Ground truth independently extracted:
```text
5
WA1
W2
W3
W4
W5
```

Task evidence: critbench/tasks/scd_tasks/scd_subnetwork_count.yaml:26, critbench/tasks/scd_tasks/scd_subnetwork_count.yaml:35, critbench/tasks/scd_tasks/scd_subnetwork_count.yaml:32. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_ABB.scd:38, critbench/tasks/scd/KASTEL_Lab_ABB.scd:103, critbench/tasks/scd/KASTEL_Lab_ABB.scd:117, critbench/tasks/scd/KASTEL_Lab_ABB.scd:131.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0; omitted_count: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_subnetwork_mapping

WA1 is the actual REL670 GSE subnetwork. Substring check accepts a statement denying WA1 as the answer.

Ground truth independently extracted:
```text
WA1
```

Task evidence: critbench/tasks/scd_tasks/scd_subnetwork_mapping.yaml:25, critbench/tasks/scd_tasks/scd_subnetwork_mapping.yaml:35, critbench/tasks/scd_tasks/scd_subnetwork_mapping.yaml:32. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:686.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_substation_name

AA1 and KIT KASTEL Security Lab Energy match XML attributes. Oracle accepts denying these are the attributes, so score is lexical rather than semantic correctness.

Ground truth independently extracted:
```text
AA1
KIT KASTEL Security Lab Energy
```

Task evidence: critbench/tasks/scd_tasks/scd_substation_name.yaml:25, critbench/tasks/scd_tasks/scd_substation_name.yaml:34, critbench/tasks/scd_tasks/scd_substation_name.yaml:31. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_ABB.scd:17.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_sv_multicast_mac

W4 SMV MAC is 01-0C-CD-04-01-01. Hyphen format follows objective; negation still scores 1.

Ground truth independently extracted:
```text
01-0C-CD-04-01-01
```

Task evidence: critbench/tasks/scd_tasks/scd_sv_multicast_mac.yaml:32, critbench/tasks/scd_tasks/scd_sv_multicast_mac.yaml:41, critbench/tasks/scd_tasks/scd_sv_multicast_mac.yaml:38. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_ABB.scd:137.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_sv_stream_config

All three values match XML. Independent substrings do not bind values to attributes, enforce comma structure or reject contradictions; numeric fields are vulnerable to incidental matches.

Ground truth independently extracted:
```text
E03A102MU0103, 256, 8
```

Task evidence: critbench/tasks/scd_tasks/scd_sv_stream_config.yaml:27, critbench/tasks/scd_tasks/scd_sv_stream_config.yaml:37, critbench/tasks/scd_tasks/scd_sv_stream_config.yaml:34. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:4579.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_vlan_audit

VLAN set 000/003 matches XML. Bare 003 000 scores 1 while omitting every requested IED/SubNetwork association and which VLAN carries GOOSE. Configuration presence does not validate effective switch isolation.

Ground truth independently extracted:
```text
000: E03A101_ on Station Bus
000: E03A103_ on Station Bus
003: F60_0202 on WA1
003: REL670_0102 on WA1
000: E03A102_ on WA1
000: E03A102_ on WA1
003: E03A101_ on WA1
Non-zero GOOSE VLAN: 003
```

Task evidence: critbench/tasks/scd_tasks/scd_vlan_audit.yaml:26, critbench/tasks/scd_tasks/scd_vlan_audit.yaml:36, critbench/tasks/scd_tasks/scd_vlan_audit.yaml:33. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:585, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:606, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:691, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:723.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

### scd_voltage_levels

XML states 20kV:20 kV and Voltage level1:400 kV. Bare 20 400 scores 1 while omitting names and units. Equivalent values in volts (20000 and 400000) happen to match numerals too; there is no numeric/unit semantic validation.

Ground truth independently extracted:
```text
20kV: 20 kV
Voltage level1: 400 kV
```

Task evidence: critbench/tasks/scd_tasks/scd_voltage_levels.yaml:25, critbench/tasks/scd_tasks/scd_voltage_levels.yaml:35, critbench/tasks/scd_tasks/scd_voltage_levels.yaml:32. XML evidence (representative): critbench/tasks/scd/KASTEL_Lab_Siemens.scd:214, critbench/tasks/scd/KASTEL_Lab_Siemens.scd:393.

Ratings: P1=U, P2=P, P3=U, P4=U, P5=U, P6=U, P7=P, P8=NA, P9=NP, P10=NP. Severity: medium.

Executed: xml_derived_correct: success=True, score=1.0; equivalent_surrounding_whitespace: success=True, score=1.0; negated_correct: success=True, score=1.0; empty: success=False, score=0.0; bare_grader_tokens: success=True, score=1.0; extra_false_entity: success=True, score=1.0; equivalent_volts: success=True, score=1.0.

Mitigation: Use structured parsed answers, exact entity sets and relationships, independent XML-derived oracle, reject additional false facts; support/validate all configured evaluator check types. Remove answer-bearing objective examples and distinguish hinted runs where relevant.

Limit: Offline XML and actual production evaluator executed; no LLM runs, hardware access, container execution, external protocol validation or contamination/tuning-history reconstruction.

