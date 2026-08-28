# Patient-Candidate Dataset Schema Design v0.1

## Purpose

This document defines the training-data boundary for the Track A candidate-ranking benchmark. It separates patient decision contexts, candidate definitions, features, three label families, and the future patient-level split before any full training table is generated.

## Process

### Authoritative inputs

The schema inherits Strict Extended and `t0` from [cohort_definition_v0.1.yaml](../../code/config/cohort_definition_v0.1.yaml), the 16-member main pool from [candidate_treatment_space_v0.1.yaml](../../code/config/candidate_treatment_space_v0.1.yaml), and label semantics from [evidence_constraint_label_schema_v0.1.yaml](../../code/config/evidence_constraint_label_schema_v0.1.yaml).

Candidate-space v0.1.1 already contains the verified 4.1.1 technical repairs. Medical confirmation and the formal guideline snapshot remain freeze requirements.

### Dataset contracts

| Dataset | Grain | Role | Current status |
|---|---|---|---|
| `decision_point_dataset` | one locked PDAC `t0` decision point | pre-`t0` patient context | private source available; training artifact not materialized |
| `candidate_master` | one candidate | candidate identity, evidence, and conditions | available as versioned YAML |
| `patient_candidate_dataset` | one decision point-candidate pair | feature-only model subject table | not generated |
| `observed_regimen_labels` | one decision point | observed clinician-choice proxy | separate auxiliary label |
| `evidence_constraint_labels` | one decision point-candidate pair | primary candidate-ranking target | Pilot only; full table not generated |
| `outcome_dataset` | one decision point | OS/PFS secondary endpoints | separate outcome table not generated |
| `split_manifest` | one patient | future grouped split assignment | not generated or frozen |

The development row invariant is `557 × 16 = 8,912` patient-candidate rows. This is a schema expectation for the current Strict Extended and main-pool versions, not a generated training-table result.

### Feature boundary

Track A features include the locked PDAC instance, advanced status strictly before `t0`, the selected pre-`t0` NGS report, time-aligned biomarker evidence, prior treatment components, prior line context, and candidate attributes frozen before dataset assembly.

Identifiers remain linkage fields. The observed `t0` regimen, later treatment, OS/PFS/TTNT fields, follow-up, future molecular results, and reviewer labels are excluded from model inputs. ECOG, laboratory values, organ function, dose, toxicity, interactions, and detailed contraindications remain unavailable Track B groups.

### Label boundary

`observed__*`, `evidence__*`, and `outcome__*` columns are stored in separate datasets. The feature table embeds none of them. Rule-derived unreviewed evidence labels are development-only; formal benchmark labels require expert adjudication or a supervisor-approved frozen guideline rulebook.

### Split and privacy boundary

The future split unit is one patient identified by the internal linkage key. Every decision point and all candidate rows for that patient inherit one split. Preprocessing is fitted only after the split manifest is frozen.

All patient-level artifacts remain under ignored `data/processed/`. Public outputs are aggregate-only and use the existing `<5` suppression rule.

### Validation

```powershell
python code/scripts/validate_patient_candidate_dataset_schema.py --repo-root .
python -m pytest code/tests/test_patient_candidate_dataset_schema.py -q
```

## Results

The schema defines seven separate dataset contracts and preserves the 557/475 cohort invariants. The full patient-candidate table, split manifest, formal evidence labels, materialized-feature leakage audit, and model training remain unstarted.

Machine-readable schema: [patient_candidate_dataset_schema_v0.1.yaml](../../code/config/patient_candidate_dataset_schema_v0.1.yaml)

