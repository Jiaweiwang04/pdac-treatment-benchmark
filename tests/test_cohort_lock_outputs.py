"""Automated checks for Round 3 cohort-lock audit outputs.

These tests only inspect aggregate public outputs. The private pilot file under
``data/processed`` is intentionally not read here because it may contain
patient-level identifiers and is ignored by git.
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"GENIE-(DFCI|MSK|UHN|VICC)-", re.IGNORECASE)


class CohortLockAuditOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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
        self.assertGreaterEqual(len(rows), 7)
        failed = [row for row in rows if row["status"] != "pass"]
        self.assertEqual(failed, [])

    def test_round2_reproduction_matches(self) -> None:
        rows = self.read_csv("reports/tables/round2_reproduction_check.csv")
        self.assertEqual({row["definition"] for row in rows}, {"A", "B", "C"})
        self.assertTrue(all(row["matches_previous"] == "True" for row in rows))

    def test_base_cohorts_are_not_endpoint_specific(self) -> None:
        summary = {row["cohort"]: int(row["n_patients"]) for row in self.read_csv("reports/tables/cohort_summary_v0.1.csv")}
        endpoints = [row for row in self.read_csv("reports/tables/endpoint_coverage.csv") if row["cohort"] == "Extended draft"]
        max_endpoint = max(int(row["evaluable_n"]) for row in endpoints)
        self.assertGreaterEqual(summary["extended_draft"], max_endpoint)
        self.assertGreater(summary["extended_draft"], 0)
        self.assertGreater(summary["core_draft"], 0)

    def test_public_outputs_do_not_contain_patient_ids(self) -> None:
        public_roots = [REPO_ROOT / "reports", REPO_ROOT / "code" / "mappings"]
        public_files = [REPO_ROOT / "cohort_definition_v0.1.yaml", REPO_ROOT / "README.md", REPO_ROOT / "README.zh-CN.md"]
        for root in public_roots:
            public_files.extend(path for path in root.rglob("*") if path.is_file())
        hits = []
        for path in public_files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if ID_PATTERN.search(text):
                hits.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()