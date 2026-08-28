"""Reverse tests for the Track A evidence-and-constraint label schema."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "code" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_evidence_constraint_label_schema as validator


SCHEMA_PATH = REPO_ROOT / "code" / "config" / "evidence_constraint_label_schema_v0.1.yaml"
CANDIDATE_PATH = REPO_ROOT / "code" / "config" / "candidate_treatment_space_v0.1.yaml"
COHORT_PATH = REPO_ROOT / "code" / "config" / "cohort_definition_v0.1.yaml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class EvidenceConstraintSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load(SCHEMA_PATH)
        self.candidates = load(CANDIDATE_PATH)
        self.cohort = load(COHORT_PATH)

    def errors(self, schema: dict | None = None) -> list[str]:
        return validator.validate_schema(schema or self.schema, self.candidates, self.cohort)

    def test_actual_schema_validates(self) -> None:
        self.assertEqual(validator.validate_files(SCHEMA_PATH, CANDIDATE_PATH, COHORT_PATH), [])

    def test_observed_regimen_cannot_become_gold_standard(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["label_families"]["observed_next_regimen"]["target_status"] = "gold_standard"
        self.assertTrue(any("observed next regimen is treated as a gold standard" in error for error in self.errors(schema)))

    def test_outcome_cannot_become_candidate_target(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["label_families"]["outcome_label"]["prohibited_uses"].remove("candidate_classification_target")
        self.assertTrue(any("outcome fields are not prohibited" in error for error in self.errors(schema)))

    def test_time_boundaries_must_be_strictly_before_t0(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["time_boundary"]["index_ngs_rule"] = "index_ngs_report_day <= t0_regimen_start_day"
        self.assertTrue(any("time boundary is not strict" in error for error in self.errors(schema)))

    def test_missing_data_cannot_trigger_exclusion(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["missingness_policy"]["unknown_can_trigger_exclude"] = True
        self.assertTrue(any("unknown data can incorrectly trigger exclusion" in error for error in self.errors(schema)))

    def test_track_b_must_remain_separate_from_track_a_label(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["track_b_policy"]["relationship_to_track_a_label"] = "derive_track_a_label"
        self.assertTrue(any("Track B is not separated" in error for error in self.errors(schema)))

    def test_cohort_counts_are_invariants(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["cohort_invariants"]["strict_extended_n"] += 1
        self.assertTrue(any("cohort invariant mismatch" in error for error in self.errors(schema)))

    def test_candidate_override_must_reference_main_pool(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["candidate_policy_overrides"]["does_not_exist"] = {"maximum_track_a_label": "conditional_review"}
        errors = self.errors(schema)
        self.assertTrue(any("references unknown candidate" in error for error in errors))

    def test_every_main_candidate_evidence_status_is_mapped(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["evidence_axis"]["candidate_evidence_status_mapping"]["supported"].remove("supported_by_accessible_sources")
        self.assertTrue(any("unmapped main-candidate evidence status" in error for error in self.errors(schema)))

    def test_manual_review_flag_does_not_blanket_downgrade_track_a(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["constraint_axis"]["candidate_manual_review_flag_policy"] = "always_conditional"
        self.assertTrue(any("incorrectly lower all Track A labels" in error for error in self.errors(schema)))

    def test_confirmed_conditional_candidates_have_label_ceiling(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["candidate_policy_overrides"]["folfox_or_off"]["maximum_track_a_label"] = "consider"
        self.assertTrue(any("lacks a label ceiling" in error for error in self.errors(schema)))

    def test_ntrk_output_remains_class_level(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["candidate_policy_overrides"]["ntrk_fusion_targeted_therapy"]["output_granularity"] = "individual_agent"
        self.assertTrue(any("NTRK schema output is not class-level" in error for error in self.errors(schema)))

    def test_schema_does_not_claim_patient_candidate_table_exists(self) -> None:
        schema = copy.deepcopy(self.schema)
        schema["patient_candidate_table_contract"]["creation_status"] = "created"
        self.assertTrue(any("incorrectly claims" in error for error in self.errors(schema)))


class TrackALabelDerivationTests(unittest.TestCase):
    def test_supported_and_satisfied_is_consider(self) -> None:
        label = validator.derive_track_a_label(
            {
                "row_validity_status": "valid",
                "evidence_status": "supported",
                "required_track_a_conditions": [
                    {"condition_type": "prior_treatment", "required": True, "assessment": "satisfied"},
                    {"condition_type": "maintenance_role", "required": True, "assessment": "not_applicable"},
                ],
            }
        )
        self.assertEqual(label, "consider")

    def test_unknown_required_condition_is_conditional_not_exclude(self) -> None:
        label = validator.derive_track_a_label(
            {
                "row_validity_status": "valid",
                "evidence_status": "supported",
                "required_track_a_conditions": [
                    {"condition_type": "prior_treatment", "required": True, "assessment": "satisfied"},
                    {"condition_type": "assay", "required": True, "assessment": "unknown"},
                ],
            }
        )
        self.assertEqual(label, "conditional_review")

    def test_candidate_label_ceiling_is_applied(self) -> None:
        label = validator.derive_track_a_label(
            {
                "row_validity_status": "valid",
                "evidence_status": "supported",
                "required_track_a_conditions": [
                    {"condition_type": "prior_treatment", "required": True, "assessment": "satisfied"},
                ],
                "maximum_track_a_label": "conditional_review",
            }
        )
        self.assertEqual(label, "conditional_review")

    def test_explicit_track_a_contradiction_is_exclude(self) -> None:
        label = validator.derive_track_a_label(
            {
                "row_validity_status": "valid",
                "evidence_status": "supported",
                "required_track_a_conditions": [
                    {"condition_type": "biomarker", "required": True, "assessment": "not_satisfied"},
                ],
                "track_b_status": "not_assessed_track_b_frozen",
            }
        )
        self.assertEqual(label, "exclude")

    def test_insufficient_evidence_is_distinct_from_exclude(self) -> None:
        label = validator.derive_track_a_label(
            {
                "row_validity_status": "valid",
                "evidence_status": "insufficient_evidence",
                "required_track_a_conditions": [],
            }
        )
        self.assertEqual(label, "insufficient_evidence")

    def test_invalid_row_receives_no_training_label(self) -> None:
        label = validator.derive_track_a_label(
            {
                "row_validity_status": "invalid_time_boundary",
                "evidence_status": "supported",
                "required_track_a_conditions": [
                    {"condition_type": "prior_treatment", "required": True, "assessment": "satisfied"},
                ],
            }
        )
        self.assertIsNone(label)

    def test_track_b_status_does_not_change_track_a_label(self) -> None:
        base = {
            "row_validity_status": "valid",
            "evidence_status": "supported",
            "required_track_a_conditions": [
                {"condition_type": "prior_treatment", "required": True, "assessment": "satisfied"},
            ],
        }
        frozen = validator.derive_track_a_label({**base, "track_b_status": "not_assessed_track_b_frozen"})
        hypothetical = validator.derive_track_a_label({**base, "track_b_status": "assessed"})
        self.assertEqual(frozen, "consider")
        self.assertEqual(frozen, hypothetical)


if __name__ == "__main__":
    unittest.main()
