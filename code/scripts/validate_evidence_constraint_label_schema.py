"""Validate the Track A evidence-and-constraint label schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import privacy_checks as privacy


EXPECTED_FINAL_LABELS = {"consider", "conditional_review", "exclude", "insufficient_evidence"}
EXPECTED_EVIDENCE_VALUES = {"supported", "conditional", "not_supported", "insufficient_evidence"}
EXPECTED_CONSTRAINT_VALUES = {"satisfied", "not_satisfied", "unknown", "not_applicable", "manual_review"}
HARD_NEGATIVE_CONDITION_TYPES = {"disease_scope", "treatment_setting", "line_of_therapy", "prior_treatment", "biomarker"}
REQUIRED_TOP_LEVEL = {
    "version",
    "status",
    "task",
    "purpose",
    "authoritative_inputs",
    "cohort_invariants",
    "unit_of_analysis",
    "time_boundary",
    "label_families",
    "track_a_input_policy",
    "track_b_policy",
    "missingness_policy",
    "evidence_axis",
    "constraint_axis",
    "clinical_clearance_axis",
    "track_a_label",
    "candidate_policy_overrides",
    "row_validity",
    "provenance",
    "patient_candidate_table_contract",
    "privacy",
    "pilot_readiness",
}


def _walk(value: Any, path: str = ""):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _candidate_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(candidate.get("candidate_id")): candidate for candidate in config.get("candidates", [])}


def derive_track_a_label(assessment: dict[str, Any]) -> str | None:
    """Apply the schema precedence to one synthetic assessment."""

    if assessment.get("row_validity_status") != "valid":
        return None
    conditions = assessment.get("required_track_a_conditions", [])
    if not isinstance(conditions, list):
        raise ValueError("required Track A conditions are not a list")
    required_assessments: list[str] = []
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError("Track A condition is not a mapping")
        condition_type = condition.get("condition_type")
        condition_assessment = condition.get("assessment")
        if condition_type not in {
            "disease_scope",
            "treatment_setting",
            "line_of_therapy",
            "prior_treatment",
            "biomarker",
            "assay",
            "maintenance_role",
        }:
            raise ValueError(f"unknown Track A condition type: {condition_type}")
        if condition_assessment not in EXPECTED_CONSTRAINT_VALUES:
            raise ValueError(f"unknown Track A condition assessment: {condition_assessment}")
        if condition.get("required") is True:
            required_assessments.append(str(condition_assessment))
            if condition_assessment == "not_satisfied" and condition_type in HARD_NEGATIVE_CONDITION_TYPES:
                return "exclude"
    evidence_status = assessment.get("evidence_status")
    if evidence_status not in EXPECTED_EVIDENCE_VALUES:
        raise ValueError(f"unknown evidence status: {evidence_status}")
    if evidence_status == "not_supported":
        return "exclude"
    if evidence_status == "insufficient_evidence":
        return "insufficient_evidence"
    if evidence_status == "conditional" or any(item in {"unknown", "manual_review", "not_satisfied"} for item in required_assessments):
        return "conditional_review"
    label = "consider"
    if assessment.get("maximum_track_a_label") == "conditional_review":
        label = "conditional_review"
    return label


def validate_schema(schema: dict[str, Any], candidate_space: dict[str, Any], cohort: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(f"missing top-level field: {field}" for field in sorted(REQUIRED_TOP_LEVEL - set(schema)))
    if schema.get("status") != "draft_not_locked":
        errors.append("schema status must remain draft_not_locked")
    if schema.get("version") != "v0.1":
        errors.append("unexpected schema version")

    inputs = schema.get("authoritative_inputs", {})
    cohort_ref = inputs.get("cohort_definition", {})
    candidate_ref = inputs.get("candidate_space", {})
    if cohort_ref.get("required_version") != cohort.get("version"):
        errors.append("cohort definition version does not match the schema reference")
    if cohort_ref.get("required_status") != cohort.get("status"):
        errors.append("cohort definition status does not match the schema reference")
    if candidate_ref.get("required_version") != candidate_space.get("version"):
        errors.append("candidate-space version does not match the schema reference")
    if candidate_ref.get("required_status") != candidate_space.get("status"):
        errors.append("candidate-space status does not match the schema reference")
    if candidate_ref.get("candidate_pool") != "main_candidate_pool":
        errors.append("schema must target the frozen main-candidate-pool field")

    invariants = schema.get("cohort_invariants", {})
    cohort_counts = cohort.get("cohorts", {})
    for field in ("strict_extended_n", "strict_core_n"):
        if invariants.get(field) != cohort_counts.get(field):
            errors.append(f"cohort invariant mismatch: {field}")
    if invariants.get("schema_must_not_reselect_t0_or_rebuild_cohort") is not True:
        errors.append("schema must prohibit t0 reselection and cohort rebuilding")

    time_boundary = schema.get("time_boundary", {})
    if time_boundary.get("input_rule") != "information_must_be_available_strictly_before_t0":
        errors.append("Track A input rule is not strictly pre-t0")
    for field in ("index_ngs_rule", "advanced_evidence_rule", "prior_treatment_rule"):
        if " < " not in str(time_boundary.get(field, "")):
            errors.append(f"time boundary is not strict: {field}")
    if time_boundary.get("post_t0_information_policy") != "prohibited":
        errors.append("post-t0 information is not explicitly prohibited")

    families = schema.get("label_families", {})
    observed = families.get("observed_next_regimen", {})
    evidence_label = families.get("evidence_label", {})
    outcome = families.get("outcome_label", {})
    if observed.get("target_status") != "not_gold_standard":
        errors.append("observed next regimen is treated as a gold standard")
    if "best_treatment_target" not in observed.get("prohibited_uses", []):
        errors.append("observed next regimen is not prohibited as a best-treatment target")
    if evidence_label.get("role") != "primary_benchmark_target":
        errors.append("evidence label is not the primary benchmark target")
    if evidence_label.get("independent_of_observed_choice") is not True:
        errors.append("evidence label is not independent of observed choice")
    if evidence_label.get("independent_of_post_t0_outcome") is not True:
        errors.append("evidence label is not independent of post-t0 outcome")
    if "candidate_classification_target" not in outcome.get("prohibited_uses", []):
        errors.append("outcome fields are not prohibited as candidate targets")
    if "best_treatment_target" not in outcome.get("prohibited_uses", []):
        errors.append("outcome fields are not prohibited as best-treatment targets")

    evidence_axis = schema.get("evidence_axis", {})
    constraint_axis = schema.get("constraint_axis", {})
    label = schema.get("track_a_label", {})
    if set(evidence_axis.get("allowed_values", [])) != EXPECTED_EVIDENCE_VALUES:
        errors.append("evidence-axis values do not match the v0.1 contract")
    if set(constraint_axis.get("allowed_values", [])) != EXPECTED_CONSTRAINT_VALUES:
        errors.append("constraint-axis values do not match the v0.1 contract")
    if set(label.get("allowed_values", [])) != EXPECTED_FINAL_LABELS:
        errors.append("final Track A labels do not match the v0.1 contract")
    priorities = [rule.get("priority") for rule in label.get("ordered_derivation_rules", []) if isinstance(rule, dict)]
    if priorities != list(range(1, 7)):
        errors.append("Track A derivation priorities must be complete and ordered")
    if label.get("track_b_status_changes_track_a_label") is not False:
        errors.append("Track B status must not change the Track A evidence label")

    status_mapping = evidence_axis.get("candidate_evidence_status_mapping", {})
    if set(status_mapping) != EXPECTED_EVIDENCE_VALUES:
        errors.append("candidate evidence-status mapping does not cover every schema evidence state")
    mapped_statuses: list[str] = []
    for target_status, source_statuses in status_mapping.items():
        if not isinstance(source_statuses, list):
            errors.append(f"candidate evidence-status mapping is not a list: {target_status}")
            continue
        mapped_statuses.extend(str(status) for status in source_statuses)
    if len(mapped_statuses) != len(set(mapped_statuses)):
        errors.append("a candidate evidence status maps to more than one schema state")

    track_b = schema.get("track_b_policy", {})
    if track_b.get("status") != "frozen":
        errors.append("Track B must remain frozen")
    if track_b.get("relationship_to_track_a_label") != "separate_not_used_to_derive_track_a_label":
        errors.append("Track B is not separated from Track A label derivation")
    if track_b.get("clinical_clearance_policy") != "never_infer_clearance_from_missing_track_b":
        errors.append("missing Track B data could be interpreted as clinical clearance")

    missingness = schema.get("missingness_policy", {})
    for field in ("missing_is_not_negative", "missing_is_not_normal", "missing_is_not_no_contraindication"):
        if missingness.get(field) is not True:
            errors.append(f"unsafe missingness policy: {field}")
    if missingness.get("unknown_can_trigger_exclude") is not False:
        errors.append("unknown data can incorrectly trigger exclusion")

    prohibited = set(schema.get("track_a_input_policy", {}).get("prohibited_fields_or_groups", []))
    required_prohibited = {
        "observed_next_regimen",
        "t0_regimen_drugs",
        "post_t0_regimen_or_line",
        "os_pfs_ttnt_fields",
        "death_or_last_alive_fields",
        "follow_up_fields",
        "future_ngs_or_biomarker_results",
    }
    for field in sorted(required_prohibited - prohibited):
        errors.append(f"missing prohibited Track A field group: {field}")

    candidate_by_id = _candidate_map(candidate_space)
    main_pool = set(candidate_space.get("main_candidate_pool", []))
    main_evidence_statuses = {str(candidate_by_id.get(candidate_id, {}).get("evidence_status")) for candidate_id in main_pool}
    for status in sorted(main_evidence_statuses - set(mapped_statuses)):
        errors.append(f"unmapped main-candidate evidence status: {status}")
    if evidence_axis.get("unmapped_main_candidate_status_policy") != "invalid_row":
        errors.append("unmapped main-candidate evidence statuses must invalidate the row")

    field_mapping = constraint_axis.get("candidate_field_to_condition_type", {})
    required_source_fields = {
        "disease.name",
        "candidate.treatment_setting",
        "candidate.line_of_therapy",
        "candidate.prior_treatment_requirements",
        "candidate.biomarker_requirements",
        "candidate.maintenance_or_active_treatment",
    }
    for field in sorted(required_source_fields - set(field_mapping)):
        errors.append(f"candidate condition mapping is missing: {field}")
    if constraint_axis.get("candidate_manual_review_flag_policy") != "does_not_automatically_lower_track_a_label_unless_track_a_condition_or_evidence_requires_review":
        errors.append("candidate manual-review flag can incorrectly lower all Track A labels")

    overrides = schema.get("candidate_policy_overrides", {})
    for candidate_id in overrides:
        if candidate_id not in candidate_by_id:
            errors.append(f"candidate policy references unknown candidate: {candidate_id}")
        if candidate_id not in main_pool:
            errors.append(f"candidate policy references a candidate outside the main pool: {candidate_id}")
    for candidate_id in ("folfox_or_off", "gemcitabine_paclitaxel_after_folfirinox"):
        if overrides.get(candidate_id, {}).get("maximum_track_a_label") != "conditional_review":
            errors.append(f"confirmed conditional candidate lacks a label ceiling: {candidate_id}")
    ntrk_override = overrides.get("ntrk_fusion_targeted_therapy", {})
    ntrk_candidate = candidate_by_id.get("ntrk_fusion_targeted_therapy", {})
    if ntrk_override.get("output_granularity") != "class_only":
        errors.append("NTRK schema output is not class-level")
    if ntrk_override.get("permitted_agents_are_mutually_exclusive") is not True:
        errors.append("NTRK permitted agents are not explicitly mutually exclusive")
    if ntrk_candidate.get("canonical_drug_set"):
        errors.append("NTRK class candidate is encoded as a drug combination")

    table_contract = schema.get("patient_candidate_table_contract", {})
    required_columns = set(table_contract.get("required_columns", []))
    for field in (
        "evidence_source_ids",
        "track_a_condition_assessments",
        "track_b_assessment_status",
        "track_a_evidence_constraint_label",
        "clinical_clearance_status",
        "reason_codes",
        "schema_version",
        "candidate_space_version",
    ):
        if field not in required_columns:
            errors.append(f"patient-candidate contract missing required column: {field}")
    if table_contract.get("creation_status") != "not_created_schema_only":
        errors.append("schema incorrectly claims that the patient-candidate table exists")
    if table_contract.get("observed_next_regimen_auxiliary_is_model_target") is not False:
        errors.append("observed regimen auxiliary field is incorrectly a model target")
    if table_contract.get("outcome_linkage_available_is_model_target") is not False:
        errors.append("outcome linkage is incorrectly a model target")

    privacy_config = schema.get("privacy", {})
    if privacy_config.get("public_outputs") != "aggregate_only":
        errors.append("schema allows patient-level public outputs")
    if privacy_config.get("small_count_threshold") != 5:
        errors.append("schema small-count threshold is not 5")
    for path, value in _walk(schema):
        if isinstance(value, str) and privacy.contains_identifier(value):
            errors.append(f"schema contains a GENIE-like identifier at {path}")
    return errors


def validate_files(schema_path: Path, candidate_path: Path, cohort_path: Path) -> list[str]:
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    candidate_space = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    cohort = yaml.safe_load(cohort_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        return ["label schema is not a mapping"]
    if not isinstance(candidate_space, dict):
        return ["candidate space is not a mapping"]
    if not isinstance(cohort, dict):
        return ["cohort definition is not a mapping"]
    return validate_schema(schema, candidate_space, cohort)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.repo_root.resolve()
    errors = validate_files(
        root / "config" / "evidence_constraint_label_schema_v0.1.yaml",
        root / "config" / "candidate_treatment_space_v0.1.yaml",
        root / "cohort_definition_v0.1.yaml",
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"evidence_constraint_schema_validation=fail errors={len(errors)}")
        return 1
    print("evidence_constraint_schema_validation=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
