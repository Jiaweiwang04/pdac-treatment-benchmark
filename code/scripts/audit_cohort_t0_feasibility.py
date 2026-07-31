"""Read-only cohort and t0 feasibility audit for AACR GENIE BPC PANC.

Outputs are aggregate-only. The script does not modify data/raw, train models,
or construct final labels.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PANC_RELATIVE_ROOT = Path(
    "data/raw/AACR GENIE Biopharma Collaborative Public/"
    "Data Releases/PANC/1.0-public"
)
KEY_PATIENT = ["cohort", "record_id"]
KEY_CANCER = ["cohort", "record_id", "ca_seq"]
MISSING_TOKENS = {"", "NA", "N/A", "NULL", "NONE", "NAN", "UNKNOWN", "NOT AVAILABLE", "NOT APPLICABLE"}
PDAC_ONCOTREE_CODES = {"PAAD"}
PDAC_HISTOLOGY_TERMS = ("adenocarcinoma", "ductal")
OUTCOME_PAIRS = [
    ("os_g_status", "tt_os_g_days"),
    ("pfs_i_g_status", "tt_pfs_i_g_days"),
    ("pfs_m_g_status", "tt_pfs_m_g_days"),
    ("pfs_i_or_m_g_status", "tt_pfs_i_or_m_g_days"),
    ("pfs_i_and_m_g_status", "tt_pfs_i_and_m_g_days"),
    ("ttnt_any_ca_status", "ttnt_any_ca_days"),
    ("ttnt_ca_seq_status", "ttnt_ca_seq_days"),
]
DEFINITION_LABELS = {
    "A": "First new regimen after NGS report; report_day < regimen_start_day",
    "B": "First new regimen after or on NGS report day; report_day <= regimen_start_day",
    "C": "First regimen with NGS report available before start; report_day < first_regimen_start_day",
}


def find_repo_root(start: Path) -> Path:
    start = start.resolve()
    for path in [start, *start.parents]:
        if (path / "README.md").exists() and (path / "data").exists():
            return path
    raise FileNotFoundError("repository root not found")


def read_csv_str(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or text.upper() in MISSING_TOKENS


def nonmissing(series: pd.Series) -> pd.Series:
    return ~series.map(is_missing_value)


def numeric(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned.mask(cleaned.str.upper().isin(MISSING_TOKENS), pd.NA)
    cleaned = cleaned.mask(cleaned.eq(""), pd.NA)
    return pd.to_numeric(cleaned, errors="coerce")


def safe_lower(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def ascii_clean(value: Any) -> str:
    return str(value).encode("ascii", "ignore").decode("ascii")


def patient_set(df: pd.DataFrame) -> set[str]:
    if "record_id" not in df.columns:
        return set()
    return set(df.loc[nonmissing(df["record_id"]), "record_id"].astype(str))


def count_patients(df: pd.DataFrame) -> int:
    return len(patient_set(df))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def data_guide_status(raw_root: Path) -> str:
    pdfs = list(raw_root.glob("*Analytic-Data-Guide.pdf"))
    if not pdfs:
        return "Analytic data guide PDF not found."
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdfs[0]))
        text = " ".join((page.extract_text() or "") for page in reader.pages)
        found = []
        for key in ["record_id", "ca_seq", "dx_cpt_rep_days", "dx_reg_start_int", "ca_resect_status", "pfs_i_g_status"]:
            found.append(f"{key}={'yes' if key.lower() in text.lower() else 'no'}")
        return f"Read {ascii_clean(pdfs[0].name)} with pypdf; pages={len(reader.pages)}; " + "; ".join(found)
    except Exception as exc:
        return f"Analytic data guide present but pypdf read failed: {exc}"


def prepare_data(raw_root: Path) -> dict[str, pd.DataFrame]:
    clinical = raw_root / "clinical_data"
    return {
        "patient": read_csv_str(clinical / "patient_level_dataset.csv"),
        "cancer": read_csv_str(clinical / "cancer_level_dataset_index.csv"),
        "cpt": read_csv_str(clinical / "cancer_panel_test_level_dataset.csv"),
        "regimen": read_csv_str(clinical / "regimen_cancer_level_dataset.csv"),
        "imaging": read_csv_str(clinical / "imaging_level_dataset.csv"),
        "medonc": read_csv_str(clinical / "med_onc_note_level_dataset.csv"),
        "pathology": read_csv_str(clinical / "pathology_report_level_dataset.csv"),
    }


def annotate_pdac(cancer: pd.DataFrame, cpt: pd.DataFrame) -> pd.DataFrame:
    cancer = cancer.copy()
    cpt = cpt.copy()
    cpt["oncotree_is_paad"] = cpt["cpt_oncotree_code"].astype(str).str.upper().isin(PDAC_ONCOTREE_CODES)
    by_cancer = cpt.groupby(KEY_CANCER, dropna=False)["oncotree_is_paad"].any().reset_index()
    cancer = cancer.merge(by_cancer, on=KEY_CANCER, how="left")
    cancer["oncotree_is_paad"] = cancer["oncotree_is_paad"].fillna(False)
    hist = safe_lower(cancer["ca_histology"])
    cancer["histology_adenocarcinoma_compatible"] = False
    for term in PDAC_HISTOLOGY_TERMS:
        cancer["histology_adenocarcinoma_compatible"] |= hist.str.contains(term, regex=False, na=False)
    cancer["pdac_compatible"] = cancer["histology_adenocarcinoma_compatible"] | cancer["oncotree_is_paad"]
    return cancer


def annotate_advanced(cancer: pd.DataFrame) -> pd.DataFrame:
    cancer = cancer.copy()
    stage_iv = safe_lower(cancer["stage_dx_iv"]).eq("stage iv")
    dmets_dx = safe_lower(cancer["ca_dmets_yn"]).eq("yes")
    unresectable = safe_lower(cancer["ca_resect_status"]).eq("unresectable/locally advanced or metastatic")
    dmets_post = numeric(cancer["dmets_post_dx"]).eq(1)
    dmets_day = numeric(cancer["dx_to_dmets_days"])
    adv_day = pd.Series(pd.NA, index=cancer.index, dtype="Float64")
    baseline = stage_iv | dmets_dx | unresectable
    adv_day = adv_day.mask(baseline, 0)
    adv_day = adv_day.mask(~baseline & dmets_post & dmets_day.notna(), dmets_day)
    cancer["advanced_evidence_day"] = adv_day
    cancer["advanced_evidence_available"] = adv_day.notna()
    cancer["advanced_stage_iv_dx"] = stage_iv
    cancer["advanced_dmets_dx"] = dmets_dx
    cancer["advanced_unresectable_baseline"] = unresectable
    cancer["advanced_dmets_post_dx_dated"] = dmets_post & dmets_day.notna()
    return cancer


def prepare_cpt(cpt: pd.DataFrame) -> pd.DataFrame:
    cpt = cpt.copy()
    cpt["report_day"] = numeric(cpt["dx_cpt_rep_days"])
    cpt["path_proc_day"] = numeric(cpt["dx_path_proc_cpt_days"])
    cpt["path_proc_to_report_day"] = numeric(cpt["path_proc_cpt_rep_days"])
    cpt["cpt_order_dob_day"] = numeric(cpt["cpt_order_int"])
    cpt["cpt_n_ca_seq_num"] = numeric(cpt["cpt_n_ca_seq"])
    cpt["has_key_cancer"] = True
    for col in KEY_CANCER:
        cpt["has_key_cancer"] &= nonmissing(cpt[col])
    cpt["report_interpretable"] = cpt["report_day"].notna() & cpt["has_key_cancer"]
    cpt["ngs_ambiguous_cancer"] = cpt["cpt_n_ca_seq_num"].notna() & cpt["cpt_n_ca_seq_num"].gt(1)
    cpt["report_after_death_flag"] = numeric(cpt["cpt_report_post_death"]).eq(1)
    cpt["report_after_last_alive_flag"] = numeric(cpt["cpt_report_post_last_alive"]).eq(1)
    cpt["ngs_usable_for_t0"] = cpt["report_interpretable"] & ~cpt["ngs_ambiguous_cancer"] & ~cpt["report_after_death_flag"] & ~cpt["report_after_last_alive_flag"]
    return cpt


def prepare_regimen(regimen: pd.DataFrame) -> pd.DataFrame:
    regimen = regimen.copy()
    regimen["start_day"] = numeric(regimen["dx_reg_start_int"])
    regimen["end_any_day"] = numeric(regimen["dx_reg_end_any_int"])
    regimen["end_all_day"] = numeric(regimen["dx_reg_end_all_int"])
    regimen["regimen_number_num"] = numeric(regimen["regimen_number"])
    regimen["regimen_number_within_cancer_num"] = numeric(regimen["regimen_number_within_cancer"])
    regimen["has_key_cancer"] = True
    for col in KEY_CANCER:
        regimen["has_key_cancer"] &= nonmissing(regimen[col])
    regimen["regimen_usable_start"] = regimen["start_day"].notna() & regimen["has_key_cancer"]
    return regimen

def advanced_possible_patients(cancer: pd.DataFrame, regimen: pd.DataFrame) -> set[str]:
    cancer_adv = cancer.loc[cancer["advanced_evidence_available"], KEY_CANCER + ["advanced_evidence_day"]]
    reg = regimen.loc[regimen["regimen_usable_start"], KEY_CANCER + ["start_day"]]
    merged = reg.merge(cancer_adv, on=KEY_CANCER, how="inner")
    eligible = merged.loc[merged["advanced_evidence_day"].le(merged["start_day"])]
    return patient_set(eligible)


def selected_t0_for_definition(definition: str, base_patients: set[str], cancer: pd.DataFrame, cpt: pd.DataFrame, regimen: pd.DataFrame) -> pd.DataFrame:
    cpt_use = cpt.loc[cpt["ngs_usable_for_t0"], KEY_CANCER + ["report_day", "path_proc_day", "cpt_number", "cpt_genie_sample_id"]]
    reg_use = regimen.loc[regimen["regimen_usable_start"]].copy()
    reg_use = reg_use.loc[reg_use["record_id"].isin(base_patients)]
    adv = cancer.loc[cancer["advanced_evidence_available"], KEY_CANCER + ["advanced_evidence_day"]]
    if definition in {"A", "B"}:
        pairs = reg_use.merge(cpt_use, on=KEY_CANCER, how="inner")
        if definition == "A":
            pairs = pairs.loc[pairs["report_day"].lt(pairs["start_day"])]
        else:
            pairs = pairs.loc[pairs["report_day"].le(pairs["start_day"])]
    elif definition == "C":
        first_reg = reg_use.sort_values(["record_id", "start_day", "regimen_number_num", "ca_seq"], kind="mergesort")
        first_reg = first_reg.groupby("record_id", as_index=False).head(1)
        pairs = first_reg.merge(cpt_use, on=KEY_CANCER, how="inner")
        pairs = pairs.loc[pairs["report_day"].lt(pairs["start_day"])]
    else:
        raise ValueError(definition)
    pairs = pairs.merge(adv, on=KEY_CANCER, how="left")
    pairs = pairs.loc[pairs["advanced_evidence_day"].notna() & pairs["advanced_evidence_day"].le(pairs["start_day"])]
    if pairs.empty:
        return pairs
    pairs = pairs.sort_values(["record_id", "start_day", "regimen_number_num", "ca_seq", "report_day", "cpt_number"], kind="mergesort")
    return pairs.groupby("record_id", as_index=False).head(1).copy()


def has_evaluable_outcome(row: pd.Series) -> bool:
    for status_col, time_col in OUTCOME_PAIRS:
        if status_col in row.index and time_col in row.index and not is_missing_value(row[status_col]):
            try:
                value = float(row[time_col])
            except Exception:
                value = math.nan
            if not math.isnan(value) and value >= 0:
                return True
    return False


def evaluate_prior_reconstructability(selected: pd.DataFrame, regimen: pd.DataFrame) -> pd.DataFrame:
    selected = selected.copy()
    if selected.empty:
        selected["prior_treatment_reconstructable"] = pd.Series(dtype=bool)
        selected["same_day_t0_regimen_ambiguity"] = pd.Series(dtype=bool)
        selected["prior_overlap_with_t0"] = pd.Series(dtype=bool)
        selected["has_evaluable_outcome"] = pd.Series(dtype=bool)
        return selected
    grouped = {key: group.copy() for key, group in regimen.loc[regimen["regimen_usable_start"]].groupby(KEY_CANCER, dropna=False)}
    reconstructable = []
    same_day_ambiguity = []
    prior_overlap = []
    for _, row in selected.iterrows():
        key = tuple(row[col] for col in KEY_CANCER)
        group = grouped.get(key, pd.DataFrame())
        t0_start = row["start_day"]
        same_day = group.loc[group["start_day"].eq(t0_start)] if not group.empty else pd.DataFrame()
        same_day_ambiguous = len(same_day[["regimen_number", "regimen_drugs"]].drop_duplicates()) > 1 if not same_day.empty else False
        prior = group.loc[group["start_day"].lt(t0_start)] if not group.empty else pd.DataFrame()
        if group.empty:
            regnum_ok = False
        else:
            regnum_ok = nonmissing(group.loc[group["start_day"].le(t0_start), "regimen_number_within_cancer"]).all()
        overlap = False
        if not prior.empty:
            prior_with_end = prior.loc[prior["end_all_day"].notna()]
            overlap = bool(prior_with_end["end_all_day"].gt(t0_start).any()) if not prior_with_end.empty else False
        reconstructable.append(bool(regnum_ok and not same_day_ambiguous))
        same_day_ambiguity.append(bool(same_day_ambiguous))
        prior_overlap.append(bool(overlap))
    selected["prior_treatment_reconstructable"] = reconstructable
    selected["same_day_t0_regimen_ambiguity"] = same_day_ambiguity
    selected["prior_overlap_with_t0"] = prior_overlap
    selected["has_evaluable_outcome"] = selected.apply(has_evaluable_outcome, axis=1)
    return selected


def regimen_timeline_quality(regimen: pd.DataFrame) -> dict[str, int]:
    metrics: dict[str, int] = {}
    reg = regimen.copy()
    metrics["regimen_rows"] = len(reg)
    metrics["regimen_patients"] = count_patients(reg)
    metrics["regimen_missing_start_rows"] = int(reg["start_day"].isna().sum())
    metrics["regimen_missing_end_any_rows"] = int(reg["end_any_day"].isna().sum())
    metrics["regimen_missing_end_all_rows"] = int(reg["end_all_day"].isna().sum())
    metrics["regimen_negative_end_any_rows"] = int((reg["end_any_day"].notna() & reg["start_day"].notna() & reg["end_any_day"].lt(reg["start_day"])).sum())
    metrics["regimen_negative_end_all_rows"] = int((reg["end_all_day"].notna() & reg["start_day"].notna() & reg["end_all_day"].lt(reg["start_day"])).sum())
    overlap_patients: set[str] = set()
    overlap_pairs = 0
    same_day_patients: set[str] = set()
    same_day_groups = 0
    for _, group in reg.loc[reg["regimen_usable_start"]].sort_values(KEY_CANCER + ["start_day", "regimen_number_num"]).groupby(KEY_CANCER, dropna=False):
        start_sizes = group.groupby("start_day").size()
        if (start_sizes > 1).any():
            same_day_groups += int((start_sizes > 1).sum())
            same_day_patients.update(group.loc[group["start_day"].isin(start_sizes[start_sizes > 1].index), "record_id"].astype(str))
        prev_end = math.nan
        for _, row in group.dropna(subset=["start_day"]).sort_values("start_day").iterrows():
            start = row["start_day"]
            if not math.isnan(prev_end) and start < prev_end:
                overlap_pairs += 1
                overlap_patients.add(str(row["record_id"]))
            if not pd.isna(row["end_all_day"]):
                prev_end = float(row["end_all_day"]) if math.isnan(prev_end) else max(prev_end, float(row["end_all_day"]))
    metrics["treatment_overlap_pairs_by_end_all"] = overlap_pairs
    metrics["treatment_overlap_patients_by_end_all"] = len(overlap_patients)
    metrics["same_day_multiple_regimen_start_groups"] = same_day_groups
    metrics["same_day_multiple_regimen_start_patients"] = len(same_day_patients)
    return metrics


def cpt_regimen_pair_quality(cpt: pd.DataFrame, regimen: pd.DataFrame) -> dict[str, int]:
    cpt_use = cpt.loc[cpt["report_interpretable"], KEY_CANCER + ["report_day"]]
    reg_use = regimen.loc[regimen["regimen_usable_start"], KEY_CANCER + ["start_day"]]
    pairs = reg_use.merge(cpt_use, on=KEY_CANCER, how="inner")
    same_day = pairs.loc[pairs["report_day"].eq(pairs["start_day"])]
    after = pairs.loc[pairs["report_day"].gt(pairs["start_day"])]
    return {
        "ngs_report_same_day_as_regimen_pairs": len(same_day),
        "ngs_report_same_day_as_regimen_patients": count_patients(same_day),
        "ngs_report_after_regimen_pairs": len(after),
        "ngs_report_after_regimen_patients": count_patients(after),
    }


def sample_count_distribution(cpt: pd.DataFrame) -> list[dict[str, Any]]:
    per_patient = cpt.groupby("record_id")["cpt_genie_sample_id"].nunique().reset_index(name="sample_count_per_patient")
    rows = []
    for sample_count, n_patients in per_patient["sample_count_per_patient"].value_counts().sort_index().items():
        rows.append({
            "sample_count_per_patient": int(sample_count),
            "n_patients": int(n_patients),
            "n_samples": int(sample_count) * int(n_patients),
            "note": "aggregate only; patient IDs suppressed",
        })
    return rows


def suppress_counts(series: pd.Series, threshold: int = 5, top_n: int = 12) -> list[tuple[str, int]]:
    counts = series.fillna("").replace("", "Missing/blank").value_counts(dropna=False)
    visible = []
    small_total = 0
    small_cats = 0
    for label, count in counts.items():
        count = int(count)
        if count < threshold:
            small_total += count
            small_cats += 1
        else:
            visible.append((str(label), count))
    visible = visible[:top_n]
    if small_cats:
        visible.append((f"Suppressed categories with n<{threshold} ({small_cats} categories)", small_total))
    return visible


def field_dictionary_evidence(repo_root: Path) -> list[dict[str, str]]:
    targets = {
        "ca_histology", "naaccr_histology_cd", "stage_dx_iv", "ca_dmets_yn",
        "dmets_post_dx", "dx_to_dmets_days", "ca_resect_status",
        "dx_cpt_rep_days", "dx_path_proc_cpt_days", "path_proc_cpt_rep_days", "cpt_seq_date",
        "dx_reg_start_int", "dx_reg_end_any_int", "dx_reg_end_all_int",
        "regimen_number", "regimen_number_within_cancer",
        "pfs_i_g_status", "pfs_m_g_status", "os_g_status",
        "hybrid_death_int", "dob_lastalive_int",
    }
    path = repo_root / "code" / "results" / "data_audit" / "tables" / "field_inventory.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    df = df[df["field_name"].isin(targets) & df["table_path"].str.contains("/clinical_data/", regex=False)]
    df = df.drop_duplicates(["field_name", "dictionary_label"]).sort_values("field_name")
    rows = []
    for _, row in df.iterrows():
        rows.append({
            "field_name": str(row["field_name"]),
            "dictionary_label": str(row["dictionary_label"]),
        })
    return rows

def build_outputs(repo_root: Path) -> dict[str, Any]:
    raw_root = repo_root / PANC_RELATIVE_ROOT
    data = prepare_data(raw_root)
    patient = data["patient"]
    cancer = annotate_advanced(annotate_pdac(data["cancer"], data["cpt"]))
    cpt = prepare_cpt(data["cpt"])
    regimen = prepare_regimen(data["regimen"])
    field_evidence = field_dictionary_evidence(repo_root)

    all_patients = patient_set(patient)
    pdac_patients = set(cancer.loc[cancer["pdac_compatible"], "record_id"].astype(str))
    adv_possible = advanced_possible_patients(cancer, regimen)
    ngs_time = patient_set(cpt.loc[cpt["ngs_usable_for_t0"]])

    flow_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    selected_by_def: dict[str, pd.DataFrame] = {}

    for definition in ["A", "B", "C"]:
        step1 = all_patients
        step2 = step1 & pdac_patients
        step3 = step2 & adv_possible
        step4 = step3 & ngs_time
        selected = selected_t0_for_definition(definition, step4, cancer, cpt, regimen)
        selected = evaluate_prior_reconstructability(selected, regimen)
        selected_by_def[definition] = selected
        step5 = set(selected["record_id"].astype(str))
        step6 = set(selected.loc[selected["prior_treatment_reconstructable"], "record_id"].astype(str))
        step7 = set(selected.loc[selected["prior_treatment_reconstructable"] & selected["has_evaluable_outcome"], "record_id"].astype(str))
        steps = [
            ("raw_patients", step1, "patient_level_dataset.record_id"),
            ("confirmed_pdac_compatible", step2, "ca_histology/naaccr_histology_cd and cpt_oncotree_code; feasibility proxy, not final label"),
            ("advanced_metastatic_recurrent_unresectable_evidence_before_possible_t0", step3, "Stage IV or distant metastasis at diagnosis, baseline unresectable/locally advanced/metastatic, or dated post-diagnosis distant metastasis before a regimen opportunity"),
            ("interpretable_ngs_report_time", step4, "dx_cpt_rep_days present; cancer association unambiguous; not flagged post-death or post-last-alive"),
            ("definition_matching_t0_regimen", step5, "selected regimen also requires advanced_evidence_day <= t0 start"),
            ("prior_treatment_reconstructable", step6, "regimen order/start history available and no same-day t0 regimen ambiguity"),
            ("post_t0_evaluable_outcome", step7, "regimen-level PFS/OS/TTNT status with non-negative time"),
        ]
        previous: set[str] | None = None
        for order, (step, patients_for_step, note) in enumerate(steps, start=1):
            flow_rows.append({
                "t0_definition": definition,
                "definition_label": DEFINITION_LABELS[definition],
                "step_order": order,
                "step": step,
                "n_patients": len(patients_for_step),
                "excluded_from_previous": "" if previous is None else len(previous - patients_for_step),
                "notes": note,
            })
            previous = patients_for_step
        comparison_rows.append({
            "t0_definition": definition,
            "definition_label": DEFINITION_LABELS[definition],
            "usable_patients": len(step7),
            "raw_patients": len(step1),
            "confirmed_pdac_compatible": len(step2),
            "advanced_before_possible_t0": len(step3),
            "interpretable_ngs_report_time": len(step4),
            "definition_matching_t0_regimen": len(step5),
            "prior_treatment_reconstructable": len(step6),
            "post_t0_evaluable_outcome": len(step7),
            "main_exclusion_counts": (
                f"non_pdac={len(step1-step2)}; no_advanced_evidence={len(step2-step3)}; "
                f"no_usable_ngs_time={len(step3-step4)}; no_definition_t0={len(step4-step5)}; "
                f"prior_unreconstructable={len(step5-step6)}; no_post_t0_outcome={len(step6-step7)}"
            ),
            "caution": "Counts are feasibility estimates only; do not select t0 definition without manual review.",
        })

    per_patient_samples = cpt.groupby("record_id")["cpt_genie_sample_id"].nunique()
    quality_rows: list[dict[str, Any]] = []
    def add_metric(metric: str, value: Any, numerator: Any = "", denominator: Any = "", note: str = "") -> None:
        quality_rows.append({"metric": metric, "value": value, "numerator": numerator, "denominator": denominator, "note": note})

    add_metric("patient_level_unique_record_id", len(all_patients), note="Expected 1109 from first audit")
    add_metric("cpt_rows", len(cpt), note="Cancer panel test records")
    add_metric("cpt_unique_sample_ids", cpt["cpt_genie_sample_id"].nunique(), note="Expected 1130 samples")
    add_metric("patients_with_multiple_ngs_samples", int((per_patient_samples > 1).sum()), note="Expected 20 multi-NGS patients")
    add_metric("max_ngs_samples_per_patient", int(per_patient_samples.max()))
    add_metric("cpt_missing_report_day_rows", int(cpt["report_day"].isna().sum()), int(cpt["report_day"].isna().sum()), len(cpt))
    add_metric("cpt_missing_pathology_procedure_day_rows", int(cpt["path_proc_day"].isna().sum()), int(cpt["path_proc_day"].isna().sum()), len(cpt))
    add_metric("cpt_order_date_dob_based_missing_rows", int(cpt["cpt_order_dob_day"].isna().sum()), note="Order date is DOB-relative, not diagnosis-relative")
    add_metric("cpt_ambiguous_cancer_association_rows", int(cpt["ngs_ambiguous_cancer"].sum()), note="cpt_n_ca_seq > 1")
    add_metric("cpt_report_post_death_rows", int(cpt["report_after_death_flag"].sum()), note="Excluded from usable NGS time")
    add_metric("cpt_report_post_last_alive_rows", int(cpt["report_after_last_alive_flag"].sum()), note="Excluded from usable NGS time")
    for name, value in regimen_timeline_quality(regimen).items():
        add_metric(name, value)
    for name, value in cpt_regimen_pair_quality(cpt, regimen).items():
        add_metric(name, value)
    add_metric("date_granularity", "day intervals relative to cancer diagnosis for key t0 fields; exact calendar dates masked", note="cpt_seq_date is year only")
    add_metric("recurrence_field_status", "no explicit recurrence field found by keyword scan in clinical_data column names", note="Post-diagnosis distant metastasis fields are available")
    for definition, selected in selected_by_def.items():
        add_metric(f"definition_{definition}_selected_t0_patients", len(selected), note=DEFINITION_LABELS[definition])
        add_metric(f"definition_{definition}_same_day_t0_regimen_ambiguity_patients", int(selected.get("same_day_t0_regimen_ambiguity", pd.Series(dtype=bool)).sum()))
        add_metric(f"definition_{definition}_prior_overlap_with_t0_patients", int(selected.get("prior_overlap_with_t0", pd.Series(dtype=bool)).sum()))
        add_metric(f"definition_{definition}_post_t0_evaluable_outcome_patients", int(selected.get("has_evaluable_outcome", pd.Series(dtype=bool)).sum()))

    tables_dir = repo_root / "reports" / "tables"
    write_csv(tables_dir / "cohort_flow_counts.csv", flow_rows, ["t0_definition", "definition_label", "step_order", "step", "n_patients", "excluded_from_previous", "notes"])
    write_csv(tables_dir / "t0_definition_comparison.csv", comparison_rows, ["t0_definition", "definition_label", "usable_patients", "raw_patients", "confirmed_pdac_compatible", "advanced_before_possible_t0", "interpretable_ngs_report_time", "definition_matching_t0_regimen", "prior_treatment_reconstructable", "post_t0_evaluable_outcome", "main_exclusion_counts", "caution"])
    write_csv(tables_dir / "ngs_sample_count_distribution.csv", sample_count_distribution(cpt), ["sample_count_per_patient", "n_patients", "n_samples", "note"])
    write_csv(tables_dir / "timeline_quality_summary.csv", quality_rows, ["metric", "value", "numerator", "denominator", "note"])

    hist_counts = suppress_counts(cancer["ca_histology"])
    oncotree_counts = suppress_counts(cpt["cpt_oncotree_code"])
    stage_counts = suppress_counts(cancer["stage_dx_iv"])
    resect_counts = suppress_counts(cancer["ca_resect_status"])
    report_path = repo_root / "reports" / "cohort_t0_feasibility_v1.md"
    lines = [
        "# Cohort and t0 Feasibility Audit v1",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Raw data root: `{PANC_RELATIVE_ROOT.as_posix()}`",
        "",
        "Scope: read-only feasibility audit. No modeling, no final labels, no patient-level records in outputs.",
        "",
        "## Documents Reviewed",
        "",
        "- README.md and README.zh-CN.md",
        "- docs/notes/data_feasibility_audit_v1.md",
        "- docs/notes/research_plan_pdac_treatment_benchmark_v3.0.docx",
        f"- PANC analytic data guide: {data_guide_status(raw_root)}",
        "- PANC variable synopsis workbook was present and used to confirm requested field names against clinical_data columns.",
        "",
        "## Data-Guide Confirmed Relationships",
        "",
        "- Patient Characteristics: one record per patient; link to all datasets with cohort + record_id.",
        "- BPC Project Cancer Diagnosis: link to Cancer-Directed Regimen, Cancer Panel Test, and Radiation Therapy with cohort + record_id + ca_seq.",
        "- BPC Project Cancer Diagnosis: link to Patient, Pathology, Imaging, Medical Oncologist Assessment, and Tumor Marker datasets with cohort + record_id.",
        "- Pathology to Cancer Panel Test: link with cohort + record_id + path_proc_number + path_rep_number.",
        "- cpt_genie_sample_id corresponds to Tier 1 sample_id; it is used here only for aggregate sample-count checks.",
        "",
        "## Key Field Confirmation",
        "",
        "- PDAC histology: no final PDAC boolean exists. Candidate fields are ca_histology, naaccr_histology_cd, and cpt_oncotree_code. This audit uses a PDAC-compatible feasibility flag: adenocarcinoma/ductal-like histology or OncoTree PAAD; manual confirmation is required.",
        "- Advanced/metastatic/unresectable: stage_dx_iv, ca_dmets_yn, ca_resect_status, dmets_post_dx, dx_to_dmets_days.",
        "- Recurrence: no explicit recurrence field was found in clinical_data column names; dated post-diagnosis distant metastasis is available.",
        "- NGS timing: dx_path_proc_cpt_days, dx_cpt_rep_days, path_proc_cpt_rep_days, cpt_seq_date year only.",
        "- Regimen timing/order: dx_reg_start_int, dx_reg_end_any_int, dx_reg_end_all_int, regimen_number, regimen_number_within_cancer.",
        "- Outcomes/follow-up: regimen-level pfs_*_g_status, tt_pfs_*_g_days, os_g_status, tt_os_g_days, ttnt_*; patient-level hybrid_death_int and dob_lastalive_int are outcome/follow-up fields, not t0 inputs.",
        "",
        "## 1109/1130/20 Consistency Check",
        "",
        f"- Unique patients: {len(all_patients)}",
        f"- Unique NGS samples: {cpt['cpt_genie_sample_id'].nunique()}",
        f"- Patients with >1 NGS sample: {int((per_patient_samples > 1).sum())}",
        f"- Maximum NGS samples per patient: {int(per_patient_samples.max())}",
        "- Aggregated distribution: reports/tables/ngs_sample_count_distribution.csv",
        "",
        "## Aggregate Distributions",
        "",
        "### Histology, rare categories suppressed",
    ]
    if field_evidence:
        insert_at = lines.index("## 1109/1130/20 Consistency Check")
        dict_lines = [
            "## Variable Dictionary Evidence",
            "",
            "Source: code/results/data_audit/tables/field_inventory.csv parsed from the PANC Variable Synopsis workbook during the first audit.",
            "",
            "| Field | Dictionary label |",
            "|---|---|",
        ]
        for row in field_evidence:
            label = ascii_clean(re.sub(r"\s+", " ", row["dictionary_label"]).strip())
            dict_lines.append(f"| `{row['field_name']}` | {label} |")
        dict_lines.append("")
        lines[insert_at:insert_at] = dict_lines
    for label, count in hist_counts:
        lines.append(f"- {label}: {count}")
    lines.extend(["", "### OncoTree, rare categories suppressed"])
    for label, count in oncotree_counts:
        lines.append(f"- {label}: {count}")
    lines.extend(["", "### Stage IV grouping"])
    for label, count in stage_counts:
        lines.append(f"- {label}: {count}")
    lines.extend(["", "### Resectability"])
    for label, count in resect_counts:
        lines.append(f"- {label}: {count}")
    lines.extend([
        "",
        "## t0 Definition Comparison",
        "",
        "Definitions are compared only; no definition is selected.",
        "",
        "| Definition | Matching t0 regimen | Prior reconstructable | Post-t0 evaluable outcome | Usable patients |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in comparison_rows:
        lines.append(f"| {row['t0_definition']} | {row['definition_matching_t0_regimen']} | {row['prior_treatment_reconstructable']} | {row['post_t0_evaluable_outcome']} | {row['usable_patients']} |")
    lines.extend(["", "Full flow: reports/tables/cohort_flow_counts.csv", "Full comparison: reports/tables/t0_definition_comparison.csv", "", "## Main Exclusion Reasons"])
    for row in comparison_rows:
        lines.append(f"- Definition {row['t0_definition']}: {row['main_exclusion_counts']}")
    lines.extend([
        "",
        "## Timeline Quality and Leakage Risks",
        "",
        "See reports/tables/timeline_quality_summary.csv for aggregate metrics.",
        "- Same-day NGS report and regimen start affects A vs B.",
        "- Regimen end, PFS, OS, TTNT, death, and last-alive fields are post-t0/outcome fields and must be excluded from t0 inputs.",
        "- Exact dates are masked; key comparisons use day intervals from associated cancer diagnosis.",
        "- cpt_seq_date is year-level only and should not substitute for dx_cpt_rep_days.",
        "- cpt_report_post_death and cpt_report_post_last_alive are excluded from usable NGS timing.",
        "- Treatment overlap and same-day regimen starts require manual review before locking cohort definitions.",
        "",
        "## Manual Confirmation Needed",
        "",
        "- Final PDAC histology inclusion/exclusion mapping from ca_histology, naaccr_histology_cd, and OncoTree codes.",
        "- Whether same-day report and regimen start should be considered clinically available information.",
        "- Whether regimen_number_within_cancer is sufficient as a line-of-therapy proxy.",
        "- How to handle post-diagnosis metastatic disease because recurrence-specific fields were not found.",
        "- Whether same-day multiple regimen starts or treatment overlaps should be excluded or adjudicated.",
        "- Which endpoint should define post-t0 evaluability: PFS-I, PFS-M, OS, TTNT, or a composite.",
    ])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "raw_patients": len(all_patients),
        "unique_samples": int(cpt["cpt_genie_sample_id"].nunique()),
        "multi_ngs_patients": int((per_patient_samples > 1).sum()),
        "comparison": comparison_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only cohort/t0 feasibility audit for BPC PANC")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = find_repo_root(args.repo_root or Path.cwd())
    result = build_outputs(repo_root)
    print("cohort_t0_audit_complete")
    print(f"repo_root={repo_root}")
    print(f"raw_patients={result['raw_patients']}")
    print(f"unique_samples={result['unique_samples']}")
    print(f"multi_ngs_patients={result['multi_ngs_patients']}")
    for row in result["comparison"]:
        print(f"definition_{row['t0_definition']}: t0={row['definition_matching_t0_regimen']} prior={row['prior_treatment_reconstructable']} outcome={row['post_t0_evaluable_outcome']} usable={row['usable_patients']}")


if __name__ == "__main__":
    main()