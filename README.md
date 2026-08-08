# pdac-treatment-benchmark

Language: English | [Chinese](README.zh-CN.md)

## Project Overview

This project builds a patient-level evidence and clinical-constraint benchmark for candidate treatment identification in advanced pancreatic ductal adenocarcinoma (advanced PDAC). The current phase is a read-only feasibility audit of the BPC PANC raw data. The project does not train models at this stage, does not recommend doses, does not prescribe treatment, and does not replace clinician judgment.

## Data Boundary

- Core raw data: [data/raw/](data/raw/) `AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/`
- [data/raw/](data/raw/) is the immutable raw-data record. Do not modify, overwrite, or commit patient-level raw data.
- [data/processed/](data/processed/) is reserved for reproducible derived data. Its contents are ignored by default to avoid accidental commits of patient-level derivatives.
- Track A and Track B are separated. Track A uses stable fields available in BPC PANC. Track B should only be created after real ECOG, laboratory, dose/modification, and toxicity fields are available.

## Repository Structure

```text
data/
  raw/                 # Raw data; read-only; not committed
  processed/           # Reproducible derived data; contents ignored by default
code/
  src/                 # Reusable source code
  scripts/             # Audit, preprocessing, and evaluation scripts
  notebooks/           # Exploratory notebooks
  results/             # Generated aggregate outputs and tables
docs/
  notes/               # Research plans, audit reports, and analysis notes
  papers/              # Manuscripts and submission materials
  slides/              # Presentation materials
warehouse/             # Inactive local files; contents ignored by default
```

## Environment

Use the local Python environment configured for this project. Current audit scripts use `pandas` and `pypdf`; see `code/requirements.txt`.

## Run the Data Audit

From the repository root:

```powershell
python code/scripts/audit_raw_data.py --repo-root .
```

Main outputs:

- [Data feasibility audit report](docs/notes/data_feasibility_audit_v1.md)
- [File inventory](code/results/data_audit/tables/file_inventory.csv)
- [Field inventory](code/results/data_audit/tables/field_inventory.csv)
- [Table relationships](code/results/data_audit/tables/table_relationships.csv)
- [Missingness summary](code/results/data_audit/tables/missingness_summary.csv)
- [Feasibility summary](code/results/data_audit/tables/feasibility_summary.csv)
- [Categorical summaries](code/results/data_audit/tables/categorical_summaries.csv)
- [Raw data inventory notebook](code/notebooks/00_raw_data_inventory.ipynb)

## Project Documents

- [V3.0 research protocol](docs/notes/research_plan_pdac_treatment_benchmark_v3.0.docx)
- [Data feasibility audit report](docs/notes/data_feasibility_audit_v1.md)

## Current Status

The first read-only audit of the BPC PANC raw data has been completed. Primary-key candidates, foreign-key candidates, field meanings, and cohort-size estimates in the report are first-pass audit outputs. They must be checked against the analytic data guide, variable dictionary, and research protocol before cohort construction.

## Round 3 Cohort Lock and Label Feasibility Audit

Run from the repository root:

```powershell
python code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

Main outputs:

- [Cohort definition draft](cohort_definition_v0.1.yaml)
- [Round 3 audit report](reports/cohort_lock_label_feasibility_v0.1.md)
- [Cohort lock flow counts](reports/tables/cohort_lock_flow_counts.csv)
- [Endpoint coverage](reports/tables/endpoint_coverage.csv)
- [Treatment sequence quality](reports/tables/treatment_sequence_quality.csv)
- [NGS selection sensitivity](reports/tables/ngs_selection_sensitivity.csv)
- [Label availability](reports/tables/label_availability.csv)
- [Time leakage field audit](reports/tables/time_leakage_field_audit.csv)
- [PDAC mapping](code/mappings/pdac_mapping_v0.1.csv)
- [Regimen mapping](code/mappings/regimen_mapping_v0.1.csv)

## Round 3.1 Cohort Repair Audit

Run from the repository root:

```powershell
C:\Users\ASUS\miniconda3\envs\ml\python.exe code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

Main repaired outputs:

- [Cohort definition draft](cohort_definition_v0.1.yaml)
- [Round 3.1 audit report](reports/cohort_lock_label_feasibility_v0.1.md)
- [Cohort reconciliation](reports/tables/cohort_reconciliation.csv)
- [Cross-cancer t0 audit](reports/tables/cross_cancer_t0_audit.csv)
- [Advanced evidence sensitivity](reports/tables/advanced_evidence_sensitivity.csv)
- [Endpoint coverage](reports/tables/endpoint_coverage.csv)
- [Center-year distribution](reports/tables/center_year_distribution.csv)
- [Regimen mapping](code/mappings/regimen_mapping_v0.1.csv)

Current 3.1 status: Conditional Go; strict Extended n=557, strict Core n=475. Counts in public CSVs apply n<5 suppression.
