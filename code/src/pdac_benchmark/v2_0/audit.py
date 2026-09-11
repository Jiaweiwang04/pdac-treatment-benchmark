"""Stage 01: inventory original files and preserve clinical records without clinical labels."""

import argparse
import csv
import json
import platform
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

from .documentation import write_audit_report
from .layout import resolve_paths
from .source import CANCER_KEY, KEYS, PATIENT_KEY, expand_specimens, key, number, read_csv, record_id, relative_day, sha256

BASE = Path(__file__).resolve().parents[4]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def run(config_path):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["project_version"] != "v2.0":
        raise ValueError("Only the formal v2.0 configuration is supported")
    root, processed, out = resolve_paths(BASE, config)
    if not root.is_dir():
        raise FileNotFoundError(root)
    out.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    preserved = processed / "clinical_records"
    preserved.mkdir(exist_ok=True)
    manifest = {"project_version": "v2.0", "phase": "01_source_audit", "status": "running",
                "started_utc": datetime.now(timezone.utc).isoformat(), "config_sha256": sha256(config_path),
                "config_file": config_path.resolve().relative_to(BASE).as_posix(),
                "processed_dir": processed.relative_to(BASE).as_posix(), "results_dir": out.relative_to(BASE).as_posix(),
                "source_release": config["source_release"], "source_root": str(root),
                "runtime": {"python": platform.python_version(), "platform": platform.platform(), "third_party_runtime_dependencies": []},
                "code_sha256": {p.relative_to(BASE).as_posix(): sha256(p) for p in sorted([*(BASE / "code/src").rglob("*.py"), *(BASE / "code/scripts").glob("*.py")])},
                "test_sha256": {p.relative_to(BASE).as_posix(): sha256(p) for p in sorted((BASE / "code/tests/v2_0").glob("*.py"))},
                "legacy_outputs_used": False, "clinical_eligibility_evaluated": False, "expert_labels_generated": False}
    write_json(out / "run_manifest.json", manifest)
    inventory = [{"file": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
                 for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith("~$")]
    write_json(out / "source_inventory.json", inventory)
    issues = []

    def issue(kind, table, row_index, detail):
        issues.append({"issue": kind, "table": table, "source_logical_row": row_index + 2, "detail": detail})

    tables, schemas, profiles = {}, [], []
    for table, columns in KEYS.items():
        path = root / config["clinical_directory"] / (table + ".csv")
        header, rows = read_csv(path)
        missing_keys = set(columns) - set(header)
        if missing_keys:
            raise ValueError(f"Required columns absent in {table}: {missing_keys}")
        tables[table] = rows
        seen = set()
        for i, row in enumerate(rows):
            record_key = key(row, columns)
            if any(value == "" for value in record_key):
                issue("empty_primary_key", table, i, str(record_key))
            if record_key in seen:
                issue("duplicate_primary_key", table, i, str(record_key))
            seen.add(record_key)
        src = {"file": path.relative_to(root).as_posix(), "sha256": sha256(path), "primary_key_columns": list(columns)}
        def records():
            for i, row in enumerate(rows, 2):
                yield {"project_version": "v2.0", "record_id": record_id(table, row),
                       "source": {**src, "logical_row": i, "primary_key_values": list(key(row, columns))}, "fields": row}
        write_jsonl(preserved / (table + ".jsonl"), records())
        # Independent reread catches truncation, changed values and serialization losses.
        original_header, original_rows = read_csv(path)
        with (preserved / (table + ".jsonl")).open(encoding="utf-8") as stream:
            for i, (raw, exported) in enumerate(zip_longest(original_rows, stream)):
                if raw is None or exported is None or json.loads(exported)["fields"] != raw:
                    raise AssertionError(f"Clinical value roundtrip failed: {table}, {i + 2}")
        if header != original_header:
            raise AssertionError("Source header changed during run")
        schemas.append({"table": table, "rows": len(rows), "column_count": len(header), "columns": header,
                        "patient_count": len({key(row, PATIENT_KEY) for row in rows}), "primary_key": list(columns)})
        for column in header:
            counts = Counter(row[column] for row in rows)
            explicit = {value: count for value, count in counts.items()
                        if value.strip().lower() in {"unknown", "not available", "not applicable", "not reported", "not stated", "na", "n/a"}}
            profiles.append({"table": table, "field": column, "rows": len(rows), "empty_cells": counts.get("", 0),
                             "literal_zero_cells": counts.get("0", 0), "unique_nonempty_values": len(counts) - int("" in counts),
                             "explicit_missing_values": json.dumps(explicit, ensure_ascii=False)})
    write_json(out / "table_schemas.json", schemas)
    write_csv(out / "field_profile.csv", list(profiles[0]), profiles)

    def grouped(table, columns):
        result = defaultdict(list)
        for row in tables[table]:
            result[key(row, columns)].append(row)
        return result

    patients = grouped("patient_level_dataset", PATIENT_KEY)
    index_cancers = grouped("cancer_level_dataset_index", CANCER_KEY)
    other_cancers = grouped("cancer_level_dataset_non_index", CANCER_KEY)
    diagnoses = defaultdict(list)
    for mapping in (index_cancers, other_cancers):
        for k, rows in mapping.items():
            diagnoses[k].extend(rows)
    paths = grouped("pathology_report_level_dataset", KEYS["pathology_report_level_dataset"])
    for table, rows in tables.items():
        for i, row in enumerate(rows):
            if len(patients.get(key(row, PATIENT_KEY), [])) != 1:
                issue("patient_link_not_unique", table, i, str(key(row, PATIENT_KEY)))
            if table in {"regimen_cancer_level_dataset", "ca_radtx_dataset", "cancer_panel_test_level_dataset"}:
                if len(diagnoses.get(key(row, CANCER_KEY), [])) != 1:
                    issue("cancer_link_not_unique", table, i, str(key(row, CANCER_KEY)))
            if table == "cancer_panel_test_level_dataset":
                pathkey = key(row, KEYS["pathology_report_level_dataset"])
                if len(paths.get(pathkey, [])) != 1:
                    issue("ngs_pathology_link_not_unique", table, i, str(pathkey))

    specimen_rows, report_rows = [], []
    table = "pathology_report_level_dataset"
    for i, row in enumerate(tables[table]):
        specimens = expand_specimens(row)
        report = {"project_version": "v2.0", "report_id": record_id(table, row),
                  "cohort": row["cohort"], "patient_id": row["record_id"], "source_file": "clinical_data/" + table + ".csv",
                  "source_logical_row": i + 2, "procedure_number": row["path_proc_number"], "report_number": row["path_rep_number"],
                  "procedure_day_raw": row["dx_path_proc_days"], "histology_report_availability": "unconfirmed",
                  "declared_specimen_count_raw": row["path_num_spec"], "expanded_specimen_count": len(specimens),
                  "full_fields_location": "clinical_records/" + table + ".jsonl"}
        report_rows.append(report)
        for specimen in specimens:
            specimen_rows.append({"report_id": report["report_id"], "cohort": row["cohort"], "patient_id": row["record_id"],
                                  "source_logical_row": i + 2, **specimen})
        if number(row["path_num_spec"]) != len(specimens):
            issue("specimen_count_mismatch", table, i, f"declared={row['path_num_spec']}, expanded={len(specimens)}")
    write_jsonl(processed / "pathology_reports.jsonl", report_rows)
    write_jsonl(processed / "pathology_specimens.jsonl", specimen_rows)

    first_days = defaultdict(list)
    for row in tables["cancer_level_dataset_index"]:
        date = number(row["dob_ca_dx_days"])
        if date is not None:
            first_days[key(row, PATIENT_KEY)].append(date)
    first_days = {k: min(v) for k, v in first_days.items()}
    registry, all_starts = [], Counter()
    table = "regimen_cancer_level_dataset"
    for i, row in enumerate(tables[table]):
        ck, pk = key(row, CANCER_KEY), key(row, PATIENT_KEY)
        linked = diagnoses.get(ck, [])
        cancer = linked[0] if len(linked) == 1 else None
        start = relative_day(row["dx_reg_start_int"], cancer["dob_ca_dx_days"] if cancer else None, first_days.get(pk))
        if start is None:
            issue("regimen_start_not_resolved", table, i, str(ck))
        if start is not None:
            all_starts[(*ck, start)] += 1
        reg = {"project_version": "v2.0", "record_id": record_id(table, row), "cohort": row["cohort"],
               "patient_id": row["record_id"], "cancer_seq": row["ca_seq"], "source_file": "clinical_data/" + table + ".csv",
               "source_logical_row": i + 2, "is_index_cancer": ck in index_cancers,
               "source_index_flag_raw": row["redcap_ca_index"], "regimen_number": row["regimen_number"],
               "regimen_order_raw": row["regimen_number_within_cancer"], "start_relative_to_cancer_raw": row["dx_reg_start_int"],
               "start_day_first_index": start, "observed_drugs": [row.get("drugs_drug_" + str(j), "") for j in range(1, 6)],
               "decision_adjudication": "not_evaluated", "training_test_eligibility": "not_evaluated"}
        registry.append(reg)
    for row in registry:
        row["same_cancer_same_day_record_count"] = all_starts.get((row["cohort"], row["patient_id"], row["cancer_seq"], row["start_day_first_index"]), 0)
    write_jsonl(processed / "treatment_record_registry.jsonl", registry)
    csv_rows = [{**r, "observed_drugs": " | ".join(x for x in r["observed_drugs"] if x)} for r in registry]
    write_csv(processed / "treatment_record_registry.csv", list(csv_rows[0]), csv_rows)
    write_csv(out / "quality_issues.csv", ["issue", "table", "source_logical_row", "detail"], issues)
    changed = [r["file"] for r in inventory if not (root / r["file"]).is_file() or sha256(root / r["file"]) != r["sha256"]]
    summary = {"project_version": "v2.0", "source_files": len(inventory), "source_files_changed": changed,
               "clinical_tables": len(tables), "clinical_records": sum(len(r) for r in tables.values()),
               "patients": len(patients), "index_cancers": len(index_cancers), "pathology_reports": len(report_rows),
               "pathology_source_columns": len(next(s for s in schemas if s["table"] == "pathology_report_level_dataset")["columns"]),
               "pathology_specimens": len(specimen_rows), "maximum_specimens_per_report": max(r["expanded_specimen_count"] for r in report_rows),
               "all_regimen_records": len(registry), "index_cancer_regimen_records": sum(r["is_index_cancer"] for r in registry),
               "non_index_cancer_regimen_records": sum(not r["is_index_cancer"] for r in registry),
               "same_cancer_same_day_groups": sum(n > 1 for n in all_starts.values()),
               "same_day_groups_index_cancer": sum(n > 1 and k[:3] in index_cancers for k, n in all_starts.items()),
               "same_day_groups_non_index_cancer": sum(n > 1 and k[:3] not in index_cancers for k, n in all_starts.items()),
               "clinical_field_roundtrip_mismatches": 0, "quality_issue_counts": dict(Counter(i["issue"] for i in issues)),
               "final_eligible_decisions": None, "expert_labels": None}
    write_json(out / "audit_summary.json", summary)
    fatal = bool(changed) or any(i["issue"] in {"empty_primary_key", "duplicate_primary_key", "specimen_count_mismatch"} for i in issues)
    manifest.update(status="failed" if fatal else "completed_with_issues" if issues else "completed",
                    finished_utc=datetime.now(timezone.utc).isoformat(), summary=summary)
    write_json(out / "run_manifest.json", manifest)
    report_path = BASE / "docs/notes/v2.0/source_data_audit_report_v2.0.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_audit_report(BASE, out, processed, report_path, summary, schemas, manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if fatal else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BASE / "code/config/v2.0/source.json")
    args = parser.parse_args()
    try:
        return run(args.config)
    except Exception as error:
        print(f"v2.0 source audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
