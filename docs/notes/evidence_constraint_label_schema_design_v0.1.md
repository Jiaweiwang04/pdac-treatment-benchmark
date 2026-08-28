# Track A Evidence and Constraint Label Schema v0.1

Status: `draft_not_locked`

## Purpose

This document defines the patient-candidate label contract for the Track A benchmark. The unit is one locked PDAC decision point `t0` and one candidate from the main candidate pool.

## Process

### Source definitions

The schema references:

- [cohort_definition_v0.1.yaml](../../code/config/cohort_definition_v0.1.yaml), version v0.1.3.1;
- [candidate_treatment_space_v0.1.yaml](../../code/config/candidate_treatment_space_v0.1.yaml), version v0.1.1;
- [evidence_constraint_label_schema_v0.1.yaml](../../code/config/evidence_constraint_label_schema_v0.1.yaml), version v0.1.

Strict Extended contains 557 decision points and Strict Core contains 475. Evidence inputs use the locked cancer instance and information available strictly before `t0`.

### Label families

| Family | Purpose |
|---|---|
| `observed_next_regimen` | auxiliary observational alignment and behavioral baseline |
| `evidence_label` | primary benchmark target from frozen evidence and Track A conditions |
| `outcome_label` | secondary survival-aware endpoint linkage |

TTNT remains in the endpoint validation queue because its time origin requires confirmation against `t0`.

### Assessment axes

| Axis | Values |
|---|---|
| `evidence_status` | `supported`, `conditional`, `not_supported`, `insufficient_evidence` |
| Track A condition | `satisfied`, `not_satisfied`, `unknown`, `not_applicable`, `manual_review` |
| `clinical_clearance_status` | `not_assessed_track_b_frozen`, `requires_clinical_review` |
| Track A label | `consider`, `conditional_review`, `exclude`, `insufficient_evidence` |

Candidate evidence vocabulary is mapped deterministically. Accessible supporting evidence maps to `supported`; conflicting FOLFOX/OFF evidence and the GEMPAX evidence profile map to `conditional`. Missing or incomplete observations map to `unknown` or `manual_review`.

### Label derivation

The derivation order is:

1. row validity;
2. explicit contradiction of a required Track A condition;
3. evidence support status;
4. conditional, unknown, or manual-review conditions;
5. supported candidate consideration.

| Label | Meaning |
|---|---|
| `consider` | supported evidence and satisfied observable Track A conditions |
| `conditional_review` | conditional evidence or unresolved Track A condition |
| `exclude` | explicit pre-`t0` contradiction or unsupported evidence context |
| `insufficient_evidence` | available evidence does not support a directional assessment |

Track B is stored as a separate axis. Its fields include performance status, laboratory values, organ function, dose modification, toxicity, detailed contraindications, and drug interactions.

### Candidate-specific policies

- `folfox_or_off` and `gemcitabine_paclitaxel_after_folfirinox` have a maximum Track A label of `conditional_review`.
- `ntrk_fusion_targeted_therapy` produces a class-level output with mutually exclusive permitted agents.
- Tumor BRCA findings are stored as review signals for the germline BRCA maintenance condition.
- Biomarker absence is represented according to assay coverage and result availability.

### Data and privacy controls

Formal identifiers serve as linkage keys. Model features use clinical variables and provenance fields. Patient-level outputs are stored under `data/processed/`; public reports contain aggregate values with `n < 5` suppression.

The time-leakage audit covers the selected `t0` regimen, later treatments, OS/PFS/TTNT, death and last-alive fields, follow-up fields, and NGS or biomarker results by report time.

## Results

The schema defines the following patient-candidate fields:

- formal linkage keys and candidate ID;
- row validity and source versions;
- evidence source IDs;
- structured Track A condition assessments;
- Track B assessment status;
- reason codes;
- Track A evidence-and-constraint label;
- clinical-clearance status;
- auxiliary observed-regimen and outcome linkage flags.

The 24-case Pilot has instantiated this contract for 16 main-pool candidates, producing 384 rule-derived rows. Expert review is Plan A. A supervisor-approved frozen-guideline rulebook is Plan B and produces `guideline_evidence_eligibility`.

## Validation

```powershell
python code/scripts/validate_evidence_constraint_label_schema.py --repo-root .
python -m pytest code/tests/test_evidence_constraint_label_schema.py -q
```

The validator checks source-version alignment, cohort invariants, strict pre-`t0` operators, label-family separation, missingness states, Track A/Track B separation, candidate overrides, table contract, and privacy fields.
