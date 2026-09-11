"""Checks protect against silent loss and clinically material timing mistakes."""

import tempfile
import unittest
from pathlib import Path

from pdac_benchmark.v2_0.source import expand_specimens, number, read_csv, record_id, relative_day


class SourceTests(unittest.TestCase):
    def test_csv_retains_quotes_newlines_unknown_blank_and_zero(self):
        for newline in ["\n", "\r\n"]:
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "clinical.csv"
                content = 'id,text,unknown,missing,number\na,"line1\nline2,quoted ""word""",Unknown,,0\n'.replace("\n", newline)
                path.write_bytes(content.encode("utf-8"))
                header, rows = read_csv(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], {"id": "a", "text": 'line1'+newline+'line2,quoted "word"', "unknown": "Unknown", "missing": "", "number": "0"})

    def test_invalid_csv_cannot_silently_drop_or_shift_values(self):
        for content in ["id,id\n1,2\n", "id,value\n1,2,3\n", "id,value\n1\n"]:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.csv"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_csv(path)

    def test_multi_cancer_time_origin_is_not_reset_to_zero(self):
        self.assertEqual(relative_day("20", "1100", "1000"), 120)
        self.assertEqual(relative_day("-10", "1000", "1000"), -10)
        self.assertEqual(relative_day("0", "1000", "1000"), 0)
        self.assertIsNone(relative_day("", "1000", "1000"))
        self.assertIsNone(relative_day("20", "", "1000"))
        self.assertIsNone(number("NaN"))

    def test_negative_specimens_and_last_slot_are_preserved(self):
        row = {"path_site1": "Pancreas", "path_ca1": "No", "path_insitu1": "No",
               "path_site30": "Liver", "path_ca30": "Yes", "path_ca_type30": "Pancreatic Cancer", "path_ca_hist30": "8140 Adenocarcinoma NOS"}
        result = expand_specimens(row)
        self.assertEqual([s["specimen_number"] for s in result], [1, 30])
        self.assertEqual(result[0]["invasive"], "No")
        self.assertEqual(result[1]["source_fields"]["invasive_histology"], "path_ca_hist30")

    def test_record_ids_include_cohort_and_cancer(self):
        row = {"cohort": "PANC", "record_id": "P1", "ca_seq": "0", "regimen_number": "1"}
        original = record_id("regimen_cancer_level_dataset", row)
        self.assertEqual(original, record_id("regimen_cancer_level_dataset", dict(row)))
        self.assertNotEqual(original, record_id("regimen_cancer_level_dataset", {**row, "ca_seq": "1"}))
        self.assertNotEqual(original, record_id("regimen_cancer_level_dataset", {**row, "cohort": "OTHER"}))


if __name__ == "__main__":
    unittest.main()
