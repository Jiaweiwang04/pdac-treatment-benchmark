# Cohort Lock and Label Feasibility Audit v0.1.3.1

Generated: deterministic 3.1 rebuild; no wall-clock timestamp
Cohort definition file: cohort_definition_v0.1.yaml
Status: draft_not_locked

## Key Repairs

- t0 selection is now locked to formal PDAC cancer-instance keys before regimen, NGS, and advanced-evidence filtering.
- Main advanced-evidence rule is strict: advanced_evidence_day < t0 regimen start day.
- Regimen mapping now separates canonical_drug_set from regimen_family and retains all recognized components.
- Endpoint availability distinguishes t0-validated OS/PFS fields from field_present_not_t0_validated TTNT fields.
- Public CSV count cells with 0<n<5 are suppressed.

## Cohort Accounting

| Cohort | n | Status | Definition |
|---|---:|---|---|
| round2_definition_A_reference | 566 | reference_from_previous_round | Old Definition A usable count from second-round report. |
| round2_definition_A_recomputed | 566 | recomputed_legacy_logic | Recomputed old Definition A for reconciliation only. |
| round3_initial_extended_reference | 557 | reference_from_e7a7007 | Old third-round Extended draft, not reused for selection. |
| round3_initial_core_reference | 485 | reference_from_e7a7007 | Old third-round Core draft, not reused for selection. |
| legacy_round3_selected_all | 589 | legacy_recomputed_for_risk_audit | Old patient-first third-round candidate selection. |
| repaired_candidate_pool | 594 | candidate_pool | Locked PDAC instance regimen candidates with strict prior NGS; advanced relation not yet filtered. |
| strict_extended | 557 | draft_not_locked | Outcome-independent repaired Extended: first PDAC t0 with confirmed_pre_t0 advanced evidence. |
| strict_core | 475 | draft_not_locked | Strict Extended plus clean treatment sequence and standardized non-masked regimen family. |
| same_day_sensitivity_extended | 557 | sensitivity_only | Includes same_day_ambiguous advanced evidence; excluded from strict Core. |
| advanced_timing_pending_review | 0 | manual_review | Advanced status present but date missing or relative timing unknown. |

## Cross-Cancer t0 Audit

| Metric | n | Note |
|---|---:|---|
| patients | 1109 | Formal patient key cohort + record_id. |
| index_cancer_records | 1110 | Index cancer rows; no row is dropped arbitrarily. |
| patients_with_multiple_cancers | 216 | patient_level_dataset.n_cancers > 1. |
| patients_with_multiple_index_cancer_records | <5 | Requires instance-level handling. |
| regimen_cancer_keys_not_in_index_cancer_table | 99 | Cross-cancer regimen keys excluded before t0 selection. |
| regimen_rows_not_in_index_cancer_table | 193 | Rows excluded from PDAC t0 search. |
| legacy_selected_non_index_cancer_patients | 0 | Old patient-first script risk check. |
| legacy_selected_non_pdac_instance_patients | 32 | Old selected t0 not mapped as draft PDAC include. |
| t0_changed_after_instance_fix_patients | 0 | Same patient, different cancer-instance/regimen/start/sample signature. |
| manual_review_cancer_instance_patients | <5 | Multiple include PDAC instances cannot be automatically locked. |

## Endpoint-Specific Availability in Strict Extended

| Endpoint | Field-present evaluable | Post-t0 validated evaluable | Events | Censored | Status |
|---|---:|---:|---:|---:|---|
| OS | 557 | 557 | 464 | 93 | t0_validated |
| PFS-I | 533 | 533 | 419 | 114 | t0_validated |
| PFS-M | 533 | 533 | 352 | 181 | t0_validated |
| TTNT-any-cancer | 557 | 0 | 517 | 40 | field_present_not_t0_validated |
| TTNT-associated-cancer | 557 | 0 | 516 | 41 | field_present_not_t0_validated |

## Round 2 vs Repaired Strict Extended

| Category | Reason | n |
|---|---|---:|
| intersection | in_both | 557 |
| old_only | all_old_only | 9 |
| new_only | all_new_only | 0 |
| old_only_reason | pdac_instance_not_locked_or_not_include | 9 |

## Conclusion

Conditional Go: status remains draft_not_locked.

## Unresolved Items

- PDAC mapping remains draft_not_locked; PAASC/ambiguous histology requires medical or mentor confirmation.
- TTNT endpoints are field_present_not_t0_validated until time-origin confirmation is complete.
- Observed regimen labels include masked/manual/unknown categories outside strict Core.
- Evidence-supported candidate-set labels require the next-stage evidence snapshot and candidate-space design.
- Track B remains frozen because ECOG/labs/dose/toxicity fields are not available as stable t0 inputs.

Do not start model training, RAG, agents, or baseline modeling from this audit.
