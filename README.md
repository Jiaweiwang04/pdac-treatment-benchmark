# PDAC Treatment Benchmark

Language: English | [中文](README.zh-CN.md)

## Project Overview

This project builds a patient-level evidence-and-constraint ranking benchmark for advanced, unresectable, or metastatic pancreatic ductal adenocarcinoma (PDAC). It evaluates a predefined candidate treatment space using information available before the decision time `t0`.

## Study Design

Each assessment row represents one Strict Extended decision point and one main-pool candidate.

| Label family | Purpose |
|---|---|
| `observed_next_regimen` | Describes the clinician's observed choice for alignment and behavioral baselines |
| `evidence_label` | Represents guideline, regulatory, and observable Track A support for candidate ranking |
| `outcome_label` | Represents OS, PFS, and related follow-up endpoints for survival-aware secondary analyses |

Track A contains stable pre-`t0` disease, NGS, biomarker, and prior-treatment information. Track B contains ECOG, laboratory values, organ function, dose modification, toxicity, and detailed contraindications; its current status is `frozen`.

## Current Results

| Module | Result | Status |
|---|---|---|
| Strict cohorts | Strict Extended 557; Strict Core 475 | `conditional_go` |
| Endpoint coverage | OS 557; PFS-I 533; PFS-M 533 | audited |
| Candidate space | 16 main candidates; 11 extended candidates | `draft_not_locked` |
| Label schema | Track A evidence-and-constraint schema v0.1 | `draft_not_locked` |
| Pilot | 24 decision points × 16 candidates = 384 rows | rule-derived, review pending |
| Review Plan A | Independent double review and adjudication | primary |
| Review Plan B | Frozen rulebook producing `guideline_evidence_eligibility` | supervisor-approved fallback |

## Environment

Validated environment:

- Python 3.11.15
- pandas 3.0.3
- pypdf 6.14.2
- PyYAML 6.0.3
- pytest 9.1.1

Install dependencies:

```powershell
python -m pip install -r code/requirements.txt
```

## Directory Structure

```text
data/
  raw/                 # source data records
  processed/           # reproducible patient-level derivatives
code/
  src/                 # reusable source modules
  scripts/             # audit, generation, and validation entry points
  notebooks/           # exploratory analyses
  config/              # cohort, candidate, label, and Pilot configurations
  tests/               # automated tests
  results/
    mappings/          # PDAC, regimen, and candidate crosswalks
    reports/           # aggregate reports and tables
    data_audit/        # generated data-audit outputs
docs/
  notes/               # study plans and design decisions
    standards/         # local project-management standards index
  papers/              # manuscript materials
  slides/              # presentation materials
warehouse/             # inactive materials
```

## Data Preparation

The primary data release is located at:

```text
data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/
```

`data/raw/` stores source releases, `data/processed/` stores reproducible patient-level derivatives, and `code/results/reports/` stores aggregate outputs with small-cell suppression. External materials are registered in [external_material_registry_v0.1.yaml](code/config/external_material_registry_v0.1.yaml); machine-specific locations are recorded in `code/config/local_external_sources.yaml`.

## Reproduction Steps

### 1. Data audits

```powershell
python code/scripts/audit_raw_data.py --repo-root .
python code/scripts/audit_cohort_t0_feasibility.py --repo-root .
python code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

### 2. Candidate treatment space

```powershell
python code/scripts/generate_candidate_regimen_crosswalk.py --repo-root .
python code/scripts/validate_candidate_treatment_space.py --repo-root .
```

### 3. Label schema and evidence registry

```powershell
python code/scripts/validate_evidence_constraint_label_schema.py --repo-root .
python code/scripts/validate_external_material_registry.py --repo-root .
python code/scripts/validate_patient_candidate_dataset_schema.py --repo-root .
```

### 4. Pilot generation and validation

```powershell
python code/scripts/build_pilot_evidence_labels.py --repo-root .
python code/scripts/validate_pilot_evidence_labels.py --repo-root .
```

### 5. Automated tests

```powershell
python -m pytest code/tests/test_candidate_treatment_space.py code/tests/test_evidence_constraint_label_schema.py code/tests/test_external_material_registry.py code/tests/test_patient_candidate_dataset_schema.py code/tests/test_pilot_evidence_labels.py -q
```

## Main Outputs

- [Cohort definition](code/config/cohort_definition_v0.1.yaml)
- [Round 1 data audit](code/results/reports/data_feasibility_audit_v1.md)
- [Candidate treatment space](code/config/candidate_treatment_space_v0.1.yaml)
- [Label schema](code/config/evidence_constraint_label_schema_v0.1.yaml)
- [Patient-candidate dataset schema](code/config/patient_candidate_dataset_schema_v0.1.yaml)
- [Patient-candidate dataset design](docs/notes/patient_candidate_dataset_schema_design_v0.1.md)
- [Pilot protocol](code/config/pilot_label_protocol_v0.1.yaml)
- [Candidate-regimen crosswalk](code/results/mappings/candidate_regimen_crosswalk_v0.1.csv)
- [Cohort audit report](code/results/reports/cohort_lock_label_feasibility_v0.1.md)
- [Pilot aggregate report](code/results/reports/pilot_label_validation_report_v0.1.md)
- [Experiment progress report (Chinese)](code/results/reports/experiment_progress_report_v1.0.md)
- [Project document index](docs/notes/project_document_index_v1.0.md)

## Next Stage

The training-data contracts are defined but not materialized. Plan A produces expert-adjudicated labels after double review. Plan B produces guideline evidence eligibility labels after supervisor approval. The confirmed label path then feeds patient-candidate materialization, patient-level split freezing, leakage audit, and baseline training.

## Round 3.1 Cohort Repair Audit

Run from the repository root:

```powershell
C:\Users\ASUS\miniconda3\envs\ml\python.exe code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

Main repaired outputs:

- [Cohort definition draft](code/config/cohort_definition_v0.1.yaml)
- [Round 3.1 audit report](code/results/reports/cohort_lock_label_feasibility_v0.1.md)
- [Cohort reconciliation](code/results/reports/tables/cohort_reconciliation.csv)
- [Cross-cancer t0 audit](code/results/reports/tables/cross_cancer_t0_audit.csv)
- [Advanced evidence sensitivity](code/results/reports/tables/advanced_evidence_sensitivity.csv)
- [Endpoint coverage](code/results/reports/tables/endpoint_coverage.csv)
- [Center-year distribution](code/results/reports/tables/center_year_distribution.csv)
- [Regimen mapping](code/results/mappings/regimen_mapping_v0.1.csv)

Current 3.1 status: Conditional Go; strict Extended n=557, strict Core n=475. Counts in public CSVs apply n<5 suppression.
