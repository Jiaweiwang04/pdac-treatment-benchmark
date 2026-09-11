"""Preserve supplied molecular observations and panel coverage without actionability claims."""
import csv
from .source import sha256


def tsv(path):
    """Return source lines and fields, retaining empty/NA/zero values."""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        lines = list(enumerate(stream, 1))
    while lines and lines[0][1].startswith('#'):
        lines.pop(0)
    reader = csv.DictReader((line for _, line in lines), delimiter='\t')
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('Duplicate molecular column: ' + path.name)
    rows = []
    previous_line = reader.line_num
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed molecular row: ' + path.name)
        rows.append((lines[previous_line][0], row))
        previous_line = reader.line_num
    return reader.fieldnames, rows


def load_molecular(raw):
    folder = raw/'cBioPortal_files'
    samples, issues, counts = {}, [], {}
    panels = {}
    for path in sorted(folder.glob('data_gene_panel_*.txt')):
        attrs = {}
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition(':')
            if sep:
                attrs[key] = value.strip()
        panels[attrs['stable_id']] = {'genes': attrs['gene_list'].split(), 'source_file': path.relative_to(raw).as_posix(), 'sha256': sha256(path)}
    def source(path, line):
        return {'file': path.relative_to(raw).as_posix(), 'physical_line': line, 'sha256': hashes[path.name]}
    names = ['data_clinical_sample.txt', 'data_gene_matrix.txt', 'data_mutations_extended.txt', 'data_sv.txt', 'data_CNA.txt']
    hashes = {name: sha256(folder/name) for name in names}
    _, rows = tsv(folder/names[0])
    for line, row in rows:
        sid = row['SAMPLE_ID']
        if sid in samples:
            raise ValueError('Duplicate sample ID: ' + sid)
        samples[sid] = {'sample_id': sid, 'patient_id': row['PATIENT_ID'], 'metadata': row,
                        'source': source(folder/names[0], line), 'mutations': [], 'structural_variants': [],
                        'cna_values': {}, 'panel_assignments': {}, 'coverage_interpretation': 'panel_gene_membership_is_not_a_validated_negative_test'}
    counts['samples'] = len(samples)
    _, rows = tsv(folder/names[1])
    for line, row in rows:
        if row['SAMPLE_ID'] not in samples:
            issues.append({'kind': 'panel_sample_unlinked', 'sample': row['SAMPLE_ID']})
            continue
        samples[row['SAMPLE_ID']]['panel_assignments'] = {'fields': row, 'source': source(folder/names[1], line)}
    for filename, sample_field, key in [('data_mutations_extended.txt', 'Tumor_Sample_Barcode', 'mutations'), ('data_sv.txt', 'Sample_Id', 'structural_variants')]:
        _, rows = tsv(folder/filename)
        counts[key] = len(rows)
        for line, row in rows:
            sid = row[sample_field]
            if sid not in samples:
                issues.append({'kind': key + '_sample_unlinked', 'sample': sid, 'line': line})
                continue
            samples[sid][key].append({'source': source(folder/filename, line), 'fields': row})
    header, rows = tsv(folder/'data_CNA.txt')
    counts['cna_genes'] = len(rows)
    counts['cna_samples'] = len(header) - 1
    for sid in header[1:]:
        if sid not in samples:
            issues.append({'kind': 'cna_sample_unlinked', 'sample': sid})
            continue
        samples[sid]['cna_source'] = {'file': 'cBioPortal_files/data_CNA.txt', 'sample_column': sid, 'sha256': hashes['data_CNA.txt']}
        for line, row in rows:
            gene = row[header[0]]
            if gene in samples[sid]['cna_values']:
                raise ValueError('Duplicate CNA gene: ' + gene)
            samples[sid]['cna_values'][gene] = {'raw_value': row[sid], 'physical_line': line}
    counts['panel_definitions'] = len(panels)
    return samples, panels, counts, issues
