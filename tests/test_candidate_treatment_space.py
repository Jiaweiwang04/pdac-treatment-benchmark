"""Synthetic validation and reverse tests for the candidate treatment space."""

from __future__ import annotations

import csv
import copy
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "code" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import generate_candidate_regimen_crosswalk as generator
import privacy_checks as privacy
import validate_candidate_treatment_space as validator


CONFIG_PATH = REPO_ROOT / "config" / "candidate_treatment_space_v0.1.yaml"
CROSSWALK_PATH = REPO_ROOT / "code" / "mappings" / "candidate_regimen_crosswalk_v0.1.csv"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def fake_genie_id(serial: str) -> str:
    return "GENIE-" + "FAKE-" + "P-" + serial + "-T01-IMX"


def write_config(tmp: Path, config: dict) -> Path:
    path = tmp / "candidate.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


class CandidateTreatmentSpaceTests(unittest.TestCase):
    def test_actual_space_and_crosswalk_validate(self) -> None:
        self.assertEqual(validator.validate_candidate_treatment_space(CONFIG_PATH, CROSSWALK_PATH), [])

    def test_candidate_ids_are_unique(self) -> None:
        config = load_config()
        config["candidates"].append(copy.deepcopy(config["candidates"][0]))
        with tempfile.TemporaryDirectory() as directory:
            errors = validator.validate_config(yaml.safe_load(write_config(Path(directory), config).read_text(encoding="utf-8")))
        self.assertTrue(any("candidate IDs are not unique" in error for error in errors))

    def test_missing_evidence_source_fails(self) -> None:
        config = load_config()
        config["candidates"][0]["evidence_source_ids"] = ["missing_source"]
        errors = validator.validate_config(config)
        self.assertTrue(any("references missing evidence source" in error for error in errors))

    def test_ordinary_and_liposomal_irinotecan_cannot_be_merged(self) -> None:
        config = load_config()
        config["candidates"][0]["canonical_drug_set"].append("liposomal_irinotecan")
        errors = validator.validate_config(config)
        self.assertTrue(any("mixes ordinary and liposomal irinotecan" in error for error in errors))

    def test_biomarker_candidate_requires_structured_condition(self) -> None:
        config = load_config()
        candidate = next(item for item in config["candidates"] if item["candidate_id"] == "pembrolizumab_msi_h_dmmr")
        candidate["biomarker_requirements"]["required_markers"] = []
        errors = validator.validate_config(config)
        self.assertTrue(any("requires a structured biomarker condition" in error for error in errors))

    def test_masked_regimen_cannot_map_to_concrete_candidate(self) -> None:
        config = load_config()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "crosswalk.csv"
            with CROSSWALK_PATH.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                if row["mapping_relation"] == "masked_or_unresolvable":
                    row["candidate_id"] = "folfirinox"
            with output.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            errors = validator.validate_crosswalk(config, output)
        self.assertTrue(any("maps masked regimen to a concrete candidate" in error for error in errors))

    def test_unknown_main_pool_candidate_fails(self) -> None:
        config = load_config()
        config["main_candidate_pool"].append("does_not_exist")
        errors = validator.validate_config(config)
        self.assertTrue(any("main pool references unknown candidate" in error for error in errors))

    def test_document_and_yaml_candidate_ids_are_present(self) -> None:
        document = (REPO_ROOT / "docs" / "notes" / "candidate_treatment_space_design_v0.1.md").read_text(encoding="utf-8")
        config = load_config()
        for candidate_id in config["main_candidate_pool"] + config["extended_candidate_pool"]:
            self.assertIn(f"`{candidate_id}`", document)

    def test_crosswalk_is_programmatically_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "crosswalk.csv"
            count = generator.generate(REPO_ROOT / "code" / "mappings" / "regimen_mapping_v0.1.csv", output)
            self.assertEqual(count, 46)
            errors = validator.validate_crosswalk(load_config(), output)
        self.assertEqual(errors, [])


class CandidateTreatmentSpacePrivacyTests(unittest.TestCase):
    def test_synthetic_genie_like_id_in_results_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "code" / "results" / "fake.csv"
            path.parent.mkdir(parents=True)
            path.write_text(f"metric,value\nexample,{fake_genie_id('000001')}\n", encoding="utf-8")
            hits = privacy.privacy_scan_hits(root, ["code/results/fake.csv"])
        self.assertTrue(hits)

    def test_synthetic_genie_like_id_in_reports_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "reports" / "fake.md"
            path.parent.mkdir(parents=True)
            path.write_text(fake_genie_id("000002"), encoding="utf-8")
            hits = privacy.privacy_scan_hits(root, ["reports/fake.md"])
        self.assertTrue(hits)

    def test_safe_aggregate_table_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "reports" / "aggregate.csv"
            path.parent.mkdir(parents=True)
            path.write_text("metric,n\npatients,27\n", encoding="utf-8")
            hits = privacy.privacy_scan_hits(root, ["reports/aggregate.csv"])
        self.assertEqual(hits, [])

    def test_binary_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "reports" / "binary.csv"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"\xff\xfe\x00\x01")
            self.assertEqual(privacy.privacy_scan_hits(root, ["reports/binary.csv"]), [])

    def test_scan_uses_tracked_file_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hidden = root / "reports" / "untracked.md"
            hidden.parent.mkdir(parents=True)
            hidden.write_text(fake_genie_id("000003"), encoding="utf-8")
            self.assertEqual(privacy.privacy_scan_hits(root, []), [])
            self.assertTrue(privacy.privacy_scan_hits(root, ["reports/untracked.md"]))


class CandidateTreatmentSpaceSuppressionTests(unittest.TestCase):
    def test_common_count_column_is_suppressed(self) -> None:
        self.assertEqual(privacy.public_cell("count", 1), "<5")
        self.assertEqual(privacy.public_cell("n_patients", 4), "<5")

    def test_semantic_different_index_count_is_suppressed(self) -> None:
        self.assertEqual(privacy.public_cell("different_index_sample_vs_main", 2), "<5")

    def test_metric_value_count_is_suppressed(self) -> None:
        row = {"metric": "same_day_multiple_t0_patients", "value": 3}
        self.assertEqual(privacy.public_cell("value", row["value"], row), "<5")

    def test_non_count_values_are_not_suppressed(self) -> None:
        self.assertEqual(privacy.public_cell("missing_rate", 0.03), 0.03)
        self.assertEqual(privacy.public_cell("year", 2024), 2024)
        self.assertEqual(privacy.public_cell("duration_days", 3), 3)

    def test_unsuppressed_small_public_cell_fails_then_passes_after_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "reports" / "counts.csv"
            path.parent.mkdir(parents=True)
            path.write_text("metric,different_index_sample_vs_main\ncomparison,2\n", encoding="utf-8")
            self.assertTrue(privacy.small_count_scan_hits(root, ["reports/counts.csv"]))
            path.write_text("metric,different_index_sample_vs_main\ncomparison,<5\n", encoding="utf-8")
            self.assertEqual(privacy.small_count_scan_hits(root, ["reports/counts.csv"]), [])


if __name__ == "__main__":
    unittest.main()
