"""Read the distributed XLSX variable synopsis using only the standard library."""
import re
import zipfile
import xml.etree.ElementTree as ET
from .source import sha256

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_synopsis(path):
    rows = []
    digest = sha256(path)
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            tree = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(n.itertext()) for n in tree.findall('s:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in rels}
        sheet = next(s for s in workbook.findall('s:sheets/s:sheet', NS) if s.attrib['name'] == 'Variable Synopsis')
        relation = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        location = targets[relation]
        location = location.lstrip('/') if location.startswith('/') else 'xl/' + location
        data = ET.fromstring(archive.read(location))
        for row in data.findall('s:sheetData/s:row', NS):
            values = {}
            for cell in row.findall('s:c', NS):
                col = re.sub(r'\d', '', cell.attrib['r'])
                value = cell.find('s:v', NS)
                text = value.text if value is not None else ''
                if cell.attrib.get('t') == 's':
                    text = strings[int(text)]
                elif cell.attrib.get('t') == 'inlineStr':
                    text = ''.join(cell.find('s:is', NS).itertext())
                values[col] = text
            if int(row.attrib['r']) > 1 and values.get('B'):
                rows.append({'dataset': values.get('A', ''), 'field': values['B'], 'label': values.get('C', ''),
                             'type': values.get('D', ''), 'values_raw': values.get('E', ''),
                             'source': {'file': 'Documentation/' + path.name, 'sheet': 'Variable Synopsis', 'row': int(row.attrib['r']), 'sha256': digest}})
    return rows
