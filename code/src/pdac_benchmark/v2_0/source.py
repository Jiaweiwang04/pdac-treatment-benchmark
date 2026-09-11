"""Lossless CSV reading and explicit keys/time conversion for PANC source data."""

import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

PATIENT_KEY = ("cohort", "record_id")
CANCER_KEY = (*PATIENT_KEY, "ca_seq")
KEYS = {
    "patient_level_dataset": PATIENT_KEY,
    "cancer_level_dataset_index": CANCER_KEY,
    "cancer_level_dataset_non_index": CANCER_KEY,
    "pathology_report_level_dataset": (*PATIENT_KEY, "path_proc_number", "path_rep_number"),
    "cancer_panel_test_level_dataset": (*PATIENT_KEY, "cpt_number"),
    "regimen_cancer_level_dataset": (*CANCER_KEY, "regimen_number"),
    "ca_radtx_dataset": (*CANCER_KEY, "rt_number"),
    "imaging_level_dataset": (*PATIENT_KEY, "scan_number"),
    "med_onc_note_level_dataset": (*PATIENT_KEY, "md_visit_number"),
    "tm_level_dataset": (*PATIENT_KEY, "tm_number"),
}
SPECIMEN_FIELDS = {
    "site": "path_site", "in_situ": "path_insitu",
    "in_situ_histology": "path_ca_ishist", "invasive": "path_ca",
    "cancer_type": "path_ca_type", "invasive_histology": "path_ca_hist",
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path: Path):
    """Retain exact decoded cell strings; reject malformed widths and headers."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        if len(header) != len(set(header)) or any(not x for x in header):
            raise ValueError(f"Invalid or duplicate header: {path.name}")
        rows = []
        for logical_row, values in enumerate(reader, 2):
            if len(values) != len(header):
                raise ValueError(f"CSV width mismatch: {path.name}, record {logical_row}")
            rows.append(dict(zip(header, values)))
    return header, rows


def key(row, columns):
    return tuple(row[name] for name in columns)


def record_id(table, row):
    encoded = json.dumps([table, *key(row, KEYS[table])], ensure_ascii=False, separators=(",", ":"))
    return "v2.0:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def number(value):
    """Derived numeric view; do not replace the original string field."""
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            return None
        return int(result) if result == result.to_integral_value() else float(result)
    except InvalidOperation:
        return None


def relative_day(interval, cancer_dob_day, first_index_dob_day):
    values = [number(x) for x in (interval, cancer_dob_day, first_index_dob_day)]
    return None if any(x is None for x in values) else values[0] + values[1] - values[2]


def expand_specimens(row):
    records = []
    for slot in range(1, 31):
        fields = {name: prefix + str(slot) for name, prefix in SPECIMEN_FIELDS.items()}
        values = {name: row.get(field, "") for name, field in fields.items()}
        if any(value != "" for value in values.values()):
            records.append({"specimen_number": slot, **values, "source_fields": fields})
    return records
