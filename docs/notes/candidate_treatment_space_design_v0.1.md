# Advanced PDAC Candidate Treatment Space v0.1.1

Status: `draft_not_locked`

## Purpose

This document defines the candidate treatment space used to evaluate systemic treatment options at the locked PDAC decision time `t0`. The machine-readable definition is [candidate_treatment_space_v0.1.yaml](../../code/config/candidate_treatment_space_v0.1.yaml).

## Process

### Scope and granularity

The space covers systemic treatment and explicit review actions for unresectable locally advanced, recurrent, or metastatic PDAC. Each candidate represents a complete regimen, a maintenance action, a biomarker-matched treatment action, or a review action. Separate candidates are used when drug composition, irinotecan formulation, treatment role, line, or biomarker requirement differs.

The cohort and `t0` definitions come from [cohort_definition_v0.1.yaml](../../code/config/cohort_definition_v0.1.yaml). Observed BPC regimens provide alignment information through the candidate-regimen crosswalk. Candidate evidence comes from versioned evidence summaries, regulatory records, trials, and official practice guidance.

### Evidence snapshot

The evidence cutoff is 2026-08-28.

| Source ID | Type | Use |
|---|---|---|
| `nci_pdq_pancreatic_treatment_2025` | peer-reviewed evidence summary | PDAC treatment evidence context |
| `nhc_antitumor_guidance_2025` | official practice guidance | China context for gemcitabine plus erlotinib |
| `jco_conko_003_2014` | phase III trial | OFF after gemcitabine progression |
| `jco_pancreox_2016` | phase III trial | mFOLFOX6 after gemcitabine-based therapy |
| `jco_gempax_2024` | phase III trial | gemcitabine/paclitaxel after FOLFIRINOX |
| `fda_onivyde_first_line_pdac_2024` | regulatory approval | NALIRIFOX first-line indication |
| `fda_olaparib_pancreatic_2019` | regulatory approval | germline BRCA maintenance indication |
| `fda_bizengri_nrg1_pdac_2024` | regulatory approval | NRG1 fusion-positive treatment |
| `fda_keytruda_msi_h_dmmr_2017` | regulatory approval | MSI-H/dMMR treatment |
| `fda_keytruda_tmb_h_2020` | regulatory approval | TMB-H treatment |
| `fda_ntrk_entrectinib_2023` | regulatory approval | NTRK fusion treatment |
| `fda_ntrk_larotrectinib_2025` | regulatory approval | NTRK fusion treatment |
| `fda_ntrk_repotrectinib_2024` | regulatory approval | NTRK fusion treatment |
| `fda_ret_selpercatinib_2026` | regulatory approval | RET fusion treatment |
| `fda_braf_dabrafenib_trametinib_2022` | regulatory approval | BRAF V600E treatment |
| `fda_enhertu_her2_solid_tumor_2024` | regulatory approval | HER2 IHC3+ treatment |
| `nci_pancreatic_drugs_2025` | official drug summary | PDAC drugs and combinations |
| `aacr_bpc_panc_1_0_public` | dataset documentation | observed-regimen alignment |

NCI PDQ is recorded as an evidence summary. Formal guideline status is stored separately in the candidate configuration. The NHC source is linked to the specific extended candidate `gemcitabine_erlotinib`.

### Track A and Track B

Track A uses the locked PDAC instance, advanced status, pre-`t0` NGS timing, prior treatment sequence, canonical regimen components, and time-aligned biomarker results. Missing evidence is represented as `unknown` or `manual_review`.

Track B represents performance status, laboratory and organ-function thresholds, dose feasibility, dose modification, toxicity, drug interactions, and detailed contraindications. Its current status is `frozen`.

### Regimen mapping

- FOLFIRINOX and mFOLFIRINOX share the `folfirinox` candidate with a variant relation.
- NALIRIFOX has a separate candidate because it contains liposomal irinotecan.
- Ordinary irinotecan and liposomal irinotecan remain separate components.
- Maintenance olaparib is separate from active treatment.
- NTRK is represented as one class-level candidate with mutually exclusive permitted single agents.
- Pembrolizumab has separate MSI-H/dMMR and TMB-H candidates.

The generated [candidate_regimen_crosswalk_v0.1.csv](../../code/results/mappings/candidate_regimen_crosswalk_v0.1.csv) contains 46 aggregate relations using `exact`, `variant`, `partial`, `not_candidate`, `ambiguous`, and `masked_or_unresolvable` statuses.

## Results

### Main candidate pool

The main pool contains 16 candidates.

| Candidate ID | Role and key condition |
|---|---|
| `folfirinox` | active systemic treatment; includes modified variants |
| `nalirifox` | first-line liposomal-irinotecan combination |
| `gemcitabine_nab_paclitaxel` | active systemic treatment |
| `gemcitabine_monotherapy` | single-agent systemic treatment |
| `liposomal_irinotecan_fluorouracil_leucovorin` | later-line treatment after gemcitabine-based therapy |
| `fluorouracil_leucovorin` | later-line fluoropyrimidine treatment |
| `folfox_or_off` | later-line comparison with conditional evidence status |
| `gemcitabine_paclitaxel_after_folfirinox` | post-FOLFIRINOX comparison with conditional evidence status |
| `olaparib_maintenance_brca` | maintenance after platinum response or stability with germline BRCA1/2 |
| `pembrolizumab_msi_h_dmmr` | MSI-H/dMMR biomarker-matched treatment |
| `pembrolizumab_tmb_h` | TMB-H biomarker-matched treatment |
| `zenocutuzumab_nrg1_fusion` | NRG1 fusion-matched treatment |
| `ntrk_fusion_targeted_therapy` | NTRK fusion-directed class action |
| `selpercatinib_ret_fusion` | RET fusion-matched treatment |
| `dabrafenib_trametinib_braf_v600e` | BRAF V600E-matched combination |
| `trastuzumab_deruxtecan_her2_positive` | HER2 IHC3+ biomarker-matched treatment |

### Extended candidate pool

The extended pool contains 11 candidates.

| Candidate ID | Role |
|---|---|
| `gemcitabine_cisplatin_hrd` | HRD-context combination under guideline review |
| `gemcitabine_capecitabine` | observed combination with context-dependent advanced-PDAC role |
| `capecitabine_monotherapy` | observed single-agent treatment |
| `gemcitabine_erlotinib` | historical option with China exceptional-use context |
| `folfiri_or_irinotecan_fluoropyrimidine` | ordinary-irinotecan combination |
| `gemcitabine_oxaliplatin` | observed combination under role review |
| `kras_g12c_targeted_therapy` | biomarker pathway under PDAC-specific evidence review |
| `other_actionable_biomarker_trial_or_label` | validated alteration review action |
| `clinical_trial_referral` | clinical-trial action |
| `evidence_insufficient_direct_treatment` | evidence abstention action |
| `masked_investigational_regimen_review` | masked-regimen review action |

### Review decisions

The project owner confirmed two benchmark design decisions:

1. `folfox_or_off` and `gemcitabine_paclitaxel_after_folfirinox` remain in the Track A main pool with a maximum label of `conditional_review`.
2. `ntrk_fusion_targeted_therapy` remains a class-level candidate with entrectinib, larotrectinib, and repotrectinib as mutually exclusive permitted agents.

The medical review queue contains the current role of `gemcitabine_cisplatin_hrd`, the frozen formal-guideline snapshot, future Track B constraints, and the representation of accelerated tissue-agnostic indications.

### Validation

```powershell
python code/scripts/generate_candidate_regimen_crosswalk.py --repo-root .
python code/scripts/validate_candidate_treatment_space.py --repo-root .
```

The validator checks candidate IDs, pool membership, evidence references, source semantics, NTRK agent structure, crosswalk relations, and privacy-safe aggregate output.

Candidate-space v0.1.1 passes all six 4.1.1 technical checks: NTRK single-agent class representation, conditional main-pool retention for `folfox_or_off` and `gemcitabine_paclitaxel_after_folfirinox`, NCI PDQ evidence-summary classification, claim-specific regulatory sources, and the adenosquamous manual-review boundary. Clinical confirmation and the formal guideline snapshot remain freeze requirements.
