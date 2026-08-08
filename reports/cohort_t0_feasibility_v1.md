# Cohort and t0 Feasibility Audit v1

Generated: deterministic t0 feasibility rebuild; no wall-clock timestamp
Raw data root: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public`

Scope: read-only feasibility audit. No modeling, no final labels, no patient-level records in outputs.

## Documents Reviewed

- README.md and README.zh-CN.md
- docs/notes/data_feasibility_audit_v1.md
- docs/notes/research_plan_pdac_treatment_benchmark_v3.0.docx
- PANC analytic data guide: Read GENIE-BPC-PANC-1.0-public-Analytic-Data-Guide.pdf with pypdf; pages=190; record_id=yes; ca_seq=yes; dx_cpt_rep_days=yes; dx_reg_start_int=yes; ca_resect_status=yes; pfs_i_g_status=yes
- PANC variable synopsis workbook was present and used to confirm requested field names against clinical_data columns.

## Data-Guide Confirmed Relationships

- Patient Characteristics: one record per patient; link to all datasets with cohort + record_id.
- BPC Project Cancer Diagnosis: link to Cancer-Directed Regimen, Cancer Panel Test, and Radiation Therapy with cohort + record_id + ca_seq.
- BPC Project Cancer Diagnosis: link to Patient, Pathology, Imaging, Medical Oncologist Assessment, and Tumor Marker datasets with cohort + record_id.
- Pathology to Cancer Panel Test: link with cohort + record_id + path_proc_number + path_rep_number.
- cpt_genie_sample_id corresponds to Tier 1 sample_id; it is used here only for aggregate sample-count checks.

## Key Field Confirmation

- PDAC histology: no final PDAC boolean exists. Candidate fields are ca_histology, naaccr_histology_cd, and cpt_oncotree_code. This audit uses a PDAC-compatible feasibility flag: adenocarcinoma/ductal-like histology or OncoTree PAAD; manual confirmation is required.
- Advanced/metastatic/unresectable: stage_dx_iv, ca_dmets_yn, ca_resect_status, dmets_post_dx, dx_to_dmets_days.
- Recurrence: no explicit recurrence field was found in clinical_data column names; dated post-diagnosis distant metastasis is available.
- NGS timing: dx_path_proc_cpt_days, dx_cpt_rep_days, path_proc_cpt_rep_days, cpt_seq_date year only.
- Regimen timing/order: dx_reg_start_int, dx_reg_end_any_int, dx_reg_end_all_int, regimen_number, regimen_number_within_cancer.
- Outcomes/follow-up: regimen-level pfs_*_g_status, tt_pfs_*_g_days, os_g_status, tt_os_g_days, ttnt_*; patient-level hybrid_death_int and dob_lastalive_int are outcome/follow-up fields, not t0 inputs.

## Variable Dictionary Evidence

Source: code/results/data_audit/tables/field_inventory.csv parsed from the PANC Variable Synopsis workbook during the first audit.

| Field | Dictionary label |
|---|---|
| `ca_dmets_yn` | Presence of Distant Metastasis at the Time of Cancer Diagnosis (Stage IV Diagnoses) |
| `ca_histology` | Histology |
| `ca_resect_status` | Tumor Resectability Status |
| `cpt_seq_date` | Year of Next Generation Sequencing |
| `dmets_post_dx` | Distant Metastasis Post Diagnosis |
| `dob_lastalive_int` | Time (Days) from Date of Birth to Last Known Alive Date |
| `dx_cpt_rep_days` | Time (Days) from Diagnosis to NGS Report |
| `dx_path_proc_cpt_days` | Time (Days) from Diagnosis to Pathology Procedure Corresponding to the NGS Report |
| `dx_reg_end_all_int` | Time (Days) from Associated Cancer Diagnosis to End of All Drugs in Cancer-Directed Regimen |
| `dx_reg_end_any_int` | Time (Days) from Associated Cancer Diagnosis to End of First Drug Discontinued in Cancer-Directed Regimen |
| `dx_reg_start_int` | Time (Days) from Associated Cancer Diagnosis to Start of Cancer-Directed Regimen |
| `dx_to_dmets_days` | Time (Days) from Diagnosis of Stage I-III to Distant Metastasis |
| `hybrid_death_int` | Time (Days) from Date of Birth to Death |
| `naaccr_histology_cd` | Tumor Registry Histology |
| `os_g_status` | Overall Survival from Start of Cancer-Directed Regimen: Status Indicator |
| `path_proc_cpt_rep_days` | Time (days) from pathology procedure to NGS report date |
| `pfs_i_g_status` | Progression Free Survival  Imaging (PFS-I) from Start of Cancer-Directed Regimen: Status Indicator |
| `pfs_m_g_status` | Progression Free Survival  Medical Oncologist Assessment (PFS-M) from Start of Cancer-Directed Regimen: Status Indicator |
| `regimen_number` | Regimen Number |
| `regimen_number_within_cancer` | Regimen Number Within Cancer Diagnosis |
| `stage_dx_iv` | Derived Stage IV at Diagnosis |

## 1109/1130/20 Consistency Check

- Unique patients: 1109
- Unique NGS samples: 1130
- Patients with >1 NGS sample: 20
- Maximum NGS samples per patient: 3
- Aggregated distribution: reports/tables/ngs_sample_count_distribution.csv

## Aggregate Distributions

### Histology, rare categories suppressed
- Adenocarcinoma, NOS: 431
- Missing/blank: 402
- Invasive carcinoma of no special type: 176
- Tubular adenocarcinoma: 40
- Adenosquamous carcinoma: 18
- Acinar cell carcinoma: 11
- Carcinoma, NOS: 5
- Suppressed categories with n<5 (14 categories): 27

### OncoTree, rare categories suppressed
- PAAD: 1075
- PAASC: 24
- PAAC: 23
- UCP: 8

### Stage IV grouping
- Stage I-III: 613
- Stage IV: 497

### Resectability
- Unresectable/locally advanced or metastatic: 585
- Resectable: 379
- Borderline resectable: 125
- Indeterminate: 20
- Suppressed categories with n<5 (1 categories): 1

## t0 Definition Comparison

Definitions are compared only; no definition is selected.

| Definition | Matching t0 regimen | Prior reconstructable | Post-t0 evaluable outcome | Usable patients |
|---|---:|---:|---:|---:|
| A | 566 | 566 | 566 | 566 |
| B | 568 | 568 | 568 | 568 |
| C | 50 | 50 | 50 | 50 |

Full flow: reports/tables/cohort_flow_counts.csv
Full comparison: reports/tables/t0_definition_comparison.csv

## Main Exclusion Reasons
- Definition A: non_pdac=42; no_advanced_evidence=186; no_usable_ngs_time=27; no_definition_t0=288; prior_unreconstructable=0; no_post_t0_outcome=0
- Definition B: non_pdac=42; no_advanced_evidence=186; no_usable_ngs_time=27; no_definition_t0=286; prior_unreconstructable=0; no_post_t0_outcome=0
- Definition C: non_pdac=42; no_advanced_evidence=186; no_usable_ngs_time=27; no_definition_t0=804; prior_unreconstructable=0; no_post_t0_outcome=0

## Timeline Quality and Leakage Risks

See reports/tables/timeline_quality_summary.csv for aggregate metrics.
- Same-day NGS report and regimen start affects A vs B.
- Regimen end, PFS, OS, TTNT, death, and last-alive fields are post-t0/outcome fields and must be excluded from t0 inputs.
- Exact dates are masked; key comparisons use day intervals from associated cancer diagnosis.
- cpt_seq_date is year-level only and should not substitute for dx_cpt_rep_days.
- cpt_report_post_death and cpt_report_post_last_alive are excluded from usable NGS timing.
- Treatment overlap and same-day regimen starts require manual review before locking cohort definitions.

## Manual Confirmation Needed

- Final PDAC histology inclusion/exclusion mapping from ca_histology, naaccr_histology_cd, and OncoTree codes.
- Whether same-day report and regimen start should be considered clinically available information.
- Whether regimen_number_within_cancer is sufficient as a line-of-therapy proxy.
- How to handle post-diagnosis metastatic disease because recurrence-specific fields were not found.
- Whether same-day multiple regimen starts or treatment overlaps should be excluded or adjudicated.
- Which endpoint should define post-t0 evaluability: PFS-I, PFS-M, OS, TTNT, or a composite.
