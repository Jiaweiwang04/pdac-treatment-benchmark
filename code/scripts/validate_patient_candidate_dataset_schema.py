"""Validate the design-only patient-candidate dataset contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


REQUIRED_DATASETS = {
    "decision_point_dataset",
    "candidate_master",
    "patient_candidate_dataset",
    "observed_regimen_labels",
    "evidence_constraint_labels",
    "outcome_dataset",
    "split_manifest",
}
PAIR_KEY = ["cohort", "record_id", "ca_seq", "candidate_id"]
DECISION_KEY = ["cohort", "record_id", "ca_seq"]
PATIENT_KEY = ["cohort", "record_id"]
PATIENT_LEVEL_DATASETS = REQUIRED_DATASETS - {"candidate_master"}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root is not a mapping: {path}")
    return value


def validate_schema(
    schema: dict[str, Any],
    cohort: dict[str, Any],
    candidates: dict[str, Any],
    labels: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    required_top = {
        "version",
        "status",
        "materialization_status",
        "authoritative_inputs",
        "candidate_space_4_1_1_verification",
        "development_invariants",
        "dataset_contracts",
        "feature_policy",
        "time_policy",
        "label_join_policy",
        "split_policy",
        "privacy",
        "stage_gates",
    }
    errors.extend(f"missing top-level field: {field}" for field in sorted(required_top - set(schema)))
    if schema.get("status") != "draft_not_locked":
        errors.append("dataset schema must remain draft_not_locked")
    if schema.get("materialization_status") != "design_only_not_materialized":
        errors.append("dataset schema must remain design-only before materialization")

    inputs = schema.get("authoritative_inputs", {})
    expected_versions = {
        "cohort_definition": cohort.get("version"),
        "candidate_space": candidates.get("version"),
        "label_schema": labels.get("version"),
    }
    for name, actual_version in expected_versions.items():
        if inputs.get(name, {}).get("required_version") != actual_version:
            errors.append(f"{name} version does not match its authoritative input")
    if inputs.get("candidate_space", {}).get("candidate_pool") != "main_candidate_pool":
        errors.append("patient-candidate schema must use the main candidate pool")
    if inputs.get("candidate_regimen_crosswalk", {}).get("role") != "observed_regimen_alignment_only":
        errors.append("candidate-regimen crosswalk role exceeds observed alignment")

    verification = schema.get("candidate_space_4_1_1_verification", {})
    checks = verification.get("checks", {})
    if verification.get("version") != candidates.get("version"):
        errors.append("4.1.1 verification version does not match candidate space")
    if len(checks) != 6 or set(checks.values()) != {"pass"}:
        errors.append("all six candidate-space 4.1.1 technical checks must pass")

    invariants = schema.get("development_invariants", {})
    strict_extended_n = cohort.get("cohorts", {}).get("strict_extended_n")
    main_candidate_n = len(candidates.get("main_candidate_pool", []))
    if invariants.get("decision_point_count") != strict_extended_n:
        errors.append("decision-point count does not match Strict Extended")
    if invariants.get("main_candidate_count") != main_candidate_n:
        errors.append("main-candidate count does not match candidate space")
    if invariants.get("expected_patient_candidate_rows") != strict_extended_n * main_candidate_n:
        errors.append("expected patient-candidate row count is inconsistent")

    datasets = schema.get("dataset_contracts", {})
    errors.extend(f"missing dataset contract: {name}" for name in sorted(REQUIRED_DATASETS - set(datasets)))
    expected_keys = {
        "decision_point_dataset": DECISION_KEY,
        "candidate_master": ["candidate_id"],
        "patient_candidate_dataset": PAIR_KEY,
        "observed_regimen_labels": DECISION_KEY,
        "evidence_constraint_labels": PAIR_KEY,
        "outcome_dataset": DECISION_KEY,
        "split_manifest": PATIENT_KEY,
    }
    for name, key in expected_keys.items():
        contract = datasets.get(name, {})
        if contract.get("primary_key") != key:
            errors.append(f"{name} has an invalid primary key")
        if name in PATIENT_LEVEL_DATASETS:
            path = str(contract.get("proposed_path", ""))
            if not path.startswith("data/processed/"):
                errors.append(f"{name} is outside ignored processed storage")
            if contract.get("public_output_allowed") is not False:
                errors.append(f"{name} permits patient-level public output")

    feature_table = datasets.get("patient_candidate_dataset", {})
    if feature_table.get("status") != "not_generated":
        errors.append("patient-candidate feature table is incorrectly marked generated")
    if feature_table.get("embedded_label_families") != []:
        errors.append("patient-candidate feature table embeds labels")
    if datasets.get("observed_regimen_labels", {}).get("formal_target_eligible") is not False:
        errors.append("observed regimen is incorrectly eligible as a formal target")
    if datasets.get("outcome_dataset", {}).get("formal_candidate_classification_target_eligible") is not False:
        errors.append("outcomes are incorrectly eligible as candidate classification targets")

    feature_policy = schema.get("feature_policy", {})
    allowed = set(feature_policy.get("allowed_track_a_groups", []))
    unavailable = set(feature_policy.get("unavailable_track_b_groups", []))
    if allowed & unavailable:
        errors.append("Track A feature groups overlap unavailable Track B groups")
    prohibited = set(feature_policy.get("prohibited_model_inputs", []))
    for required in ("observed_next_regimen", "t0_regimen_drugs", "os_pfs_ttnt_fields", "future_ngs_or_biomarker_results"):
        if required not in prohibited:
            errors.append(f"missing prohibited model input: {required}")
    if schema.get("label_join_policy", {}).get("feature_dataset_contains_no_labels") is not True:
        errors.append("label join policy permits labels in the feature dataset")
    if schema.get("time_policy", {}).get("post_t0_feature_policy") != "prohibited":
        errors.append("post-t0 features are not prohibited")

    split = schema.get("split_policy", {})
    if split.get("grouping_key") != PATIENT_KEY:
        errors.append("split grouping key is not patient-level")
    if split.get("candidate_rows_inherit_patient_split") is not True:
        errors.append("candidate rows do not inherit the patient split")
    if split.get("current_split_is_frozen") is not False:
        errors.append("split is incorrectly marked frozen")

    gates = schema.get("stage_gates", {})
    if any(value is not False for value in gates.values()):
        errors.append("a downstream stage gate is incorrectly marked complete")
    if schema.get("privacy", {}).get("public_release") != "prohibited":
        errors.append("patient-level public release is not prohibited")
    return errors


def validate_files(repo_root: Path) -> list[str]:
    config = repo_root / "code" / "config"
    return validate_schema(
        load_yaml(config / "patient_candidate_dataset_schema_v0.1.yaml"),
        load_yaml(config / "cohort_definition_v0.1.yaml"),
        load_yaml(config / "candidate_treatment_space_v0.1.yaml"),
        load_yaml(config / "evidence_constraint_label_schema_v0.1.yaml"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    errors = validate_files(args.repo_root.resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"patient_candidate_dataset_schema_validation=fail errors={len(errors)}")
        return 1
    print("patient_candidate_dataset_schema_validation=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

