"""Shared privacy scanning and small-cell suppression utilities."""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_SMALL_COUNT_THRESHOLD = 5
DEFAULT_SUPPRESSED = "<5"

TEXT_FILE_EXTENSIONS = {
    ".csv",
    ".ipynb",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}
BINARY_FILE_EXTENSIONS = {
    ".docx",
    ".idx",
    ".ipynb_checkpoints",
    ".pack",
    ".pdf",
    ".png",
    ".pyc",
    ".rev",
    ".xlsx",
}
PRIVATE_PATH_PARTS = {"data/raw", "data/processed", "reports/private", "reports/patient_level", "warehouse"}

GENIE_CENTER_ID_PATTERN = re.compile(
    r"\bGENIE-(?!BPC\b)[A-Z0-9]{2,8}-(?:P-)?[A-Z0-9]*\d[A-Z0-9-]*\b",
    re.IGNORECASE,
)
HIGH_RISK_FIELD_NAMES = {
    "case_id",
    "cpt_genie_sample_id",
    "patient_id",
    "record_id",
    "sample_id",
    "tumor_sample_barcode",
}
HIGH_RISK_FIELD_PATTERN = re.compile(
    r"(^|[_\s-])(patient|record|sample|barcode|case)[_\s-]*(id|identifier|number)($|[_\s-])",
    re.IGNORECASE,
)
PROJECT_GENIE_ALLOWLIST = (
    "AACR GENIE",
    "Project GENIE",
    "GENIE BPC",
    "GENIE-BPC",
    "cpt_genie_sample_id",
    "GENIE-BPC-PANC",
)

EXPLICIT_COUNT_FIELDS = {
    "different_index_sample_vs_main",
    "n",
    "n_hits",
    "value",
}
NON_COUNT_FIELDS = {
    "age",
    "cpt_seq_year",
    "duration",
    "index_ngs_year",
    "missing_rate",
    "rate",
    "release_version",
    "sample_count_per_patient",
    "sha256",
    "size_mb",
    "size_bytes",
    "step_order",
    "time",
    "version",
    "year",
}
COUNT_FIELD_TOKENS = (
    "case",
    "censored",
    "cohort_n",
    "count",
    "event",
    "evaluable",
    "hit",
    "manual_review",
    "missing_count",
    "n_",
    "_n",
    "patient",
    "record",
    "row",
    "sample",
)
COUNT_METRIC_PATTERN = re.compile(
    r"(?:^|[_\s-])(n|count|coverage|files?|fields?|tables?|columns?|patients?|samples?|records?|rows?|events?|groups?|pairs?|censored|evaluable|hits?|manual_review|core|extended)(?:$|[_\s-])",
    re.IGNORECASE,
)
NON_COUNT_METRIC_PATTERN = re.compile(
    r"(rate|ratio|share|year|date|duration|time|day|days|month|months|version|sha|size|bytes)",
    re.IGNORECASE,
)


def _cohort_yaml_path() -> Path:
    return Path(__file__).resolve().parents[2] / "cohort_definition_v0.1.yaml"


def _read_privacy_config() -> tuple[int, str]:
    threshold = DEFAULT_SMALL_COUNT_THRESHOLD
    symbol = DEFAULT_SUPPRESSED
    path = _cohort_yaml_path()
    if not path.exists():
        return threshold, symbol
    in_privacy = False
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith(" ") and stripped.endswith(":"):
            in_privacy = stripped == "privacy:"
            continue
        if not in_privacy or ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        value = raw_value.strip().strip('"').strip("'")
        if key == "small_count_threshold":
            try:
                threshold = int(value)
            except ValueError:
                threshold = DEFAULT_SMALL_COUNT_THRESHOLD
        elif key == "suppression_symbol":
            symbol = value or DEFAULT_SUPPRESSED
    return threshold, symbol


SMALL_COUNT_THRESHOLD, SUPPRESSED = _read_privacy_config()


def normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def tracked_files(repo_root: Path) -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=repo_root, check=True, capture_output=True, text=True)
    return [normalize_path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def is_public_tracked_file(path: str | Path) -> bool:
    normalized = normalize_path(path)
    if any(normalized == part or normalized.startswith(part + "/") for part in PRIVATE_PATH_PARTS):
        return False
    return is_text_file(normalized)


def is_text_file(path: str | Path) -> bool:
    suffix = Path(str(path)).suffix.lower()
    if suffix in BINARY_FILE_EXTENSIONS:
        return False
    return suffix in TEXT_FILE_EXTENSIONS


def read_public_text(path: Path) -> str | None:
    if not is_text_file(path):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def is_high_risk_field_name(name: str) -> bool:
    normalized = str(name).strip().lower()
    return normalized in HIGH_RISK_FIELD_NAMES or bool(HIGH_RISK_FIELD_PATTERN.search(normalized))


def contains_identifier(text: str) -> bool:
    if not text:
        return False
    return bool(GENIE_CENTER_ID_PATTERN.search(text))


def safe_public_field_name(name: str) -> str:
    return "<redacted_identifier_field>" if contains_identifier(str(name)) else name


def privacy_scan_hits(repo_root: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    tracked = files if files is not None else tracked_files(repo_root)
    for rel in tracked:
        rel = normalize_path(rel)
        if not is_public_tracked_file(rel):
            continue
        path = repo_root / rel
        if not path.exists():
            continue
        text = read_public_text(path)
        if text is None:
            continue
        if contains_identifier(text):
            hits.append({"file": rel, "kind": "genie_identifier_pattern"})
        if path.suffix.lower() == ".csv":
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    risky_headers = [header for header in (reader.fieldnames or []) if is_high_risk_field_name(header)]
                    for line_no, row in enumerate(reader, start=2):
                        for header in risky_headers:
                            value = row.get(header, "")
                            if value and not value.startswith("<") and not value.lower().startswith("suppressed"):
                                hits.append({"file": rel, "kind": "high_risk_identifier_column", "line": line_no, "column": header})
                                raise StopIteration
            except StopIteration:
                continue
            except (csv.Error, UnicodeDecodeError):
                continue
    return hits


def suppress_count(value: Any, threshold: int = SMALL_COUNT_THRESHOLD) -> str:
    if value is None:
        return ""
    text = str(value)
    if text in {"", "not_applicable", SUPPRESSED}:
        return text
    try:
        number = int(text)
    except (TypeError, ValueError):
        return text
    if 0 < number < threshold:
        return SUPPRESSED
    return str(number)


def is_count_field(field: str) -> bool:
    lower = field.strip().lower()
    if lower in NON_COUNT_FIELDS:
        return False
    if lower in EXPLICIT_COUNT_FIELDS:
        return lower != "value"
    if lower.startswith("n_") or lower.endswith("_n") or lower == "n":
        return True
    return any(token in lower for token in COUNT_FIELD_TOKENS)


def metric_implies_count(metric: Any) -> bool:
    text = str(metric or "").strip().lower()
    if not text:
        return False
    if COUNT_METRIC_PATTERN.search(text):
        return True
    if NON_COUNT_METRIC_PATTERN.search(text):
        return False
    return False


def is_count_cell(field: str, row: dict[str, Any] | None = None) -> bool:
    lower = field.strip().lower()
    row = row or {}
    if lower == "value":
        return metric_implies_count(row.get("metric") or row.get("check") or row.get("check_name"))
    return is_count_field(field)


def public_cell(field: str, value: Any, row: dict[str, Any] | None = None) -> Any:
    if is_count_cell(field, row):
        return suppress_count(value)
    return value


def small_count_scan_hits(repo_root: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    tracked = files if files is not None else tracked_files(repo_root)
    for rel in tracked:
        rel = normalize_path(rel)
        if not is_public_tracked_file(rel) or not rel.lower().endswith(".csv"):
            continue
        path = repo_root / rel
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for line_no, row in enumerate(reader, start=2):
                    for field, value in row.items():
                        if not field or not is_count_cell(field, row):
                            continue
                        try:
                            number = int(str(value))
                        except (TypeError, ValueError):
                            continue
                        if 0 < number < SMALL_COUNT_THRESHOLD:
                            hits.append({"file": rel, "line": line_no, "column": field})
        except (csv.Error, UnicodeDecodeError):
            continue
    return hits
