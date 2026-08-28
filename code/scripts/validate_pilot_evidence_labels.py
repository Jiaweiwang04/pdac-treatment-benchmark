#!/usr/bin/env python3
"""Validate the Pilot evidence-label protocol and generated outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

import privacy_checks as privacy


PROHIBITED_DERIVATION_COLUMNS = {
    "observed_next_regimen",
    "t0_regimen_drugs",
    "regimen_family",
    "os_status",
    "os_days",
    "pfs_i_status",
    "pfs_i_days",
    "pfs_m_status",
    "pfs_m_days",
    "ttnt_status",
    "ttnt_days",
}
EXPECTED_LABELS = {"consider", "conditional_review", "exclude", "insufficient_evidence"}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root is not a mapping: {path}")
    return value


def validate_protocol(repo_root: Path) -> list[str]:
    errors: list[str] = []
    protocol = load_yaml(repo_root / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    scope = protocol.get("scope", {})
    candidate = load_yaml(repo_root / scope["candidate_space_path"])
    schema = load_yaml(repo_root / scope["label_schema_path"])
    cohort = load_yaml(repo_root / scope["cohort_definition_path"])

    if protocol.get("status") != "draft_not_locked":
        errors.append("Pilot protocol must remain draft_not_locked")
    if protocol.get("version") != "v0.1":
        errors.append("unexpected Pilot protocol version")
    if scope.get("required_cohort_version") != cohort.get("version"):
        errors.append("cohort version mismatch")
    if scope.get("required_candidate_space_version") != candidate.get("version"):
        errors.append("candidate-space version mismatch")
    if scope.get("required_label_schema_version") != schema.get("version"):
        errors.append("label-schema version mismatch")
    if scope.get("candidate_pool_field") != "main_candidate_pool":
        errors.append("Pilot must target main_candidate_pool")
    if scope.get("track") != "Track A":
        errors.append("Pilot must remain Track A")

    sample = protocol.get("sample", {})
    minimum = int(sample.get("minimum_decision_points", 0))
    target = int(sample.get("target_decision_points", 0))
    maximum = int(sample.get("maximum_decision_points", 0))
    if not minimum <= target <= maximum:
        errors.append("Pilot target is outside configured bounds")
    if minimum < 20 or maximum > 30:
        errors.append("Pilot bounds must remain within 20-30 decision points")

    time_policy = protocol.get("time_policy", {})
    if time_policy.get("same_day_ngs") != "excluded":
        errors.append("same-day NGS must be excluded")
    if time_policy.get("post_t0_fields_allowed") is not False:
        errors.append("post-t0 fields must be prohibited")
    evidence = protocol.get("evidence_policy", {})
    if evidence.get("absent_somatic_call_means_negative") is not False:
        errors.append("absent somatic calls cannot be interpreted as negative")
    if evidence.get("tumor_brca_means_germline_brca") is not False:
        errors.append("tumor BRCA cannot be interpreted as germline BRCA")
    if evidence.get("missing_track_b_means_clinically_cleared") is not False:
        errors.append("missing Track B data cannot imply clinical clearance")
    label_policy = protocol.get("label_policy", {})
    if label_policy.get("current_t0_regimen_allowed_in_label_derivation") is not False:
        errors.append("current t0 regimen cannot be used in label derivation")
    if label_policy.get("outcome_is_primary_label") is not False:
        errors.append("outcomes cannot be the primary Pilot label")
    strategy = protocol.get("review_strategy", {})
    if strategy.get("plan_a", {}).get("priority") != "primary":
        errors.append("expert double review must remain the primary strategy")
    plan_b = strategy.get("plan_b", {})
    if plan_b.get("priority") != "secondary_only_if_plan_a_is_not_available":
        errors.append("guideline rulebook must remain the secondary strategy")
    if plan_b.get("activation_requires") != "documented_project_lead_or_supervisor_approval":
        errors.append("guideline fallback lacks supervisor activation control")
    prohibited_claims = set(plan_b.get("prohibited_claims", []))
    if not {"clinical_appropriateness", "best_treatment", "track_b_clinical_clearance"}.issubset(prohibited_claims):
        errors.append("guideline fallback does not prohibit clinical overclaiming")
    return errors


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def validate_private_outputs(repo_root: Path) -> list[str]:
    errors: list[str] = []
    protocol = load_yaml(repo_root / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    candidate = load_yaml(repo_root / protocol["scope"]["candidate_space_path"])
    output = protocol["outputs"]
    private_dir = repo_root / output["private_directory"]
    paths = {
        "decision": private_dir / output["private_decision_points"],
        "candidate": private_dir / output["private_patient_candidate_rows"],
        "linkage": private_dir / output["private_case_linkage"],
        "case_index": private_dir / output["private_reviewer_case_index"],
        "review": private_dir / output["private_review_template"],
    }
    for name, path in paths.items():
        if not path.exists():
            errors.append(f"missing private {name} output: {path}")
    if errors:
        return errors

    decision = read_csv(paths["decision"])
    rows = read_csv(paths["candidate"])
    linkage = read_csv(paths["linkage"])
    case_index = read_csv(paths["case_index"])
    review = read_csv(paths["review"])
    key = ["cohort", "record_id", "ca_seq", "t0_start_day"]
    minimum = int(protocol["sample"]["minimum_decision_points"])
    maximum = int(protocol["sample"]["maximum_decision_points"])
    if not minimum <= len(decision) <= maximum:
        errors.append("private decision-point count is outside Pilot bounds")
    if decision.duplicated(key).any():
        errors.append("private decision points are not unique")
    expected_case_codes = {f"PILOT-{index:03d}" for index in range(1, len(decision) + 1)}
    if set(decision["pilot_case_code"]) != expected_case_codes or decision["pilot_case_code"].duplicated().any():
        errors.append("Pilot case identifiers are missing, duplicated, or unstable")

    candidate_ids = set(candidate[protocol["scope"]["candidate_pool_field"]])
    expected_rows = len(decision) * len(candidate_ids)
    if len(rows) != expected_rows:
        errors.append(f"patient-candidate row count mismatch: {len(rows)} != {expected_rows}")
    grouped = rows.groupby(key, dropna=False)["candidate_id"].agg(lambda values: set(values))
    if any(values != candidate_ids for values in grouped):
        errors.append("not every decision point is crossed with the complete main candidate pool")
    if rows.duplicated(key + ["candidate_id"]).any():
        errors.append("duplicate patient-candidate rows")
    if set(rows["pilot_case_code"]) != expected_case_codes:
        errors.append("patient-candidate rows do not cover every Pilot case identifier")
    if PROHIBITED_DERIVATION_COLUMNS & set(rows.columns):
        errors.append("patient-candidate output contains prohibited current-treatment or outcome columns")

    ngs_day = pd.to_numeric(decision["index_ngs_report_day"], errors="coerce")
    t0_day = pd.to_numeric(decision["t0_start_day"], errors="coerce")
    if ngs_day.isna().any() or not ngs_day.lt(t0_day).all():
        errors.append("not every Pilot NGS report is strictly before t0")
    pathology_day = pd.to_numeric(decision["latest_pathology_evidence_day"], errors="coerce")
    if not pathology_day.dropna().lt(t0_day.loc[pathology_day.notna()]).all():
        errors.append("a Pilot pathology biomarker report is not strictly before t0")

    if set(rows["track_a_evidence_constraint_label"]) - EXPECTED_LABELS:
        errors.append("unexpected Track A label value")
    if set(rows["label_origin"]) != {"rule_derived"}:
        errors.append("Pilot rows are not explicitly rule-derived")
    if set(rows["review_status"]) != {"not_reviewed"}:
        errors.append("Pilot rows incorrectly claim clinical review")
    if set(rows["track_b_assessment_status"]) != {"frozen_unavailable"}:
        errors.append("Track B status is not frozen_unavailable")
    if set(rows["clinical_clearance_status"]) != {"not_assessed_track_b_frozen"}:
        errors.append("Pilot rows incorrectly imply clinical clearance")
    for field in ("evidence_source_ids", "track_a_condition_assessments", "reason_codes"):
        for index, value in enumerate(rows[field]):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                errors.append(f"invalid JSON in {field} at row {index + 2}")
                break
            if not isinstance(parsed, list):
                errors.append(f"{field} must encode a list")
                break

    if len(linkage) != len(decision) or linkage["pilot_case_code"].duplicated().any():
        errors.append("case linkage is not one row per Pilot case")
    if set(linkage["pilot_case_code"]) != expected_case_codes:
        errors.append("case linkage does not cover every Pilot case identifier")
    if len(case_index) != len(decision) or case_index["pilot_case_code"].duplicated().any():
        errors.append("reviewer case index is not one row per Pilot case")
    if set(case_index["pilot_case_code"]) != expected_case_codes:
        errors.append("reviewer case index does not cover every Pilot case identifier")
    if any(privacy.is_high_risk_field_name(field) for field in case_index.columns):
        errors.append("reviewer case index exposes a high-risk identifier column")
    if privacy.contains_identifier(case_index.to_csv(index=False)):
        errors.append("reviewer case index exposes a GENIE identifier")
    for field in ("prior_regimen_families", "fusion_genes", "priority_candidate_ids", "review_questions"):
        for index, value in enumerate(case_index[field]):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                errors.append(f"invalid JSON in reviewer case index {field} at row {index + 2}")
                break
            if not isinstance(parsed, list):
                errors.append(f"reviewer case index {field} must encode a list")
                break

    if len(review) != len(rows):
        errors.append("review template row count does not match patient-candidate rows")
    if set(review["pilot_case_code"]) != expected_case_codes:
        errors.append("review template does not cover every Pilot case identifier")
    if any(privacy.is_high_risk_field_name(field) for field in review.columns):
        errors.append("review template exposes a high-risk identifier column")
    if privacy.contains_identifier(review.to_csv(index=False)):
        errors.append("review template exposes a GENIE identifier")
    if set(review["review_status"]) != {"not_reviewed"}:
        errors.append("review template incorrectly claims review completion")
    for field in (
        "reviewer_1_label",
        "reviewer_1_reason",
        "reviewer_2_label",
        "reviewer_2_reason",
        "adjudicated_label",
        "adjudication_reason",
    ):
        if review[field].astype(bool).any():
            errors.append(f"review template field must be blank before review: {field}")
    return errors


def validate_public_outputs(repo_root: Path) -> list[str]:
    errors: list[str] = []
    protocol = load_yaml(repo_root / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    output = protocol["outputs"]
    public_paths = [repo_root / output["public_summary_table"], repo_root / output["public_report"]]
    for path in public_paths:
        if not path.exists():
            errors.append(f"missing public Pilot output: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if privacy.contains_identifier(text):
            errors.append(f"public Pilot output contains an identifier pattern: {path}")

    table_path = public_paths[0]
    if table_path.exists():
        with table_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if any(privacy.is_high_risk_field_name(header) for header in headers):
                errors.append("public Pilot table contains a high-risk identifier column")
            for line_number, row in enumerate(reader, start=2):
                if privacy.is_count_cell("value", row):
                    value = str(row.get("value", ""))
                    try:
                        number = int(value)
                    except ValueError:
                        continue
                    if 0 < number < int(protocol["outputs"]["public_small_cell_threshold"]):
                        errors.append(f"unsuppressed public small count at line {line_number}")
    return errors


def validate_all(repo_root: Path, require_outputs: bool = True) -> list[str]:
    errors = validate_protocol(repo_root)
    if require_outputs:
        errors.extend(validate_private_outputs(repo_root))
        errors.extend(validate_public_outputs(repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--protocol-only", action="store_true")
    args = parser.parse_args()
    errors = validate_all(args.repo_root.resolve(), require_outputs=not args.protocol_only)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Pilot evidence-label validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
