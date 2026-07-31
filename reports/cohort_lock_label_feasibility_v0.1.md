# Cohort Lock and Label Feasibility Audit v0.1

Generated: 2026-07-31T17:41:31
Cohort definition file: cohort_definition_v0.1.yaml
Status: draft_not_locked

## Reproduction of Round 2

| Definition | Previous usable | Recomputed usable | Recomputed t0 | Match |
|---|---:|---:|---:|---|
| A | 566 | 566 | 566 | True |
| B | 568 | 568 | 568 | True |
| C | 50 | 50 | 50 | True |

## Draft Cohorts

| Cohort | n | Status | Definition |
|---|---:|---|---|
| round2_definition_A_reproduced | 566 | recomputed | Second-round feasibility proxy definition A |
| definition_A_selected_all_index_pancreatic | 589 | audit_pool | Definition A before final PDAC include filter |
| definition_A_pdac_include_selected | 557 | draft | Definition A with draft PDAC include mapping |
| definition_A_pdac_manual_review_selected | 15 | manual_review | Definition A selected but PDAC mapping uncertain |
| definition_A_pdac_exclude_selected | 17 | exclude | Definition A selected but mapped non-PDAC |
| extended_draft | 557 | draft_not_locked | Outcome-independent Extended draft |
| core_draft | 485 | draft_not_locked | Outcome-independent clean Track A Core draft |

Extended and Core are outcome-independent. Endpoint-specific subcohorts are reported separately.

## Endpoint-Specific Availability in Extended Draft

| Endpoint | Evaluable | Events | Censored | Negative time |
|---|---:|---:|---:|---:|
| OS | 557 | 464 | 93 | 0 |
| PFS-I | 533 | 419 | 114 | 0 |
| PFS-M | 533 | 352 | 181 | 0 |
| TTNT-any-cancer | 557 | 517 | 40 | 0 |
| TTNT-associated-cancer | 557 | 516 | 41 | 0 |

## Label Capability Boundaries

- `observed_next_regimen`: available_as_observed_data. Descriptive next observed regimen only; standardized=485; masked_investigational=58; manual_review=14; not a gold standard or optimal treatment label.
- `evidence_supported_candidate_set`: not_available_from_BPC_alone. Requires external evidence snapshot, candidate treatment space, clinical constraints, and manual/structured evidence labels. Do not derive by assuming observed regimen is evidence-supported.
- `post_t0_outcome`: endpoint_specific_available. OS evaluable=557; PFS-I evaluable=533; PFS-M evaluable=533; TTNT-any-cancer evaluable=557; TTNT-associated-cancer evaluable=557

## NGS Selection Sensitivity

| Strategy | n patients | Different index sample vs main | Note |
|---|---:|---:|---|
| main_latest_report_strict_before_t0 | 557 | 0 | Main analysis index NGS rule. |
| earliest_report_strict_before_t0 | 557 | 2 | Sensitivity only; same t0 patients if an NGS exists before t0. |
| latest_sample_collection_before_t0 | 557 | 1 | Uses pathology procedure date before t0 when available. |
| allow_same_day_report_t0_definition_B | 559 | not_applicable | Allows dx_cpt_rep_days <= dx_reg_start_int for t0 eligibility, but index NGS remains strict before t0 for input. |

## Key Quality Risks

- Definition A selected but PDAC manual_review: 15 patients.
- Definition A selected but PDAC excluded: 17 patients.
- Extended treatment-sequence anomalies: 0 patients.
- Extended masked/manual regimen mapping: 72 patients.
- Public reports/tables suppress patient identifiers; local Pilot patient list is written under ignored data/processed.

## Unresolved Items

- PDAC mapping is draft_not_locked and manual review is still required for PAASC/ambiguous histology.
- Track B remains frozen because ECOG/labs/dose/toxicity fields are not available as stable t0 inputs.
- Evidence-supported candidate-set labels require the next-stage evidence snapshot and candidate-space design.

## Conclusion

Conditional Go: proceed to candidate treatment space and evidence label design for Track A only, while keeping cohort_definition_v0.1.yaml as draft_not_locked. Do not start model training.
