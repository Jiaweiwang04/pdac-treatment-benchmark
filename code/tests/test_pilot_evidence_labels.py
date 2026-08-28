from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "code" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_pilot_evidence_labels as pilot
import validate_pilot_evidence_labels as validator


def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_protocol_is_internally_consistent():
    assert validator.validate_protocol(ROOT) == []


def test_pathology_dates_are_converted_and_same_day_is_excluded():
    row = pd.Series(
        {
            "t0_dob_day": 110,
            "dob_ca_dx_days": 100,
            "msi_prepaint": 109,
            "msi_result": "MSI-H: HIGH",
            "msi_prepaint_2": 110,
            "msi_result_2": "MSS: STABLE",
            "msi_prepaint_3": "",
            "msi_result_3": "",
            "mmr_prepaint": "",
            "mmr_result": "",
            "mmr_prepaint_2": "",
            "mmr_result_2": "",
            "mmr_prepaint_3": "",
            "mmr_result_3": "",
        }
    )
    summary = pilot.pathology_biomarker_summary(row)
    assert summary["msi_mmr_evidence_state"] == "positive_msi_h_or_dmmr"
    assert summary["latest_pathology_evidence_day"] == 9


def test_proficient_mmr_requires_review_not_hard_negative():
    row = pd.Series(
        {
            "t0_dob_day": 110,
            "dob_ca_dx_days": 100,
            "msi_prepaint": "",
            "msi_result": "",
            "msi_prepaint_2": "",
            "msi_result_2": "",
            "msi_prepaint_3": "",
            "msi_result_3": "",
            "mmr_prepaint": 105,
            "mmr_result": "No loss of nuclear expression of MMR proteins: proficient",
            "mmr_prepaint_2": "",
            "mmr_result_2": "",
            "mmr_prepaint_3": "",
            "mmr_result_3": "",
        }
    )
    summary = pilot.pathology_biomarker_summary(row)
    assert summary["msi_mmr_evidence_state"] == "explicit_nonpositive_requires_manual_review"


def test_tumor_brca_does_not_satisfy_germline_requirement():
    candidate = {
        "biomarker_requirements": {
            "status": "required",
            "required_markers": ["deleterious_germline_brca1_or_brca2"],
        }
    }
    assessment, reason, state = pilot.biomarker_assessment(candidate, {"tumor_brca_signal": True})
    assert assessment == "unknown"
    assert reason == "TUMOR_BRCA_SIGNAL_NOT_GERMLINE_EVIDENCE"
    assert state == "tumor_brca_signal_not_germline"


def test_absent_fusion_signal_is_unknown_not_negative():
    candidate = {
        "biomarker_requirements": {
            "status": "required",
            "required_markers": ["ntrk1_ntrk2_or_ntrk3_gene_fusion"],
        }
    }
    assessment, _, _ = pilot.biomarker_assessment(candidate, {"fusion_genes": []})
    assert assessment == "unknown"


def test_ntrk_fusion_signal_satisfies_class_level_candidate():
    candidate = {
        "biomarker_requirements": {
            "status": "required",
            "required_markers": ["ntrk1_ntrk2_or_ntrk3_gene_fusion"],
        }
    }
    assessment, reason, _ = pilot.biomarker_assessment(candidate, {"fusion_genes": ["NTRK1"]})
    assert assessment == "satisfied"
    assert reason == "PRE_T0_NTRK_FUSION"


def test_no_satisfactory_alternative_clause_is_not_hard_negative():
    candidate = {"line_of_therapy": {"allowed": ["later_line_or_no_satisfactory_alternative"]}}
    assessment, reason = pilot.line_assessment(candidate, {"n_prior_advanced_regimens": 0})
    assert assessment == "manual_review"
    assert reason == "LINE_NO_SATISFACTORY_ALTERNATIVE_STATUS_UNAVAILABLE"


def test_conditional_candidates_retain_label_ceiling():
    candidate_space = load(ROOT / "code" / "config" / "candidate_treatment_space_v0.1.yaml")
    schema = load(ROOT / "code" / "config" / "evidence_constraint_label_schema_v0.1.yaml")
    protocol = load(ROOT / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    by_id = {item["candidate_id"]: item for item in candidate_space["candidates"]}
    context = {
        "cohort": "synthetic",
        "record_id": "synthetic",
        "ca_seq": "0",
        "t0_start_day": 10,
        "pilot_stratum": "synthetic",
        "pilot_case_code": "PILOT-001",
        "n_prior_advanced_regimens": 1,
        "prior_mapping_uncertain": False,
        "has_prior_gemcitabine_based": True,
        "has_prior_folfirinox": True,
        "has_prior_platinum_based": True,
        "tumor_brca_signal": False,
        "msi_mmr_evidence_state": "unknown_no_pre_t0_linked_result",
        "fusion_genes": [],
        "braf_v600e": False,
    }
    for candidate_id in ("folfox_or_off", "gemcitabine_paclitaxel_after_folfirinox"):
        row = pilot.candidate_row(
            context,
            by_id[candidate_id],
            protocol,
            schema,
            "v0.1.3.1",
            "v0.1.1",
        )
        assert row["track_a_evidence_constraint_label"] == "conditional_review"


def test_public_summary_suppresses_small_strata():
    protocol = load(ROOT / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    frame = pd.DataFrame({"pilot_stratum": ["rare"] * 3 + ["common"] * 5})
    rows = [{"track_a_evidence_constraint_label": "conditional_review"} for _ in range(8)]
    summary = pilot.build_public_summary(frame, rows, protocol)
    values = {row["metric"]: row["value"] for row in summary if row["section"] == "sampling"}
    assert values["rare"] == "<5"
    assert values["common"] == "5"


def test_priority_sampling_never_exceeds_configured_target():
    protocol = load(ROOT / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    context = pd.DataFrame(
        {
            "cohort": ["synthetic"] * 30,
            "record_id": [f"synthetic-{index}" for index in range(30)],
            "ca_seq": ["0"] * 30,
            "fusion_genes": [["NTRK1"]] * 30,
            "has_pre_t0_msi_or_mmr_report": [True] * 30,
            "tumor_brca_signal": [True] * 30,
            "has_prior_folfirinox": [True] * 30,
            "has_prior_gemcitabine_based": [True] * 30,
            "n_prior_advanced_regimens": [1] * 30,
            "prior_mapping_uncertain": [True] * 30,
        }
    )
    selected = pilot.assign_pilot_strata(context, protocol)
    assert len(selected) == protocol["sample"]["target_decision_points"]
    assert set(selected["pilot_case_code"]) == {f"PILOT-{index:03d}" for index in range(1, 25)}


def test_reviewer_case_summary_uses_code_and_no_dataset_identifier():
    summary = pilot.reviewer_case_summary(
        {
            "pilot_case_code": "PILOT-001",
            "pilot_stratum": "no_prior_advanced_regimen",
            "n_prior_advanced_regimens": 0,
            "prior_regimen_families": [],
            "msi_mmr_evidence_state": "unknown_no_pre_t0_linked_result",
            "braf_v600e": False,
            "tumor_brca_signal": False,
            "fusion_genes": [],
            "has_pre_t0_msi_or_mmr_report": False,
            "has_prior_folfirinox": False,
            "has_prior_gemcitabine_based": False,
            "prior_mapping_uncertain": False,
        }
    )
    assert summary["pilot_case_code"] == "PILOT-001"
    assert not {"cohort", "record_id", "ca_seq", "index_ngs_sample_id"} & set(summary)
