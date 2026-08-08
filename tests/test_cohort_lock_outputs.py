"""Tests for Round 3.1 cohort-lock repair logic.

Synthetic tests avoid depending on patient-level raw data. Integration tests
run only when the local BPC PANC raw release is present.
"""

from __future__ import annotations

import csv
import subprocess
import sys
import unittest
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "code" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import audit_cohort_lock_label_feasibility as audit
import audit_cohort_t0_feasibility as t0audit


def make_patient(cohort: str, record_id: str, n_cancers: str = "1") -> dict[str, str]:
    return {"cohort": cohort, "record_id": record_id, "n_cancers": n_cancers}


def make_cancer(
    cohort: str,
    record_id: str,
    ca_seq: str,
    *,
    ca_type: str = "Pancreatic Cancer",
    site: str = "C25.0",
    oncotree: str = "PAAD",
    histology: str = "Adenocarcinoma, NOS",
    hist_code: str = "8140",
    stage_iv: str = "Stage IV",
    dmets: str = "No",
    resect: str = "",
    dmets_post: str = "0",
    dmets_day: str = "",
) -> dict[str, str]:
    return {
        "cohort": cohort,
        "record_id": record_id,
        "institution": "TEST",
        "ca_seq": ca_seq,
        "redcap_ca_index": "Yes",
        "ca_type": ca_type,
        "ca_d_site": site,
        "ca_histology": histology,
        "naaccr_histology_cd": hist_code,
        "stage_dx_iv": stage_iv,
        "ca_dmets_yn": dmets,
        "ca_resect_status": resect,
        "dmets_post_dx": dmets_post,
        "dx_to_dmets_days": dmets_day,
        "_oncotree": oncotree,
    }


def make_cpt(cohort: str, record_id: str, ca_seq: str, report_day: str, *, oncotree: str = "PAAD") -> dict[str, str]:
    return {
        "cohort": cohort,
        "record_id": record_id,
        "institution": "TEST",
        "ca_seq": ca_seq,
        "cpt_number": "1",
        "cpt_n_ca_seq": "1",
        "dx_cpt_rep_days": report_day,
        "dx_path_proc_cpt_days": report_day,
        "path_proc_cpt_rep_days": "0",
        "cpt_order_int": "",
        "cpt_report_post_death": "0",
        "cpt_report_post_last_alive": "0",
        "path_proc_number": "1",
        "path_rep_number": "1",
        "cpt_genie_sample_id": f"S-{cohort}-{record_id}-{ca_seq}-{report_day}",
        "cpt_oncotree_code": oncotree,
        "cpt_seq_date": "2018",
    }


def make_regimen(
    cohort: str,
    record_id: str,
    ca_seq: str,
    start_day: str,
    drugs: str,
    *,
    regimen_number: str = "1",
    within: str = "1",
) -> dict[str, str]:
    parts = [part.strip() for part in drugs.split(",")]
    row = {
        "cohort": cohort,
        "record_id": record_id,
        "institution": "TEST",
        "ca_seq": ca_seq,
        "regimen_number": regimen_number,
        "regimen_number_within_cancer": within,
        "redcap_ca_index": "Yes",
        "regimen_drugs": drugs,
        "dx_reg_start_int": start_day,
        "dx_reg_end_any_int": "",
        "dx_reg_end_all_int": "",
        "os_g_status": "",
        "tt_os_g_days": "",
        "pfs_i_g_status": "",
        "tt_pfs_i_g_days": "",
        "pfs_m_g_status": "",
        "tt_pfs_m_g_days": "",
        "ttnt_any_ca_status": "",
        "ttnt_any_ca_days": "",
        "ttnt_ca_seq_status": "",
        "ttnt_ca_seq_days": "",
    }
    for idx in range(1, 6):
        row[f"drugs_drug_{idx}"] = parts[idx - 1] if idx <= len(parts) else ""
    return row


def build_synthetic_data(
    patients: list[dict[str, str]],
    cancers: list[dict[str, str]],
    cpts: list[dict[str, str]],
    regimens: list[dict[str, str]],
) -> dict[str, pd.DataFrame]:
    patient = pd.DataFrame(patients)
    raw_cancer = pd.DataFrame([{k: v for k, v in row.items() if k != "_oncotree"} for row in cancers])
    cpt_rows = []
    for row in cpts:
        cpt_rows.append(row.copy())
    cpt = t0audit.prepare_cpt(pd.DataFrame(cpt_rows))
    regimen = audit.annotate_regimen_standardization(t0audit.prepare_regimen(pd.DataFrame(regimens)))
    cancer = audit.annotate_pdac_mapping(raw_cancer, cpt)
    cancer = audit.annotate_advanced_evidence(cancer)
    cancer = audit.annotate_instance_resolution(cancer)
    return {
        "patient": patient,
        "raw_cancer": raw_cancer,
        "raw_cpt": pd.DataFrame(cpt_rows),
        "raw_regimen": pd.DataFrame(regimens),
        "cancer": cancer,
        "cpt": cpt,
        "regimen": regimen,
        "non_index_cancer": pd.DataFrame(),
    }


class SyntheticCohortRepairTests(unittest.TestCase):
    def test_selects_only_pdac_instance_treatment(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1", "2")],
            [
                make_cancer("A", "P1", "0", oncotree="PAAD"),
                make_cancer("A", "P1", "1", ca_type="Breast Cancer", site="C50.9", oncotree="BRCA", histology="", hist_code=""),
            ],
            [make_cpt("A", "P1", "0", "5"), make_cpt("A", "P1", "1", "1", oncotree="BRCA")],
            [
                make_regimen("A", "P1", "1", "10", "Capecitabine", regimen_number="1", within="1"),
                make_regimen("A", "P1", "0", "20", "Gemcitabine HCL", regimen_number="2", within="1"),
            ],
        )
        selected = audit.select_t0_candidates(data, advanced_rule="strict")
        self.assertEqual(len(selected), 1)
        self.assertEqual(str(selected.iloc[0]["ca_seq"]), "0")
        self.assertEqual(float(selected.iloc[0]["start_day"]), 20.0)

    def test_continues_after_earliest_other_cancer_treatment(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1", "2")],
            [
                make_cancer("A", "P1", "0", oncotree="PAAD"),
                make_cancer("A", "P1", "1", ca_type="Other", site="C18.9", oncotree="COAD", histology="", hist_code=""),
            ],
            [make_cpt("A", "P1", "0", "2"), make_cpt("A", "P1", "1", "2", oncotree="COAD")],
            [
                make_regimen("A", "P1", "1", "3", "Capecitabine", regimen_number="1", within="1"),
                make_regimen("A", "P1", "0", "30", "Gemcitabine HCL", regimen_number="2", within="1"),
            ],
        )
        selected = audit.select_t0_candidates(data, advanced_rule="strict")
        self.assertEqual(float(selected.iloc[0]["start_day"]), 30.0)

    def test_formal_patient_key_includes_cohort_and_record_id(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1"), make_patient("B", "P1")],
            [make_cancer("A", "P1", "0"), make_cancer("B", "P1", "0")],
            [make_cpt("A", "P1", "0", "1"), make_cpt("B", "P1", "0", "1")],
            [make_regimen("A", "P1", "0", "10", "Gemcitabine HCL"), make_regimen("B", "P1", "0", "10", "Gemcitabine HCL")],
        )
        selected = audit.select_t0_candidates(data, advanced_rule="strict")
        self.assertEqual(audit.count_patient_keys(selected), 2)

    def test_same_day_advanced_evidence_not_strict_core(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1")],
            [make_cancer("A", "P1", "0", stage_iv="Stage IV")],
            [make_cpt("A", "P1", "0", "-1")],
            [make_regimen("A", "P1", "0", "0", "Gemcitabine HCL")],
        )
        strict = audit.select_t0_candidates(data, advanced_rule="strict")
        same_day = audit.select_t0_candidates(data, advanced_rule="same_day_sensitivity")
        self.assertEqual(len(strict), 0)
        self.assertEqual(len(same_day), 1)
        self.assertEqual(audit.strict_core_from_extended(same_day).query("advanced_relation == 'same_day_ambiguous'").shape[0], 0)

    def test_pdac_mapping_is_mutually_exclusive_and_complete(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", f"P{i}") for i in range(4)],
            [
                make_cancer("A", "P0", "0", oncotree="PAAD"),
                make_cancer("A", "P1", "0", oncotree="PAASC", histology="Adenosquamous carcinoma", hist_code="8560"),
                make_cancer("A", "P2", "0", oncotree="PAAC", histology="Acinar cell carcinoma", hist_code="8550"),
                make_cancer("A", "P3", "0", oncotree="", histology="", hist_code=""),
            ],
            [make_cpt("A", f"P{i}", "0", "1", oncotree=["PAAD", "PAASC", "PAAC", ""][i]) for i in range(4)],
            [make_regimen("A", f"P{i}", "0", "10", "Gemcitabine HCL") for i in range(4)],
        )
        statuses = set(data["cancer"]["pdac_mapping_status"])
        self.assertEqual(statuses, {"include", "manual_review", "exclude", "insufficient_info"})
        self.assertTrue(data["cancer"]["pdac_mapping_status"].isin(statuses).all())

    def test_combination_standardization_is_lossless(self) -> None:
        row = make_regimen("A", "P1", "0", "10", "Cisplatin, Gemcitabine HCL, Nabpaclitaxel")
        result = audit.standardize_regimen_row(row)
        self.assertTrue(result["standardized_components_lossless"])
        self.assertEqual(result["canonical_drug_set"], "cisplatin+gemcitabine+nab-paclitaxel")
        self.assertEqual(result["regimen_family"], "cisplatin_gemcitabine_nab_paclitaxel")

    def test_ordinary_and_liposomal_irinotecan_are_distinct(self) -> None:
        ordinary = audit.standardize_regimen_row(make_regimen("A", "P1", "0", "10", "Fluorouracil, Irinotecan HCL, Leucovorin"))
        liposomal = audit.standardize_regimen_row(make_regimen("A", "P1", "0", "10", "Fluorouracil, Irinotecan liposome, Leucovorin"))
        self.assertIn("irinotecan", ordinary["canonical_drug_set"])
        self.assertIn("liposomal_irinotecan", liposomal["canonical_drug_set"])
        self.assertNotEqual(ordinary["regimen_family"], liposomal["regimen_family"])

    def test_all_raw_regimens_have_mapping_status(self) -> None:
        regimen = pd.DataFrame(
            [
                make_regimen("A", "P1", "0", "10", "Gemcitabine HCL"),
                make_regimen("A", "P2", "0", "10", "Investigational Drug"),
                make_regimen("A", "P3", "0", "10", "Unlisted Mystery Drug"),
            ]
        )
        annotated = audit.annotate_regimen_standardization(t0audit.prepare_regimen(regimen))
        self.assertTrue(audit.nonmissing(annotated["regimen_mapping_status"]).all())

    def test_main_cohort_has_one_sample_per_patient_and_prior_ngs(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1")],
            [make_cancer("A", "P1", "0")],
            [make_cpt("A", "P1", "0", "1"), make_cpt("A", "P1", "0", "5")],
            [make_regimen("A", "P1", "0", "10", "Gemcitabine HCL")],
        )
        selected = audit.select_t0_candidates(data, advanced_rule="strict")
        self.assertEqual(len(selected), 1)
        self.assertTrue((selected["index_ngs_report_day"] < selected["start_day"]).all())

    def test_t0_treatment_and_post_t0_outcomes_not_inputs(self) -> None:
        rows = audit.field_leakage_rows()
        by_field = {row["field"]: row for row in rows}
        self.assertEqual(by_field["t0 regimen_drugs"]["allowed_as_model_input"], "no")
        self.assertEqual(by_field["pfs*/os*/ttnt*"]["allowed_as_model_input"], "no")

    def test_base_cohort_does_not_depend_on_outcome_availability(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1")],
            [make_cancer("A", "P1", "0")],
            [make_cpt("A", "P1", "0", "1")],
            [make_regimen("A", "P1", "0", "10", "Gemcitabine HCL")],
        )
        selected = audit.select_t0_candidates(data, advanced_rule="strict")
        self.assertEqual(len(selected), 1)
        endpoints = audit.endpoint_coverage_rows("Synthetic", selected)
        self.assertTrue(all(row["field_present_evaluable_n"] == 0 for row in endpoints))

    def test_flow_accounting_is_monotonic(self) -> None:
        data = build_synthetic_data(
            [make_patient("A", "P1"), make_patient("A", "P2")],
            [make_cancer("A", "P1", "0"), make_cancer("A", "P2", "0", oncotree="PAAC")],
            [make_cpt("A", "P1", "0", "1"), make_cpt("A", "P2", "0", "1", oncotree="PAAC")],
            [make_regimen("A", "P1", "0", "10", "Gemcitabine HCL"), make_regimen("A", "P2", "0", "10", "Gemcitabine HCL")],
        )
        candidates = audit.t0_candidate_regimens(data["cancer"], data["cpt"], data["regimen"])
        strict = audit.select_t0_candidates(data, advanced_rule="strict")
        rows = audit.flow_rows(data, candidates, strict, audit.strict_core_from_extended(strict), strict, pd.DataFrame())
        main_counts = [row["n_patients"] for row in rows if row["cohort_stage"] == "round3_1_main"]
        self.assertTrue(all(main_counts[i] >= main_counts[i + 1] for i in range(len(main_counts) - 1)))


class IntegrationOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw_root = REPO_ROOT / audit.PANC_RELATIVE_ROOT
        if not raw_root.exists():
            raise unittest.SkipTest("Local BPC PANC raw data not present")
        subprocess.run(
            [sys.executable, "code/scripts/audit_cohort_lock_label_feasibility.py", "--repo-root", "."],
            cwd=REPO_ROOT,
            check=True,
        )

    def read_csv(self, relative_path: str) -> list[dict[str, str]]:
        with (REPO_ROOT / relative_path).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_automated_checks_all_pass(self) -> None:
        rows = self.read_csv("reports/tables/automated_checks.csv")
        self.assertGreaterEqual(len(rows), 10)
        self.assertEqual([row for row in rows if row["status"] != "pass"], [])

    def test_public_outputs_do_not_contain_patient_ids(self) -> None:
        self.assertEqual(audit.scan_public_patient_ids(REPO_ROOT), 0)

    def test_public_count_cells_are_suppressed(self) -> None:
        self.assertEqual(audit.scan_public_small_counts(REPO_ROOT), [])

    def test_endpoint_validation_statuses_are_explicit(self) -> None:
        rows = self.read_csv("reports/tables/endpoint_coverage.csv")
        statuses = {(row["endpoint"], row["post_t0_outcome_status"]) for row in rows if row["cohort"] == "Strict Extended"}
        self.assertIn(("OS", "t0_validated"), statuses)
        self.assertIn(("PFS-I", "t0_validated"), statuses)
        self.assertIn(("PFS-M", "t0_validated"), statuses)
        self.assertIn(("TTNT-any-cancer", "field_present_not_t0_validated"), statuses)


if __name__ == "__main__":
    unittest.main()
