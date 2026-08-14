"""Validate the versioned candidate-treatment-space draft and safe crosswalk."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import privacy_checks as privacy


REQUIRED_CANDIDATE_FIELDS = {
    "candidate_id",
    "display_name",
    "candidate_type",
    "canonical_drug_set",
    "regimen_family",
    "clinical_role",
    "treatment_setting",
    "line_of_therapy",
    "maintenance_or_active_treatment",
    "biomarker_requirements",
    "prior_treatment_requirements",
    "clinical_requirements",
    "exclusion_conditions",
    "track_a_observability",
    "requires_track_b",
    "evidence_status",
    "regulatory_status",
    "guideline_status",
    "evidence_level",
    "evidence_source_ids",
    "observed_bpc_mapping_status",
    "main_pool_eligible",
    "manual_review_required",
    "notes",
}
ALLOWED_RELATIONS = {"exact", "variant", "partial", "not_candidate", "ambiguous", "masked_or_unresolvable"}
STANDARD_DRUGS = {
    "capecitabine",
    "cisplatin",
    "dabrafenib",
    "entrectinib",
    "erlotinib",
    "fluorouracil",
    "gemcitabine",
    "irinotecan",
    "larotrectinib",
    "leucovorin",
    "liposomal_irinotecan",
    "nab-paclitaxel",
    "olaparib",
    "oxaliplatin",
    "paclitaxel",
    "pembrolizumab",
    "repotrectinib",
    "selpercatinib",
    "trametinib",
    "trastuzumab_deruxtecan",
    "zenocutuzumab",
}
FORBIDDEN_KEY_PATTERN = re.compile(r"(?:dose|dosage|schedule|mg(?:_|$)|mg_m2|patient_id|sample_id|record_id)", re.IGNORECASE)
SNAKE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _walk(value: Any, path: str = ""):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _has_empty_string(value: Any) -> bool:
    return any(isinstance(child, str) and child == "" for _, child in _walk(value))


def _candidate_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(candidate.get("candidate_id")): candidate for candidate in config.get("candidates", [])}


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = {"version", "status", "disease", "setting", "evidence_cutoff_date", "track", "candidate_granularity", "main_candidate_pool", "extended_candidate_pool", "excluded_categories", "evidence_sources", "unresolved_decisions"}
    missing_top = sorted(required_top - set(config))
    errors.extend(f"missing top-level field: {field}" for field in missing_top)
    if config.get("status") != "draft_not_locked":
        errors.append("status must remain draft_not_locked")
    sources = config.get("evidence_sources", [])
    source_ids = [source.get("source_id") for source in sources if isinstance(source, dict)]
    if len(source_ids) != len(set(source_ids)):
        errors.append("evidence source IDs are not unique")
    for source in sources:
        if not isinstance(source, dict):
            errors.append("evidence source is not a mapping")
            continue
        for field in ("source_id", "source_type", "title", "organization_or_journal", "publication_date", "version_or_update_date", "url_or_doi", "access_date", "supported_claim"):
            if field not in source:
                errors.append(f"evidence source missing {field}: {source.get('source_id')}")
    candidates = config.get("candidates", [])
    candidate_ids = [candidate.get("candidate_id") for candidate in candidates if isinstance(candidate, dict)]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("candidate IDs are not unique")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("candidate is not a mapping")
            continue
        candidate_id = str(candidate.get("candidate_id"))
        if not SNAKE_ID_PATTERN.fullmatch(candidate_id):
            errors.append(f"candidate ID is not ASCII snake_case: {candidate_id}")
        missing = sorted(REQUIRED_CANDIDATE_FIELDS - set(candidate))
        errors.extend(f"{candidate_id} missing candidate field: {field}" for field in missing)
        components = candidate.get("canonical_drug_set")
        if not isinstance(components, list):
            errors.append(f"{candidate_id} canonical_drug_set is not a list")
        else:
            unknown = sorted(set(str(component) for component in components) - STANDARD_DRUGS)
            errors.extend(f"{candidate_id} has non-standard drug component: {component}" for component in unknown)
            if "irinotecan" in components and "liposomal_irinotecan" in components:
                errors.append(f"{candidate_id} mixes ordinary and liposomal irinotecan")
        for path, value in _walk(candidate):
            if isinstance(value, str) and FORBIDDEN_KEY_PATTERN.search(path):
                errors.append(f"{candidate_id} contains forbidden field or dosage-like key: {path}")
            if isinstance(value, str) and privacy.contains_identifier(value):
                errors.append(f"{candidate_id} contains a GENIE-like identifier")
        source_refs = candidate.get("evidence_source_ids", [])
        if not source_refs:
            errors.append(f"{candidate_id} has no evidence source")
        for source_ref in source_refs:
            if source_ref not in source_ids:
                errors.append(f"{candidate_id} references missing evidence source: {source_ref}")
        biomarker = candidate.get("biomarker_requirements", {})
        if biomarker.get("status") == "required" and not biomarker.get("required_markers"):
            errors.append(f"{candidate_id} requires a structured biomarker condition")
        if candidate.get("maintenance_or_active_treatment") == "maintenance" and candidate.get("clinical_role") == "active_systemic_treatment":
            errors.append(f"{candidate_id} has inconsistent maintenance and clinical_role")
        if candidate.get("requires_track_b") is True and not candidate.get("clinical_requirements"):
            errors.append(f"{candidate_id} requires Track B but has no clinical requirements")
    candidate_by_id = _candidate_map(config)
    main_pool = config.get("main_candidate_pool", [])
    extended_pool = config.get("extended_candidate_pool", [])
    if set(main_pool) & set(extended_pool):
        errors.append("main and extended candidate pools overlap")
    for pool_name, pool in (("main", main_pool), ("extended", extended_pool)):
        for candidate_id in pool:
            if candidate_id not in candidate_by_id:
                errors.append(f"{pool_name} pool references unknown candidate: {candidate_id}")
            elif bool(candidate_by_id[candidate_id].get("main_pool_eligible")) != (pool_name == "main"):
                errors.append(f"{candidate_id} main_pool_eligible disagrees with {pool_name} pool")
    excluded = config.get("excluded_categories", [])
    for candidate_id in main_pool:
        if candidate_id in excluded:
            errors.append(f"excluded category enters main pool: {candidate_id}")
    if _has_empty_string(config):
        errors.append("configuration contains an unexplained empty string")
    return errors


def validate_crosswalk(config: dict[str, Any], crosswalk_path: Path) -> list[str]:
    errors: list[str] = []
    candidate_by_id = _candidate_map(config)
    if not crosswalk_path.exists():
        return [f"missing crosswalk: {crosswalk_path}"]
    text = crosswalk_path.read_text(encoding="utf-8")
    if privacy.contains_identifier(text):
        errors.append("crosswalk contains a GENIE-like identifier")
    with crosswalk_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"regimen_family", "canonical_drug_set", "candidate_id", "mapping_relation", "mapping_status", "reason", "manual_review_required"}
        errors.extend(f"crosswalk missing field: {field}" for field in sorted(required - set(reader.fieldnames or [])))
        for line_no, row in enumerate(reader, start=2):
            relation = row.get("mapping_relation", "")
            candidate_id = row.get("candidate_id", "")
            if relation not in ALLOWED_RELATIONS:
                errors.append(f"crosswalk line {line_no} has invalid relation: {relation}")
            if candidate_id != "not_applicable" and candidate_id not in candidate_by_id:
                errors.append(f"crosswalk line {line_no} references unknown candidate: {candidate_id}")
            if relation == "masked_or_unresolvable":
                if candidate_id != "masked_investigational_regimen_review":
                    errors.append(f"crosswalk line {line_no} maps masked regimen to a concrete candidate")
                elif candidate_by_id.get(candidate_id, {}).get("canonical_drug_set"):
                    errors.append(f"crosswalk line {line_no} maps masked regimen to a drug-bearing candidate")
            for key, value in row.items():
                if key and privacy.is_high_risk_field_name(key):
                    errors.append(f"crosswalk contains high-risk field: {key}")
                if privacy.contains_identifier(str(value or "")):
                    errors.append(f"crosswalk line {line_no} contains an identifier")
    return errors


def validate_candidate_treatment_space(config_path: Path, crosswalk_path: Path) -> list[str]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        return ["candidate configuration is not a mapping"]
    return validate_config(config) + validate_crosswalk(config, crosswalk_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.repo_root.resolve()
    errors = validate_candidate_treatment_space(root / "config/candidate_treatment_space_v0.1.yaml", root / "code/mappings/candidate_regimen_crosswalk_v0.1.csv")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"candidate_space_validation=fail errors={len(errors)}")
        return 1
    print("candidate_space_validation=pass")
    print("crosswalk_validation=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
