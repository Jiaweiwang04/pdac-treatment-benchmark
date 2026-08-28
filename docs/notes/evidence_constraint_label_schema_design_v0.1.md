# Track A Evidence and Constraint Label Schema v0.1

Status: `draft_not_locked`

This document defines the label contract for the next private Pilot. It does not create patient-level labels, a patient-candidate table, a treatment recommendation, or a medically frozen candidate list.

## 1. Objective and non-objectives

The unit is one locked PDAC `t0` and one candidate from the main candidate pool. The schema asks whether the frozen evidence and strictly pre-`t0` Track A context support considering, conditionally reviewing, excluding, or abstaining on that candidate.

It does not predict the observed regimen as a gold standard, use OS/PFS to identify the best treatment, infer clinical fitness from missing data, select doses, or replace clinician review.

## 2. Authoritative boundaries

The schema references [cohort_definition_v0.1.yaml](../../cohort_definition_v0.1.yaml) v0.1.3.1 and [candidate_treatment_space_v0.1.yaml](../../config/candidate_treatment_space_v0.1.yaml) v0.1.1. Strict Extended remains 557 and Strict Core remains 475. The schema cannot rebuild either cohort or reselect `t0`.

Inputs must be available strictly before `t0`: the selected NGS report, advanced evidence, prior regimens, prior line or exposure context, and any biomarker result used for assessment. Same-day and post-`t0` information are excluded from the main Track A label.

## 3. Three separate label families

| Family | Role | Not allowed |
|---|---|---|
| `observed_next_regimen` | auxiliary observational proxy for descriptive alignment | gold standard, model input at `t0`, evidence source, best-treatment target |
| `evidence_label` | primary benchmark target derived from frozen evidence and pre-`t0` Track A context | copying observed choice, outcome optimization |
| `outcome_label` | secondary endpoint linkage for validated OS/PFS analyses | candidate classification, evidence label, ordinary regression target that ignores censoring |

TTNT remains unavailable for outcome use because its time origin has not been validated against `t0`.

## 4. Multi-axis representation

The schema does not collapse all uncertainty into one field.

- `evidence_status`: `supported`, `conditional`, `not_supported`, or `insufficient_evidence`.
- `track_a_constraint_status`: `satisfied`, `not_satisfied`, `unknown`, `not_applicable`, or `manual_review` for each observable condition.
- `clinical_clearance_status`: `not_assessed_track_b_frozen` or `requires_clinical_review`.
- `track_a_evidence_constraint_label`: the derived Track A target.

Missing means unknown. It never means a negative biomarker, normal laboratory value, absent contraindication, or clinical fitness.

The detailed candidate-space vocabulary is mapped deterministically: `supported_by_accessible_sources` becomes `supported`; conflicting FOLFOX/OFF evidence and the GEMPAX no-OS-benefit status become `conditional`. Any previously unseen main-candidate evidence status invalidates the row until the schema is versioned. A candidate's broad `manual_review_required` flag does not automatically downgrade every Track A label, because that flag often represents missing Track B safety review rather than uncertainty in observable Track A evidence.

## 5. Track A label semantics

| Label | Meaning |
|---|---|
| `consider` | evidence is supported and all required observable Track A conditions are satisfied or not applicable |
| `conditional_review` | evidence is conditional, required Track A information is unknown, or manual review is needed |
| `exclude` | a required Track A condition is explicitly contradicted by pre-`t0` data, or evidence is explicitly not supported for the context |
| `insufficient_evidence` | available evidence is insufficient and there is no explicit exclusion basis |

`consider` is not clinical clearance or a treatment recommendation. A row that violates the time boundary or references the wrong cohort/candidate receives no training label.

The deterministic precedence is: invalid row, explicit Track A contradiction, evidence not supported, insufficient evidence, conditional/unknown/manual review, then consider. The derivation function reads each structured condition directly; it does not trust a precomputed contradiction flag. Unknown data cannot trigger exclusion.

## 6. Track A and Track B

Track A uses stable BPC fields available strictly before `t0`. Track B remains frozen because ECOG, laboratory values, organ function, dose changes, toxicity, detailed contraindications, and drug interactions are unavailable as a stable package.

Track B does not derive or lower the Track A evidence label. Instead, every v0.1 row separately records that clinical clearance was not assessed. A future Track B version must add a separate axis and cannot reinterpret historical missing values as normal.

## 7. Confirmed candidate policies

- `folfox_or_off` and `gemcitabine_paclitaxel_after_folfirinox` remain in the Track A main pool, but their maximum Track A label is `conditional_review` because their evidence remains conditional or conflicting.
- `ntrk_fusion_targeted_therapy` remains a class-level output. Entrectinib, larotrectinib, and repotrectinib are mutually exclusive permitted agents; v0.1 cannot emit a selected agent.

These are benchmark-scope decisions, not medically frozen conclusions.

## 8. Future patient-candidate table

The schema defines the future table contract but marks it `not_created_schema_only`. The table will contain formal linkage keys, candidate ID, row validity, evidence source IDs, structured per-condition assessments, Track B assessment status, reason codes, Track A label, clinical-clearance status, provenance, and auxiliary observed/outcome linkage flags.

Formal identifiers are linkage keys only and are prohibited as model features. The observed regimen and outcome linkage flags remain auxiliary and cannot become model targets.

## 9. Privacy and leakage

Patient-level label and Pilot outputs must remain under ignored processed-data paths. Public outputs are aggregate only with the existing `n<5` suppression rule. Patient or sample identifiers cannot appear in logs, tests, reports, or public tables.

The prohibited feature groups include the selected `t0` regimen, future regimens, OS/PFS/TTNT, death and last-alive fields, follow-up fields, and NGS or biomarker results not available before `t0`.

## 10. Pilot entry criteria

The next stage may create a private 20-30 case Pilot only after implementing candidate-condition extraction and row-level provenance. It must cover supported and conditional evidence, biomarker positive/negative/unknown states when available, prior-treatment conditions, and manual-review uncertainty.

Pilot acceptance requires zero post-`t0` input fields, zero missing-as-negative logic, valid candidate/evidence references, no outcome-optimized labels, and recorded reviewer disagreements without public identifiers. No agreement threshold is frozen before observing the Pilot review process.

## 11. Remaining limits

The current guideline role of `gemcitabine_cisplatin_hrd`, a legally accessible formal guideline snapshot, detailed Track B rules, and the long-term representation of tissue-agnostic accelerated approvals remain open for clinical review. The schema preserves unknown and manual-review states so these issues do not silently become labels.

## 12. Validation

Run from the repository root:

```powershell
python -B code/scripts/validate_evidence_constraint_label_schema.py --repo-root .
python -B -m unittest tests.test_evidence_constraint_label_schema
```

The validator checks source-version alignment, 557/475 invariants, strict pre-`t0` operators, label-family separation, missingness behavior, Track B separation, candidate overrides, table non-existence, and privacy-safe schema content.
