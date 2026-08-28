from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "code" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_patient_candidate_dataset_schema as validator


def load(name: str):
    path = ROOT / "code" / "config" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def configs():
    return (
        load("patient_candidate_dataset_schema_v0.1.yaml"),
        load("cohort_definition_v0.1.yaml"),
        load("candidate_treatment_space_v0.1.yaml"),
        load("evidence_constraint_label_schema_v0.1.yaml"),
    )


def validate(schema):
    _, cohort, candidates, labels = configs()
    return validator.validate_schema(schema, cohort, candidates, labels)


def test_actual_patient_candidate_schema_validates():
    assert validator.validate_files(ROOT) == []


def test_expected_rows_equal_strict_extended_cross_main_pool():
    schema, cohort, candidates, _ = configs()
    invariants = schema["development_invariants"]
    assert invariants["decision_point_count"] == cohort["cohorts"]["strict_extended_n"] == 557
    assert invariants["main_candidate_count"] == len(candidates["main_candidate_pool"]) == 16
    assert invariants["expected_patient_candidate_rows"] == 8912


def test_feature_table_contains_no_label_family():
    schema, *_ = configs()
    assert schema["dataset_contracts"]["patient_candidate_dataset"]["embedded_label_families"] == []


def test_observed_and_outcome_labels_are_not_formal_candidate_targets():
    schema, *_ = configs()
    datasets = schema["dataset_contracts"]
    assert datasets["observed_regimen_labels"]["formal_target_eligible"] is False
    assert datasets["outcome_dataset"]["formal_candidate_classification_target_eligible"] is False


def test_split_is_patient_grouped_and_not_frozen():
    schema, *_ = configs()
    split = schema["split_policy"]
    assert split["grouping_key"] == ["cohort", "record_id"]
    assert split["candidate_rows_inherit_patient_split"] is True
    assert split["current_split_is_frozen"] is False


def test_all_patient_level_outputs_are_private_processed_artifacts():
    schema, *_ = configs()
    for name, contract in schema["dataset_contracts"].items():
        if name == "candidate_master":
            continue
        assert contract["proposed_path"].startswith("data/processed/")
        assert contract["public_output_allowed"] is False


def test_candidate_count_mismatch_fails():
    schema, *_ = configs()
    changed = copy.deepcopy(schema)
    changed["development_invariants"]["main_candidate_count"] = 15
    assert "main-candidate count does not match candidate space" in validate(changed)


def test_embedded_labels_fail():
    schema, *_ = configs()
    changed = copy.deepcopy(schema)
    changed["dataset_contracts"]["patient_candidate_dataset"]["embedded_label_families"] = ["outcome_label"]
    assert "patient-candidate feature table embeds labels" in validate(changed)


def test_patient_level_split_violation_fails():
    schema, *_ = configs()
    changed = copy.deepcopy(schema)
    changed["split_policy"]["grouping_key"] = ["cohort", "record_id", "candidate_id"]
    assert "split grouping key is not patient-level" in validate(changed)


def test_completed_training_gate_fails_at_design_stage():
    schema, *_ = configs()
    changed = copy.deepcopy(schema)
    changed["stage_gates"]["model_training_started"] = True
    assert "a downstream stage gate is incorrectly marked complete" in validate(changed)

