"""Round 3 cohort lock and label feasibility audit for BPC PANC.

The script reads raw BPC PANC data in read-only mode and writes public
aggregate outputs plus an ignored local pilot-review file. It does not train
models, build RAG/agents, or construct final labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import audit_cohort_t0_feasibility as t0audit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PANC_RELATIVE_ROOT = t0audit.PANC_RELATIVE_ROOT
KEY_PATIENT = t0audit.KEY_PATIENT
KEY_CANCER = t0audit.KEY_CANCER
INSTITUTION_ID_PATTERN = re.compile(r"GENIE-(DFCI|MSK|UHN|VICC)-", re.IGNORECASE)

PDAC_INCLUDE_HIST_CODES = {"8140", "81403", "8500", "85003", "8211", "82603"}
PDAC_EXCLUDE_HIST_CODES = {"8550", "85503", "8154", "8244", "8070", "80703"}
PDAC_INCLUDE_ONCOTREE = {"PAAD"}
PDAC_EXCLUDE_ONCOTREE = {"PAAC", "UCP"}
PDAC_MANUAL_ONCOTREE = {"PAASC"}

IMMUNO_DRUGS = {"pembrolizumab", "nivolumab", "ipilimumab", "atezolizumab", "avelumab", "durvalumab"}
PARP_DRUGS = {"olaparib", "rucaparib", "niraparib", "talazoparib"}
TARGETED_DRUGS = {"erlotinib", "trametinib", "cobimetinib", "imatinib", "cetuximab", "trastuzumab"}
ENDOCRINE_DRUGS = {"anastrozole", "tamoxifen", "exemestane", "letrozole", "leuprolide", "bicalutamide", "fulvestrant"}

ENDPOINTS = [
    ("OS", "os_g_status", "tt_os_g_days", "regimen start", "Death or censoring from regimen start"),
    ("PFS-I", "pfs_i_g_status", "tt_pfs_i_g_days", "regimen start", "Radiology progression/death or censoring from regimen start"),
    ("PFS-M", "pfs_m_g_status", "tt_pfs_m_g_days", "regimen start", "Medical oncology assessment progression/death or censoring from regimen start"),
    ("TTNT-any-cancer", "ttnt_any_ca_status", "ttnt_any_ca_days", "regimen start", "Next treatment for any cancer or censoring"),
    ("TTNT-associated-cancer", "ttnt_ca_seq_status", "ttnt_ca_seq_days", "regimen start", "Next treatment for associated cancer or censoring"),
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def norm_code(value: Any) -> str:
    return clean_text(value).upper().replace(".", "")


def patient_count(df: pd.DataFrame) -> int:
    return t0audit.count_patients(df)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    t0audit.write_csv(path, rows, fieldnames)


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def aggregate_status(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).sort_index().items()}


def load_data(repo_root: Path) -> dict[str, pd.DataFrame]:
    data = t0audit.prepare_data(repo_root / PANC_RELATIVE_ROOT)
    data["cancer"] = t0audit.annotate_advanced(data["cancer"])
    data["cpt"] = t0audit.prepare_cpt(data["cpt"])
    data["regimen"] = t0audit.prepare_regimen(data["regimen"])
    return data


def oncotree_by_cancer(cpt: pd.DataFrame) -> pd.DataFrame:
    usable = cpt.loc[t0audit.nonmissing(cpt["cpt_oncotree_code"]), KEY_CANCER + ["cpt_oncotree_code"]].copy()
    usable["cpt_oncotree_code"] = usable["cpt_oncotree_code"].astype(str).str.upper().str.strip()
    grouped = usable.groupby(KEY_CANCER, dropna=False)["cpt_oncotree_code"].agg(lambda s: ";".join(sorted(set(s)))).reset_index()
    grouped = grouped.rename(columns={"cpt_oncotree_code": "all_oncotree_codes"})
    return grouped


def classify_pdac(ca_type: str, site: str, redcap_index: str, histology: str, hist_code: str, oncotree_codes: set[str]) -> tuple[str, str]:
    ca_type_l = clean_text(ca_type).lower()
    site_u = clean_text(site).upper()
    index_l = clean_text(redcap_index).lower()
    hist_l = clean_text(histology).lower()
    hist_code_u = norm_code(hist_code)
    if ca_type_l != "pancreatic cancer" or not site_u.startswith("C25") or index_l != "yes":
        return "exclude", "Not an index pancreatic primary site record by ca_type/ca_d_site/redcap_ca_index."
    if oncotree_codes & PDAC_INCLUDE_ONCOTREE and not (oncotree_codes - PDAC_INCLUDE_ONCOTREE):
        return "include", "OncoTree PAAD with pancreatic index cancer."
    if oncotree_codes & PDAC_INCLUDE_ONCOTREE and (oncotree_codes - PDAC_INCLUDE_ONCOTREE):
        return "manual_review", "Conflicting OncoTree codes include PAAD and non-PAAD values."
    if oncotree_codes & PDAC_MANUAL_ONCOTREE:
        return "manual_review", "OncoTree PAASC/adeno-squamous mapping requires medical review."
    if oncotree_codes & PDAC_EXCLUDE_ONCOTREE:
        return "exclude", "OncoTree indicates non-PDAC pancreatic subtype (PAAC/UCP)."
    if not hist_l and not hist_code_u:
        return "insufficient_info", "No usable histology code/text and no informative OncoTree code."
    if hist_code_u in PDAC_INCLUDE_HIST_CODES or ("adenocarcinoma" in hist_l and not any(x in hist_l for x in ["acinar", "adenosquamous", "neuroendocrine", "mixed islet"])):
        return "include", "Histology code/text is adenocarcinoma-compatible for draft PDAC mapping."
    if hist_code_u in PDAC_EXCLUDE_HIST_CODES or any(x in hist_l for x in ["acinar", "carcinoid", "squamous", "sarcoma", "anaplastic"]):
        return "exclude", "Histology suggests non-ductal pancreatic subtype."
    return "manual_review", "Pancreatic index cancer but histology/OncoTree is ambiguous for PDAC."


def annotate_pdac_mapping(cancer: pd.DataFrame, cpt: pd.DataFrame) -> pd.DataFrame:
    cancer = cancer.copy().merge(oncotree_by_cancer(cpt), on=KEY_CANCER, how="left")
    cancer["all_oncotree_codes"] = cancer["all_oncotree_codes"].fillna("")
    statuses = []
    reasons = []
    for _, row in cancer.iterrows():
        codes = {c for c in str(row["all_oncotree_codes"]).split(";") if c}
        status, reason = classify_pdac(row["ca_type"], row["ca_d_site"], row["redcap_ca_index"], row["ca_histology"], row["naaccr_histology_cd"], codes)
        statuses.append(status)
        reasons.append(reason)
    cancer["pdac_mapping_status"] = statuses
    cancer["pdac_mapping_reason"] = reasons
    cancer["index_pancreatic_primary"] = (
        cancer["ca_type"].map(clean_text).str.lower().eq("pancreatic cancer")
        & cancer["ca_d_site"].map(clean_text).str.upper().str.startswith("C25")
        & cancer["redcap_ca_index"].map(clean_text).str.lower().eq("yes")
    )
    return cancer

def select_t0_candidates(data: dict[str, pd.DataFrame], base_patients: set[str], allow_same_day: bool = False) -> pd.DataFrame:
    cancer = data["cancer"]
    cpt = data["cpt"]
    regimen = data["regimen"]
    reg = regimen.loc[regimen["regimen_usable_start"] & regimen["record_id"].isin(base_patients)].copy()
    cpt_use = cpt.loc[cpt["ngs_usable_for_t0"], KEY_CANCER + ["report_day", "path_proc_day", "cpt_number", "cpt_genie_sample_id", "cpt_oncotree_code"]].copy()
    adv = cancer.loc[cancer["advanced_evidence_available"], KEY_CANCER + ["advanced_evidence_day", "advanced_stage_iv_dx", "advanced_dmets_dx", "advanced_unresectable_baseline", "advanced_dmets_post_dx_dated"]]
    pairs = reg.merge(cpt_use, on=KEY_CANCER, how="inner")
    pairs = pairs.loc[pairs["report_day"].le(pairs["start_day"])] if allow_same_day else pairs.loc[pairs["report_day"].lt(pairs["start_day"])]
    pairs = pairs.merge(adv, on=KEY_CANCER, how="left")
    pairs = pairs.loc[pairs["advanced_evidence_day"].notna() & pairs["advanced_evidence_day"].le(pairs["start_day"])]
    if pairs.empty:
        return pairs
    t0_rows = pairs.sort_values(["record_id", "start_day", "regimen_number_num", "ca_seq", "report_day"], kind="mergesort").groupby("record_id", as_index=False).head(1)
    return t0_rows.copy()


def attach_index_ngs(selected: pd.DataFrame, cpt: pd.DataFrame, strategy: str = "latest_strict_before_t0") -> pd.DataFrame:
    selected = selected.copy()
    if selected.empty:
        return selected
    cpt_use = cpt.loc[cpt["ngs_usable_for_t0"], KEY_CANCER + ["report_day", "path_proc_day", "cpt_number", "cpt_genie_sample_id", "cpt_oncotree_code"]].copy()
    cpt_use = cpt_use.rename(columns={
        "report_day": "index_ngs_report_day",
        "path_proc_day": "index_ngs_path_proc_day",
        "cpt_number": "index_ngs_cpt_number",
        "cpt_genie_sample_id": "index_ngs_sample_id",
        "cpt_oncotree_code": "index_ngs_oncotree_code",
    })
    base = selected[KEY_CANCER + ["start_day"]].drop_duplicates()
    pairs = base.merge(cpt_use, on=KEY_CANCER, how="inner")
    pairs = pairs.loc[pairs["index_ngs_report_day"].lt(pairs["start_day"])]
    if strategy == "latest_strict_before_t0":
        pairs = pairs.sort_values(["record_id", "start_day", "index_ngs_report_day", "index_ngs_cpt_number"], ascending=[True, True, False, False], kind="mergesort")
    elif strategy == "earliest_strict_before_t0":
        pairs = pairs.sort_values(["record_id", "start_day", "index_ngs_report_day", "index_ngs_cpt_number"], ascending=[True, True, True, True], kind="mergesort")
    elif strategy == "latest_sample_before_t0":
        pairs = pairs.loc[pairs["index_ngs_path_proc_day"].notna() & pairs["index_ngs_path_proc_day"].le(pairs["start_day"])]
        pairs = pairs.sort_values(["record_id", "start_day", "index_ngs_path_proc_day", "index_ngs_report_day"], ascending=[True, True, False, False], kind="mergesort")
    else:
        raise ValueError(strategy)
    idx = pairs.groupby(["record_id", "start_day"], as_index=False).head(1)
    return selected.drop(columns=[c for c in selected.columns if c.startswith("index_ngs_")], errors="ignore").merge(idx, on=KEY_CANCER + ["start_day"], how="left")


def reproduce_round2_counts(data: dict[str, pd.DataFrame], patient: pd.DataFrame) -> list[dict[str, Any]]:
    cancer_compat = t0audit.annotate_pdac(data["cancer"], data["cpt"])
    cpt = data["cpt"]
    regimen = data["regimen"]
    all_patients = t0audit.patient_set(patient)
    pdac_patients = set(cancer_compat.loc[cancer_compat["pdac_compatible"], "record_id"].astype(str))
    adv_possible = t0audit.advanced_possible_patients(cancer_compat, regimen)
    ngs_time = t0audit.patient_set(cpt.loc[cpt["ngs_usable_for_t0"]])
    rows = []
    for definition in ["A", "B", "C"]:
        step4 = all_patients & pdac_patients & adv_possible & ngs_time
        selected = t0audit.selected_t0_for_definition(definition, step4, cancer_compat, cpt, regimen)
        selected = t0audit.evaluate_prior_reconstructability(selected, regimen)
        usable = int((selected["prior_treatment_reconstructable"] & selected["has_evaluable_outcome"]).sum()) if not selected.empty else 0
        rows.append({"definition": definition, "recomputed_usable_patients": usable, "recomputed_t0_patients": len(selected)})
    return rows


def drug_tokens(regimen_drugs: str) -> set[str]:
    raw = clean_text(regimen_drugs).lower()
    return {token.strip() for token in re.split(r",|/|\+|;", raw) if token.strip()}


def contains_any(text: str, needles: set[str]) -> bool:
    lower = clean_text(text).lower()
    return any(needle in lower for needle in needles)


def standardize_regimen(regimen_drugs: str) -> tuple[str, str]:
    text = clean_text(regimen_drugs)
    lower = text.lower()
    has = lambda s: s in lower
    if not text:
        return "missing_regimen", "manual_review"
    if "investigational drug" in lower:
        return "investigational_or_masked", "masked_not_actionable"
    if contains_any(lower, PARP_DRUGS):
        return "PARP_inhibitor", "standardized"
    if contains_any(lower, IMMUNO_DRUGS):
        return "immune_checkpoint_inhibitor", "standardized"
    if has("fluorouracil") and has("irinotecan") and has("oxaliplatin"):
        return "FOLFIRINOX_or_variant", "standardized"
    if has("gemcitabine") and has("nabpaclitaxel"):
        return "gemcitabine_nab_paclitaxel", "standardized"
    if has("cisplatin") and has("gemcitabine"):
        return "gemcitabine_cisplatin", "standardized"
    if has("gemcitabine") and has("oxaliplatin"):
        return "gemcitabine_oxaliplatin", "standardized"
    if has("capecitabine") and has("gemcitabine"):
        return "gemcitabine_capecitabine", "standardized"
    if has("erlotinib") and has("gemcitabine"):
        return "gemcitabine_erlotinib", "standardized"
    if has("gemcitabine") and not any(has(x) for x in ["cisplatin", "oxaliplatin", "capecitabine", "nabpaclitaxel", "erlotinib"]):
        return "gemcitabine_monotherapy_or_other_gemcitabine", "standardized"
    if has("fluorouracil") and has("oxaliplatin"):
        return "FOLFOX_or_variant", "standardized"
    if has("capecitabine") and has("oxaliplatin"):
        return "CAPOX", "standardized"
    if has("fluorouracil") and has("irinotecan"):
        return "FOLFIRI_or_5FU_nalIRI_variant", "standardized"
    if has("fluorouracil") and has("leucovorin"):
        return "5FU_leucovorin", "standardized"
    if has("capecitabine") and len(drug_tokens(lower)) == 1:
        return "capecitabine_monotherapy", "standardized"
    if contains_any(lower, TARGETED_DRUGS):
        return "targeted_or_biologic_other", "manual_review"
    if contains_any(lower, ENDOCRINE_DRUGS):
        return "non_pdac_context_or_endocrine", "manual_review"
    if lower == "other nos":
        return "other_nos", "manual_review"
    return "manual_review_other_regimen", "manual_review"


def annotate_regimen_standardization(regimen: pd.DataFrame) -> pd.DataFrame:
    regimen = regimen.copy()
    cats = []
    statuses = []
    for value in regimen["regimen_drugs"]:
        cat, status = standardize_regimen(value)
        cats.append(cat)
        statuses.append(status)
    regimen["observed_next_regimen"] = cats
    regimen["regimen_mapping_status"] = statuses
    return regimen


def attach_regimen_standardization(selected: pd.DataFrame, regimen_std: pd.DataFrame) -> pd.DataFrame:
    keys = KEY_CANCER + ["regimen_number", "regimen_number_within_cancer", "start_day"]
    cols = keys + ["observed_next_regimen", "regimen_mapping_status"]
    selected = selected.drop(columns=["observed_next_regimen", "regimen_mapping_status"], errors="ignore")
    return selected.merge(regimen_std[cols].drop_duplicates(), on=keys, how="left")


def sequence_quality_for_selected(selected: pd.DataFrame, regimen: pd.DataFrame) -> pd.DataFrame:
    selected = selected.copy()
    flags = defaultdict(list)
    grouped = {key: group.copy() for key, group in regimen.loc[regimen["regimen_usable_start"]].groupby(KEY_CANCER, dropna=False)}
    for _, row in selected.iterrows():
        key = tuple(row[col] for col in KEY_CANCER)
        group = grouped.get(key, pd.DataFrame())
        t0_start = row["start_day"]
        hist = group.loc[group["start_day"].le(t0_start)].copy() if not group.empty else pd.DataFrame()
        same_day = group.loc[group["start_day"].eq(t0_start)] if not group.empty else pd.DataFrame()
        prior = group.loc[group["start_day"].lt(t0_start)] if not group.empty else pd.DataFrame()
        flags["n_prior_regimens"].append(int(len(prior)))
        flags["line_number_present"].append(bool(not hist.empty and t0audit.nonmissing(hist["regimen_number_within_cancer"]).all()))
        flags["same_day_multiple_t0_regimens"].append(bool(len(same_day[["regimen_number", "regimen_drugs"]].drop_duplicates()) > 1) if not same_day.empty else False)
        duplicate_cols = ["regimen_number", "regimen_drugs", "dx_reg_start_int"]
        flags["duplicate_regimen_records_before_t0"].append(bool(hist.duplicated(duplicate_cols).any()) if not hist.empty else False)
        flags["end_before_start_before_t0"].append(bool(((hist["end_all_day"].notna()) & (hist["end_all_day"].lt(hist["start_day"]))).any()) if not hist.empty else False)
        flags["prior_overlap_with_t0"].append(bool((prior["end_all_day"].notna() & prior["end_all_day"].gt(t0_start)).any()) if not prior.empty else False)
        if hist.empty:
            flags["line_start_order_consistent"].append(False)
        else:
            ordered = hist.sort_values(["regimen_number_within_cancer_num", "start_day"], kind="mergesort")
            starts = list(ordered["start_day"])
            flags["line_start_order_consistent"].append(all(starts[i] <= starts[i + 1] for i in range(len(starts) - 1)))
    for key, values in flags.items():
        selected[key] = values
    clean = (
        selected["line_number_present"]
        & ~selected["same_day_multiple_t0_regimens"]
        & ~selected["duplicate_regimen_records_before_t0"]
        & ~selected["end_before_start_before_t0"]
        & ~selected["prior_overlap_with_t0"]
        & selected["line_start_order_consistent"]
    )
    selected["treatment_sequence_clean"] = clean
    return selected

def endpoint_coverage_rows(cohort_name: str, selected: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    n = len(selected)
    for endpoint, status_col, time_col, origin, definition in ENDPOINTS:
        if selected.empty:
            status_nonmissing = event = censored = time_nonmissing = negative = zero = evaluable = 0
        else:
            status = selected[status_col] if status_col in selected.columns else pd.Series([], dtype=str)
            time = t0audit.numeric(selected[time_col]) if time_col in selected.columns else pd.Series([], dtype=float)
            status_nonmissing = int(t0audit.nonmissing(status).sum())
            event = int(status.astype(str).str.strip().isin(["1", "1.0"]).sum())
            censored = int(status.astype(str).str.strip().isin(["0", "0.0"]).sum())
            time_nonmissing = int(time.notna().sum())
            negative = int(time.lt(0).sum())
            zero = int(time.eq(0).sum())
            evaluable = int((t0audit.nonmissing(status) & time.notna() & time.ge(0)).sum())
        rows.append({
            "cohort": cohort_name,
            "endpoint": endpoint,
            "status_field": status_col,
            "time_field": time_col,
            "time_origin": origin,
            "endpoint_definition": definition,
            "cohort_n": n,
            "status_nonmissing_n": status_nonmissing,
            "event_n": event,
            "censored_n": censored,
            "time_nonmissing_n": time_nonmissing,
            "negative_time_n": negative,
            "zero_time_n": zero,
            "evaluable_n": evaluable,
            "usable_from_t0": "yes" if evaluable > 0 and negative == 0 else "needs_review",
            "note": "Endpoint-specific only; base cohort does not require outcome availability.",
        })
    return rows


def mapping_summary_rows(cancer: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for field in ["ca_type", "ca_d_site", "ca_histology", "naaccr_histology_cd", "all_oncotree_codes"]:
        values = cancer[field].fillna("").replace("", "Missing/blank")
        counts = values.value_counts(dropna=False)
        for value, count in counts.items():
            count = int(count)
            if count < 5:
                continue
            subset = cancer.loc[values.eq(value)]
            status_counts = subset["pdac_mapping_status"].value_counts().to_dict()
            rows.append({
                "source_field": field,
                "source_value": value,
                "n_index_cancer_records": count,
                "n_patients": patient_count(subset),
                "include_n": int(status_counts.get("include", 0)),
                "exclude_n": int(status_counts.get("exclude", 0)),
                "manual_review_n": int(status_counts.get("manual_review", 0)),
                "insufficient_info_n": int(status_counts.get("insufficient_info", 0)),
                "rule_status": "aggregate_value_mapping",
            })
        rare = int(counts[counts < 5].sum())
        if rare:
            rows.append({
                "source_field": field,
                "source_value": "suppressed_rare_values_n_lt_5",
                "n_index_cancer_records": rare,
                "n_patients": "suppressed",
                "include_n": "suppressed",
                "exclude_n": "suppressed",
                "manual_review_n": "suppressed",
                "insufficient_info_n": "suppressed",
                "rule_status": "rare_categories_suppressed",
            })
    rule_rows = [
        ("rule", "OncoTree PAAD + pancreatic index primary", "include", "Draft include"),
        ("rule", "OncoTree PAAC/UCP + pancreatic index primary", "exclude", "Non-PDAC pancreatic subtype"),
        ("rule", "OncoTree PAASC + pancreatic index primary", "manual_review", "Adenosquamous requires medical review"),
        ("rule", "No OncoTree but adenocarcinoma-compatible histology/code", "include", "Fallback only when OncoTree not informative"),
        ("rule", "Pancreatic primary but ambiguous histology/code", "manual_review", "Do not infer"),
        ("rule", "Missing OncoTree and histology/code", "insufficient_info", "Not enough information"),
    ]
    for field, value, status, note in rule_rows:
        rows.append({
            "source_field": field,
            "source_value": value,
            "n_index_cancer_records": "",
            "n_patients": "",
            "include_n": "",
            "exclude_n": "",
            "manual_review_n": "",
            "insufficient_info_n": "",
            "rule_status": f"{status}: {note}",
        })
    return rows


def regimen_mapping_rows(regimen_std: pd.DataFrame, t0_selected: pd.DataFrame) -> list[dict[str, Any]]:
    t0_counts = t0_selected["regimen_drugs"].value_counts(dropna=False).to_dict() if not t0_selected.empty else {}
    rows = []
    counts = regimen_std["regimen_drugs"].replace("", "Missing/blank").value_counts(dropna=False)
    for raw_value, count in counts.items():
        count = int(count)
        if count < 5:
            continue
        cat, status = standardize_regimen(raw_value if raw_value != "Missing/blank" else "")
        rows.append({
            "raw_regimen_drugs": raw_value,
            "observed_next_regimen": cat,
            "mapping_status": status,
            "n_all_regimen_rows": count,
            "n_definition_A_t0_rows": int(t0_counts.get(raw_value, 0)),
            "note": "Mapping is descriptive; not best treatment or gold standard.",
        })
    rare = int(counts[counts < 5].sum())
    if rare:
        rows.append({
            "raw_regimen_drugs": "suppressed_rare_regimen_values_n_lt_5",
            "observed_next_regimen": "manual_review_other_regimen",
            "mapping_status": "manual_review",
            "n_all_regimen_rows": rare,
            "n_definition_A_t0_rows": "suppressed",
            "note": "Rare treatment strings suppressed from public output.",
        })
    return rows


def label_availability_rows(extended: pd.DataFrame, core: pd.DataFrame, endpoint_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    endpoint_summary = {r["endpoint"]: r for r in endpoint_rows if r["cohort"] == "Extended draft"}
    std_n = int(extended["regimen_mapping_status"].eq("standardized").sum()) if not extended.empty else 0
    masked_n = int(extended["regimen_mapping_status"].eq("masked_not_actionable").sum()) if not extended.empty else 0
    review_n = int(extended["regimen_mapping_status"].eq("manual_review").sum()) if not extended.empty else 0
    rows = [
        {
            "label_family": "observed_next_regimen",
            "availability": "available_as_observed_data",
            "extended_n": len(extended),
            "core_n": len(core),
            "limitations": f"Descriptive next observed regimen only; standardized={std_n}; masked_investigational={masked_n}; manual_review={review_n}; not a gold standard or optimal treatment label.",
        },
        {
            "label_family": "evidence_supported_candidate_set",
            "availability": "not_available_from_BPC_alone",
            "extended_n": 0,
            "core_n": 0,
            "limitations": "Requires external evidence snapshot, candidate treatment space, clinical constraints, and manual/structured evidence labels. Do not derive by assuming observed regimen is evidence-supported.",
        },
        {
            "label_family": "post_t0_outcome",
            "availability": "endpoint_specific_available",
            "extended_n": len(extended),
            "core_n": len(core),
            "limitations": "; ".join(f"{ep} evaluable={row['evaluable_n']}" for ep, row in endpoint_summary.items()),
        },
    ]
    return rows


def field_leakage_rows() -> list[dict[str, Any]]:
    return [
        {"table": "patient_level_dataset", "field": "record_id/cohort", "role": "technical_key", "available_at_t0": "conditional", "allowed_as_model_input": "no", "rationale": "Join key only; patient ID must not enter features."},
        {"table": "patient_level_dataset", "field": "institution", "role": "source/context", "available_at_t0": "yes", "allowed_as_model_input": "conditional", "rationale": "May encode care-source differences; use only after fairness/site leakage review."},
        {"table": "cancer_level_dataset_index", "field": "ca_type/ca_d_site/redcap_ca_index", "role": "cohort_definition", "available_at_t0": "yes", "allowed_as_model_input": "conditional", "rationale": "Disease cohort fields; not treatment/outcome labels."},
        {"table": "cancer_level_dataset_index", "field": "ca_histology/naaccr_histology_cd", "role": "cohort_definition_or_input", "available_at_t0": "conditional", "allowed_as_model_input": "yes_if_documented_before_t0", "rationale": "Use only when known by t0; ambiguous values manual_review."},
        {"table": "cancer_level_dataset_index", "field": "stage_dx_iv/ca_dmets_yn/ca_resect_status", "role": "pre_t0_input_or_cohort", "available_at_t0": "yes_for_baseline_status", "allowed_as_model_input": "yes", "rationale": "Baseline stage/resectability is before treatment decision."},
        {"table": "cancer_level_dataset_index", "field": "dmets_post_dx/dx_to_dmets_days", "role": "pre_t0_input_or_cohort", "available_at_t0": "conditional", "allowed_as_model_input": "yes_if_dx_to_dmets_days <= t0", "rationale": "Cannot use post-t0 metastatic events."},
        {"table": "cancer_panel_test_level_dataset", "field": "dx_cpt_rep_days", "role": "t0_alignment", "available_at_t0": "conditional", "allowed_as_model_input": "yes_if_report_day < t0", "rationale": "Main NGS selection requires strict report before t0."},
        {"table": "cancer_panel_test_level_dataset", "field": "cpt_seq_date", "role": "metadata", "available_at_t0": "year_only", "allowed_as_model_input": "no_for_exact_timing", "rationale": "Year-level sequencing date cannot replace report day."},
        {"table": "regimen_cancer_level_dataset", "field": "prior regimen_drugs/regimen_number/dx_reg_start_int", "role": "pre_t0_treatment_history", "available_at_t0": "yes_if_start < t0", "allowed_as_model_input": "yes", "rationale": "Prior treatment history only."},
        {"table": "regimen_cancer_level_dataset", "field": "t0 regimen_drugs", "role": "observed_next_regimen_label", "available_at_t0": "decision_target", "allowed_as_model_input": "no", "rationale": "This is the observed next regimen label, not an input."},
        {"table": "regimen_cancer_level_dataset", "field": "dx_reg_end_any_int/dx_reg_end_all_int", "role": "post_t0_or_sequence_quality", "available_at_t0": "no_for_t0_regimen", "allowed_as_model_input": "prior_only", "rationale": "End dates for current/future regimen leak post-t0 information."},
        {"table": "regimen_cancer_level_dataset", "field": "pfs*/os*/ttnt*", "role": "outcome", "available_at_t0": "no", "allowed_as_model_input": "no", "rationale": "Outcome fields only."},
        {"table": "patient_level_dataset", "field": "hybrid_death_int/dob_lastalive_int/last_*", "role": "followup_outcome", "available_at_t0": "no", "allowed_as_model_input": "no", "rationale": "Death/follow-up fields are outcome or censoring data."},
    ]


def public_output_paths(repo_root: Path) -> list[Path]:
    paths = []
    for root in [repo_root / "reports", repo_root / "code" / "mappings"]:
        if root.exists():
            paths.extend([p for p in root.rglob("*") if p.is_file()])
    for name in ["cohort_definition_v0.1.yaml", "README.md", "README.zh-CN.md"]:
        p = repo_root / name
        if p.exists():
            paths.append(p)
    return paths


def scan_public_patient_ids(repo_root: Path) -> int:
    hits = 0
    for path in public_output_paths(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits += len(INSTITUTION_ID_PATTERN.findall(text))
    return hits

def choose_pilot_set(repo_root: Path, extended: pd.DataFrame, review_pool: pd.DataFrame, anomaly_pool: pd.DataFrame) -> list[dict[str, Any]]:
    private_dir = repo_root / "data" / "processed" / "cohort_lock_label_feasibility"
    private_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    def take(pool: pd.DataFrame, stratum: str, n: int) -> None:
        nonlocal rows
        if pool.empty or n <= 0:
            return
        work = pool.copy()
        work["_hash"] = work["record_id"].astype(str).map(stable_hash)
        for _, row in work.sort_values("_hash", kind="mergesort").head(n).iterrows():
            rows.append({
                "record_id": row["record_id"],
                "pilot_stratum": stratum,
                "t0_start_day": row.get("start_day", ""),
                "pdac_mapping_status": row.get("pdac_mapping_status", ""),
                "observed_next_regimen": row.get("observed_next_regimen", ""),
                "regimen_mapping_status": row.get("regimen_mapping_status", ""),
            })
    core_like = extended.loc[extended["treatment_sequence_clean"] & extended["regimen_mapping_status"].eq("standardized")]
    take(core_like, "core_like", 20)
    take(review_pool, "pdac_or_mapping_review", 5)
    take(anomaly_pool, "timeline_or_regimen_anomaly", 5)
    seen = set()
    deduped = []
    for row in rows:
        if row["record_id"] in seen:
            continue
        seen.add(row["record_id"])
        deduped.append(row)
    pilot_path = private_dir / "pilot_set_v0.1.csv"
    write_csv(pilot_path, deduped, ["record_id", "pilot_stratum", "t0_start_day", "pdac_mapping_status", "observed_next_regimen", "regimen_mapping_status"])
    return [{"pilot_stratum": stratum, "n_patients": count} for stratum, count in Counter(row["pilot_stratum"] for row in deduped).items()]


def build_yaml(repo_root: Path, counts: dict[str, Any]) -> None:
    text = f"""# Cohort definition v0.1 - draft, not locked
version: v0.1
status: draft_not_locked
track_a_status: conditional_go
track_b_status: frozen
raw_data_root: data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public
formal_keys:
  patient: [cohort, record_id]
  cancer_linked_tables: [cohort, record_id, ca_seq]
  pathology_to_ngs: [cohort, record_id, path_proc_number, path_rep_number]
main_t0_definition:
  name: definition_A
  rule: first new cancer-directed regimen with a valid NGS report strictly before regimen start
  inequality: dx_cpt_rep_days < dx_reg_start_int
  index_ngs_strategy: latest valid NGS report strictly before t0
  status: draft_not_locked
pdac_mapping:
  status: draft_manual_review_required
  include: OncoTree PAAD with pancreatic index primary, or adenocarcinoma-compatible histology when OncoTree is unavailable
  exclude: non-pancreatic primary or clear non-PDAC pancreatic subtype such as PAAC/UCP
  manual_review: PAASC, conflicting OncoTree codes, ambiguous histology
  insufficient_info: no usable histology/code/OncoTree evidence
cohorts:
  extended_draft_n: {counts['extended_n']}
  core_draft_n: {counts['core_n']}
  pilot_local_n: {counts['pilot_n']}
endpoint_specific_subcohorts:
  os_n: {counts['os_n']}
  pfs_i_n: {counts['pfs_i_n']}
  pfs_m_n: {counts['pfs_m_n']}
  ttnt_any_cancer_n: {counts['ttnt_any_n']}
  ttnt_associated_cancer_n: {counts['ttnt_ca_seq_n']}
labels:
  observed_next_regimen: available_as_observed_data_not_gold_standard
  evidence_supported_candidate_set: not_available_from_bpc_alone_requires_next_stage_evidence_design
  post_t0_outcome: endpoint_specific_available_not_base_cohort_requirement
privacy:
  public_outputs: aggregate_only
  patient_level_intermediates: data/processed/cohort_lock_label_feasibility/ignored_by_git
"""
    (repo_root / "cohort_definition_v0.1.yaml").write_text(text, encoding="utf-8")


def update_readme(repo_root: Path) -> None:
    en = repo_root / "README.md"
    zh = repo_root / "README.zh-CN.md"
    en_text = en.read_text(encoding="utf-8") if en.exists() else "# pdac-treatment-benchmark\n"
    zh_text = zh.read_text(encoding="utf-8") if zh.exists() else "# pdac-treatment-benchmark\n"
    en_section = """
## Round 3 Cohort Lock and Label Feasibility Audit

Run from the repository root:

```powershell
python code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

Main outputs:

- [Cohort definition draft](cohort_definition_v0.1.yaml)
- [Round 3 audit report](reports/cohort_lock_label_feasibility_v0.1.md)
- [Cohort lock flow counts](reports/tables/cohort_lock_flow_counts.csv)
- [Endpoint coverage](reports/tables/endpoint_coverage.csv)
- [Treatment sequence quality](reports/tables/treatment_sequence_quality.csv)
- [NGS selection sensitivity](reports/tables/ngs_selection_sensitivity.csv)
- [Label availability](reports/tables/label_availability.csv)
- [Time leakage field audit](reports/tables/time_leakage_field_audit.csv)
- [PDAC mapping](code/mappings/pdac_mapping_v0.1.csv)
- [Regimen mapping](code/mappings/regimen_mapping_v0.1.csv)
"""
    zh_section = """
## 第三轮队列锁定与标签可用性审计

在仓库根目录运行：

```powershell
python code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

主要输出：

- [队列定义草案](cohort_definition_v0.1.yaml)
- [第三轮审计报告](reports/cohort_lock_label_feasibility_v0.1.md)
- [队列流程计数](reports/tables/cohort_lock_flow_counts.csv)
- [终点覆盖](reports/tables/endpoint_coverage.csv)
- [治疗序列质量](reports/tables/treatment_sequence_quality.csv)
- [NGS 选择敏感性](reports/tables/ngs_selection_sensitivity.csv)
- [标签可用性](reports/tables/label_availability.csv)
- [时间泄漏字段审计](reports/tables/time_leakage_field_audit.csv)
- [PDAC 映射](code/mappings/pdac_mapping_v0.1.csv)
- [Regimen 映射](code/mappings/regimen_mapping_v0.1.csv)
"""
    if "## Round 3 Cohort Lock and Label Feasibility Audit" not in en_text:
        en.write_text(en_text.rstrip() + "\n" + en_section, encoding="utf-8")
    if "## 第三轮队列锁定与标签可用性审计" not in zh_text:
        zh.write_text(zh_text.rstrip() + "\n" + zh_section, encoding="utf-8")


def update_gitignore(repo_root: Path) -> None:
    path = repo_root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    additions = [
        "",
        "# Local patient-level review files",
        "data/processed/cohort_lock_label_feasibility/",
        "reports/private/",
        "reports/patient_level/",
    ]
    if "data/processed/cohort_lock_label_feasibility/" not in text:
        path.write_text(text.rstrip() + "\n" + "\n".join(additions) + "\n", encoding="utf-8")


def automated_checks(repo_root: Path, selected: pd.DataFrame, extended: pd.DataFrame, endpoint_rows: list[dict[str, Any]], flow_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    def add(name: str, passed: bool, value: Any, detail: str) -> None:
        checks.append({"check_name": name, "status": "pass" if passed else "fail", "value": value, "detail": detail})
    add("main_cohort_max_one_decision_sample_per_patient", len(selected) == selected["record_id"].nunique(), len(selected), "One selected t0 row per patient.")
    add("index_ngs_strictly_before_t0", bool((extended["index_ngs_report_day"] < extended["start_day"]).all()) if not extended.empty else True, len(extended), "Main analysis uses latest valid NGS report strictly before t0.")
    add("advanced_evidence_before_t0", bool((extended["advanced_evidence_day"] <= extended["start_day"]).all()) if not extended.empty else True, len(extended), "Advanced evidence day must be <= t0 day.")
    leakage_rows = field_leakage_rows()
    bad_inputs = [r for r in leakage_rows if r["field"] in {"t0 regimen_drugs", "pfs*/os*/ttnt*", "hybrid_death_int/dob_lastalive_int/last_*"} and r["allowed_as_model_input"] not in {"no", "prior_only"}]
    add("t0_treatment_and_post_t0_outcomes_not_inputs", not bad_inputs, len(bad_inputs), "Field leakage table excludes t0 treatment/outcome fields from inputs.")
    by_def_step = defaultdict(dict)
    for row in flow_rows:
        by_def_step[row["cohort_stage"]][row["step_order"]] = int(row["n_patients"])
    monotonic = all(all(values[i] >= values[i + 1] for i in sorted(values)[:-1]) for values in by_def_step.values())
    add("cohort_flow_counts_monotonic", monotonic, len(flow_rows), "Each flow should be non-increasing.")
    endpoint_max = max([int(r["evaluable_n"]) for r in endpoint_rows if r["cohort"] == "Extended draft"] or [0])
    add("base_cohort_not_endpoint_dependent", len(extended) >= endpoint_max, f"extended={len(extended)} max_endpoint={endpoint_max}", "Extended cohort is defined before endpoint-specific filtering.")
    public_hits = scan_public_patient_ids(repo_root)
    add("public_outputs_no_patient_level_ids", public_hits == 0, public_hits, "Scans public outputs for institution-prefixed GENIE patient/sample IDs.")
    return checks

def build_outputs(repo_root: Path) -> dict[str, Any]:
    update_gitignore(repo_root)
    data = load_data(repo_root)
    patient = data["patient"]
    cancer = annotate_pdac_mapping(data["cancer"], data["cpt"])
    data["cancer"] = cancer
    regimen_std = annotate_regimen_standardization(data["regimen"])
    data["regimen"] = regimen_std

    all_patients = t0audit.patient_set(patient)
    index_pancreatic_patients = set(cancer.loc[cancer["index_pancreatic_primary"], "record_id"].astype(str))
    pdac_include_patients = set(cancer.loc[cancer["pdac_mapping_status"].eq("include"), "record_id"].astype(str))
    pdac_manual_patients = set(cancer.loc[cancer["pdac_mapping_status"].eq("manual_review"), "record_id"].astype(str))
    pdac_exclude_patients = set(cancer.loc[cancer["pdac_mapping_status"].eq("exclude"), "record_id"].astype(str))
    adv_possible = t0audit.advanced_possible_patients(cancer, regimen_std)
    usable_ngs = t0audit.patient_set(data["cpt"].loc[data["cpt"]["ngs_usable_for_t0"]])

    repro_rows = reproduce_round2_counts(data, patient)
    selected_all = select_t0_candidates(data, index_pancreatic_patients, allow_same_day=False)
    selected_all = attach_index_ngs(selected_all, data["cpt"], "latest_strict_before_t0")
    selected_all = selected_all.merge(cancer[KEY_CANCER + ["pdac_mapping_status", "pdac_mapping_reason", "index_pancreatic_primary"]], on=KEY_CANCER, how="left")
    selected_all = attach_regimen_standardization(selected_all, regimen_std)
    selected_all = sequence_quality_for_selected(selected_all, regimen_std)

    selected_include = selected_all.loc[selected_all["pdac_mapping_status"].eq("include")].copy()
    selected_manual = selected_all.loc[selected_all["pdac_mapping_status"].eq("manual_review")].copy()
    selected_exclude = selected_all.loc[selected_all["pdac_mapping_status"].eq("exclude")].copy()
    extended = selected_include.loc[
        selected_include["index_ngs_report_day"].notna()
        & selected_include["index_ngs_report_day"].lt(selected_include["start_day"])
        & selected_include["advanced_evidence_day"].le(selected_include["start_day"])
        & selected_include["line_number_present"]
        & ~selected_include["same_day_multiple_t0_regimens"]
    ].copy()
    core = extended.loc[
        extended["treatment_sequence_clean"]
        & extended["regimen_mapping_status"].eq("standardized")
    ].copy()

    selected_same_day = select_t0_candidates(data, index_pancreatic_patients, allow_same_day=True)
    selected_same_day = attach_index_ngs(selected_same_day, data["cpt"], "latest_strict_before_t0")
    selected_same_day = selected_same_day.merge(cancer[KEY_CANCER + ["pdac_mapping_status"]], on=KEY_CANCER, how="left")
    b_include_n = patient_count(selected_same_day.loc[selected_same_day["pdac_mapping_status"].eq("include")])

    earliest = attach_index_ngs(selected_include, data["cpt"], "earliest_strict_before_t0")
    sample_latest = attach_index_ngs(selected_include, data["cpt"], "latest_sample_before_t0")
    latest_diff_earliest = int((earliest["index_ngs_sample_id"].fillna("").reset_index(drop=True) != selected_include["index_ngs_sample_id"].fillna("").reset_index(drop=True)).sum()) if not selected_include.empty else 0
    latest_diff_sample = int((sample_latest["index_ngs_sample_id"].fillna("").reset_index(drop=True) != selected_include["index_ngs_sample_id"].fillna("").reset_index(drop=True)).sum()) if not selected_include.empty else 0
    ngs_sensitivity_rows = [
        {"strategy": "main_latest_report_strict_before_t0", "t0_definition": "A", "n_patients": patient_count(selected_include), "different_index_sample_vs_main": 0, "note": "Main analysis index NGS rule."},
        {"strategy": "earliest_report_strict_before_t0", "t0_definition": "A", "n_patients": patient_count(earliest), "different_index_sample_vs_main": latest_diff_earliest, "note": "Sensitivity only; same t0 patients if an NGS exists before t0."},
        {"strategy": "latest_sample_collection_before_t0", "t0_definition": "A", "n_patients": patient_count(sample_latest.loc[sample_latest["index_ngs_sample_id"].notna()]), "different_index_sample_vs_main": latest_diff_sample, "note": "Uses pathology procedure date before t0 when available."},
        {"strategy": "allow_same_day_report_t0_definition_B", "t0_definition": "B", "n_patients": b_include_n, "different_index_sample_vs_main": "not_applicable", "note": "Allows dx_cpt_rep_days <= dx_reg_start_int for t0 eligibility, but index NGS remains strict before t0 for input."},
    ]

    endpoint_rows = endpoint_coverage_rows("Extended draft", extended) + endpoint_coverage_rows("Core draft", core)
    label_rows = label_availability_rows(extended, core, endpoint_rows)
    treatment_rows = []
    for cohort_name, df in [("All definition A selected", selected_all), ("Extended draft", extended), ("Core draft", core)]:
        treatment_rows.extend([
            {"cohort": cohort_name, "metric": "n_patients", "value": len(df), "note": "One t0 row per patient"},
            {"cohort": cohort_name, "metric": "line_number_present", "value": int(df["line_number_present"].sum()) if not df.empty else 0, "note": "regimen_number_within_cancer present through t0"},
            {"cohort": cohort_name, "metric": "same_day_multiple_t0_regimens", "value": int(df["same_day_multiple_t0_regimens"].sum()) if not df.empty else 0, "note": "Potential t0 ambiguity"},
            {"cohort": cohort_name, "metric": "duplicate_regimen_records_before_t0", "value": int(df["duplicate_regimen_records_before_t0"].sum()) if not df.empty else 0, "note": "Same regimen number/drugs/start duplicated"},
            {"cohort": cohort_name, "metric": "prior_overlap_with_t0", "value": int(df["prior_overlap_with_t0"].sum()) if not df.empty else 0, "note": "Prior regimen end_all_day after t0 start"},
            {"cohort": cohort_name, "metric": "line_start_order_consistent", "value": int(df["line_start_order_consistent"].sum()) if not df.empty else 0, "note": "Line order nondecreasing by start day"},
            {"cohort": cohort_name, "metric": "treatment_sequence_clean", "value": int(df["treatment_sequence_clean"].sum()) if not df.empty else 0, "note": "Clean sequence flag used for Core"},
        ])

    flow_steps = [
        (1, "raw_patients", len(all_patients), "patient_level_dataset record_id"),
        (2, "index_pancreatic_primary", len(all_patients & index_pancreatic_patients), "ca_type=Pancreatic Cancer, ca_d_site C25.*, redcap_ca_index=Yes"),
        (3, "pdac_mapping_include", len(index_pancreatic_patients & pdac_include_patients), "draft v0.1 include mapping"),
        (4, "advanced_evidence_before_possible_t0", len(index_pancreatic_patients & pdac_include_patients & adv_possible), "advanced evidence before a possible regimen opportunity"),
        (5, "usable_ngs_time", len(index_pancreatic_patients & pdac_include_patients & adv_possible & usable_ngs), "valid report timing and no post-death/post-last-alive flag"),
        (6, "definition_A_t0_regimen", patient_count(selected_include), "strict report_day < regimen_start_day"),
        (7, "extended_draft", len(extended), "definition A + PDAC include + latest strict index NGS + reconstructable t0 sequence; outcome independent"),
        (8, "core_draft", len(core), "Extended + clean treatment sequence + standardized non-masked observed regimen; outcome independent"),
    ]
    flow_rows = [{"cohort_stage": "main_definition_A", "step_order": order, "step": step, "n_patients": n, "notes": note} for order, step, n, note in flow_steps]

    cohort_summary_rows = [
        {"cohort": "round2_definition_A_reproduced", "n_patients": next(r["recomputed_usable_patients"] for r in repro_rows if r["definition"] == "A"), "status": "recomputed", "definition": "Second-round feasibility proxy definition A"},
        {"cohort": "definition_A_selected_all_index_pancreatic", "n_patients": patient_count(selected_all), "status": "audit_pool", "definition": "Definition A before final PDAC include filter"},
        {"cohort": "definition_A_pdac_include_selected", "n_patients": patient_count(selected_include), "status": "draft", "definition": "Definition A with draft PDAC include mapping"},
        {"cohort": "definition_A_pdac_manual_review_selected", "n_patients": patient_count(selected_manual), "status": "manual_review", "definition": "Definition A selected but PDAC mapping uncertain"},
        {"cohort": "definition_A_pdac_exclude_selected", "n_patients": patient_count(selected_exclude), "status": "exclude", "definition": "Definition A selected but mapped non-PDAC"},
        {"cohort": "extended_draft", "n_patients": len(extended), "status": "draft_not_locked", "definition": "Outcome-independent Extended draft"},
        {"cohort": "core_draft", "n_patients": len(core), "status": "draft_not_locked", "definition": "Outcome-independent clean Track A Core draft"},
    ]

    reports_dir = repo_root / "reports"
    tables_dir = reports_dir / "tables"
    mappings_dir = repo_root / "code" / "mappings"
    write_csv(tables_dir / "cohort_lock_flow_counts.csv", flow_rows, ["cohort_stage", "step_order", "step", "n_patients", "notes"])
    write_csv(tables_dir / "cohort_summary_v0.1.csv", cohort_summary_rows, ["cohort", "n_patients", "status", "definition"])
    write_csv(tables_dir / "endpoint_coverage.csv", endpoint_rows, ["cohort", "endpoint", "status_field", "time_field", "time_origin", "endpoint_definition", "cohort_n", "status_nonmissing_n", "event_n", "censored_n", "time_nonmissing_n", "negative_time_n", "zero_time_n", "evaluable_n", "usable_from_t0", "note"])
    write_csv(tables_dir / "treatment_sequence_quality.csv", treatment_rows, ["cohort", "metric", "value", "note"])
    write_csv(tables_dir / "ngs_selection_sensitivity.csv", ngs_sensitivity_rows, ["strategy", "t0_definition", "n_patients", "different_index_sample_vs_main", "note"])
    write_csv(tables_dir / "label_availability.csv", label_rows, ["label_family", "availability", "extended_n", "core_n", "limitations"])
    write_csv(tables_dir / "time_leakage_field_audit.csv", field_leakage_rows(), ["table", "field", "role", "available_at_t0", "allowed_as_model_input", "rationale"])
    write_csv(mappings_dir / "pdac_mapping_v0.1.csv", mapping_summary_rows(cancer), ["source_field", "source_value", "n_index_cancer_records", "n_patients", "include_n", "exclude_n", "manual_review_n", "insufficient_info_n", "rule_status"])
    write_csv(mappings_dir / "regimen_mapping_v0.1.csv", regimen_mapping_rows(regimen_std, selected_include), ["raw_regimen_drugs", "observed_next_regimen", "mapping_status", "n_all_regimen_rows", "n_definition_A_t0_rows", "note"])
    observed_rows = []
    observed_counts = extended["observed_next_regimen"].value_counts() if not extended.empty else pd.Series(dtype=int)
    rare_total = 0
    rare_categories = 0
    for category, count in observed_counts.items():
        count = int(count)
        if count < 5:
            rare_total += count
            rare_categories += 1
            continue
        observed_rows.append({"observed_next_regimen": category, "n_extended_t0": count, "note": "Observed next regimen only; not a gold standard."})
    if rare_categories:
        observed_rows.append({"observed_next_regimen": "suppressed_categories_n_lt_5", "n_extended_t0": rare_total, "note": f"{rare_categories} rare standardized categories suppressed."})
    write_csv(tables_dir / "observed_next_regimen_distribution.csv", observed_rows, ["observed_next_regimen", "n_extended_t0", "note"])

    anomaly_pool = selected_include.loc[~selected_include["treatment_sequence_clean"] | ~selected_include["regimen_mapping_status"].eq("standardized")]
    pilot_summary_rows = choose_pilot_set(repo_root, extended, selected_manual, anomaly_pool)
    write_csv(tables_dir / "pilot_set_summary.csv", pilot_summary_rows, ["pilot_stratum", "n_patients"])

    endpoint_by_name = {(r["cohort"], r["endpoint"]): r for r in endpoint_rows}
    counts = {
        "extended_n": len(extended),
        "core_n": len(core),
        "pilot_n": sum(int(r["n_patients"]) for r in pilot_summary_rows),
        "os_n": endpoint_by_name[("Extended draft", "OS")]["evaluable_n"],
        "pfs_i_n": endpoint_by_name[("Extended draft", "PFS-I")]["evaluable_n"],
        "pfs_m_n": endpoint_by_name[("Extended draft", "PFS-M")]["evaluable_n"],
        "ttnt_any_n": endpoint_by_name[("Extended draft", "TTNT-any-cancer")]["evaluable_n"],
        "ttnt_ca_seq_n": endpoint_by_name[("Extended draft", "TTNT-associated-cancer")]["evaluable_n"],
    }
    build_yaml(repo_root, counts)
    update_readme(repo_root)

    checks = automated_checks(repo_root, selected_include, extended, endpoint_rows, flow_rows)
    write_csv(tables_dir / "automated_checks.csv", checks, ["check_name", "status", "value", "detail"])

    previous_expected = {}
    previous_path = tables_dir / "t0_definition_comparison.csv"
    if previous_path.exists():
        for row in csv.DictReader(previous_path.open(encoding="utf-8")):
            previous_expected[row["t0_definition"]] = int(row["usable_patients"])
    repro_compare_rows = []
    for row in repro_rows:
        expected = previous_expected.get(row["definition"], "not_found")
        repro_compare_rows.append({
            "definition": row["definition"],
            "previous_round_usable_patients": expected,
            "recomputed_usable_patients": row["recomputed_usable_patients"],
            "recomputed_t0_patients": row["recomputed_t0_patients"],
            "matches_previous": expected == row["recomputed_usable_patients"],
        })
    write_csv(tables_dir / "round2_reproduction_check.csv", repro_compare_rows, ["definition", "previous_round_usable_patients", "recomputed_usable_patients", "recomputed_t0_patients", "matches_previous"])

    conclusion = "Conditional Go"
    unresolved = [
        "PDAC mapping is draft_not_locked and manual review is still required for PAASC/ambiguous histology.",
        "Track B remains frozen because ECOG/labs/dose/toxicity fields are not available as stable t0 inputs.",
        "Evidence-supported candidate-set labels require the next-stage evidence snapshot and candidate-space design.",
    ]
    report = [
        "# Cohort Lock and Label Feasibility Audit v0.1",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Cohort definition file: cohort_definition_v0.1.yaml",
        "Status: draft_not_locked",
        "",
        "## Reproduction of Round 2",
        "",
        "| Definition | Previous usable | Recomputed usable | Recomputed t0 | Match |",
        "|---|---:|---:|---:|---|",
    ]
    for row in repro_compare_rows:
        report.append(f"| {row['definition']} | {row['previous_round_usable_patients']} | {row['recomputed_usable_patients']} | {row['recomputed_t0_patients']} | {row['matches_previous']} |")
    report.extend([
        "",
        "## Draft Cohorts",
        "",
        "| Cohort | n | Status | Definition |",
        "|---|---:|---|---|",
    ])
    for row in cohort_summary_rows:
        report.append(f"| {row['cohort']} | {row['n_patients']} | {row['status']} | {row['definition']} |")
    report.extend([
        "",
        "Extended and Core are outcome-independent. Endpoint-specific subcohorts are reported separately.",
        "",
        "## Endpoint-Specific Availability in Extended Draft",
        "",
        "| Endpoint | Evaluable | Events | Censored | Negative time |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in endpoint_rows:
        if row["cohort"] == "Extended draft":
            report.append(f"| {row['endpoint']} | {row['evaluable_n']} | {row['event_n']} | {row['censored_n']} | {row['negative_time_n']} |")
    report.extend([
        "",
        "## Label Capability Boundaries",
        "",
    ])
    for row in label_rows:
        report.append(f"- `{row['label_family']}`: {row['availability']}. {row['limitations']}")
    report.extend([
        "",
        "## NGS Selection Sensitivity",
        "",
        "| Strategy | n patients | Different index sample vs main | Note |",
        "|---|---:|---:|---|",
    ])
    for row in ngs_sensitivity_rows:
        report.append(f"| {row['strategy']} | {row['n_patients']} | {row['different_index_sample_vs_main']} | {row['note']} |")
    report.extend([
        "",
        "## Key Quality Risks",
        "",
        f"- Definition A selected but PDAC manual_review: {patient_count(selected_manual)} patients.",
        f"- Definition A selected but PDAC excluded: {patient_count(selected_exclude)} patients.",
        f"- Extended treatment-sequence anomalies: {len(extended) - int(extended['treatment_sequence_clean'].sum()) if not extended.empty else 0} patients.",
        f"- Extended masked/manual regimen mapping: {int(~extended['regimen_mapping_status'].eq('standardized').sum()) if False else int((~extended['regimen_mapping_status'].eq('standardized')).sum()) if not extended.empty else 0} patients.",
        "- Public reports/tables suppress patient identifiers; local Pilot patient list is written under ignored data/processed.",
        "",
        "## Unresolved Items",
        "",
    ])
    for item in unresolved:
        report.append(f"- {item}")
    report.extend([
        "",
        "## Conclusion",
        "",
        f"{conclusion}: proceed to candidate treatment space and evidence label design for Track A only, while keeping cohort_definition_v0.1.yaml as draft_not_locked. Do not start model training.",
    ])
    (reports_dir / "cohort_lock_label_feasibility_v0.1.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    return {
        "extended_n": len(extended),
        "core_n": len(core),
        "pilot_n": counts["pilot_n"],
        "repro": repro_compare_rows,
        "checks": checks,
        "conclusion": conclusion,
        "endpoint_rows": endpoint_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Round 3 cohort lock and label feasibility audit")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = t0audit.find_repo_root(args.repo_root or Path.cwd())
    result = build_outputs(repo_root)
    print("cohort_lock_label_audit_complete")
    print(f"repo_root={repo_root}")
    print(f"extended_draft_n={result['extended_n']}")
    print(f"core_draft_n={result['core_n']}")
    print(f"pilot_local_n={result['pilot_n']}")
    for row in result["repro"]:
        print(f"round2_{row['definition']}: previous={row['previous_round_usable_patients']} recomputed={row['recomputed_usable_patients']} match={row['matches_previous']}")
    failed = [row for row in result["checks"] if row["status"] != "pass"]
    print(f"automated_checks_failed={len(failed)}")
    print(f"conclusion={result['conclusion']}")


if __name__ == "__main__":
    main()