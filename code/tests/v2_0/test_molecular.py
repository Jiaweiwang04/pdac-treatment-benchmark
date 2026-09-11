import tempfile
import unittest
from pathlib import Path
from pdac_benchmark.v2_0.molecular import tsv


class MolecularTests(unittest.TestCase):
    def test_multiline_fields_and_physical_source_rows_remain_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'observations.tsv'
            path.write_bytes(b'#metadata\nsample\tvalue\tnote\na\t0\t"first\n#inside quoted field"\nb\tNA\t\n')
            header, rows = tsv(path)
        self.assertEqual(header, ['sample', 'value', 'note'])
        self.assertEqual([line for line, _ in rows], [3, 5])
        self.assertEqual(rows[0][1]['note'], 'first\n#inside quoted field')
        self.assertEqual(rows[0][1]['value'], '0')
        self.assertEqual(rows[1][1]['value'], 'NA')
        self.assertEqual(rows[1][1]['note'], '')
