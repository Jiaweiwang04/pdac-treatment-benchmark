"""Read-only audit for the AACR GENIE BPC PANC raw data package.

The script writes only derived audit outputs under docs/notes, code/results, and code/notebooks.
It does not modify, clean, model, or resave any file under data/raw.
Patient-level records and raw cell values are not printed or written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import privacy_checks as privacy


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PANC_RELATIVE_ROOT = Path(
    "data/raw/AACR GENIE Biopharma Collaborative Public/"
    "Data Releases/PANC/1.0-public"
)
SMALL_COUNT_THRESHOLD = privacy.SMALL_COUNT_THRESHOLD
TEXT_EXTENSIONS = {".csv", ".txt", ".seg"}
XLSX_EXTENSIONS = {".xlsx"}
PDF_EXTENSIONS = {".pdf"}
MISSING_TOKENS = {
    "",
    "NA",
    "N/A",
    "NULL",
    "NONE",
    "NAN",
    "[NOT AVAILABLE]",
    "[NOT APPLICABLE]",
    "NOT AVAILABLE",
    "NOT APPLICABLE",
}
LEAKAGE_TERMS = (
    "death",
    "deceased",
    "survival",
    "os_",
    "pfs",
    "progress",
    "response",
    "last_alive",
    "last_fu",
    "last_onc",
    "end",
    "post_death",
    "post_last_alive",
)
DATE_TERMS = (
    "date",
    "days",
    "mos",
    "yrs",
    "_int",
    "start",
    "end",
    "dx_",
    "report",
    "collect",
)
STRUCTURAL_WIDE_FIELDS = {
    "hugo_symbol",
    "entrez_gene_id",
    "gene",
    "gene_id",
    "sample_id",
    "patient_id",
}


@dataclass
class FieldStats:
    table_path: str
    field_name: str
    public_field_name: str
    is_redacted_dynamic_field: bool = False
    row_count: int = 0
    missing_count: int = 0
    non_missing_count: int = 0
    unique_values: set[str] = field(default_factory=set)
    type_votes: Counter[str] = field(default_factory=Counter)
    max_value_length: int = 0
    dictionary_label: str = "待确认"
    dictionary_source: str = ""
    data_role_hint: str = ""
    date_field_hint: str = ""
    leakage_risk_hint: str = ""

    @property
    def unique_count(self) -> int:
        return len(self.unique_values)

    @property
    def missing_rate(self) -> float:
        if self.row_count == 0:
            return 0.0
        return self.missing_count / self.row_count

    @property
    def inferred_type(self) -> str:
        if not self.type_votes:
            return "empty_or_unknown"
        priority = ["string", "float", "integer", "date_like", "boolean"]
        if len(self.type_votes) == 1:
            return next(iter(self.type_votes.keys()))
        if set(self.type_votes).issubset({"integer", "float"}):
            return "float"
        for typ in priority:
            if typ in self.type_votes:
                return "mixed_" + typ
        return "mixed"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[:65536]
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "gbk"):
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "binary_or_unknown"


def read_text_lines(path: Path, encoding: str) -> list[str]:
    if encoding == "binary_or_unknown":
        return []
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        return f.readlines()


def delimiter_label(delimiter: str | None) -> str:
    return {
        "\t": "tab",
        ",": "comma",
        ";": "semicolon",
        "|": "pipe",
        ":": "colon",
        None: "",
    }.get(delimiter, delimiter or "")


def detect_delimiter(lines: list[str], extension: str) -> str | None:
    if extension == ".csv":
        return ","
    candidates = ["\t", ",", ";", "|", ":"]
    usable = [
        line.strip("\r\n")
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ][:30]
    if not usable:
        return None
    scores: list[tuple[float, str]] = []
    for delim in candidates:
        counts = [len(line.split(delim)) for line in usable if delim in line]
        if not counts:
            continue
        consistency = counts.count(max(set(counts), key=counts.count)) / len(usable)
        mean_cols = sum(counts) / len(counts)
        scores.append((consistency * mean_cols, delim))
    if not scores:
        return None
    return max(scores)[1]


def is_key_value_metadata_file(path: Path) -> bool:
    low_name = path.name.lower()
    low_path = path.as_posix().lower()
    return (
        "/case_lists/" in low_path
        or low_name.startswith("meta_")
        or low_name.startswith("data_gene_panel_")
    )


def split_row(line: str, delimiter: str) -> list[str]:
    return next(csv.reader([line], delimiter=delimiter))


def is_missing(value: str) -> bool:
    return value.strip().upper() in MISSING_TOKENS


def infer_value_type(value: str) -> str:
    v = value.strip()
    if re.fullmatch(r"(?i:true|false|yes|no|y|n|0|1)", v):
        return "boolean"
    if re.fullmatch(r"[+-]?\d+", v):
        return "integer"
    if re.fullmatch(r"[+-]?(\d+\.\d*|\d*\.\d+)([eE][+-]?\d+)?", v):
        return "float"
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", v):
        return "date_like"
    return "string"


def topic_from_path(rel: str) -> str:
    low = rel.lower()
    if "documentation" in low or "数据手册" in low or "variable-synopsis" in low:
        return "documentation_or_data_dictionary"
    if "meta_" in low or "manifest" in low or "case_lists" in low:
        return "metadata_or_case_list"
    if "patient" in low:
        return "patient"
    if "sample" in low or "cpt_" in low or "cancer_panel_test" in low:
        return "sample_or_ngs_test"
    if "cancer_level" in low or "diagnosis" in low:
        return "diagnosis_or_cancer"
    if "regimen" in low or "treatment" in low or "medonc" in low or "radtx" in low:
        return "treatment"
    if "mutation" in low or "cna" in low or "sv" in low or "gene" in low or "genomic" in low:
        return "genomic"
    if "survival" in low or "imaging" in low or "labtest" in low or "tm_level" in low:
        return "outcome_or_followup"
    return "待确认"


def role_for_field(field_name: str) -> str:
    low = field_name.lower()
    if low in {"record_id", "patient_id"} or "patient" in low:
        return "patient_key_or_patient_level"
    if "sample" in low or "cpt_genie_sample_id" in low:
        return "sample_or_ngs_key"
    if "gene" in low or "hugo" in low or "entrez" in low or "variant" in low:
        return "genomic"
    if "regimen" in low or "drug" in low or low.startswith("rt_"):
        return "treatment"
    if "hist" in low or "stage" in low or "mets" in low or "resect" in low or low.startswith("ca_"):
        return "diagnosis_or_disease_status"
    if any(term in low for term in ("death", "os_", "pfs", "survival", "response", "last_alive")):
        return "outcome"
    if any(term in low for term in DATE_TERMS):
        return "date_or_relative_time"
    if "institution" in low or "cohort" in low or "release" in low:
        return "source_or_version"
    return "待确认"


def leakage_hint(field_name: str) -> str:
    low = field_name.lower()
    if any(term in low for term in LEAKAGE_TERMS):
        return "potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned"
    if "report_post" in low or "post_" in low:
        return "potential post-event indicator; inspect for leakage"
    return ""


def date_hint(field_name: str) -> str:
    low = field_name.lower()
    if any(term in low for term in DATE_TERMS):
        return "relative_date_or_event_interval; confirm event meaning in data dictionary"
    return ""


def is_wide_dynamic_column(path: Path, index: int, name: str, header_len: int) -> bool:
    low_file = path.name.lower()
    low_name = name.lower()
    if low_name in STRUCTURAL_WIDE_FIELDS:
        return False
    if privacy.contains_identifier(name):
        return True
    if low_file in {"data_cna.txt", "data_gene_matrix.txt"} and index >= 1:
        return True
    if header_len > 200 and index >= 1:
        if re.search(r"\d", name) and re.search(r"[-_.]", name):
            return True
    return False


def public_header(path: Path, header: list[str]) -> tuple[list[str], list[int]]:
    dynamic_indices = [
        idx
        for idx, name in enumerate(header)
        if is_wide_dynamic_column(path, idx, name, len(header))
    ]
    if not dynamic_indices:
        return [privacy.safe_public_field_name(name) for name in header], []
    public: list[str] = []
    inserted = False
    for idx, name in enumerate(header):
        if idx in dynamic_indices:
            if not inserted:
                public.append(f"<redacted_dynamic_sample_columns:{len(dynamic_indices)}>")
                inserted = True
            continue
        public.append(privacy.safe_public_field_name(name))
    return public, dynamic_indices


def update_field_stat(stat: FieldStats, value: str) -> None:
    stat.row_count += 1
    v = value.strip()
    stat.max_value_length = max(stat.max_value_length, len(v))
    if is_missing(v):
        stat.missing_count += 1
        return
    stat.non_missing_count += 1
    stat.unique_values.add(v)
    if len(stat.unique_values) > 100000:
        stat.unique_values = set(list(stat.unique_values)[:100000])
    stat.type_votes[infer_value_type(v)] += 1


def analyze_delimited(path: Path, repo_root: Path, data_dict: dict[str, dict[str, str]]) -> tuple[dict[str, Any], list[FieldStats], dict[str, Any]]:
    extension = path.suffix.lower()
    encoding = detect_encoding(path)
    lines = read_text_lines(path, encoding)
    rel = relpath(path, repo_root)
    force_key_value = is_key_value_metadata_file(path)
    delimiter = ":" if force_key_value else detect_delimiter(lines, extension)
    line_count = len(lines)
    notes: list[str] = []

    if delimiter is None:
        return (
            {
                "relative_path": rel,
                "file_name": path.name,
                "extension": extension,
                "format": "plain_text_or_unknown",
                "size_bytes": path.stat().st_size,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 4),
                "sha256": sha256_file(path),
                "encoding": encoding,
                "delimiter": "",
                "line_count": line_count,
                "data_row_count": "",
                "column_count": "",
                "field_names": "",
                "field_names_redacted": "false",
                "table_theme": topic_from_path(rel),
                "notes": "No reliable table delimiter detected; not parsed as tabular data.",
            },
            [],
            {"row_count": 0, "column_count": 0, "duplicate_rows": 0},
        )

    header: list[str] | None = None
    header_idx = -1
    generated_header = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if delimiter == ":" and stripped.count(":") >= 1 and (force_key_value or len(stripped.split(":")) <= 3):
            header = ["key", "value"]
            header_idx = idx - 1
            generated_header = True
            break
        row = split_row(line, delimiter)
        if len(row) > 1:
            header = [c.strip() for c in row]
            header_idx = idx
            break
    if header is None:
        notes.append("No header row detected.")
        header = []

    public_names, dynamic_indices = public_header(path, header)
    field_stats: list[FieldStats] = []
    raw_to_stat: dict[int, FieldStats] = {}
    for idx, field_name in enumerate(header):
        if idx in dynamic_indices:
            continue
        public_name = privacy.safe_public_field_name(field_name)
        dd = data_dict.get(field_name.lower(), {})
        stat = FieldStats(
            table_path=rel,
            field_name=public_name,
            public_field_name=public_name,
            dictionary_label=dd.get("label", "待确认"),
            dictionary_source=dd.get("source", ""),
            data_role_hint=role_for_field(field_name),
            date_field_hint=date_hint(field_name),
            leakage_risk_hint=leakage_hint(field_name),
        )
        field_stats.append(stat)
        raw_to_stat[idx] = stat
    if dynamic_indices:
        aggregate = FieldStats(
            table_path=rel,
            field_name="<redacted>",
            public_field_name=f"<redacted_dynamic_sample_columns:{len(dynamic_indices)}>",
            is_redacted_dynamic_field=True,
            data_role_hint="sample_level_dynamic_matrix_columns",
            dictionary_label="suppressed_to_avoid_sample_or_patient_identifier_disclosure",
        )
        field_stats.append(aggregate)
        notes.append(f"{len(dynamic_indices)} dynamic wide-matrix columns redacted.")

    row_count = 0
    duplicate_rows = 0
    row_hashes: set[str] = set()
    bad_width_rows = 0
    start_idx = max(header_idx + 1, 0)
    if generated_header:
        start_idx = max(header_idx + 1, 0)

    for idx, line in enumerate(lines[start_idx:], start=start_idx):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row = split_row(line, delimiter)
        except csv.Error:
            bad_width_rows += 1
            continue
        if generated_header:
            parts = stripped.split(":", 1)
            row = [parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""]
        if len(row) != len(header):
            bad_width_rows += 1
        row_count += 1
        row_hash = hashlib.sha256("\x1f".join(row).encode("utf-8", errors="replace")).hexdigest()
        if row_hash in row_hashes:
            duplicate_rows += 1
        else:
            row_hashes.add(row_hash)
        for col_idx, stat in raw_to_stat.items():
            value = row[col_idx] if col_idx < len(row) else ""
            update_field_stat(stat, value)
        for stat in field_stats:
            if stat.is_redacted_dynamic_field:
                stat.row_count = row_count

    if bad_width_rows:
        notes.append(f"{bad_width_rows} rows had a column count different from the header.")
    if generated_header:
        notes.append("Parsed as key-value text; values are not reported.")
    if force_key_value:
        notes.append("Forced key-value metadata parsing to avoid treating ID lists as field names.")

    return (
        {
            "relative_path": rel,
            "file_name": path.name,
            "extension": extension,
            "format": "delimited_text",
            "size_bytes": path.stat().st_size,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 4),
            "sha256": sha256_file(path),
            "encoding": encoding,
            "delimiter": delimiter_label(delimiter),
            "line_count": line_count,
            "data_row_count": row_count,
            "column_count": len(header),
            "field_names": "|".join(public_names),
            "field_names_redacted": "true" if dynamic_indices else "false",
            "table_theme": topic_from_path(rel),
            "notes": " ".join(notes),
        },
        field_stats,
        {
            "row_count": row_count,
            "column_count": len(header),
            "duplicate_rows": duplicate_rows,
            "header": header,
            "public_header": public_names,
        },
    )


def xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for si in root.findall("a:si", ns):
        parts = [t.text or "" for t in si.findall(".//a:t", ns)]
        strings.append("".join(parts))
    return strings


def xlsx_sheet_paths(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    ns_main = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ns_rel = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("r:Relationship", ns_rel)}
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall(".//a:sheet", ns_main):
        name = sheet.attrib.get("name", "sheet")
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_map.get(rid or "", "")
        if target:
            sheets.append((name, "xl/" + target.lstrip("/")))
    return sheets


def xlsx_cell_value(cell: ET.Element, shared: list[str], ns: dict[str, str]) -> str:
    typ = cell.attrib.get("t")
    if typ == "s":
        v = cell.find("a:v", ns)
        if v is None or v.text is None:
            return ""
        idx = int(v.text)
        return shared[idx] if idx < len(shared) else ""
    if typ == "inlineStr":
        parts = [t.text or "" for t in cell.findall(".//a:t", ns)]
        return "".join(parts)
    v = cell.find("a:v", ns)
    return v.text if v is not None and v.text is not None else ""


def read_xlsx_rows(path: Path) -> dict[str, list[list[str]]]:
    rows_by_sheet: dict[str, list[list[str]]] = {}
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as zf:
        shared = xlsx_shared_strings(zf)
        for sheet_name, sheet_path in xlsx_sheet_paths(zf):
            try:
                root = ET.fromstring(zf.read(sheet_path))
            except KeyError:
                continue
            rows: list[list[str]] = []
            for row in root.findall(".//a:sheetData/a:row", ns):
                values: list[str] = []
                for cell in row.findall("a:c", ns):
                    ref = cell.attrib.get("r", "")
                    col_letters = re.sub(r"\d", "", ref)
                    col_idx = 0
                    for ch in col_letters:
                        col_idx = col_idx * 26 + (ord(ch.upper()) - ord("A") + 1)
                    col_idx -= 1
                    while len(values) < col_idx:
                        values.append("")
                    values.append(xlsx_cell_value(cell, shared, ns))
                rows.append(values)
            rows_by_sheet[sheet_name] = rows
    return rows_by_sheet


def analyze_xlsx(path: Path, repo_root: Path, data_dict: dict[str, dict[str, str]]) -> tuple[dict[str, Any], list[FieldStats], dict[str, Any]]:
    rel = relpath(path, repo_root)
    rows_by_sheet = read_xlsx_rows(path)
    field_stats: list[FieldStats] = []
    sheet_summaries: list[str] = []
    first_header: list[str] = []
    max_cols = 0
    total_rows = 0
    for sheet_name, rows in rows_by_sheet.items():
        if not rows:
            continue
        total_rows += max(len(rows) - 1, 0)
        max_cols = max(max_cols, max((len(r) for r in rows), default=0))
        header_idx = 0
        header = [str(c).strip() for c in rows[header_idx]]
        if not first_header:
            first_header = [privacy.safe_public_field_name(name) for name in header]
        sheet_summaries.append(f"{sheet_name}:rows={max(len(rows)-1,0)},cols={len(header)}")
        for col_idx, field_name in enumerate(header):
            if not field_name:
                continue
            public_name = privacy.safe_public_field_name(field_name)
            dd = data_dict.get(field_name.lower(), {})
            stat = FieldStats(
                table_path=f"{rel}::{sheet_name}",
                field_name=public_name,
                public_field_name=public_name,
                dictionary_label=dd.get("label", "待确认"),
                dictionary_source=dd.get("source", ""),
                data_role_hint=role_for_field(field_name),
                date_field_hint=date_hint(field_name),
                leakage_risk_hint=leakage_hint(field_name),
            )
            for row in rows[1:]:
                update_field_stat(stat, row[col_idx] if col_idx < len(row) else "")
            field_stats.append(stat)
    return (
        {
            "relative_path": rel,
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "format": "xlsx_workbook",
            "size_bytes": path.stat().st_size,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 4),
            "sha256": sha256_file(path),
            "encoding": "",
            "delimiter": "",
            "line_count": "",
            "data_row_count": total_rows,
            "column_count": max_cols,
            "field_names": "|".join(first_header),
            "field_names_redacted": "false",
            "table_theme": topic_from_path(rel),
            "notes": "; ".join(sheet_summaries),
        },
        field_stats,
        {"row_count": total_rows, "column_count": max_cols, "duplicate_rows": ""},
    )


def analyze_binary_or_pdf(path: Path, repo_root: Path) -> tuple[dict[str, Any], list[FieldStats], dict[str, Any]]:
    rel = relpath(path, repo_root)
    return (
        {
            "relative_path": rel,
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "format": "pdf_or_binary_document" if path.suffix.lower() == ".pdf" else "binary_or_unknown",
            "size_bytes": path.stat().st_size,
            "size_mb": round(path.stat().st_size / (1024 * 1024), 4),
            "sha256": sha256_file(path),
            "encoding": "",
            "delimiter": "",
            "line_count": "",
            "data_row_count": "",
            "column_count": "",
            "field_names": "",
            "field_names_redacted": "false",
            "table_theme": topic_from_path(rel),
            "notes": "Content not parsed; no PDF parser was assumed or required.",
        },
        [],
        {"row_count": "", "column_count": "", "duplicate_rows": ""},
    )


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", "", xml)
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("\xa0", " ")
    )


def load_variable_dictionary(raw_root: Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    xlsx_files = sorted(raw_root.glob("**/*Variable*Synopsis*.xlsx")) + sorted(raw_root.glob("**/*变量*.xlsx"))
    for path in xlsx_files:
        try:
            rows_by_sheet = read_xlsx_rows(path)
        except Exception:
            continue
        for sheet_name, rows in rows_by_sheet.items():
            for idx, row in enumerate(rows[:20]):
                lower = [str(c).strip().lower().replace(" ", "_") for c in row]
                var_candidates = [
                    i
                    for i, c in enumerate(lower)
                    if c in {"variable", "variable_name", "field", "field_name", "column", "column_name", "name"}
                    or ("variable" in c and "name" in c)
                ]
                label_candidates = [
                    i
                    for i, c in enumerate(lower)
                    if any(term in c for term in ("label", "description", "definition", "meaning", "synopsis"))
                ]
                if not var_candidates:
                    continue
                var_idx = var_candidates[0]
                label_idx = label_candidates[0] if label_candidates else None
                for data_row in rows[idx + 1 :]:
                    if var_idx >= len(data_row):
                        continue
                    var = str(data_row[var_idx]).strip()
                    if not var:
                        continue
                    label = ""
                    if label_idx is not None and label_idx < len(data_row):
                        label = str(data_row[label_idx]).strip()
                    mapping[var.lower()] = {
                        "label": label or "dictionary_row_found_no_label_column",
                        "source": relpath(path, raw_root.parents[5] if len(raw_root.parents) > 5 else raw_root)
                        + f"::{sheet_name}",
                    }
                break
    return mapping


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: privacy.public_cell(name, row.get(name, ""), row) for name in fieldnames})


def candidate_key_and_relationships(
    field_stats: list[FieldStats],
    table_meta: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    by_table: dict[str, list[FieldStats]] = defaultdict(list)
    for stat in field_stats:
        if not stat.is_redacted_dynamic_field:
            by_table[stat.table_path].append(stat)

    pk_by_table: dict[str, list[str]] = defaultdict(list)
    relationships: list[dict[str, Any]] = []
    unique_field_values: dict[tuple[str, str], set[str]] = {}
    for table, stats in by_table.items():
        row_count = table_meta.get(table, {}).get("row_count", 0) or 0
        for stat in stats:
            unique_field_values[(table, stat.public_field_name)] = stat.unique_values
            if row_count and stat.missing_count == 0 and stat.unique_count == row_count:
                low = stat.public_field_name.lower()
                if any(term in low for term in ("id", "number", "seq", "sample", "barcode")):
                    pk_by_table[table].append(stat.public_field_name)
                    relationships.append(
                        {
                            "source_table": table,
                            "source_field": stat.public_field_name,
                            "target_table": table,
                            "target_field": stat.public_field_name,
                            "relationship_type": "candidate_primary_key",
                            "evidence": f"unique_count equals row_count ({row_count}) and no missing values",
                            "caution": "Heuristic only; confirm against data dictionary.",
                        }
                    )

        id_like = [
            s
            for s in stats
            if any(term in s.public_field_name.lower() for term in ("record_id", "sample_id", "number", "seq"))
        ][:8]
        for left, right in combinations(id_like, 2):
            row_count = table_meta.get(table, {}).get("row_count", 0) or 0
            if not row_count:
                continue
            # Composite uniqueness is approximated by min(unique counts) and name patterns
            # to avoid storing patient-level ID tuples in outputs.
            if max(left.unique_count, right.unique_count) >= row_count and "record_id" in {
                left.public_field_name.lower(),
                right.public_field_name.lower(),
            }:
                relationships.append(
                    {
                        "source_table": table,
                        "source_field": f"{left.public_field_name}+{right.public_field_name}",
                        "target_table": table,
                        "target_field": f"{left.public_field_name}+{right.public_field_name}",
                        "relationship_type": "possible_composite_key",
                        "evidence": "ID-like fields; composite uniqueness requires formal confirmation.",
                        "caution": "No patient-level tuples are written by this audit.",
                    }
                )

    patient_tables = [
        table
        for table, pks in pk_by_table.items()
        if "patient_level_dataset.csv" in table and "record_id" in [p.lower() for p in pks]
    ]
    for (src_table, src_field), src_values in unique_field_values.items():
        if not src_values:
            continue
        low = src_field.lower()
        if low == "record_id" and patient_tables and src_table not in patient_tables:
            target = patient_tables[0]
            target_values = unique_field_values.get((target, "record_id"), set())
            if target_values:
                overlap = len(src_values & target_values)
                relationships.append(
                    {
                        "source_table": src_table,
                        "source_field": src_field,
                        "target_table": target,
                        "target_field": "record_id",
                        "relationship_type": "candidate_foreign_key",
                        "evidence": f"{overlap}/{len(src_values)} distinct values overlap patient table record_id",
                        "caution": "Heuristic only; do not join until confirmed by data guide/dictionary.",
                    }
                )
        if low in {"patient_id", "sample_id", "tumor_sample_barcode", "cpt_genie_sample_id"}:
            for (target_table, target_field), target_values in unique_field_values.items():
                if (target_table, target_field) == (src_table, src_field):
                    continue
                if target_field.lower() in {"patient_id", "sample_id", "tumor_sample_barcode", "cpt_genie_sample_id"}:
                    overlap = len(src_values & target_values)
                    if overlap:
                        relationships.append(
                            {
                                "source_table": src_table,
                                "source_field": src_field,
                                "target_table": target_table,
                                "target_field": target_field,
                                "relationship_type": "shared_identifier_candidate",
                                "evidence": f"{overlap} overlapping distinct non-missing values",
                                "caution": "Shared identifiers require dictionary confirmation before joins.",
                            }
                        )
    return relationships, pk_by_table


def parse_float(value: str) -> float | None:
    v = value.strip()
    if is_missing(v):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def iter_dict_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return reader.fieldnames or [], rows


def add_metric(rows: list[dict[str, Any]], metric: str, value: Any, source: str, caution: str = "") -> None:
    rows.append(
        {
            "metric": metric,
            "value": value,
            "source": source,
            "evidence_scope": "aggregate_only_no_patient_level_values",
            "caution": caution,
        }
    )


def categorical_summary(
    rows: list[dict[str, Any]],
    table: str,
    field_name: str,
    counter: Counter[str],
    threshold: int = SMALL_COUNT_THRESHOLD,
) -> None:
    suppressed = 0
    for value, count in counter.most_common():
        if count < threshold:
            suppressed += count
            continue
        rows.append(
            {
                "table_path": table,
                "field_name": field_name,
                "value_public": value if value else "<missing>",
                "count": count,
                "suppressed_small_count": 0,
                "privacy_note": "categories with count below threshold are suppressed",
            }
        )
    if suppressed:
        rows.append(
            {
                "table_path": table,
                "field_name": field_name,
                "value_public": "<suppressed_small_count_categories>",
                "count": "",
                "suppressed_small_count": suppressed,
                "privacy_note": f"threshold={threshold}",
            }
        )


def feasibility_audit(repo_root: Path, raw_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    clinical_root = raw_root / "clinical_data"
    cbio_root = raw_root / "cBioPortal_files"

    patient_file = clinical_root / "patient_level_dataset.csv"
    cancer_index_file = clinical_root / "cancer_level_dataset_index.csv"
    cancer_non_index_file = clinical_root / "cancer_level_dataset_non_index.csv"
    cpt_file = clinical_root / "cancer_panel_test_level_dataset.csv"
    regimen_file = clinical_root / "regimen_cancer_level_dataset.csv"
    sample_file = cbio_root / "data_clinical_sample.txt"

    patient_ids: set[str] = set()
    if patient_file.exists():
        _, patient_rows = iter_dict_rows(patient_file)
        patient_ids = {r.get("record_id", "").strip() for r in patient_rows if r.get("record_id", "").strip()}
        add_metric(metrics, "unique_patients_patient_level", len(patient_ids), relpath(patient_file, repo_root))
        categorical_summary(
            categories,
            relpath(patient_file, repo_root),
            "institution",
            Counter(r.get("institution", "").strip() for r in patient_rows),
        )
        for field in ("hybrid_death_int", "age_death_yrs", "last_alive_int", "age_last_fu_yrs"):
            if field in (patient_rows[0].keys() if patient_rows else []):
                available = sum(1 for r in patient_rows if not is_missing(r.get(field, "")))
                add_metric(metrics, f"coverage_{field}", available, relpath(patient_file, repo_root))

    cancer_rows: list[dict[str, str]] = []
    if cancer_index_file.exists():
        _, cancer_rows = iter_dict_rows(cancer_index_file)
        add_metric(metrics, "index_cancer_rows", len(cancer_rows), relpath(cancer_index_file, repo_root))
        add_metric(
            metrics,
            "unique_patients_with_index_cancer_row",
            len({r.get("record_id", "").strip() for r in cancer_rows if r.get("record_id", "").strip()}),
            relpath(cancer_index_file, repo_root),
        )
        for field in ("ca_histology", "stage_dx", "stage_dx_iv", "ca_dmets_yn", "ca_resect_status", "summary_stage"):
            if cancer_rows and field in cancer_rows[0]:
                categorical_summary(
                    categories,
                    relpath(cancer_index_file, repo_root),
                    field,
                    Counter(r.get(field, "").strip() for r in cancer_rows),
                )
                available = sum(1 for r in cancer_rows if not is_missing(r.get(field, "")))
                add_metric(metrics, f"coverage_{field}", available, relpath(cancer_index_file, repo_root))

    if cancer_non_index_file.exists():
        _, non_rows = iter_dict_rows(cancer_non_index_file)
        add_metric(metrics, "non_index_cancer_rows", len(non_rows), relpath(cancer_non_index_file, repo_root))

    cpt_rows: list[dict[str, str]] = []
    if cpt_file.exists():
        _, cpt_rows = iter_dict_rows(cpt_file)
        cpt_patients = {r.get("record_id", "").strip() for r in cpt_rows if r.get("record_id", "").strip()}
        cpt_samples = {
            r.get("cpt_genie_sample_id", "").strip()
            for r in cpt_rows
            if r.get("cpt_genie_sample_id", "").strip()
        }
        add_metric(metrics, "ngs_test_rows", len(cpt_rows), relpath(cpt_file, repo_root))
        add_metric(metrics, "unique_patients_with_ngs_test", len(cpt_patients), relpath(cpt_file, repo_root))
        add_metric(metrics, "unique_ngs_samples_cpt_genie_sample_id", len(cpt_samples), relpath(cpt_file, repo_root))
        multi = Counter(r.get("record_id", "").strip() for r in cpt_rows if r.get("record_id", "").strip())
        add_metric(metrics, "patients_with_multiple_ngs_tests", sum(1 for c in multi.values() if c > 1), relpath(cpt_file, repo_root))
        for field in ("dx_cpt_rep_days", "cpt_seq_date", "cpt_genie_sample_id", "sample_type", "cpt_seq_assay_id"):
            if cpt_rows and field in cpt_rows[0]:
                available = sum(1 for r in cpt_rows if not is_missing(r.get(field, "")))
                add_metric(metrics, f"coverage_{field}", available, relpath(cpt_file, repo_root))
        if cpt_rows and "institution" in cpt_rows[0]:
            categorical_summary(categories, relpath(cpt_file, repo_root), "institution", Counter(r.get("institution", "").strip() for r in cpt_rows))

    regimen_rows: list[dict[str, str]] = []
    if regimen_file.exists():
        _, regimen_rows = iter_dict_rows(regimen_file)
        regimen_patients = {
            r.get("record_id", "").strip()
            for r in regimen_rows
            if r.get("record_id", "").strip()
        }
        add_metric(metrics, "treatment_regimen_rows", len(regimen_rows), relpath(regimen_file, repo_root))
        add_metric(metrics, "unique_patients_with_treatment_regimen", len(regimen_patients), relpath(regimen_file, repo_root))
        multi = Counter(r.get("record_id", "").strip() for r in regimen_rows if r.get("record_id", "").strip())
        add_metric(metrics, "patients_with_multiple_regimens", sum(1 for c in multi.values() if c > 1), relpath(regimen_file, repo_root))
        for field in ("regimen_drugs", "dx_reg_start_int", "dx_reg_end_any_int", "regimen_number_within_cancer", "pfs_i_g_status", "os_g_status"):
            if regimen_rows and field in regimen_rows[0]:
                available = sum(1 for r in regimen_rows if not is_missing(r.get(field, "")))
                add_metric(metrics, f"coverage_{field}", available, relpath(regimen_file, repo_root))
        if cpt_rows:
            cpt_patients = {r.get("record_id", "").strip() for r in cpt_rows if r.get("record_id", "").strip()}
            add_metric(
                metrics,
                "unique_patients_with_both_ngs_and_treatment",
                len(cpt_patients & regimen_patients),
                f"{relpath(cpt_file, repo_root)} + {relpath(regimen_file, repo_root)}",
                "This is an aggregate intersection only; not a cohort definition.",
            )
            earliest_cpt: dict[str, float] = {}
            for r in cpt_rows:
                rid = r.get("record_id", "").strip()
                val = parse_float(r.get("dx_cpt_rep_days", ""))
                if rid and val is not None:
                    earliest_cpt[rid] = min(earliest_cpt.get(rid, math.inf), val)
            earliest_reg: dict[str, float] = {}
            for r in regimen_rows:
                rid = r.get("record_id", "").strip()
                val = parse_float(r.get("dx_reg_start_int", ""))
                if rid and val is not None:
                    earliest_reg[rid] = min(earliest_reg.get(rid, math.inf), val)
            both_timed = set(earliest_cpt) & set(earliest_reg)
            add_metric(metrics, "patients_with_ngs_and_regimen_timing", len(both_timed), f"{relpath(cpt_file, repo_root)} + {relpath(regimen_file, repo_root)}")
            add_metric(metrics, "patients_ngs_report_on_or_before_earliest_regimen", sum(1 for rid in both_timed if earliest_cpt[rid] <= earliest_reg[rid]), "aggregate_timing_check")
            add_metric(metrics, "patients_ngs_report_after_earliest_regimen", sum(1 for rid in both_timed if earliest_cpt[rid] > earliest_reg[rid]), "aggregate_timing_check", "Important for treatment-decision time leakage.")

    if sample_file.exists():
        sample_fields, sample_rows = read_cbio_table(sample_file)
        sample_ids = {r.get("SAMPLE_ID", "").strip() for r in sample_rows if r.get("SAMPLE_ID", "").strip()}
        sample_patients = {r.get("PATIENT_ID", "").strip() for r in sample_rows if r.get("PATIENT_ID", "").strip()}
        add_metric(metrics, "cbio_unique_samples", len(sample_ids), relpath(sample_file, repo_root))
        add_metric(metrics, "cbio_unique_patients_with_samples", len(sample_patients), relpath(sample_file, repo_root))
        multi = Counter(r.get("PATIENT_ID", "").strip() for r in sample_rows if r.get("PATIENT_ID", "").strip())
        add_metric(metrics, "patients_with_multiple_cbio_samples", sum(1 for c in multi.values() if c > 1), relpath(sample_file, repo_root))
        _ = sample_fields

    return metrics, categories


def read_cbio_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    encoding = detect_encoding(path)
    rows: list[list[str]] = []
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            rows.append(split_row(line.rstrip("\r\n"), "\t"))
    if not rows:
        return [], []
    header = rows[0]
    records = [dict(zip(header, row)) for row in rows[1:]]
    return header, records


def table_rows_for_report(path: Path, max_rows: int = 12) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [row for _, row in zip(range(max_rows), reader)]


def write_markdown_report(
    repo_root: Path,
    raw_root: Path,
    report_path: Path,
    file_rows: list[dict[str, Any]],
    field_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
    feasibility_rows: list[dict[str, Any]],
    categorical_rows: list[dict[str, Any]],
    document_notes: dict[str, str],
) -> None:
    format_counts = Counter(row["extension"] or row["format"] for row in file_rows)
    total_size = sum(int(row["size_bytes"]) for row in file_rows)
    metrics = {row["metric"]: row["value"] for row in feasibility_rows}
    key_missing = sorted(
        [
            row
            for row in field_rows
            if row["public_field_name"].lower()
            in {
                "record_id",
                "institution",
                "ca_histology",
                "stage_dx_iv",
                "ca_dmets_yn",
                "ca_resect_status",
                "cpt_genie_sample_id",
                "dx_cpt_rep_days",
                "regimen_drugs",
                "dx_reg_start_int",
            }
        ],
        key=lambda r: (r["table_path"], r["public_field_name"]),
    )
    leakage_fields = [row for row in field_rows if row["leakage_risk_hint"]][:30]

    def metric(name: str, default: str = "未统计") -> Any:
        return metrics.get(name, default)

    lines: list[str] = []
    lines.append("# BPC PANC 原始数据可行性审计 v1")
    lines.append("")
    lines.append("- Generated: deterministic raw data audit rebuild; no wall-clock timestamp")
    lines.append(f"- 仓库根目录：`{repo_root}`")
    lines.append(f"- 原始数据目录：`{raw_root.relative_to(repo_root).as_posix()}`")
    lines.append("- 审计边界：只读扫描 PANC 1.0-public；不清洗、不建模、不输出患者级记录。")
    lines.append("")
    lines.append("## 1. 数据包概况")
    lines.append("")
    lines.append(f"- 文件数：{len(file_rows)}")
    lines.append(f"- 总大小：{round(total_size / (1024 * 1024), 3)} MB")
    lines.append("- 文件格式计数：" + ", ".join(f"{k}={v}" for k, v in sorted(format_counts.items())))
    lines.append(f"- 聚合唯一患者数（patient_level_dataset.record_id）：{metric('unique_patients_patient_level')}")
    lines.append(f"- 聚合唯一 NGS 样本数（cpt_genie_sample_id）：{metric('unique_ngs_samples_cpt_genie_sample_id')}")
    lines.append("")
    lines.append("## 2. 已检查项目材料")
    lines.append("")
    for name, note in document_notes.items():
        lines.append(f"- {name}: {note}")
    lines.append("")
    lines.append("## 3. 文件和数据表说明")
    lines.append("")
    lines.append("完整清单位于 `code/results/data_audit/tables/file_inventory.csv`。核心表主题由文件路径和字段名启发式推断，待数据字典复核。")
    for row in file_rows[:20]:
        lines.append(f"- `{row['relative_path']}`: {row['format']}, rows={row['data_row_count']}, cols={row['column_count']}, theme={row['table_theme']}")
    if len(file_rows) > 20:
        lines.append(f"- 其余 {len(file_rows) - 20} 个文件见 CSV 清单。")
    lines.append("")
    lines.append("## 4. 主键、外键及表关系")
    lines.append("")
    lines.append("关系均为候选关系，不作为正式 join 规则。必须用数据手册/变量字典确认后才能用于队列构建。")
    for row in relationship_rows[:25]:
        lines.append(
            f"- {row['relationship_type']}: `{row['source_table']}`.`{row['source_field']}` -> "
            f"`{row['target_table']}`.`{row['target_field']}`; {row['evidence']}"
        )
    if len(relationship_rows) > 25:
        lines.append(f"- 其余 {len(relationship_rows) - 25} 条候选关系见 `code/results/data_audit/tables/table_relationships.csv`。")
    lines.append("")
    lines.append("## 5. 患者、样本、治疗、分子和结局覆盖")
    lines.append("")
    lines.append(f"- 唯一患者数：{metric('unique_patients_patient_level')}")
    lines.append(f"- index cancer 行数：{metric('index_cancer_rows')}")
    lines.append(f"- 有 NGS 检测记录的患者数：{metric('unique_patients_with_ngs_test')}")
    lines.append(f"- 有治疗 regimen 记录的患者数：{metric('unique_patients_with_treatment_regimen')}")
    lines.append(f"- 同时有 NGS 和治疗记录的患者数：{metric('unique_patients_with_both_ngs_and_treatment')}")
    lines.append(f"- cBioPortal 样本数：{metric('cbio_unique_samples')}")
    lines.append(f"- 多 NGS 检测患者数：{metric('patients_with_multiple_ngs_tests')}")
    lines.append(f"- 多治疗 regimen 患者数：{metric('patients_with_multiple_regimens')}")
    lines.append("")
    lines.append("组织学、分期、转移、可切除状态和机构分布的聚合统计见 `code/results/data_audit/tables/categorical_summaries.csv`；小于阈值的类别已合并隐藏。")
    lines.append("")
    lines.append("## 6. 关键字段缺失情况")
    lines.append("")
    lines.append("完整字段级缺失率见 `code/results/data_audit/tables/missingness_summary.csv`。以下仅列关键字段：")
    for row in key_missing[:30]:
        lines.append(
            f"- `{row['table_path']}`.`{row['public_field_name']}`: missing={row['missing_count']}/"
            f"{row['row_count']} ({row['missing_rate']})"
        )
    lines.append("")
    lines.append("## 7. 时间顺序和数据泄漏风险")
    lines.append("")
    lines.append(f"- 有 NGS 与 regimen 相对时间字段的患者数：{metric('patients_with_ngs_and_regimen_timing')}")
    lines.append(f"- NGS 报告早于或等于最早 regimen 的患者数：{metric('patients_ngs_report_on_or_before_earliest_regimen')}")
    lines.append(f"- NGS 报告晚于最早 regimen 的患者数：{metric('patients_ngs_report_after_earliest_regimen')}")
    lines.append("- 上述只是第一轮聚合检查。正式 t0 必须按具体治疗决策点逐例对齐，不能用结局字段、停药字段或未来随访字段构造输入。")
    lines.append("")
    lines.append("潜在泄漏字段示例：")
    for row in leakage_fields[:20]:
        lines.append(f"- `{row['table_path']}`.`{row['public_field_name']}`: {row['leakage_risk_hint']}")
    lines.append("")
    lines.append("## 8. 数据质量问题")
    lines.append("")
    dup_tables = [row for row in file_rows if str(row.get("duplicate_rows", "0")) not in {"", "0"}]
    if dup_tables:
        for row in dup_tables[:20]:
            lines.append(f"- `{row['relative_path']}` 完全重复行数：{row['duplicate_rows']}")
    else:
        lines.append("- 未在表级摘要中发现完全重复行；仍需在正式建队列时检查业务键重复。")
    lines.append("- 宽基因矩阵中的动态样本列名已脱敏汇总，避免在审计产物中泄露样本级标识。")
    lines.append("- PDF 数据手册和流程文档因环境缺少 PDF 解析器，本轮只确认文件存在和校验值，正文待人工或合规工具复核。")
    lines.append("")
    lines.append("## 9. Track A 可行性")
    lines.append("")
    lines.append(
        "初步可行，但只能作为 Track A 病例骨架和分子/治疗/结局描述基准。"
        "BPC PANC 提供患者、癌种、NGS、治疗、影像/随访和部分生存/PFS 相关字段；"
        "是否可纳入还需逐患者确认 PDAC 组织学、晚期/复发/转移状态、NGS<=t0、既往治疗可解释性和结局时间位置。"
    )
    lines.append("")
    lines.append("## 10. Track B 当前条件")
    lines.append("")
    lines.append(
        "当前 PANC 原始包不足以建立完整 Track B。V3.0 方案要求 Track B 具备决策时点附近 ECOG、关键实验室、给药/减量和毒性字段；"
        "本轮文件名和字段级审计未确认这些字段在 BPC PANC 中完整存在。不得用跨数据源伪拼接补齐。"
    )
    lines.append("")
    lines.append("## 11. Pilot、Core、Extended 现实定义与估计规模")
    lines.append("")
    lines.append("- Pilot：从通过 Track A 初筛的患者中人工抽取 20-30 例，用于修订 schema 和审计时间线。")
    lines.append("- Core：优先选择字段完整、NGS 早于候选决策点、治疗和结局可解释的 50-80 例人工复核病例；真实可达规模待 t0 逐例审计后锁定。")
    lines.append("- Extended：可从剩余通过 Track A 机器审计的患者形成；当前保守上界可参考“同时有 NGS 和治疗记录的患者数”，但这不是正式队列规模。")
    lines.append("")
    lines.append("## 12. 尚需确认的问题")
    lines.append("")
    lines.append("- PDF 数据手册、GA01 基本流程、GA09 数据与代码管理规范的正文需要进一步读取或人工核对。")
    lines.append("- 数据许可/使用限制需从 AACR/Synapse 官方条款和包内说明正式确认；当前 README 仅提供来源链接和数据包简介。")
    lines.append("- 字段含义、缺失编码、相对日期定义、药物遮蔽规则和机构差异需以变量字典/数据手册为准。")
    lines.append("- 四类候选状态的标签细则需继续从 V3.0 全文和后续标注指南中固化为机器可读规则。")
    lines.append("")
    lines.append("## 13. 下一步建议")
    lines.append("")
    lines.append("1. 先补齐 PDF 文档解析或人工摘录，确认数据字典、许可和时间字段定义。")
    lines.append("2. 基于本审计输出制定 Track A 初筛 SQL/脚本，但仍不要训练模型。")
    lines.append("3. 手工核验 10-20 个非敏感、去标识病例时间线，只输出聚合问题清单。")
    lines.append("4. 明确 t0 定义后再做时间泄漏审计和候选池冻结。")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_notebook(path: Path) -> None:
    nb = {
        "cells": [
            {
                "cell_type": "markdown",
                "id": "audit-overview",
                "metadata": {},
                "source": [
                    "# BPC PANC Raw Data Read-Only Audit\n",
                    "\n",
                    "This notebook runs `code/scripts/audit_raw_data.py` and inspects aggregate outputs only. Do not display patient-level records here.\n",
                ],
            },
            {
                "cell_type": "code",
                "id": "run-audit",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from pathlib import Path\n",
                    "import subprocess, sys\n",
                    "\n",
                    "def find_repo_root(start):\n",
                    "    for p in [start, *start.parents]:\n",
                    "        if (p / 'data').exists() and (p / 'code' / 'scripts' / 'audit_raw_data.py').exists():\n",
                    "            return p\n",
                    "    raise RuntimeError('repo root not found')\n",
                    "repo = find_repo_root(Path.cwd().resolve())\n",
                    "script = repo / 'code' / 'scripts' / 'audit_raw_data.py'\n",
                    "subprocess.run([sys.executable, str(script), '--repo-root', str(repo)], check=True)\n",
                ],
            },
            {
                "cell_type": "code",
                "id": "inspect-aggregate-outputs",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "import csv\n",
                    "from pathlib import Path\n",
                    "\n",
                    "def find_repo_root(start):\n",
                    "    for p in [start, *start.parents]:\n",
                    "        if (p / 'data').exists() and (p / 'code' / 'scripts' / 'audit_raw_data.py').exists():\n",
                    "            return p\n",
                    "    raise RuntimeError('repo root not found')\n",
                    "repo = find_repo_root(Path.cwd().resolve())\n",
                    "for name in ['file_inventory.csv', 'field_inventory.csv', 'table_relationships.csv', 'feasibility_summary.csv']:\n",
                    "    path = repo / 'code' / 'results' / 'data_audit' / 'tables' / name\n",
                    "    with path.open(encoding='utf-8', newline='') as f:\n",
                    "        rows = list(csv.DictReader(f))\n",
                    "    print(name, 'rows=', len(rows))\n",
                    "    for row in rows[:5]:\n",
                    "        public = {k: row[k] for k in list(row)[:6]}\n",
                    "        print(public)\n",
                    "    print()\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(nb, ensure_ascii=False, indent=2), encoding="utf-8")


def audit(repo_root: Path, raw_root: Path) -> None:
    if not raw_root.exists():
        raise FileNotFoundError(f"Raw root not found: {raw_root}")
    tables_dir = repo_root / "code" / "results" / "data_audit" / "tables"
    report_path = repo_root / "docs" / "notes" / "data_feasibility_audit_v1.md"
    notebook_path = repo_root / "code" / "notebooks" / "00_raw_data_inventory.ipynb"
    tables_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.parent.mkdir(parents=True, exist_ok=True)

    data_dict = load_variable_dictionary(raw_root)
    file_rows: list[dict[str, Any]] = []
    all_field_stats: list[FieldStats] = []
    table_meta: dict[str, dict[str, Any]] = {}

    for path in sorted(raw_root.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in TEXT_EXTENSIONS:
            file_row, fields, meta = analyze_delimited(path, repo_root, data_dict)
        elif ext in XLSX_EXTENSIONS:
            file_row, fields, meta = analyze_xlsx(path, repo_root, data_dict)
        else:
            file_row, fields, meta = analyze_binary_or_pdf(path, repo_root)
        file_rows.append(file_row)
        table_meta[file_row["relative_path"]] = meta
        file_row["duplicate_rows"] = meta.get("duplicate_rows", "")
        all_field_stats.extend(fields)

    relationship_rows, pk_by_table = candidate_key_and_relationships(all_field_stats, table_meta)

    field_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for stat in all_field_stats:
        row = {
            "table_path": stat.table_path,
            "field_name": stat.field_name if not stat.is_redacted_dynamic_field else "<redacted>",
            "public_field_name": stat.public_field_name,
            "is_redacted_dynamic_field": str(stat.is_redacted_dynamic_field).lower(),
            "row_count": stat.row_count,
            "missing_count": stat.missing_count,
            "missing_rate": round(stat.missing_rate, 6),
            "unique_count": stat.unique_count if not stat.is_redacted_dynamic_field else "",
            "inferred_type": stat.inferred_type,
            "dictionary_label": stat.dictionary_label,
            "dictionary_source": stat.dictionary_source,
            "data_role_hint": stat.data_role_hint,
            "date_field_hint": stat.date_field_hint,
            "leakage_risk_hint": stat.leakage_risk_hint,
            "is_candidate_primary_key": "true"
            if stat.public_field_name in pk_by_table.get(stat.table_path, [])
            else "false",
        }
        field_rows.append(row)
        missing_rows.append(
            {
                "table_path": stat.table_path,
                "public_field_name": stat.public_field_name,
                "row_count": stat.row_count,
                "missing_count": stat.missing_count,
                "missing_rate": round(stat.missing_rate, 6),
                "unique_count": stat.unique_count if not stat.is_redacted_dynamic_field else "",
                "inferred_type": stat.inferred_type,
            }
        )

    feasibility_rows, categorical_rows = feasibility_audit(repo_root, raw_root)

    write_csv(
        tables_dir / "file_inventory.csv",
        file_rows,
        [
            "relative_path",
            "file_name",
            "extension",
            "format",
            "size_bytes",
            "size_mb",
            "sha256",
            "encoding",
            "delimiter",
            "line_count",
            "data_row_count",
            "column_count",
            "field_names",
            "field_names_redacted",
            "table_theme",
            "duplicate_rows",
            "notes",
        ],
    )
    write_csv(
        tables_dir / "field_inventory.csv",
        field_rows,
        [
            "table_path",
            "field_name",
            "public_field_name",
            "is_redacted_dynamic_field",
            "row_count",
            "missing_count",
            "missing_rate",
            "unique_count",
            "inferred_type",
            "dictionary_label",
            "dictionary_source",
            "data_role_hint",
            "date_field_hint",
            "leakage_risk_hint",
            "is_candidate_primary_key",
        ],
    )
    write_csv(
        tables_dir / "table_relationships.csv",
        relationship_rows,
        [
            "source_table",
            "source_field",
            "target_table",
            "target_field",
            "relationship_type",
            "evidence",
            "caution",
        ],
    )
    write_csv(
        tables_dir / "missingness_summary.csv",
        missing_rows,
        [
            "table_path",
            "public_field_name",
            "row_count",
            "missing_count",
            "missing_rate",
            "unique_count",
            "inferred_type",
        ],
    )
    write_csv(
        tables_dir / "feasibility_summary.csv",
        feasibility_rows,
        ["metric", "value", "source", "evidence_scope", "caution"],
    )
    write_csv(
        tables_dir / "categorical_summaries.csv",
        categorical_rows,
        ["table_path", "field_name", "value_public", "count", "suppressed_small_count", "privacy_note"],
    )

    document_notes = {
        "README.md": "仓库 README 仅含项目名。",
        "V3.0研究方案": "已用 DOCX 标准库解析；确认四类候选状态和 Track A/B 边界。",
        "GA01-研究的基本流程步骤.pdf": "文件存在；本环境无 PDF 文本解析器，正文待确认。",
        "GA09-数据与代码管理规范.pdf": "文件存在；本环境无 PDF 文本解析器，正文待确认。",
        "BPC PANC README": "ReadMe.txt 可用 UTF-8 读取，提供 AACR/Synapse/包说明链接。",
        "数据字典": f"解析到 {len(data_dict)} 个变量名映射；仍需人工核验列含义。",
        "数据许可或使用说明": "未在可机读文本中完整确认；需核对 AACR/Synapse 官方条款及 PDF 手册。",
    }
    write_markdown_report(
        repo_root,
        raw_root,
        report_path,
        file_rows,
        field_rows,
        relationship_rows,
        feasibility_rows,
        categorical_rows,
        document_notes,
    )
    create_notebook(notebook_path)
    print("audit_complete")
    print(f"repo_root={repo_root}")
    print(f"raw_root={raw_root}")
    print(f"files={len(file_rows)} fields={len(field_rows)} relationships={len(relationship_rows)}")


def find_repo_root(start: Path) -> Path:
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists() and (candidate / "data").exists():
            return candidate
        if (candidate / PANC_RELATIVE_ROOT).exists():
            return candidate
    raise FileNotFoundError(f"Could not locate repository root from {start}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only audit for BPC PANC raw data.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--raw-root", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(Path(__file__).resolve())
    raw_root = args.raw_root.resolve() if args.raw_root else repo_root / PANC_RELATIVE_ROOT
    audit(repo_root, raw_root)


if __name__ == "__main__":
    main()


