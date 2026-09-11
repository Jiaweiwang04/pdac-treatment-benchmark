"""Guard against destructive path configuration and cross-directory writes."""
import tempfile
import unittest
from pathlib import Path
from pdac_benchmark.v2_0.layout import resolve_paths


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = {"source_root": "data/raw/release", "processed_dir": "data/processed/v2.0/phase", "results_dir": "code/results/v2.0/phase"}

    def test_relative_paths_do_not_depend_on_working_directory(self):
        raw, processed, results = resolve_paths(self.base, self.config)
        self.assertEqual(raw, self.base / "data/raw/release")
        self.assertEqual(processed, self.base / "data/processed/v2.0/phase")
        self.assertEqual(results, self.base / "code/results/v2.0/phase")

    def test_raw_overwrite_and_mixed_outputs_are_rejected_before_writing(self):
        for field, path in [("processed_dir", "data/raw/release"), ("results_dir", "data/raw/release/results"), ("results_dir", "data/processed/v2.0/phase")]:
            with self.subTest(field=field, path=path), self.assertRaises(ValueError):
                resolve_paths(self.base, {**self.config, field: path})
        self.assertEqual(list(self.base.iterdir()), [])

    def test_traversal_and_version_root_targets_are_rejected(self):
        for field, path in [("results_dir", "code/results/v2.0/../../../../elsewhere"), ("processed_dir", "data/processed/v2.0"), ("source_root", str(self.base.parent / "outside_raw"))]:
            with self.subTest(field=field, path=path), self.assertRaises(ValueError):
                resolve_paths(self.base, {**self.config, field: path})
