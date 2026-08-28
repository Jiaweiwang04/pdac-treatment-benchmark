"""Validate the versioned candidate-treatment-space draft and safe crosswalk."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
ALLOWED_SOURCE_TYPES = {
    "dataset_documentation",
    "evidence_summary",
    "official_drug_summary",
    "official_practice_guidance",
    "peer_reviewed_randomized_trial",
    "regulatory_approval",
    "regulatory_approval_letter",
    "regulatory_label",
    "regulatory_review",
}
BROAD_REGULATORY_PATHS = {
    "/drugs/resources-information-approved-drugs/oncology-cancerhematologic-malignancies-approval-notifications",
    "/drugs/resources-information-approved-drugs/verified-clinical-benefit-cancer-accelerated-approvals",
}
OFFICIAL_HOSTS_BY_PREFIX = {
    "fda_": {"www.fda.gov", "www.accessdata.fda.gov"},
    "nci_": {"www.cancer.gov"},
    "nhc_": {"www.nhc.gov.cn"},
    "aacr_": {"www.aacr.org"},
}
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
    required_top = {"version", "status", "disease", "setting", "evidence_cutoff_date", "track", "candidate_granularity", "main_candidate_pool", "extended_candidate_pool", "excluded_categories", "evidence_sources", "review_decisions", "unresolved_decisions"}
    missing_top = sorted(required_top - set(config))
    errors.extend(f"missing top-level field: {field}" for field in missing_top)
    if config.get("status") != "draft_not_locked":
        errors.append("status must remain draft_not_locked")
    try:
        evidence_cutoff = date.fromisoformat(str(config.get("evidence_cutoff_date")))
    except ValueError:
        evidence_cutoff = None
        errors.append("evidence_cutoff_date is not an ISO date")
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
        source_id = str(source.get("source_id"))
        source_type = str(source.get("source_type"))
        if source_type not in ALLOWED_SOURCE_TYPES:
            errors.append(f"{source_id} has unsupported source type: {source_type}")
        parsed = urlparse(str(source.get("url_or_doi", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{source_id} does not use a valid HTTPS evidence URL")
        if parsed.path.rstrip("/") in BROAD_REGULATORY_PATHS:
            errors.append(f"{source_id} uses a broad regulatory directory instead of a claim-specific source")
        for prefix, allowed_hosts in OFFICIAL_HOSTS_BY_PREFIX.items():
            if source_id.startswith(prefix) and parsed.netloc.lower() not in allowed_hosts:
                errors.append(f"{source_id} does not use an official source host")
        if source_id.startswith("nci_pdq_") and source_type != "evidence_summary":
            errors.append(f"{source_id} must be classified as an evidence summary, not a clinical guideline")
        for field in ("publication_date", "access_date"):
            value = source.get(field)
            if field == "publication_date" and value == "unknown":
                continue
            try:
                source_date = date.fromisoformat(str(value))
            except ValueError:
                errors.append(f"{source_id} has invalid ISO date in {field}: {value}")
                continue
            if evidence_cutoff is not None and source_date > evidence_cutoff:
                errors.append(f"{source_id} {field} exceeds the evidence cutoff")
        version_or_update = str(source.get("version_or_update_date", ""))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", version_or_update):
            version_date = date.fromisoformat(version_or_update)
            if evidence_cutoff is not None and version_date > evidence_cutoff:
                errors.append(f"{source_id} version_or_update_date exceeds the evidence cutoff")
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
        permitted_agents = candidate.get("permitted_single_agents")
        agent_source_refs = candidate.get("agent_evidence_source_ids")
        if candidate.get("candidate_type") == "biomarker_matched_class":
            if components:
                errors.append(f"{candidate_id} class candidate must not encode alternative agents as a canonical drug combination")
            if not isinstance(permitted_agents, list) or not permitted_agents:
                errors.append(f"{candidate_id} class candidate requires permitted_single_agents")
            else:
                unknown_agents = sorted(set(str(agent) for agent in permitted_agents) - STANDARD_DRUGS)
                errors.extend(f"{candidate_id} has non-standard permitted single agent: {agent}" for agent in unknown_agents)
                if len(permitted_agents) != len(set(permitted_agents)):
                    errors.append(f"{candidate_id} permitted single agents are not unique")
            if not isinstance(agent_source_refs, dict) or set(agent_source_refs) != set(permitted_agents or []):
                errors.append(f"{candidate_id} must map every permitted single agent to evidence")
            else:
                for agent, refs in agent_source_refs.items():
                    if not isinstance(refs, list) or not refs:
                        errors.append(f"{candidate_id} permitted agent has no evidence source: {agent}")
                        continue
                    for source_ref in refs:
                        if source_ref not in source_ids:
                            errors.append(f"{candidate_id} permitted agent references missing evidence source: {source_ref}")
                        if source_ref not in candidate.get("evidence_source_ids", []):
                            errors.append(f"{candidate_id} permitted-agent evidence is absent from candidate evidence sources: {source_ref}")
        elif permitted_agents is not None or agent_source_refs is not None:
            errors.append(f"{candidate_id} uses class-agent fields but is not a class candidate")
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
        if "nci_pdq_supported" in str(candidate.get("guideline_status", "")):
            errors.append(f"{candidate_id} treats NCI PDQ as a formal clinical guideline")
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
    disease = config.get("disease", {})
    excluded_histologies = set(disease.get("excluded_histologies", []))
    manual_review_histologies = set(disease.get("manual_review_histologies", []))
    if excluded_histologies & manual_review_histologies:
        errors.append("excluded and manual-review histologies overlap")
    if "adenosquamous_carcinoma" in excluded_histologies:
        errors.append("adenosquamous carcinoma must inherit the cohort manual-review boundary")
    if "adenosquamous_carcinoma" not in manual_review_histologies:
        errors.append("adenosquamous carcinoma is missing from the candidate-space manual-review boundary")
    decisions = config.get("review_decisions", [])
    decision_ids = [decision.get("decision_id") for decision in decisions if isinstance(decision, dict)]
    if len(decision_ids) != len(set(decision_ids)):
        errors.append("review decision IDs are not unique")
    required_decision_ids = {
        "retain_conditional_cytotoxic_candidates_in_track_a_main_pool",
        "retain_ntrk_class_candidate",
    }
    for decision_id in sorted(required_decision_ids - set(decision_ids)):
        errors.append(f"missing confirmed review decision: {decision_id}")
    for decision in decisions:
        if not isinstance(decision, dict):
            errors.append("review decision is not a mapping")
            continue
        for field in ("decision_id", "status", "decision_date", "decision", "rationale", "safeguards"):
            if field not in decision:
                errors.append(f"review decision missing {field}: {decision.get('decision_id')}")
        if decision.get("status") != "project_owner_confirmed_benchmark_design_not_medical_freeze":
            errors.append(f"review decision has invalid status: {decision.get('decision_id')}")
    for candidate_id in ("folfox_or_off", "gemcitabine_paclitaxel_after_folfirinox"):
        candidate = candidate_by_id.get(candidate_id, {})
        if candidate_id not in main_pool or not candidate.get("main_pool_eligible"):
            errors.append(f"confirmed Track A candidate is absent from the main pool: {candidate_id}")
        if candidate.get("track_a_pool_status") != "retained_main_conditional_not_clinically_cleared":
            errors.append(f"confirmed Track A candidate lacks the conditional pool boundary: {candidate_id}")
        if candidate.get("manual_review_required") is not True:
            errors.append(f"confirmed Track A candidate must require manual review: {candidate_id}")
    ntrk = candidate_by_id.get("ntrk_fusion_targeted_therapy", {})
    if ntrk.get("candidate_granularity_status") != "retained_class_with_mutually_exclusive_single_agents":
        errors.append("NTRK candidate does not preserve the confirmed class-level granularity")
    nhc_linked_candidates = {
        candidate_id
        for candidate_id, candidate in candidate_by_id.items()
        if "nhc_antitumor_guidance_2025" in candidate.get("evidence_source_ids", [])
    }
    if nhc_linked_candidates != {"gemcitabine_erlotinib"}:
        errors.append("NHC 2025 guidance must link only to the reviewed gemcitabine_erlotinib claim")
    unresolved_names = {decision.get("decision") for decision in config.get("unresolved_decisions", []) if isinstance(decision, dict)}
    if unresolved_names & {"confirm_main_pool_boundary_for_folfox_off_and_gemcitabine_paclitaxel", "split_ntrk_class_into_individual_agents"}:
        errors.append("a confirmed benchmark decision remains listed as unresolved")
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
    errors = validate_candidate_treatment_space(root / "code/config/candidate_treatment_space_v0.1.yaml", root / "code/results/mappings/candidate_regimen_crosswalk_v0.1.csv")
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
