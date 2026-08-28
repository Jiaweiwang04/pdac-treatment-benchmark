"""Validate the tracked external-material intake registry and optional local locators."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import privacy_checks as privacy


REQUIRED_MATERIAL_FIELDS = {
    "material_id",
    "category",
    "admission_status",
    "project_role",
    "allowed_uses",
    "prohibited_uses",
    "redistribution_policy",
}
ADMITTED_LOCAL_IDS = {
    "aacr_bpc_panc_1_0_public",
    "nhc_antitumor_guidance_2025",
    "nmpa_marketed_drugs_snapshot_20250624",
}


def _walk(value: Any, path: str = ""):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = {
        "version",
        "status",
        "inventory_date",
        "purpose",
        "source_root_policy",
        "admission_rules",
        "materials",
        "privacy_and_publication",
        "unresolved_items",
    }
    errors.extend(f"missing top-level field: {field}" for field in sorted(required_top - set(registry)))
    if registry.get("version") != "v0.1":
        errors.append("unexpected registry version")
    if registry.get("status") != "draft_not_locked":
        errors.append("registry status must remain draft_not_locked")

    root_policy = registry.get("source_root_policy", {})
    if root_policy.get("tracked_absolute_paths") != "prohibited":
        errors.append("tracked absolute external paths are not prohibited")
    if root_policy.get("raw_material_copy_into_git") != "prohibited":
        errors.append("raw external material copy into Git is not prohibited")
    if root_policy.get("patient_level_material_copy_into_project") != "prohibited":
        errors.append("patient-level external material copy is not prohibited")

    materials = registry.get("materials", [])
    if not isinstance(materials, list):
        return errors + ["materials is not a list"]
    material_ids = [item.get("material_id") for item in materials if isinstance(item, dict)]
    if len(material_ids) != len(set(material_ids)):
        errors.append("material IDs are not unique")
    by_id: dict[str, dict[str, Any]] = {}
    for material in materials:
        if not isinstance(material, dict):
            errors.append("material is not a mapping")
            continue
        material_id = str(material.get("material_id"))
        by_id[material_id] = material
        errors.extend(
            f"{material_id} missing field: {field}"
            for field in sorted(REQUIRED_MATERIAL_FIELDS - set(material))
        )
        if not isinstance(material.get("allowed_uses"), list):
            errors.append(f"{material_id} allowed_uses is not a list")
        if not isinstance(material.get("prohibited_uses"), list):
            errors.append(f"{material_id} prohibited_uses is not a list")
        artifact = material.get("local_artifact")
        if isinstance(artifact, dict):
            sha256 = str(artifact.get("sha256", ""))
            if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
                errors.append(f"{material_id} has invalid lowercase SHA256")
        for path, value in _walk(material, f"materials.{material_id}"):
            if isinstance(value, str) and privacy.contains_identifier(value):
                errors.append(f"tracked registry contains a GENIE-like identifier at {path}")

    nhc = by_id.get("nhc_antitumor_guidance_2025", {})
    if nhc.get("admission_status") != "admitted_supplementary_claim_specific_use":
        errors.append("NHC guidance is not restricted to supplementary claim-specific use")
    if urlparse(str(nhc.get("official_notice_url", ""))).netloc.lower() != "www.nhc.gov.cn":
        errors.append("NHC guidance does not use an official NHC URL")
    if nhc.get("candidate_space_links") != ["gemcitabine_erlotinib"]:
        errors.append("NHC guidance candidate link is broader than the reviewed claim")

    nmpa = by_id.get("nmpa_marketed_drugs_snapshot_20250624", {})
    if "efficacy_evidence" not in nmpa.get("prohibited_uses", []):
        errors.append("NMPA marketed-drug snapshot can be misused as efficacy evidence")
    if "current_market_status_without_live_verification" not in nmpa.get("prohibited_uses", []):
        errors.append("stale NMPA snapshot can be treated as current without live verification")

    csco = by_id.get("csco_2026_archive", {})
    if csco.get("archive_scope_review", {}).get("pancreatic_cancer_guideline_present") is not False:
        errors.append("CSCO archive incorrectly claims to contain a PDAC guideline")
    if csco.get("allowed_uses"):
        errors.append("CSCO archive has allowed uses despite lacking a PDAC guideline")

    drugbank = by_id.get("drugbank_5_1_18_academic_archive", {})
    if drugbank.get("license_status") != "project_specific_ingestion_and_redistribution_rights_not_verified":
        errors.append("DrugBank license status is not explicitly unresolved")
    if drugbank.get("allowed_uses"):
        errors.append("DrugBank has allowed uses before license confirmation")

    private_examples = by_id.get("molecular_report_input_output_examples", {})
    if private_examples.get("access_policy") != "quarantined_do_not_read_copy_extract_or_index":
        errors.append("identifier-bearing report examples are not quarantined")
    if private_examples.get("allowed_uses"):
        errors.append("quarantined report examples have allowed project uses")

    privacy_policy = registry.get("privacy_and_publication", {})
    if privacy_policy.get("patient_or_sample_identifiers_in_tracked_files") != "prohibited":
        errors.append("tracked patient or sample identifiers are not prohibited")
    if privacy_policy.get("public_output_policy") != "aggregate_only":
        errors.append("public output policy is not aggregate-only")
    if privacy_policy.get("small_count_threshold") != 5:
        errors.append("small-count threshold is not 5")
    return errors


def validate_local(registry: dict[str, Any], local_config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if local_config.get("version") != registry.get("version"):
        errors.append("local source config version does not match registry")
    root = Path(str(local_config.get("external_source_root", "")))
    if not root.is_absolute() or not root.is_dir():
        return errors + ["local external source root is missing or not absolute"]
    locators = local_config.get("locators", {})
    if not isinstance(locators, dict):
        return errors + ["local locators is not a mapping"]
    if set(locators) != ADMITTED_LOCAL_IDS:
        errors.append("local config must contain only the three admitted material locators")

    materials = {
        str(item.get("material_id")): item
        for item in registry.get("materials", [])
        if isinstance(item, dict)
    }
    for material_id, relative in locators.items():
        relative_path = Path(str(relative))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"unsafe local locator: {material_id}")
            continue
        path = root / relative_path
        if not path.exists():
            errors.append(f"local material is missing: {material_id}")
            continue
        material = materials.get(str(material_id), {})
        if material_id == "aacr_bpc_panc_1_0_public":
            files = [item for item in path.rglob("*") if item.is_file()]
            verification = material.get("local_verification", {})
            if len(files) != verification.get("file_count"):
                errors.append("AACR PANC local file count does not match registry")
            if sum(item.stat().st_size for item in files) != verification.get("total_bytes"):
                errors.append("AACR PANC local byte count does not match registry")
        else:
            artifact = material.get("local_artifact", {})
            if path.stat().st_size != artifact.get("size_bytes"):
                errors.append(f"local material size does not match registry: {material_id}")
            if _sha256(path) != artifact.get("sha256"):
                errors.append(f"local material SHA256 does not match registry: {material_id}")
    return errors


def validate_files(registry_path: Path, local_path: Path | None = None) -> list[str]:
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict):
        return ["external material registry is not a mapping"]
    errors = validate_registry(registry)
    if local_path is not None:
        local_config = yaml.safe_load(local_path.read_text(encoding="utf-8"))
        if not isinstance(local_config, dict):
            errors.append("local external source config is not a mapping")
        else:
            errors.extend(validate_local(registry, local_config))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--skip-local", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    local_path = root / "config" / "local_external_sources.yaml"
    errors = validate_files(
        root / "config" / "external_material_registry_v0.1.yaml",
        None if args.skip_local or not local_path.exists() else local_path,
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"external_material_registry_validation=fail errors={len(errors)}")
        return 1
    print("external_material_registry_validation=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
