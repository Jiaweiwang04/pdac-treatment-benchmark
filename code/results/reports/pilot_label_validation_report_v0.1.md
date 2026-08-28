# Pilot Evidence-Label Validation Report v0.1

Status: **draft, rule-derived, review pending**.

## Purpose

Validate Track A evidence extraction, candidate coverage, time alignment, review status, privacy, and small-cell suppression on the private Pilot.

## Process

The Pilot crosses 24 Strict Extended decision points with 16 main-pool candidates. Patient-level files are stored under `data/processed/`; this report contains aggregate values with counts below five suppressed.

## Results

| Section | Metric | Value | Status | Note |
|---|---|---:|---|---|
| artifact | decision_points | 24 | pass | Configured private Pilot size. |
| artifact | patient_candidate_rows | 384 | pass | Every Pilot decision point crossed with every main candidate. |
| sampling | actionable_fusion_signal | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| sampling | no_prior_advanced_regimen | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| sampling | pre_t0_msi_or_mmr_report | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| sampling | prior_folfirinox | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| sampling | prior_gemcitabine_based | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| sampling | prior_mapping_uncertain | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| sampling | tumor_brca_signal_not_germline | <5 | descriptive | Priority strata overlap in the source cohort; assignment is without replacement. |
| rule_label | conditional_review | 241 | draft_not_reviewed | Rule-derived Pilot label; clinical adjudication pending. |
| rule_label | exclude | 94 | draft_not_reviewed | Rule-derived Pilot label; clinical adjudication pending. |
| rule_label | consider | 49 | draft_not_reviewed | Rule-derived Pilot label; clinical adjudication pending. |
| time | ngs_strictly_before_t0 | true | pass | Same-day NGS reports are excluded by the locked cohort selector. |
| time | pathology_strictly_before_t0 | true | pass | DOB-relative pathology report dates are converted before comparison. |
| leakage | current_t0_regimen_used | false | pass | Label derivation uses the pre-t0 clinical context. |
| leakage | post_t0_outcome_used | false | pass | Outcome linkage remains a secondary analysis axis. |
| review | plan_a_primary | expert_double_review | pending | Two independent reviews plus disagreement adjudication. |
| review | plan_b_secondary | frozen_guideline_rulebook | standby | Requires documented supervisor approval and yields guideline evidence eligibility only. |
| review | clinical_double_review | pending | pending | Two reviewers and adjudication are required before any label freeze. |
| track_b | clinical_clearance | not_assessed | frozen | Track B clinical clearance remains a separate frozen axis. |

## Review

Plan A uses independent double review and disagreement adjudication. Plan B uses a supervisor-approved frozen guideline rulebook and produces `guideline_evidence_eligibility`. Track B remains `frozen`.

Protocol: `v0.1` (`code/config/pilot_label_protocol_v0.1.yaml`).
