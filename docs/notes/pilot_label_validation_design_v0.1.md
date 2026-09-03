# Pilot Evidence-Label Validation Design v0.1

## Purpose

The Pilot validates Track A evidence extraction, candidate-condition assessment, label derivation, review workflow, privacy controls, and time-leakage controls before full patient-candidate generation.

## Process

### Sampling

The Pilot targets 24 Strict Extended decision points. Each selected decision point is crossed with all 16 main-pool candidates, yielding 384 patient-candidate rows when the target sample is complete. Deterministic priority strata cover:

- actionable fusion signals;
- available MSI/MMR reports;
- tumor BRCA review signals;
- prior FOLFIRINOX;
- prior gemcitabine-based treatment;
- first advanced-treatment decisions;
- uncertain prior-regimen mappings.

Stable hashing fills the target sample after priority assignment. The strata provide schema coverage rather than prevalence estimates.

### Time alignment

The selected NGS report and biomarker evidence use strict pre-`t0` timing. GENIE BPC stores PD-L1, MSI, and MMR report dates relative to date of birth; diagnosis-relative timing is calculated as:

```text
biomarker_prepaint - dob_ca_dx_days
```

The local GENIE BPC PANC v1.0 Analytic Data Guide documents `dob_ca_dx_days` on pages 26-27, PD-L1 on pages 140-146, MSI on pages 146-148, and MMR on pages 149-151. The Variable Synopsis workbook provides the result vocabularies.

Prior advanced treatment includes regimens starting on or after dated advanced-disease evidence and before `t0`.

### Biomarker interpretation

| Biomarker evidence | Assessment process |
|---|---|
| Confirmed NRG1, NTRK1/2/3, or RET fusion annotation | satisfies the matching fusion condition |
| BRAF V600E on the selected sample | satisfies the somatic BRAF condition |
| Tumor BRCA1/2 alteration | review signal for the germline BRCA condition |
| Pre-`t0` MSI/MMR result | direct pathology evidence with composite-condition review |
| TMB-H and HER2 IHC3+ | `unknown` in the current extraction |
| Uncovered or incomplete assay result | `unknown` or `manual_review` |

### Review workflow

Plan A is the primary workflow. Two clinicians independently review the 24 Pilot cases across all 16 candidates, and an adjudicator resolves disagreements. The output field is `expert_adjudicated_evidence_constraint_label`.

Plan B is the supervisor-approved fallback. A frozen rulebook applies sources in this order:

1. frozen clinical guideline;
2. current regulatory label;
3. candidate-specific primary evidence.

Plan B produces `guideline_evidence_eligibility`. Source conflicts map to `manual_review` or `insufficient_evidence`.

Reviewer materials use codes `PILOT-001` through `PILOT-024`. The local linkage file stores formal dataset keys separately from the reviewer case index and review matrix.

The reviewer package includes an anonymous, strictly pre-`t0` molecular-evidence section for each decision point. It reports normalized specimen category, report-recency band, DNA-panel coverage for candidate-relevant genes, candidate-relevant SNV/indel details, fusion or structural-variant details, ERBB2 copy-number status, and available MSI/MMR results. It does not expose direct identifiers, exact dates, center-coded assay names, the observed `t0` regimen, or outcomes. Missing calls remain unknown unless assay coverage and the source semantics support a narrower statement.

### Outputs

| Output | Location | Purpose |
|---|---|---|
| Pilot decision points | `data/processed/evidence_constraint_labels/pilot_v0.1/pilot_decision_points.csv` | private extraction record |
| Case linkage | `data/processed/evidence_constraint_labels/pilot_v0.1/pilot_case_linkage.csv` | internal key linkage |
| Reviewer case index | `data/processed/evidence_constraint_labels/pilot_v0.1/pilot_reviewer_case_index.csv` | reviewer case summary |
| Reviewer NGS evidence | `data/processed/evidence_constraint_labels/pilot_v0.1/pilot_reviewer_ngs_evidence.csv` | anonymous pre-`t0` molecular evidence |
| Review matrix | `data/processed/evidence_constraint_labels/pilot_v0.1/pilot_review_template.csv` | candidate assessment matrix |
| Reviewer package | `data/processed/evidence_constraint_labels/pilot_v0.1/PDAC_Pilot专家审核包_v1.1.docx` | Chinese expert-review document |
| Aggregate report | `code/results/reports/pilot_label_validation_report_v0.1.md` | public validation result |

## Results

This design produces private reviewer artifacts and one aggregate validation report. Execution counts, validation status, privacy checks, and review progress are maintained in the [Pilot validation report](../../code/results/reports/pilot_label_validation_report_v0.1.md).

## Validation

```powershell
python code/scripts/build_pilot_evidence_labels.py --repo-root .
python code/scripts/generate_pilot_reviewer_package.py --repo-root .
python code/scripts/validate_pilot_evidence_labels.py --repo-root .
python -m pytest code/tests/test_pilot_evidence_labels.py code/tests/test_pilot_reviewer_package.py -q
```

The validator checks sample size, candidate coverage, time alignment, linkage isolation, reviewer-file identifiers, review status, label vocabulary, privacy, and small-cell suppression.

Protocol: [pilot_label_protocol_v0.1.yaml](../../code/config/pilot_label_protocol_v0.1.yaml)  
Label schema: [evidence_constraint_label_schema_v0.1.yaml](../../code/config/evidence_constraint_label_schema_v0.1.yaml)  
Candidate space: [candidate_treatment_space_v0.1.yaml](../../code/config/candidate_treatment_space_v0.1.yaml)
