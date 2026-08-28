"""Synthetic validation tests for controlled external-material intake."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "code" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_external_material_registry as validator


REGISTRY_PATH = REPO_ROOT / "code" / "config" / "external_material_registry_v0.1.yaml"
LOCAL_PATH = REPO_ROOT / "code" / "config" / "local_external_sources.yaml"


def load_registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


class ExternalMaterialRegistryTests(unittest.TestCase):
    def test_actual_registry_and_local_materials_validate(self) -> None:
        self.assertEqual(validator.validate_files(REGISTRY_PATH, LOCAL_PATH), [])

    def test_tracked_registry_contains_no_absolute_machine_path(self) -> None:
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("D:\\", text)
        self.assertNotIn("C:\\", text)

    def test_nmpa_snapshot_cannot_be_efficacy_evidence(self) -> None:
        config = load_registry()
        material = next(item for item in config["materials"] if item["material_id"] == "nmpa_marketed_drugs_snapshot_20250624")
        material["prohibited_uses"].remove("efficacy_evidence")
        errors = validator.validate_registry(config)
        self.assertTrue(any("misused as efficacy evidence" in error for error in errors))

    def test_csco_archive_cannot_be_admitted_without_pdac_guideline(self) -> None:
        config = load_registry()
        material = next(item for item in config["materials"] if item["material_id"] == "csco_2026_archive")
        material["allowed_uses"] = ["candidate_evidence"]
        errors = validator.validate_registry(config)
        self.assertTrue(any("lacking a PDAC guideline" in error for error in errors))

    def test_drugbank_cannot_be_used_before_license_confirmation(self) -> None:
        config = load_registry()
        material = next(item for item in config["materials"] if item["material_id"] == "drugbank_5_1_18_academic_archive")
        material["allowed_uses"] = ["drug_name_normalization"]
        errors = validator.validate_registry(config)
        self.assertTrue(any("before license confirmation" in error for error in errors))

    def test_identifier_bearing_examples_must_remain_quarantined(self) -> None:
        config = load_registry()
        material = next(item for item in config["materials"] if item["material_id"] == "molecular_report_input_output_examples")
        material["access_policy"] = "read_allowed"
        errors = validator.validate_registry(config)
        self.assertTrue(any("not quarantined" in error for error in errors))

    def test_local_config_cannot_add_quarantined_material(self) -> None:
        registry = load_registry()
        local = yaml.safe_load(LOCAL_PATH.read_text(encoding="utf-8"))
        local = copy.deepcopy(local)
        local["locators"]["molecular_report_input_output_examples"] = "input-output.zip"
        errors = validator.validate_local(registry, local)
        self.assertTrue(any("only the three admitted" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
