import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pdac_benchmark.v2_0.development_split import (
    CONFIG, annotate_candidates, run, select_patients, validate_config,
)
from pdac_benchmark.v2_0.patient_split import check_identity_isolation


def population():
    rows = [{"patient_key": ["P", str(i)], "split": "development", "pilot_member": i < 5,
             "stratum": ["A" if i < 15 else "B", "met"]} for i in range(30)]
    rows += [{"patient_key": ["P", "core"], "split": "core_test", "pilot_member": False, "stratum": ["A", "met"]},
             {"patient_key": ["P", "extension"], "split": "extension_only", "pilot_member": False, "stratum": None}]
    return rows


class DevelopmentSplitTests(unittest.TestCase):
    def test_reserved_pilot_exact_counts_and_core_extension_unchanged(self):
        parent = population()
        before = copy.deepcopy(parent)
        rows, quotas = select_patients(parent, 6, 20261003, "validation")
        self.assertEqual(parent, before)
        self.assertEqual(sum(r["development_fold"] == "training" for r in rows), 24)
        self.assertEqual(sum(r["development_fold"] == "validation" for r in rows), 6)
        self.assertTrue(all(r["effective_split"] == "training" for r in rows if r["pilot_member"]))
        self.assertEqual(quotas, {("A", "met"): 2, ("B", "met"): 4})
        for r in rows:
            if r["split"] != "development":
                self.assertIsNone(r["development_fold"])
                self.assertEqual(r["effective_split"], r["split"])

    def test_order_and_labels_outcomes_molecular_changes_do_not_select_patients(self):
        rows = population()
        first, _ = select_patients(rows, 6, 20261003, "validation")
        altered = [{**r, "expert_label": "SUPPORTED", "outcome": "excellent", "mutations": ["BRCA2"]}
                   for r in reversed(rows)]
        second, _ = select_patients(altered, 6, 20261003, "validation")
        self.assertEqual([(r["patient_key"], r["effective_split"]) for r in first],
                         [(r["patient_key"], r["effective_split"]) for r in second])

    def test_pilot_only_sparse_stratum_stays_training(self):
        rows = population()
        for r in rows[:5]:
            r["stratum"] = ["PILOT_ONLY", "rare"]
        result, quotas = select_patients(rows, 6, 20261003, "validation")
        self.assertNotIn(("PILOT_ONLY", "rare"), quotas)
        self.assertTrue(all(r["effective_split"] == "training" for r in result if r["pilot_member"]))

    def test_duplicate_patient_invalid_parent_and_core_pilot_rejected(self):
        rows = population()
        with self.assertRaises(ValueError):
            select_patients(rows + [rows[0]], 6, 1, "validation")
        rows[-2]["pilot_member"] = True
        with self.assertRaises(ValueError):
            select_patients(rows, 6, 1, "validation")
        rows[-2]["pilot_member"] = False
        rows[-2]["split"] = "unknown"
        with self.assertRaises(ValueError):
            select_patients(rows, 6, 1, "validation")

    def test_validation_cannot_consume_reserved_pilot(self):
        with self.assertRaises(ValueError):
            select_patients(population(), 26, 1, "validation")

    def test_all_roles_and_future_records_inherit_fold_without_changing_facts(self):
        rows, _ = select_patients(population(), 6, 1, "validation")
        assignments = {tuple(r["patient_key"]): r for r in rows}
        patient = next(r for r in rows if r["development_fold"] == "validation")
        registry = [{"candidate_id": str(i), "patient_key": patient["patient_key"], "candidate_role": role,
                     "expert_label": None, "t0_day": i, "future_outcome": "retained_only",
                     "patient_split_assignment": {"patient_split": "development"}}
                    for i, role in enumerate(["main_observed_regimen", "progression_extension", "treatment_appendix", "pending_review"])]
        before = copy.deepcopy(registry)
        result = annotate_candidates(registry, assignments, "version")
        self.assertEqual(before, registry)
        for old, new in zip(before, result):
            self.assertEqual({k: new[k] for k in old}, old)
            self.assertEqual(new["development_split_assignment"]["effective_split"], "validation")

    def test_wrong_parent_candidate_and_duplicate_candidate_fail(self):
        rows, _ = select_patients(population(), 6, 1, "validation")
        assignments = {tuple(r["patient_key"]): r for r in rows}
        c = {"candidate_id": "one", "patient_key": ["P", "0"], "candidate_role": "main_observed_regimen",
             "patient_split_assignment": {"patient_split": "core_test"}}
        with self.assertRaises(ValueError):
            annotate_candidates([c], assignments, "version")
        c["patient_split_assignment"]["patient_split"] = "development"
        with self.assertRaises(ValueError):
            annotate_candidates([c, c], assignments, "version")

    def test_later_shared_sample_between_train_validation_is_rejected(self):
        rows, _ = select_patients(population(), 6, 1, "validation")
        train = next(r for r in rows if r["development_fold"] == "training")
        validation = next(r for r in rows if r["development_fold"] == "validation")
        assignments = {tuple(r["patient_key"]): {"split": r["effective_split"]} for r in rows}
        candidates = [{"patient_key": r["patient_key"], "source_record_id": str(i),
                       "temporal_partition": {"future": [str(i)]}} for i, r in enumerate([train, validation])]
        events = {str(i): {"patient_key": r["patient_key"], "kind": "ngs_report", "facts": {"cpt_genie_sample_id": "shared"}}
                  for i, r in enumerate([train, validation])}
        with self.assertRaises(ValueError):
            check_identity_isolation(candidates, assignments, events)

    def test_conflicting_lock_fails_before_any_result_write(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = base / CONFIG
            config.parent.mkdir(parents=True)
            config.write_text("{}", encoding="utf-8")
            processed, out, report = base / "processed", base / "results", base / "report.md"
            processed.mkdir()
            locked = processed / "development_split_lock_v2.0.json"
            locked.write_text(json.dumps({"assignment": "original"}), encoding="utf-8")
            prior = locked.read_bytes()
            with patch("pdac_benchmark.v2_0.development_split.prepare", return_value=([], [], [], [], {}, {"assignment": "changed"}, {})), \
                 patch("pdac_benchmark.v2_0.development_split.paths", return_value=(processed, out, report)):
                with self.assertRaises(ValueError):
                    run(base)
            self.assertEqual(locked.read_bytes(), prior)
            self.assertEqual(list(processed.iterdir()), [locked])
            self.assertFalse(out.exists())
            self.assertFalse(report.exists())

    def test_config_does_not_allow_labels_or_pilot_in_validation(self):
        base = Path(__file__).resolve().parents[3]
        config = json.loads((base / CONFIG).read_text(encoding="utf-8"))
        validate_config(config)
        for field, value in [("outcomes_or_labels_used_for_selection", True),
                             ("pilot_policy", "validation_allowed"), ("validation_patients", 88)]:
            with self.subTest(field=field):
                changed = {**config, field: value}
                with self.assertRaises(ValueError):
                    validate_config(changed)


if __name__ == "__main__":
    unittest.main()
