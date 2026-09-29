# PCAP v2 review

Sixteen task definitions, frozen labels, profiles, truth extractors, three full captures and the declared SCD join were reviewed under RUBRIC.md. Read-only repro: `python3 docs/bias_audit_v2/pcap_probe.py`. No validator writes or network/device actions occurred.

All16 label-derived answers and equivalent variants pass. All16 omissions/fabrications fail full success; prompt-only and empty answers score0. Independent full-capture extraction agrees with the required frozen values. These results substantially repair the v1 substring/oracle problems; they are not model-effect measurements.

One concrete false-positive remains: pcap_time_source_dependency accepts an incorrect adjacent64-bit clock identity because generic numeric normalization loses precision. Header-extraction tasks labelled P4 and timeout extraction labelled D3 have narrower demonstrated constructs than their planning/diagnosis framing. The unmanaged publisher task omits its SCD from fixture/complexity metadata and supplies an H1 prefix heuristic contradicted by its own correct SV join.

ADR0003 dev-only and fixture-clustered scope is credited: narrow site diversity alone is not rated sampling bias under this scope. Baseline extractor availability is credited but comparative model calibration remains unknown.

| Task | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 |
|---|---|---|---|---|---|---|---|---|---|---|
| pcap_appid_collisions | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_goose_publisher_map | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_goose_stream_inventory | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_goose_takeover_preconditions | NP | NP | U | NP | U | U | PP | NA | NP | PP |
| pcap_mms_endpoints | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_mms_logical_devices | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_mms_rcb_usage | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_redundancy_nodes | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_sv_sample_rates | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_sv_spoof_preconditions | NP | NP | U | NP | U | U | PP | NA | NP | PP |
| pcap_sv_stream_inventory | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_sv_sync_audit | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_tal_audit | NP | NP | U | NP | U | U | PP | NA | NP | NP |
| pcap_time_source_dependency | NP | P | U | NP | U | U | P | NA | NP | NP |
| pcap_trip_event_reconstruction | NP | NP | U | NP | U | U | NP | NA | NP | NP |
| pcap_unmanaged_publishers | PP | NP | U | NP | U | U | PP | NA | NP | NP |

## pcap_appid_collisions

Two verified collision sets: GOOSE APPID 0x0001 binds REL670 and F60; SV 0x4000 binds all three SV IDs. Oracle binds protocol, APPID and complete nested identifier set; swapped protocol/APPID associations fail. Extractor groups APPID across protocols before selecting one protocol, a latent cross-protocol conflation risk, but no such cross-protocol shared APPID exists in this fixture.

Evidence: critbench/tasksv2/pcap/pcap_appid_collisions.yaml:39 objective; :66 structured fields. critbench/tasksv2/pcap/truth.py:235 extraction semantics; labels.json and profiles.json entry pcap_appid_collisions.

Mitigation: Keep protocol in the grouping key; retain complete-set probe.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_goose_publisher_map

All six GOOSE references bind to their observed source MAC, first three OUI octets and pre-slash device text. Payload identity is explicitly a claim, not independently authenticated identity; avoiding vendor database attribution removes a v1 provenance concern.

Evidence: critbench/tasksv2/pcap/pcap_goose_publisher_map.yaml:39 objective; :63 structured fields. critbench/tasksv2/pcap/truth.py:134 extraction semantics; labels.json and profiles.json entry pcap_goose_publisher_map.

Mitigation: Maintain relation scoring; distinguish logical-device prefix from a physical chassis if expanding scope.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_goose_stream_inventory

Whole capture verifies six unique publications and all seven specified metadata fields. Metadata fields remain constant per reference; first-frame collapse therefore does not omit variation in this fixture. Explicit floor-control designation limits capability inference.

Evidence: critbench/tasksv2/pcap/pcap_goose_stream_inventory.yaml:40 objective; :62 structured fields. critbench/tasksv2/pcap/truth.py:93 extraction semantics; labels.json and profiles.json entry pcap_goose_stream_inventory.

Mitigation: Retain floor-control reporting and verify field constancy on any replacement capture.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_goose_takeover_preconditions

REL670 final and maximum stNum are both 23; six requested header fields agree with whole-capture extraction. Actual mapping omissions and crossed field values fail. However P4 planning is scored entirely as header/current-counter extraction; no acceptance policy, authentication, replay/freshness, network delivery or receiver prerequisite is required. This supports a limited observed-header task, not the ADR full-precondition planning claim.

Evidence: critbench/tasksv2/pcap/pcap_goose_takeover_preconditions.yaml:39 objective; :66 structured fields. critbench/tasksv2/pcap/truth.py:298 extraction semantics; labels.json and profiles.json entry pcap_goose_takeover_preconditions.

Mitigation: Rename/reclassify as observed-header correlation, or demand an explicit bounded receiver model and complete acceptance prerequisites; do not assert unauthenticated acceptance for every subscriber.

Severity medium; confidence medium. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_mms_endpoints

Both MMS traffic directions confirm client 169.254.10.54 and server 169.254.10.12:102; server MAC is 00:02:a3:e2:9d:c0. Client/server swap fails. Single-association premise is consistent with decoded traffic and floor-control designation.

Evidence: critbench/tasksv2/pcap/pcap_mms_endpoints.yaml:40 objective; :61 structured fields. critbench/tasksv2/pcap/truth.py:108 extraction semantics; labels.json and profiles.json entry pcap_mms_endpoints.

Mitigation: Retain typed address association and single-association scope; validate cardinality rather than silently choosing most common if fixtures change.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_mms_logical_devices

Independent decoded domainId union gives eleven logical devices. Scope says devices appearing in the exchange, avoiding v1 unsupported total-device claim. Complete-set omission/fabrication probes fail; names remain attached to this capture.

Evidence: critbench/tasksv2/pcap/pcap_mms_logical_devices.yaml:39 objective; :60 structured fields. critbench/tasksv2/pcap/truth.py:120 extraction semantics; labels.json and profiles.json entry pcap_mms_logical_devices.

Mitigation: Retain observed-domain scope; compare inventory against server-wide enumeration only if that broader claim is intended.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_mms_rcb_usage

Decoded BR/RP references give brcbStatNrml01 (13 attributes) and urcbMeasFlt01 (11 attributes). Objective asks attributes appearing in the exchange, so collecting reads and writes is consistent; attributes_written schema key and extractor docstring are misleading names, not proof of a wrong current label. Buffering is inferred in extractor from name prefix rather than BR/RP, though both agree in this fixture.

Evidence: critbench/tasksv2/pcap/pcap_mms_rcb_usage.yaml:39 objective; :63 structured fields. critbench/tasksv2/pcap/truth.py:196 extraction semantics; labels.json and profiles.json entry pcap_mms_rcb_usage.

Mitigation: Rename attributes_written to attributes_observed; derive buffering from BR/RP rather than convention in the block name.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_redundancy_nodes

Eight distinct supervision source MACs found. Five also appear as GOOSE/SV publishers and three do not. Corrected targeted negative flips first node process-data boolean and fails; naive swap of the first two MACs preserves the same true-valued set and correctly passes.

Evidence: critbench/tasksv2/pcap/pcap_redundancy_nodes.yaml:39 objective; :61 structured fields. critbench/tasksv2/pcap/truth.py:189 extraction semantics; labels.json and profiles.json entry pcap_redundancy_nodes.

Mitigation: Keep relation check and test association mutations that actually change the represented set; preserve observation-only capability scope.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_sv_sample_rates

Independent endpoint-interval estimate gives MU320 4000.9402, Siemens 12802.1549 and SEL 3999.8986 samples/s, rounding to 4000/12800/4000. Respective noASDU values are 1/8/1. This agrees with labels despite extractor counting N frames across N-1 inter-frame intervals, a small endpoint convention difference below requested rounding.

Evidence: critbench/tasksv2/pcap/pcap_sv_sample_rates.yaml:39 objective; :60 structured fields. critbench/tasksv2/pcap/truth.py:211 extraction semantics; labels.json and profiles.json entry pcap_sv_sample_rates.

Mitigation: Specify estimator/window convention; preserve rounding tolerance and verify robustness to packet loss before claiming source-generation rate.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_sv_spoof_preconditions

MU320 header values and end-of-capture smpSynch=2 verified; transition from 0 occurs at frame11020, time1.138495s. All six requested keys are required. P4 designation and wording pass for the stream exceed evidence from static headers: no receiver validation, timing/sample-counter/payload constraints or security assumptions are assessed.

Evidence: critbench/tasksv2/pcap/pcap_sv_spoof_preconditions.yaml:39 objective; :68 structured fields. critbench/tasksv2/pcap/truth.py:308 extraction semantics; labels.json and profiles.json entry pcap_sv_spoof_preconditions.

Mitigation: Limit claim to observed identity/header extraction or define receiver acceptance model and require all relevant prerequisites for a planning task.

Severity medium; confidence medium. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_sv_stream_inventory

Three unique SV streams are present in the mixed goose capture. All requested metadata fields are constant; Siemens carries eight ASDUs per frame, the others one. Explicit floor designation and relation equality repair v1 count-only oracle.

Evidence: critbench/tasksv2/pcap/pcap_sv_stream_inventory.yaml:40 objective; :61 structured fields. critbench/tasksv2/pcap/truth.py:101 extraction semantics; labels.json and profiles.json entry pcap_sv_stream_inventory.

Mitigation: Retain complete metadata relations and floor-control designation.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_sv_sync_audit

Across the mixed capture Siemens reports2, SEL0, MU320 reports0 then2. Only transition is MU320 frame11020, time1.138495s. The pure SV fixture used by sample-rate task has constant MU3202, so treating the two captures as interchangeable would be wrong; current environment selects correct mixed fixture.

Evidence: critbench/tasksv2/pcap/pcap_sv_sync_audit.yaml:39 objective; :61 structured fields. critbench/tasksv2/pcap/truth.py:174 extraction semantics; labels.json and profiles.json entry pcap_sv_sync_audit.

Mitigation: Keep fixture-specific labels and transition relation; interpret smpSynch as declared state, not proof of physical synchronization.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_tal_audit

Full capture confirms six constant TAL values, maximum20000ms on F60. Oracle requires every reference/TAL pair and maximum reference. D3 blind-window framing assumes receiver response directly from announced timeout; subscriber alarms and process response are not observed. Numerically correct extraction does not establish an operational blind interval.

Evidence: critbench/tasksv2/pcap/pcap_tal_audit.yaml:39 objective; :61 structured fields. critbench/tasksv2/pcap/truth.py:248 extraction semantics; labels.json and profiles.json entry pcap_tal_audit.

Mitigation: Describe maximum announced timeout, or provide receiver behavior evidence before treating this as diagnosis of actual protection consequence.

Severity medium; confidence medium. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_time_source_dependency

Announcement identity is 0xec4670fffe0aafae from MAC ec:46:70:0a:af:ae, priority128/domain0/steps0; MU320 and SEL are unsynchronized at some point. Actual grader also accepts different identity 0xec4670fffe0aafaf with score1.0 because structured.py:101 converts 64-bit hex to float. Observing one advertised grandmaster does not independently establish which clock each MU selected.

Evidence: critbench/tasksv2/pcap/pcap_time_source_dependency.yaml:39 objective; :63 structured fields. critbench/tasksv2/pcap/truth.py:318 extraction semantics; labels.json and profiles.json entry pcap_time_source_dependency.

Mitigation: Normalize integer/hex identifiers losslessly; add adjacent-large-integer negative probe. State advertised time source unless receiver selection evidence is supplied.

Severity high; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_trip_event_reconstruction

First transitions independently observed: REL670 frame79463 at8.201658s (21→22), Siemens frame79482 at8.203472s (15→16), F60 frame79644 at8.218638s (21→22). Next burst starts10.167341s. Thus hard-coded one-second grouping yields correct first burst here; ordering fields are graded within tuples and cannot be replaced by an unordered bag of names. State changes establish observed timing, not physical causality.

Evidence: critbench/tasksv2/pcap/pcap_trip_event_reconstruction.yaml:39 objective; :61 structured fields. critbench/tasksv2/pcap/truth.py:156 extraction semantics; labels.json and profiles.json entry pcap_trip_event_reconstruction.

Mitigation: Publish burst-window definition; retain explicit ordering keys and avoid inferring causal precedence beyond capture timestamps.

Severity low; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## pcap_unmanaged_publishers

XML independently contains seven IED names and configured smvID E03A102MU0103. Matching wire identities yields four absent publishers: MU320 GOOSE/SV, SEL SV and TEMPLATECFG GOOSE. Exact smvID matching correctly avoids flagging configured Siemens stream. Fixture metadata lists only goose_trip_pcap and profiles reports surfaces1 despite explicit PCAP+SCD join; SCD bytes/provenance are omitted from task complexity. H1 prefix advice is incorrect for Siemens SV ID because E03A102_ is not its prefix.

Evidence: critbench/tasksv2/pcap/pcap_unmanaged_publishers.yaml:39 objective; :68 structured fields. critbench/tasksv2/pcap/truth.py:258 extraction semantics; labels.json and profiles.json entry pcap_unmanaged_publishers.

Mitigation: Declare SCD fixture and count both surfaces; revise H1 to distinguish GOOSE naming from configured sampled-value identifiers.

Severity medium; confidence high. Exact probe submissions/results and all pitfall rationales are in pcap_records.json.

## Limits

A duplicate naive relation swap for redundancy nodes preserves identical true-valued records and correctly passes; the targeted wrong-boolean binding fails. Do not count that benign set permutation as an oracle failure. RCB attributes_written is an unfortunate key name: current objective requests all attributes in the exchange, so reads are not mislabeled under its stated question. Rates agree after nearest-hundred rounding despite N versus N-1 endpoint convention. No measured model ranking effect or physical exploit acceptance has been established.
