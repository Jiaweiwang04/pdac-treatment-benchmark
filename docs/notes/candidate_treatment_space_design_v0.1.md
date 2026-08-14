# Advanced PDAC Candidate Treatment Space v0.1

Status: `draft_not_locked`

This is a research design artifact for the next evidence-and-constraint labeling stage. It is not a prescription, a patient-level label set, a treatment recommendation, or a medically locked candidate list.

## 1. Task and boundary

The candidate space represents systemic treatment or explicit review actions for unresectable locally advanced, recurrent, or metastatic PDAC. The intended decision point is the frozen `t0`; candidate eligibility must be judged only with information available before `t0`.

The space does not contain doses, schedules, surgery, radiation, local treatment, supportive care, patient-level assignments, or outcome-optimized treatment labels. BPC observed treatment is used only for data alignment. It is not a gold-standard treatment choice and observed frequency is not clinical evidence.

The configuration is [candidate_treatment_space_v0.1.yaml](../../config/candidate_treatment_space_v0.1.yaml). It keeps the project status `draft_not_locked`, with `Track A: conditional_go` and `Track B: frozen` inherited from the third-round audit.

## 2. Evidence method and cutoff

The evidence snapshot was checked on 2026-08-15 with an evidence cutoff of 2026-08-15. The search prioritized the NCI PDQ, FDA approval notices and labels, and official NCI drug summaries. The inaccessible portions of licensed guidelines, including NCCN full text, were not reconstructed from memory. Those items remain unresolved for mentor or clinical-expert review.

The main sources are:

| source_id | source type | supported use |
|---|---|---|
| `nci_pdq_pancreatic_treatment_2025` | clinical guideline summary | FOLFIRINOX, NALIRIFOX, gemcitabine combinations, second-line chemotherapy, and olaparib maintenance context |
| `fda_onivyde_first_line_pdac_2024` | regulatory approval | NALIRIFOX first-line metastatic pancreatic adenocarcinoma indication |
| `fda_olaparib_pancreatic_2019` | regulatory approval | gBRCA-mutated metastatic pancreatic adenocarcinoma maintenance indication |
| `fda_bizengri_nrg1_pdac_2024` | regulatory approval | NRG1 fusion-positive pancreatic adenocarcinoma after prior systemic therapy |
| `fda_keytruda_msi_h_dmmr_2017` | regulatory approval | MSI-H or dMMR tissue-agnostic pembrolizumab indication |
| `fda_keytruda_tmb_h_2020` | regulatory approval | TMB-H tissue-agnostic pembrolizumab indication |
| `fda_ntrk_repotrectinib_2024` | regulatory approval | NTRK fusion-positive tissue-agnostic therapy context |
| `fda_ret_selpercatinib_2026` | regulatory approval | RET fusion-positive tissue-agnostic therapy context |
| `fda_braf_dabrafenib_trametinib_2022` | regulatory approval | BRAF V600E tissue-agnostic therapy context |
| `fda_enhertu_her2_solid_tumor_2024` | regulatory approval | HER2-positive IHC3+ solid-tumor therapy context |
| `nci_pancreatic_drugs_2025` | official drug summary | pancreatic drugs and commonly used combinations, with the limitation that a listed combination is not necessarily individually approved |
| `aacr_bpc_panc_1_0_public` | dataset documentation | observed BPC regimen alignment only; not clinical evidence |

Full metadata, dates, and URLs are stored in the YAML rather than copied into patient-level or restricted outputs.

## 3. Main candidate pool

The main pool has 16 candidates. It remains below the 20-candidate review threshold because candidates are kept separate when they differ in complete drug set, ordinary versus liposomal irinotecan, treatment role, maintenance status, treatment line, or biomarker requirement.

| candidate_id | clinical role and key condition | evidence source IDs | BPC observed mapping |
|---|---|---|---|
| `folfirinox` | active systemic treatment; FOLFIRINOX and mFOLFIRINOX are one candidate with variant status | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` | exact/variant `FOLFIRINOX_or_variant` |
| `nalirifox` | active systemic treatment; liposomal irinotecan-containing first-line option | `fda_onivyde_first_line_pdac_2024`, `nci_pdq_pancreatic_treatment_2025` | no complete named BPC set |
| `gemcitabine_nab_paclitaxel` | active systemic treatment | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` | exact |
| `gemcitabine_monotherapy` | active systemic treatment; kept separate from combinations | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` | exact |
| `liposomal_irinotecan_fluorouracil_leucovorin` | later-line active treatment after gemcitabine-based therapy | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` | exact/partial |
| `fluorouracil_leucovorin` | later-line active treatment | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` | exact |
| `folfox_or_off` | later-line fluoropyrimidine/oxaliplatin context; evidence and use remain conditional | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` | variant |
| `gemcitabine_paclitaxel_after_folfirinox` | later-line option after FOLFIRINOX failure or intolerance | `nci_pdq_pancreatic_treatment_2025` | no complete named BPC set |
| `olaparib_maintenance_brca` | maintenance after platinum response/stability; germline BRCA1/2 required | `fda_olaparib_pancreatic_2019`, `nci_pdq_pancreatic_treatment_2025` | olaparib observed, role/biomarker unresolved |
| `pembrolizumab_msi_h_dmmr` | tissue-agnostic biomarker-matched treatment; MSI-H or dMMR required | `fda_keytruda_msi_h_dmmr_2017` | pembrolizumab observed, biomarker unresolved |
| `pembrolizumab_tmb_h` | tissue-agnostic biomarker-matched treatment; TMB-H required | `fda_keytruda_tmb_h_2020` | pembrolizumab observed, biomarker unresolved |
| `zenocutuzumab_nrg1_fusion` | later-line NRG1 fusion-matched treatment | `fda_bizengri_nrg1_pdac_2024` | no named BPC drug mapping |
| `ntrk_fusion_targeted_therapy` | NTRK fusion-directed class; agent selection is not a single prescription | `fda_ntrk_repotrectinib_2024` | no complete named BPC mapping |
| `selpercatinib_ret_fusion` | later-line RET fusion-matched treatment | `fda_ret_selpercatinib_2026` | no named BPC drug mapping |
| `dabrafenib_trametinib_braf_v600e` | later-line BRAF V600E-matched combination | `fda_braf_dabrafenib_trametinib_2022` | no named BPC drug mapping |
| `trastuzumab_deruxtecan_her2_positive` | later-line HER2-positive IHC3+ tissue-agnostic context | `fda_enhertu_her2_solid_tumor_2024` | no named BPC drug mapping |

The NTRK class is intentionally not split into three drug candidates in v0.1. It is a class-level candidate because agent selection, resistance context, and clinical constraints are not represented in Track A. This is a review decision, not an assertion that the agents are interchangeable.

## 4. Extended candidate pool

The extended pool has 11 candidates. They preserve relevant observed or protocol-mentioned categories without presenting limited, historical, unresolved, or non-direct actions as the primary ranking space.

| candidate_id | reason for extended placement | evidence source IDs |
|---|---|---|
| `gemcitabine_cisplatin_hrd` | observed exact component set and biologically relevant HRD context, but current guideline and biomarker granularity require review | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` |
| `gemcitabine_capecitabine` | observed combination; current advanced-PDAC role requires review | `nci_pancreatic_drugs_2025` |
| `capecitabine_monotherapy` | observed drug; not promoted from frequency alone | `nci_pancreatic_drugs_2025` |
| `gemcitabine_erlotinib` | historical randomized evidence and uncertain current role | `nci_pdq_pancreatic_treatment_2025`, `nci_pancreatic_drugs_2025` |
| `folfiri_or_irinotecan_fluoropyrimidine` | observed ordinary irinotecan combination; current line-specific role requires review | `nci_pdq_pancreatic_treatment_2025` |
| `gemcitabine_oxaliplatin` | observed combination; current role requires review | `nci_pancreatic_drugs_2025` |
| `kras_g12c_targeted_therapy` | protocol-relevant biomarker pathway without a locked PDAC-specific drug in this snapshot | `nci_pdq_pancreatic_treatment_2025` |
| `other_actionable_biomarker_trial_or_label` | safe placeholder for a validated alteration requiring a label or trial-specific review | `nci_pdq_pancreatic_treatment_2025` |
| `clinical_trial_referral` | non-direct action category; not a drug recommendation | `nci_pdq_pancreatic_treatment_2025` |
| `evidence_insufficient_direct_treatment` | abstention category when evidence or constraints are insufficient | `nci_pdq_pancreatic_treatment_2025` |
| `masked_investigational_regimen_review` | preserves masked BPC observations without guessing drug identity | `aacr_bpc_panc_1_0_public` |

## 5. Explicit exclusions

Surgery, radiation, local treatment, supportive care, doses and schedules, individual prescriptions, patient-level candidate assignment, outcome-optimized labels, and unresolvable investigational drugs are excluded. Endocrine or clearly non-PDAC observed regimens are retained only as `not_candidate` crosswalk rows. A masked investigational component can map only to the review-action candidate and never to a concrete drug candidate.

## 6. Mapping decisions

`FOLFIRINOX_or_variant` maps to `folfirinox` with `variant`, so mFOLFIRINOX is not falsely treated as a different drug set. Ordinary irinotecan and `liposomal_irinotecan` remain distinct. `NALIRIFOX` is not mapped to FOLFIRINOX even though the names are similar. Single-agent gemcitabine is separate from gemcitabine plus nab-paclitaxel and other combinations. Olaparib maps only partially because the BPC regimen row cannot establish maintenance, germline BRCA status, or prior platinum response. Pembrolizumab maps to two biomarker-conditioned candidates, both partial, because regimen mapping does not provide MSI-H/dMMR or TMB-H status.

The generated [candidate_regimen_crosswalk_v0.1.csv](../../code/mappings/candidate_regimen_crosswalk_v0.1.csv) contains 46 safe aggregate rows derived from the existing [regimen_mapping_v0.1.csv](../../code/mappings/regimen_mapping_v0.1.csv). It retains `exact`, `variant`, `partial`, `not_candidate`, `ambiguous`, and `masked_or_unresolvable` relations. Counts remain subject to the shared `<5` suppression rule.

## 7. Track A and Track B boundary

Track A can observe or partially observe the locked PDAC instance, advanced status, pre-`t0` NGS timing, prior treatment sequence, canonical observed regimen components, and a biomarker result when that result is explicitly present and time-aligned. Track A cannot establish performance status, laboratory or organ-function thresholds, dose feasibility, dose modification, treatment-related toxicity, drug interactions, or detailed contraindications.

All active cytotoxic candidates require Track B for clinical safety constraints. Biomarker-matched candidates require Track A biomarker confirmation plus Track B or clinical review for safety and agent selection. Missing data are not interpreted as negative biomarkers, normal laboratories, or absence of contraindications.

## 8. Evidence uncertainty and clinical review

The candidate space is not medically confirmed. The following require mentor or clinical-expert review before freeze:

- whether `folfox_or_off` and `gemcitabine_paclitaxel_after_folfirinox` belong in the main pool;
- whether the NTRK class should be split into individual agents;
- the current guideline role and biomarker definition for `gemcitabine_cisplatin_hrd`;
- a legally accessible current guideline snapshot, because NCCN full text was not used;
- the Track A/Track B boundary and any future source-specific contraindication rules;
- whether accelerated tissue-agnostic indications should be represented as direct candidates or conditional review actions in the next schema.

## 9. Readiness for the next round

The repository has a machine-readable draft, an evidence registry, a safe aggregate crosswalk, and a validator with reverse tests. It is technically ready to inform evidence-and-constraint schema design, but it is not ready for candidate freezing or patient-level labels. The next round may proceed only after the unresolved clinical and evidence-source decisions are reviewed. No model training, RAG, Agent, Baseline, patient-by-candidate Cartesian product, or patient-level label generation is part of this round.
