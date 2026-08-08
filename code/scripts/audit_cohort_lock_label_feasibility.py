"""Round 3.1 cohort lock and label feasibility audit for BPC PANC.

This script reads the BPC PANC raw release in read-only mode, locks candidate
t0 events through formal cancer-instance keys, and writes aggregate public
outputs plus optional local patient-level review files in ignored directories.
It does not train models, build RAG/agents, or construct final clinical labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import audit_cohort_t0_feasibility as t0audit
import privacy_checks as privacy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PANC_RELATIVE_ROOT = t0audit.PANC_RELATIVE_ROOT
KEY_PATIENT = t0audit.KEY_PATIENT
KEY_CANCER = t0audit.KEY_CANCER
SUPPRESSION_THRESHOLD = privacy.SMALL_COUNT_THRESHOLD
SUPPRESSED = privacy.SUPPRESSED
ROUND2_DEFINITION_A_REFERENCE = 566
ROUND3_INITIAL_EXTENDED_REFERENCE = 557
ROUND3_INITIAL_CORE_REFERENCE = 485
PDAC_MAPPING_VERSION = "v0.1.3.1"
COHORT_DEFINITION_VERSION = "v0.1.3.1"

PDAC_INCLUDE_HIST_CODES = {"8140", "81403", "8500", "85003", "8211", "82603"}
PDAC_EXCLUDE_HIST_CODES = {"8550", "85503", "8154", "8244", "8070", "80703"}
PDAC_INCLUDE_ONCOTREE = {"PAAD"}
PDAC_EXCLUDE_ONCOTREE = {"PAAC", "UCP"}
PDAC_MANUAL_ONCOTREE = {"PAASC"}

ENDPOINTS = [
    {
        "endpoint": "OS",
        "status_field": "os_g_status",
        "time_field": "tt_os_g_days",
        "origin": "start_of_selected_regimen",
        "manual_status": "t0_validated",
        "raw_event_date_recomputable": "yes_limited_from_dob_relative_death_or_last_alive",
        "definition": "Overall survival from start of cancer-directed regimen.",
    },
    {
        "endpoint": "PFS-I",
        "status_field": "pfs_i_g_status",
        "time_field": "tt_pfs_i_g_days",
        "origin": "start_of_selected_regimen",
        "manual_status": "t0_validated",
        "raw_event_date_recomputable": "no_public_exact_dates",
        "definition": "Imaging progression-free survival from start of cancer-directed regimen.",
    },
    {
        "endpoint": "PFS-M",
        "status_field": "pfs_m_g_status",
        "time_field": "tt_pfs_m_g_days",
        "origin": "start_of_selected_regimen",
        "manual_status": "t0_validated",
        "raw_event_date_recomputable": "no_public_exact_dates",
        "definition": "Medical-oncologist-assessment progression-free survival from start of cancer-directed regimen.",
    },
    {
        "endpoint": "TTNT-any-cancer",
        "status_field": "ttnt_any_ca_status",
        "time_field": "ttnt_any_ca_days",
        "origin": "regimen_level_field_origin_not_fully_validated",
        "manual_status": "field_present_not_t0_validated",
        "raw_event_date_recomputable": "no_public_exact_dates",
        "definition": "Time to next treatment for any cancer.",
    },
    {
        "endpoint": "TTNT-associated-cancer",
        "status_field": "ttnt_ca_seq_status",
        "time_field": "ttnt_ca_seq_days",
        "origin": "regimen_level_field_origin_not_fully_validated",
        "manual_status": "field_present_not_t0_validated",
        "raw_event_date_recomputable": "no_public_exact_dates",
        "definition": "Time to next treatment for this cancer.",
    },
]

DRUG_NAME_MAP = {
    "anastrozole": "anastrozole",
    "atezolizumab": "atezolizumab",
    "avelumab": "avelumab",
    "bcg solution": "bcg",
    "bcg vaccine": "bcg",
    "bicalutamide": "bicalutamide",
    "bleomycin": "bleomycin",
    "bortezomib": "bortezomib",
    "capecitabine": "capecitabine",
    "carboplatin": "carboplatin",
    "cetuximab": "cetuximab",
    "cisplatin": "cisplatin",
    "cobimetinib": "cobimetinib",
    "cyclophosphamide": "cyclophosphamide",
    "dabrafenib": "dabrafenib",
    "dacarbazine": "dacarbazine",
    "docetaxel": "docetaxel",
    "doxorubicin hcl": "doxorubicin",
    "durvalumab": "durvalumab",
    "eribulin mesylate": "eribulin",
    "erlotinib hcl": "erlotinib",
    "etoposide": "etoposide",
    "exemestane": "exemestane",
    "fluorouracil": "fluorouracil",
    "fulvestrant": "fulvestrant",
    "gemcitabine hcl": "gemcitabine",
    "ifosfamide": "ifosfamide",
    "imatinib mesylate": "imatinib",
    "investigational drug": "investigational_drug",
    "ipilimumab": "ipilimumab",
    "irinotecan hcl": "irinotecan",
    "irinotecan liposome": "liposomal_irinotecan",
    "lenalidomide": "lenalidomide",
    "letrozole": "letrozole",
    "leucovorin": "leucovorin",
    "leuprolide": "leuprolide",
    "methotrexate": "methotrexate",
    "mitomycin": "mitomycin",
    "nabpaclitaxel": "nab-paclitaxel",
    "niraparib": "niraparib",
    "nivolumab": "nivolumab",
    "olaparib": "olaparib",
    "other nos": "other_nos",
    "oxaliplatin": "oxaliplatin",
    "paclitaxel": "paclitaxel",
    "pembrolizumab": "pembrolizumab",
    "rituximab": "rituximab",
    "rucaparib": "rucaparib",
    "talazoparib": "talazoparib",
    "tamoxifen": "tamoxifen",
    "temozolomide": "temozolomide",
    "trametinib": "trametinib",
    "trastuzumab": "trastuzumab",
    "vinblastine sulfate": "vinblastine",
    "vincristine sulfate": "vincristine",
}

PARP_DRUGS = {"olaparib", "rucaparib", "niraparib", "talazoparib"}
ICI_DRUGS = {"pembrolizumab", "nivolumab", "ipilimumab", "atezolizumab", "avelumab", "durvalumab"}
ENDOCRINE_DRUGS = {"anastrozole", "tamoxifen", "exemestane", "letrozole", "leuprolide", "bicalutamide", "fulvestrant"}
TARGETED_OR_BIOLOGIC = {"erlotinib", "trametinib", "cobimetinib", "imatinib", "cetuximab", "trastuzumab", "rituximab", "dabrafenib"}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def clean_lower(value: Any) -> str:
    return clean_text(value).lower()


def norm_code(value: Any) -> str:
    return clean_text(value).upper().replace(".", "")


def numeric(series: pd.Series) -> pd.Series:
    return t0audit.numeric(series)


def nonmissing(series: pd.Series) -> pd.Series:
    return t0audit.nonmissing(series)


def is_missing(value: Any) -> bool:
    return t0audit.is_missing_value(value)


def normalize_status(value: Any) -> str:
    text = clean_text(value)
    if text in {"0", "0.0"}:
        return "0"
    if text in {"1", "1.0"}:
        return "1"
    return text


def patient_key(row: pd.Series | dict[str, Any]) -> tuple[str, str]:
    return tuple(str(row[col]) for col in KEY_PATIENT)  # type: ignore[return-value]


def cancer_key(row: pd.Series | dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(row[col]) for col in KEY_CANCER)  # type: ignore[return-value]


def key_set(df: pd.DataFrame, columns: list[str]) -> set[tuple[str, ...]]:
    if df.empty:
        return set()
    return set(map(tuple, df[columns].astype(str).to_numpy()))


def patient_key_set(df: pd.DataFrame) -> set[tuple[str, str]]:
    return key_set(df, KEY_PATIENT)  # type: ignore[return-value]


def cancer_key_set(df: pd.DataFrame) -> set[tuple[str, str, str]]:
    return key_set(df, KEY_CANCER)  # type: ignore[return-value]


def count_patient_keys(df: pd.DataFrame) -> int:
    return len(patient_key_set(df))


def count_cancer_keys(df: pd.DataFrame) -> int:
    return len(cancer_key_set(df))


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def suppress_count(value: Any, threshold: int = SUPPRESSION_THRESHOLD) -> str:
    return privacy.suppress_count(value, threshold)


def display_count(value: Any) -> str:
    return suppress_count(value)


def is_count_field(field: str) -> bool:
    return privacy.is_count_field(field)


def public_cell(field: str, value: Any, row: dict[str, Any] | None = None) -> Any:
    return privacy.public_cell(field, value, row)


def write_public_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: public_cell(name, row.get(name, ""), row) for name in fieldnames})


def write_private_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def load_data(repo_root: Path) -> dict[str, pd.DataFrame]:
    raw_root = repo_root / PANC_RELATIVE_ROOT
    data = t0audit.prepare_data(raw_root)
    non_index = raw_root / "clinical_data" / "cancer_level_dataset_non_index.csv"
    data["non_index_cancer"] = t0audit.read_csv_str(non_index) if non_index.exists() else pd.DataFrame()
    data["raw_cancer"] = data["cancer"].copy()
    data["raw_cpt"] = data["cpt"].copy()
    data["raw_regimen"] = data["regimen"].copy()
    data["cpt"] = t0audit.prepare_cpt(data["cpt"])
    data["regimen"] = annotate_regimen_standardization(t0audit.prepare_regimen(data["regimen"]))
    data["cancer"] = annotate_advanced_evidence(annotate_pdac_mapping(data["raw_cancer"], data["cpt"]))
    data["cancer"] = annotate_instance_resolution(data["cancer"])
    return data


def oncotree_by_cancer(cpt: pd.DataFrame) -> pd.DataFrame:
    usable = cpt.loc[nonmissing(cpt["cpt_oncotree_code"]), KEY_CANCER + ["cpt_oncotree_code"]].copy()
    usable["cpt_oncotree_code"] = usable["cpt_oncotree_code"].astype(str).str.upper().str.strip()
    grouped = (
        usable.groupby(KEY_CANCER, dropna=False)["cpt_oncotree_code"]
        .agg(lambda s: ";".join(sorted(set(x for x in s if x))))
        .reset_index()
        .rename(columns={"cpt_oncotree_code": "all_oncotree_codes"})
    )
    return grouped


def classify_pdac(
    ca_type: str,
    site: str,
    redcap_index: str,
    histology: str,
    hist_code: str,
    oncotree_codes: set[str],
) -> tuple[str, str]:
    ca_type_l = clean_lower(ca_type)
    site_u = clean_text(site).upper()
    index_l = clean_lower(redcap_index)
    hist_l = clean_lower(histology)
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
    adenocarcinoma_text = "adenocarcinoma" in hist_l and not any(
        term in hist_l for term in ["acinar", "adenosquamous", "neuroendocrine", "mixed islet"]
    )
    if hist_code_u in PDAC_INCLUDE_HIST_CODES or adenocarcinoma_text:
        return "include", "Histology code/text is adenocarcinoma-compatible for draft PDAC mapping."
    if hist_code_u in PDAC_EXCLUDE_HIST_CODES or any(
        term in hist_l for term in ["acinar", "carcinoid", "squamous", "sarcoma", "anaplastic"]
    ):
        return "exclude", "Histology suggests non-ductal pancreatic subtype."
    return "manual_review", "Pancreatic index cancer but histology/OncoTree is ambiguous for PDAC."


def annotate_pdac_mapping(cancer: pd.DataFrame, cpt: pd.DataFrame) -> pd.DataFrame:
    cancer = cancer.copy().merge(oncotree_by_cancer(cpt), on=KEY_CANCER, how="left")
    cancer["all_oncotree_codes"] = cancer["all_oncotree_codes"].fillna("")
    statuses: list[str] = []
    reasons: list[str] = []
    for _, row in cancer.iterrows():
        codes = {code for code in str(row["all_oncotree_codes"]).split(";") if code}
        status, reason = classify_pdac(
            row["ca_type"],
            row["ca_d_site"],
            row["redcap_ca_index"],
            row["ca_histology"],
            row["naaccr_histology_cd"],
            codes,
        )
        statuses.append(status)
        reasons.append(reason)
    cancer["pdac_mapping_version"] = PDAC_MAPPING_VERSION
    cancer["pdac_mapping_status"] = statuses
    cancer["pdac_mapping_reason"] = reasons
    cancer["index_pancreatic_primary"] = (
        cancer["ca_type"].map(clean_lower).eq("pancreatic cancer")
        & cancer["ca_d_site"].map(clean_text).str.upper().str.startswith("C25")
        & cancer["redcap_ca_index"].map(clean_lower).eq("yes")
    )
    return cancer


def annotate_instance_resolution(cancer: pd.DataFrame) -> pd.DataFrame:
    cancer = cancer.copy()
    include_counts = (
        cancer.loc[cancer["pdac_mapping_status"].eq("include")]
        .groupby(KEY_PATIENT, dropna=False)
        .size()
        .rename("include_instance_count")
        .reset_index()
    )
    total_counts = cancer.groupby(KEY_PATIENT, dropna=False).size().rename("index_cancer_record_count").reset_index()
    cancer = cancer.merge(total_counts, on=KEY_PATIENT, how="left").merge(include_counts, on=KEY_PATIENT, how="left")
    cancer["include_instance_count"] = cancer["include_instance_count"].fillna(0).astype(int)
    status = []
    for _, row in cancer.iterrows():
        if row["pdac_mapping_status"] != "include":
            status.append("not_locked_non_include")
        elif int(row["include_instance_count"]) == 1:
            status.append("locked_single_pdac_instance")
        else:
            status.append("manual_review_multiple_pdac_instances")
    cancer["pdac_instance_resolution_status"] = status
    return cancer


def annotate_advanced_evidence(cancer: pd.DataFrame) -> pd.DataFrame:
    cancer = cancer.copy()
    stage_iv = cancer["stage_dx_iv"].map(clean_lower).eq("stage iv")
    dmets_dx = cancer["ca_dmets_yn"].map(clean_lower).eq("yes")
    unresectable = cancer["ca_resect_status"].map(clean_lower).eq("unresectable/locally advanced or metastatic")
    dmets_post = numeric(cancer["dmets_post_dx"]).eq(1)
    dated_columns = ["dx_to_dmets_days"] + [
        col for col in cancer.columns if col.startswith("dx_to_dist_mets_") and col.endswith("_days")
    ]
    dated_values = pd.DataFrame({col: numeric(cancer[col]) for col in dated_columns if col in cancer.columns})
    dated_min = dated_values.min(axis=1, skipna=True) if not dated_values.empty else pd.Series(pd.NA, index=cancer.index)
    baseline = stage_iv | dmets_dx | unresectable
    adv_day = pd.Series(pd.NA, index=cancer.index, dtype="Float64")
    adv_day = adv_day.mask(baseline, 0)
    adv_day = adv_day.mask(~baseline & dmets_post & dated_min.notna(), dated_min)
    cancer["advanced_stage_iv_dx"] = stage_iv
    cancer["advanced_dmets_dx"] = dmets_dx
    cancer["advanced_unresectable_baseline"] = unresectable
    cancer["advanced_dmets_post_dx"] = dmets_post
    cancer["advanced_dmets_post_dx_dated"] = dmets_post & dated_min.notna()
    cancer["advanced_status_present"] = baseline | dmets_post
    cancer["advanced_evidence_day"] = adv_day
    cancer["advanced_evidence_available"] = adv_day.notna()
    cancer["advanced_timing_unknown"] = cancer["advanced_status_present"] & cancer["advanced_evidence_day"].isna()
    return cancer


def classify_advanced_relation(row: pd.Series | dict[str, Any], t0_start_day: Any) -> str:
    start = float(t0_start_day) if not pd.isna(t0_start_day) else math.nan
    day = row.get("advanced_evidence_day", pd.NA)
    present = bool(row.get("advanced_status_present", False))
    unknown = bool(row.get("advanced_timing_unknown", False))
    if not present:
        return "no_advanced_evidence"
    if unknown or pd.isna(day):
        return "relative_time_unknown"
    adv_day = float(day)
    if math.isnan(start):
        return "relative_time_unknown"
    if adv_day < start:
        return "confirmed_pre_t0"
    if adv_day == start:
        return "same_day_ambiguous"
    return "post_t0_only"


def raw_drug_components(row: pd.Series | dict[str, Any]) -> list[str]:
    values = [clean_text(row.get(f"drugs_drug_{idx}", "")) for idx in range(1, 6)]
    values = [value for value in values if value and not is_missing(value)]
    if values:
        return values
    text = clean_text(row.get("regimen_drugs", ""))
    if not text or is_missing(text):
        return []
    return [clean_text(part) for part in text.split(",") if clean_text(part)]


def canonicalize_drug(raw_name: str) -> tuple[str, str]:
    normalized = clean_lower(raw_name)
    normalized = normalized.split("(", 1)[0].strip()
    normalized = normalized.replace(" hydrochloride", " hcl")
    normalized = normalized.replace("  ", " ")
    if normalized in DRUG_NAME_MAP:
        return DRUG_NAME_MAP[normalized], "recognized"
    fallback = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return f"unknown:{fallback or 'blank'}", "unknown"


def parse_regimen_components(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    raw_components = raw_drug_components(row)
    canonical_components = []
    unknown_components = []
    for raw_component in raw_components:
        canonical, status = canonicalize_drug(raw_component)
        canonical_components.append(canonical)
        if status == "unknown":
            unknown_components.append(raw_component)
    canonical_set = sorted(set(canonical_components))
    recognized_set = sorted({component for component in canonical_components if not component.startswith("unknown:")})
    return {
        "raw_component_count": len(raw_components),
        "raw_components": "|".join(raw_components),
        "canonical_components": canonical_components,
        "canonical_set": canonical_set,
        "recognized_set": recognized_set,
        "unknown_components": unknown_components,
        "canonical_drug_set": "+".join(canonical_set) if canonical_set else "missing_regimen",
        "recognized_drug_set": "+".join(recognized_set) if recognized_set else "",
    }


def assign_regimen_family(canonical_set: Iterable[str]) -> tuple[str, str, str]:
    drugs = set(canonical_set)
    if not drugs:
        return "missing_regimen", "manual_review", "No regimen components recorded."
    if any(drug.startswith("unknown:") for drug in drugs):
        return "unknown_component_regimen", "unknown_component", "At least one component is not in the current mapping dictionary."
    if "investigational_drug" in drugs:
        return "contains_investigational_drug", "masked_not_actionable", "Investigational component is masked; known co-components are retained in canonical_drug_set."
    if "other_nos" in drugs:
        return "other_nos", "manual_review", "Other NOS is not a concrete drug component."
    if drugs == {"gemcitabine"}:
        return "gemcitabine_monotherapy", "standardized", "All components recognized."
    if drugs == {"capecitabine"}:
        return "capecitabine_monotherapy", "standardized", "All components recognized."
    if drugs == {"fluorouracil"}:
        return "fluorouracil_monotherapy", "manual_review", "Single-agent fluorouracil needs clinical context review."
    if PARP_DRUGS & drugs and drugs <= PARP_DRUGS:
        return "PARP_inhibitor", "standardized", "All components recognized."
    if ICI_DRUGS & drugs and drugs <= ICI_DRUGS:
        return "immune_checkpoint_inhibitor", "standardized", "All components recognized."
    if drugs == {"gemcitabine", "nab-paclitaxel"}:
        return "gemcitabine_nab_paclitaxel", "standardized", "All components recognized."
    if drugs == {"cisplatin", "gemcitabine", "nab-paclitaxel"}:
        return "cisplatin_gemcitabine_nab_paclitaxel", "standardized", "All components recognized; platinum component retained."
    if drugs == {"gemcitabine", "capecitabine"}:
        return "gemcitabine_capecitabine", "standardized", "All components recognized."
    if drugs == {"gemcitabine", "cisplatin"}:
        return "gemcitabine_cisplatin", "standardized", "All components recognized."
    if drugs == {"gemcitabine", "oxaliplatin"}:
        return "gemcitabine_oxaliplatin", "standardized", "All components recognized."
    if drugs == {"gemcitabine", "erlotinib"}:
        return "gemcitabine_erlotinib", "standardized", "All components recognized."
    if drugs == {"fluorouracil", "leucovorin"}:
        return "5FU_leucovorin", "standardized", "All components recognized."
    if drugs == {"fluorouracil", "leucovorin", "oxaliplatin"}:
        return "FOLFOX_or_variant", "standardized", "All components recognized."
    if drugs == {"fluorouracil", "oxaliplatin"}:
        return "fluorouracil_oxaliplatin", "standardized", "All components recognized; leucovorin not recorded."
    if drugs == {"capecitabine", "oxaliplatin"}:
        return "CAPOX", "standardized", "All components recognized."
    if drugs == {"fluorouracil", "irinotecan", "leucovorin"}:
        return "FOLFIRI", "standardized", "All components recognized."
    if drugs == {"fluorouracil", "irinotecan"}:
        return "fluorouracil_irinotecan", "standardized", "All components recognized; leucovorin not recorded."
    if drugs == {"fluorouracil", "liposomal_irinotecan", "leucovorin"}:
        return "5FU_liposomal_irinotecan_leucovorin", "standardized", "Liposomal irinotecan is kept distinct from irinotecan."
    if drugs == {"fluorouracil", "liposomal_irinotecan"}:
        return "5FU_liposomal_irinotecan", "standardized", "Liposomal irinotecan is kept distinct from irinotecan."
    if drugs == {"fluorouracil", "irinotecan", "leucovorin", "oxaliplatin"}:
        return "FOLFIRINOX_or_variant", "standardized", "All components recognized."
    if drugs == {"fluorouracil", "irinotecan", "oxaliplatin"}:
        return "fluorouracil_irinotecan_oxaliplatin", "standardized", "All components recognized; leucovorin not recorded."
    if drugs == {"fluorouracil", "liposomal_irinotecan", "leucovorin", "oxaliplatin"}:
        return "5FU_liposomal_irinotecan_leucovorin_oxaliplatin", "standardized", "Liposomal irinotecan is kept distinct from irinotecan."
    if drugs == {"irinotecan"}:
        return "irinotecan_monotherapy", "manual_review", "Single-agent irinotecan needs clinical context review."
    if drugs == {"liposomal_irinotecan"}:
        return "liposomal_irinotecan_monotherapy", "manual_review", "Single-agent liposomal irinotecan needs clinical context review."
    if drugs & ENDOCRINE_DRUGS:
        return "non_pdac_context_or_endocrine", "manual_review", "Endocrine components suggest a non-PDAC context or require manual review."
    if drugs & TARGETED_OR_BIOLOGIC:
        return "targeted_or_biologic_other", "manual_review", "Targeted/biologic combination requires manual review for candidate-space design."
    return "recognized_other_combination", "manual_review", "All components recognized but regimen family is not currently locked."


def legacy_regimen_family_from_text(regimen_drugs: Any) -> str:
    text = clean_text(regimen_drugs)
    lower = text.lower()
    tokens = {token.strip() for token in re.split(r",|/|\+|;", lower) if token.strip()}

    def has(value: str) -> bool:
        return value in lower

    def contains_any(values: set[str]) -> bool:
        return any(value in lower for value in values)

    if not text:
        return "missing_regimen"
    if "investigational drug" in lower:
        return "investigational_or_masked"
    if contains_any(PARP_DRUGS):
        return "PARP_inhibitor"
    if contains_any(ICI_DRUGS):
        return "immune_checkpoint_inhibitor"
    if has("fluorouracil") and has("irinotecan") and has("oxaliplatin"):
        return "FOLFIRINOX_or_variant"
    if has("gemcitabine") and has("nabpaclitaxel"):
        return "gemcitabine_nab_paclitaxel"
    if has("cisplatin") and has("gemcitabine"):
        return "gemcitabine_cisplatin"
    if has("gemcitabine") and has("oxaliplatin"):
        return "gemcitabine_oxaliplatin"
    if has("capecitabine") and has("gemcitabine"):
        return "gemcitabine_capecitabine"
    if has("erlotinib") and has("gemcitabine"):
        return "gemcitabine_erlotinib"
    if has("gemcitabine") and not any(has(value) for value in ["cisplatin", "oxaliplatin", "capecitabine", "nabpaclitaxel", "erlotinib"]):
        return "gemcitabine_monotherapy_or_other_gemcitabine"
    if has("fluorouracil") and has("oxaliplatin"):
        return "FOLFOX_or_variant"
    if has("capecitabine") and has("oxaliplatin"):
        return "CAPOX"
    if has("fluorouracil") and has("irinotecan"):
        return "FOLFIRI_or_5FU_nalIRI_variant"
    if has("fluorouracil") and has("leucovorin"):
        return "5FU_leucovorin"
    if has("capecitabine") and len(tokens) == 1:
        return "capecitabine_monotherapy"
    if contains_any(TARGETED_OR_BIOLOGIC):
        return "targeted_or_biologic_other"
    if contains_any(ENDOCRINE_DRUGS):
        return "non_pdac_context_or_endocrine"
    if lower == "other nos":
        return "other_nos"
    return "manual_review_other_regimen"


def standardize_regimen_row(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    parsed = parse_regimen_components(row)
    family, status, note = assign_regimen_family(parsed["canonical_set"])
    expected = set(parsed["recognized_set"])
    observed = set(parsed["canonical_set"])
    lossless = expected.issubset(observed)
    return {
        "canonical_drug_set": parsed["canonical_drug_set"],
        "recognized_drug_set": parsed["recognized_drug_set"],
        "regimen_family": family,
        "legacy_regimen_family": legacy_regimen_family_from_text(row.get("regimen_drugs", "")),
        "regimen_mapping_status": status,
        "regimen_mapping_note": note,
        "raw_component_count": parsed["raw_component_count"],
        "unknown_component_count": len(parsed["unknown_components"]),
        "recognized_component_count": len(parsed["recognized_set"]),
        "standardized_components_lossless": lossless,
    }


def annotate_regimen_standardization(regimen: pd.DataFrame) -> pd.DataFrame:
    regimen = regimen.copy()
    rows = [standardize_regimen_row(row) for _, row in regimen.iterrows()]
    for column in rows[0].keys() if rows else []:
        regimen[column] = [row[column] for row in rows]
    regimen["observed_next_regimen"] = regimen["regimen_family"]
    return regimen


def attach_index_ngs(selected: pd.DataFrame, cpt: pd.DataFrame, strategy: str = "latest_report_strict_before_t0") -> pd.DataFrame:
    selected = selected.copy()
    if selected.empty:
        return selected
    cpt_use = cpt.loc[cpt["ngs_usable_for_t0"], KEY_CANCER + [
        "report_day",
        "path_proc_day",
        "cpt_number",
        "cpt_genie_sample_id",
        "cpt_oncotree_code",
        "cpt_seq_date",
    ]].copy()
    cpt_use = cpt_use.rename(
        columns={
            "report_day": "index_ngs_report_day",
            "path_proc_day": "index_ngs_path_proc_day",
            "cpt_number": "index_ngs_cpt_number",
            "cpt_genie_sample_id": "index_ngs_sample_id",
            "cpt_oncotree_code": "index_ngs_oncotree_code",
            "cpt_seq_date": "index_ngs_year",
        }
    )
    base = selected[KEY_CANCER + ["start_day"]].drop_duplicates()
    pairs = base.merge(cpt_use, on=KEY_CANCER, how="inner")
    pairs = pairs.loc[pairs["index_ngs_report_day"].lt(pairs["start_day"])]
    if strategy == "latest_report_strict_before_t0":
        pairs = pairs.sort_values(
            ["cohort", "record_id", "ca_seq", "start_day", "index_ngs_report_day", "index_ngs_cpt_number"],
            ascending=[True, True, True, True, False, False],
            kind="mergesort",
        )
    elif strategy == "earliest_report_strict_before_t0":
        pairs = pairs.sort_values(
            ["cohort", "record_id", "ca_seq", "start_day", "index_ngs_report_day", "index_ngs_cpt_number"],
            ascending=[True, True, True, True, True, True],
            kind="mergesort",
        )
    elif strategy == "latest_sample_collection_before_t0":
        pairs = pairs.loc[pairs["index_ngs_path_proc_day"].notna() & pairs["index_ngs_path_proc_day"].le(pairs["start_day"])]
        pairs = pairs.sort_values(
            ["cohort", "record_id", "ca_seq", "start_day", "index_ngs_path_proc_day", "index_ngs_report_day"],
            ascending=[True, True, True, True, False, False],
            kind="mergesort",
        )
    else:
        raise ValueError(strategy)
    idx = pairs.groupby(KEY_CANCER + ["start_day"], as_index=False).head(1)
    drop_cols = [col for col in selected.columns if col.startswith("index_ngs_")]
    return selected.drop(columns=drop_cols, errors="ignore").merge(idx, on=KEY_CANCER + ["start_day"], how="left")


def t0_candidate_regimens(
    cancer: pd.DataFrame,
    cpt: pd.DataFrame,
    regimen: pd.DataFrame,
    *,
    instance_statuses: set[str] | None = None,
    allow_same_day_ngs_report: bool = False,
) -> pd.DataFrame:
    instance_statuses = instance_statuses or {"include"}
    instances = cancer.loc[
        cancer["pdac_mapping_status"].isin(instance_statuses)
        & cancer["pdac_instance_resolution_status"].eq("locked_single_pdac_instance")
    ].copy()
    reg = regimen.loc[regimen["regimen_usable_start"]].copy()
    reg = reg.merge(
        instances[
            KEY_CANCER
            + [
                "pdac_mapping_status",
                "pdac_mapping_reason",
                "pdac_mapping_version",
                "pdac_instance_resolution_status",
                "advanced_evidence_day",
                "advanced_status_present",
                "advanced_timing_unknown",
                "advanced_stage_iv_dx",
                "advanced_dmets_dx",
                "advanced_unresectable_baseline",
                "advanced_dmets_post_dx",
                "advanced_dmets_post_dx_dated",
            ]
        ],
        on=KEY_CANCER,
        how="inner",
    )
    cpt_use = cpt.loc[cpt["ngs_usable_for_t0"], KEY_CANCER + ["report_day", "cpt_number"]].copy()
    pairs = reg.merge(cpt_use, on=KEY_CANCER, how="inner")
    if allow_same_day_ngs_report:
        pairs = pairs.loc[pairs["report_day"].le(pairs["start_day"])]
    else:
        pairs = pairs.loc[pairs["report_day"].lt(pairs["start_day"])]
    if pairs.empty:
        return pairs
    pairs["advanced_relation"] = [classify_advanced_relation(row, row["start_day"]) for _, row in pairs.iterrows()]
    regimen_cols = [col for col in reg.columns if col in pairs.columns] + ["advanced_relation"]
    candidates = pairs[regimen_cols].drop_duplicates()
    return candidates


def select_t0_candidates(
    data: dict[str, pd.DataFrame],
    *,
    advanced_rule: str = "strict",
    allow_same_day_ngs_report: bool = False,
) -> pd.DataFrame:
    candidates = t0_candidate_regimens(
        data["cancer"],
        data["cpt"],
        data["regimen"],
        allow_same_day_ngs_report=allow_same_day_ngs_report,
    )
    if candidates.empty:
        return candidates
    if advanced_rule == "strict":
        candidates = candidates.loc[candidates["advanced_relation"].eq("confirmed_pre_t0")]
    elif advanced_rule == "same_day_sensitivity":
        candidates = candidates.loc[candidates["advanced_relation"].isin({"confirmed_pre_t0", "same_day_ambiguous"})]
    elif advanced_rule == "pending_review":
        candidates = candidates.loc[candidates["advanced_relation"].isin({"relative_time_unknown"})]
    else:
        raise ValueError(advanced_rule)
    if candidates.empty:
        return candidates
    candidates = candidates.sort_values(
        [
            "cohort",
            "record_id",
            "start_day",
            "regimen_number_within_cancer_num",
            "regimen_number_num",
            "ca_seq",
        ],
        kind="mergesort",
    )
    selected = candidates.groupby(KEY_PATIENT, as_index=False).head(1).copy()
    selected = attach_index_ngs(selected, data["cpt"], "latest_report_strict_before_t0")
    selected = sequence_quality_for_selected(selected, data["regimen"])
    return selected


def legacy_round2_definition_a(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cancer_compat = t0audit.annotate_pdac(data["raw_cancer"], data["raw_cpt"])
    cancer_compat = t0audit.annotate_advanced(cancer_compat)
    cpt = data["cpt"]
    regimen = data["regimen"]
    all_patients = t0audit.patient_set(data["patient"])
    pdac_patients = set(cancer_compat.loc[cancer_compat["pdac_compatible"], "record_id"].astype(str))
    adv_possible = t0audit.advanced_possible_patients(cancer_compat, regimen)
    ngs_time = t0audit.patient_set(cpt.loc[cpt["ngs_usable_for_t0"]])
    step4 = all_patients & pdac_patients & adv_possible & ngs_time
    selected = t0audit.selected_t0_for_definition("A", step4, cancer_compat, cpt, regimen)
    return t0audit.evaluate_prior_reconstructability(selected, regimen)


def legacy_round3_selected_all(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cancer = data["cancer"]
    index_pancreatic_patients = set(cancer.loc[cancer["index_pancreatic_primary"], "record_id"].astype(str))
    reg = data["regimen"].loc[data["regimen"]["regimen_usable_start"] & data["regimen"]["record_id"].isin(index_pancreatic_patients)].copy()
    cpt_use = data["cpt"].loc[data["cpt"]["ngs_usable_for_t0"], KEY_CANCER + ["report_day", "path_proc_day", "cpt_number", "cpt_genie_sample_id"]].copy()
    adv = cancer.loc[cancer["advanced_evidence_available"], KEY_CANCER + ["advanced_evidence_day"]]
    pairs = reg.merge(cpt_use, on=KEY_CANCER, how="inner")
    pairs = pairs.loc[pairs["report_day"].lt(pairs["start_day"])]
    pairs = pairs.merge(adv, on=KEY_CANCER, how="left")
    pairs = pairs.loc[pairs["advanced_evidence_day"].notna() & pairs["advanced_evidence_day"].le(pairs["start_day"])]
    if pairs.empty:
        return pairs
    selected = (
        pairs.sort_values(["record_id", "start_day", "regimen_number_num", "ca_seq", "report_day"], kind="mergesort")
        .groupby("record_id", as_index=False)
        .head(1)
        .copy()
    )
    selected = selected.merge(
        cancer[KEY_CANCER + ["pdac_mapping_status", "pdac_mapping_reason", "pdac_instance_resolution_status"]],
        on=KEY_CANCER,
        how="left",
    )
    selected = attach_index_ngs(selected, data["cpt"])
    selected = sequence_quality_for_selected(selected, data["regimen"])
    return selected


def sequence_quality_for_selected(selected: pd.DataFrame, regimen: pd.DataFrame) -> pd.DataFrame:
    selected = selected.copy()
    flags: dict[str, list[Any]] = defaultdict(list)
    grouped = {key: group.copy() for key, group in regimen.loc[regimen["regimen_usable_start"]].groupby(KEY_CANCER, dropna=False)}
    for _, row in selected.iterrows():
        key = tuple(row[col] for col in KEY_CANCER)
        group = grouped.get(key, pd.DataFrame())
        t0_start = row["start_day"]
        hist = group.loc[group["start_day"].le(t0_start)].copy() if not group.empty else pd.DataFrame()
        same_day = group.loc[group["start_day"].eq(t0_start)] if not group.empty else pd.DataFrame()
        prior = group.loc[group["start_day"].lt(t0_start)] if not group.empty else pd.DataFrame()
        flags["n_prior_regimens"].append(int(len(prior)))
        flags["line_number_present"].append(bool(not hist.empty and nonmissing(hist["regimen_number_within_cancer"]).all()))
        flags["same_day_multiple_t0_regimens"].append(
            bool(len(same_day[["regimen_number", "regimen_drugs"]].drop_duplicates()) > 1) if not same_day.empty else False
        )
        duplicate_cols = ["regimen_number", "regimen_drugs", "dx_reg_start_int"]
        flags["duplicate_regimen_records_before_t0"].append(bool(hist.duplicated(duplicate_cols).any()) if not hist.empty else False)
        flags["end_before_start_before_t0"].append(
            bool(((hist["end_all_day"].notna()) & (hist["end_all_day"].lt(hist["start_day"]))).any()) if not hist.empty else False
        )
        flags["prior_overlap_with_t0"].append(
            bool((prior["end_all_day"].notna() & prior["end_all_day"].gt(t0_start)).any()) if not prior.empty else False
        )
        if hist.empty:
            flags["line_start_order_consistent"].append(False)
        else:
            ordered = hist.sort_values(["regimen_number_within_cancer_num", "start_day"], kind="mergesort")
            starts = list(ordered["start_day"])
            flags["line_start_order_consistent"].append(all(starts[i] <= starts[i + 1] for i in range(len(starts) - 1)))
    for key, values in flags.items():
        selected[key] = values
    if selected.empty:
        selected["treatment_sequence_clean"] = pd.Series(dtype=bool)
    else:
        selected["treatment_sequence_clean"] = (
            selected["line_number_present"]
            & ~selected["same_day_multiple_t0_regimens"]
            & ~selected["duplicate_regimen_records_before_t0"]
            & ~selected["end_before_start_before_t0"]
            & ~selected["prior_overlap_with_t0"]
            & selected["line_start_order_consistent"]
        )
    return selected


def strict_core_from_extended(extended: pd.DataFrame) -> pd.DataFrame:
    if extended.empty:
        return extended.copy()
    return extended.loc[
        extended["treatment_sequence_clean"]
        & extended["regimen_mapping_status"].eq("standardized")
        & extended["advanced_relation"].eq("confirmed_pre_t0")
    ].copy()


def endpoint_coverage_rows(cohort_name: str, selected: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    n = count_patient_keys(selected)
    for spec in ENDPOINTS:
        status_col = spec["status_field"]
        time_col = spec["time_field"]
        if selected.empty:
            status = pd.Series(dtype=str)
            time = pd.Series(dtype=float)
        else:
            status = selected[status_col].astype(str).map(normalize_status) if status_col in selected.columns else pd.Series(dtype=str)
            time = numeric(selected[time_col]) if time_col in selected.columns else pd.Series(dtype=float)
        status_present = nonmissing(status) if not status.empty else pd.Series(dtype=bool)
        legal_status = status.isin({"0", "1"}) if not status.empty else pd.Series(dtype=bool)
        event = status.eq("1") if not status.empty else pd.Series(dtype=bool)
        censored = status.eq("0") if not status.empty else pd.Series(dtype=bool)
        time_present = time.notna() if not time.empty else pd.Series(dtype=bool)
        nonnegative_time = time.ge(0) if not time.empty else pd.Series(dtype=bool)
        field_present_evaluable = status_present & legal_status & time_present & nonnegative_time
        validated_evaluable = field_present_evaluable if spec["manual_status"] == "t0_validated" else pd.Series([False] * len(field_present_evaluable))
        rows.append(
            {
                "cohort": cohort_name,
                "endpoint": spec["endpoint"],
                "status_field": status_col,
                "time_field": time_col,
                "legal_status_values": "0;1",
                "time_unit": "days",
                "time_origin": spec["origin"],
                "raw_event_date_recomputable": spec["raw_event_date_recomputable"],
                "post_t0_outcome_status": spec["manual_status"],
                "cohort_n": n,
                "status_nonmissing_n": int(status_present.sum()) if not status_present.empty else 0,
                "illegal_status_n": int((status_present & ~legal_status).sum()) if not status_present.empty else 0,
                "event_n": int(event.sum()) if not event.empty else 0,
                "censored_n": int(censored.sum()) if not censored.empty else 0,
                "time_nonmissing_n": int(time_present.sum()) if not time_present.empty else 0,
                "negative_time_n": int(time.lt(0).sum()) if not time.empty else 0,
                "zero_time_n": int(time.eq(0).sum()) if not time.empty else 0,
                "very_short_time_1_7_days_n": int((time.gt(0) & time.le(7)).sum()) if not time.empty else 0,
                "extreme_time_gt_3650_days_n": int(time.gt(3650).sum()) if not time.empty else 0,
                "field_present_evaluable_n": int(field_present_evaluable.sum()) if not field_present_evaluable.empty else 0,
                "post_t0_validated_evaluable_n": int(validated_evaluable.sum()) if not validated_evaluable.empty else 0,
                "note": spec["definition"],
            }
        )
    return rows


def endpoint_center_coverage_rows(cohort_name: str, selected: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if selected.empty:
        return rows
    for institution, group in selected.groupby("institution", dropna=False):
        for spec in ENDPOINTS:
            status = group[spec["status_field"]].astype(str).map(normalize_status)
            time = numeric(group[spec["time_field"]])
            evaluable = nonmissing(status) & status.isin({"0", "1"}) & time.notna() & time.ge(0)
            rows.append(
                {
                    "cohort": cohort_name,
                    "institution": institution,
                    "endpoint": spec["endpoint"],
                    "cohort_n": count_patient_keys(group),
                    "field_present_evaluable_n": int(evaluable.sum()),
                    "post_t0_outcome_status": spec["manual_status"],
                }
            )
    return rows


def center_year_distribution_rows(cohort_name: str, selected: pd.DataFrame) -> list[dict[str, Any]]:
    if selected.empty:
        return []
    df = selected.copy()
    df["index_ngs_year"] = df["index_ngs_year"].fillna("Missing/blank").replace("", "Missing/blank")
    rows = []
    for (institution, year), group in df.groupby(["institution", "index_ngs_year"], dropna=False):
        rows.append(
            {
                "cohort": cohort_name,
                "institution": institution,
                "index_ngs_year": year,
                "n_patients": count_patient_keys(group),
                "note": "Index NGS year distribution; exact calendar dates are masked.",
            }
        )
    return sorted(rows, key=lambda row: (row["cohort"], row["institution"], str(row["index_ngs_year"])))


def aggregate_counts(rows: Iterable[dict[str, Any]], key_field: str, count_field: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[str(row[key_field])] += int(row[count_field])
    return [{key_field: key, count_field: value} for key, value in sorted(counter.items())]


def pdac_mapping_rows(cancer: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field in ["ca_type", "ca_d_site", "ca_histology", "naaccr_histology_cd", "all_oncotree_codes"]:
        values = cancer[field].fillna("").replace("", "Missing/blank")
        counts = values.value_counts(dropna=False)
        rare_subset = []
        for value, count in counts.items():
            subset = cancer.loc[values.eq(value)]
            if int(count) < SUPPRESSION_THRESHOLD:
                rare_subset.append(subset)
                continue
            status_counts = subset["pdac_mapping_status"].value_counts().to_dict()
            rows.append(
                {
                    "source_field": field,
                    "source_value": value,
                    "n_index_cancer_records": len(subset),
                    "n_patients": count_patient_keys(subset),
                    "include_n": int(status_counts.get("include", 0)),
                    "exclude_n": int(status_counts.get("exclude", 0)),
                    "manual_review_n": int(status_counts.get("manual_review", 0)),
                    "insufficient_info_n": int(status_counts.get("insufficient_info", 0)),
                    "rule_status": "aggregate_value_mapping",
                }
            )
        if rare_subset:
            rare = pd.concat(rare_subset, ignore_index=True)
            rows.append(
                {
                    "source_field": field,
                    "source_value": f"suppressed_rare_values_n_lt_{SUPPRESSION_THRESHOLD}",
                    "n_index_cancer_records": len(rare),
                    "n_patients": count_patient_keys(rare),
                    "include_n": "suppressed",
                    "exclude_n": "suppressed",
                    "manual_review_n": "suppressed",
                    "insufficient_info_n": "suppressed",
                    "rule_status": "rare_categories_suppressed",
                }
            )
    rule_rows = [
        ("OncoTree PAAD + pancreatic index primary", "include: Draft include"),
        ("OncoTree PAAC/UCP + pancreatic index primary", "exclude: Non-PDAC pancreatic subtype"),
        ("OncoTree PAASC + pancreatic index primary", "manual_review: Adenosquamous requires medical review"),
        ("No OncoTree but adenocarcinoma-compatible histology/code", "include: Fallback only when OncoTree not informative"),
        ("Pancreatic primary but ambiguous histology/code", "manual_review: Do not infer"),
        ("Missing OncoTree and histology/code", "insufficient_info: Not enough information"),
    ]
    for value, status in rule_rows:
        rows.append(
            {
                "source_field": "rule",
                "source_value": value,
                "n_index_cancer_records": "",
                "n_patients": "",
                "include_n": "",
                "exclude_n": "",
                "manual_review_n": "",
                "insufficient_info_n": "",
                "rule_status": status,
            }
        )
    return rows


def regimen_mapping_rows(regimen: pd.DataFrame, selected: pd.DataFrame) -> list[dict[str, Any]]:
    selected_keys = set()
    if not selected.empty:
        key_cols = KEY_CANCER + ["regimen_number", "regimen_number_within_cancer", "start_day"]
        selected_keys = set(map(tuple, selected[key_cols].astype(str).to_numpy()))
    rows = []
    grouped = regimen.groupby(["regimen_drugs", "canonical_drug_set", "regimen_family", "regimen_mapping_status"], dropna=False)
    rare_rows: list[pd.DataFrame] = []
    key_cols = KEY_CANCER + ["regimen_number", "regimen_number_within_cancer", "start_day"]
    for (raw, canonical, family, status), group in grouped:
        all_n = len(group)
        if all_n < SUPPRESSION_THRESHOLD:
            rare_rows.append(group)
            continue
        group_keys = set(map(tuple, group[key_cols].astype(str).to_numpy()))
        rows.append(
            {
                "raw_regimen_drugs": raw,
                "canonical_drug_set": canonical,
                "regimen_family": family,
                "mapping_status": status,
                "n_all_regimen_rows": all_n,
                "n_strict_t0_rows": len(group_keys & selected_keys),
                "lossless_components": bool(group["standardized_components_lossless"].all()),
                "note": "Descriptive observed regimen only; not a gold standard treatment label.",
            }
        )
    if rare_rows:
        rare = pd.concat(rare_rows, ignore_index=True)
        rare_keys = set(map(tuple, rare[key_cols].astype(str).to_numpy()))
        rows.append(
            {
                "raw_regimen_drugs": f"suppressed_rare_regimen_values_n_lt_{SUPPRESSION_THRESHOLD}",
                "canonical_drug_set": "suppressed",
                "regimen_family": "suppressed",
                "mapping_status": "suppressed",
                "n_all_regimen_rows": len(rare),
                "n_strict_t0_rows": len(rare_keys & selected_keys),
                "lossless_components": bool(rare["standardized_components_lossless"].all()),
                "note": "Rare raw treatment strings suppressed from public output.",
            }
        )
    return sorted(rows, key=lambda row: str(row["raw_regimen_drugs"]))


def treatment_sequence_rows(cohorts: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows = []
    for cohort_name, df in cohorts.items():
        metrics = {
            "n_patients": count_patient_keys(df),
            "line_number_present": int(df["line_number_present"].sum()) if not df.empty and "line_number_present" in df else 0,
            "same_day_multiple_t0_regimens": int(df["same_day_multiple_t0_regimens"].sum()) if not df.empty and "same_day_multiple_t0_regimens" in df else 0,
            "duplicate_regimen_records_before_t0": int(df["duplicate_regimen_records_before_t0"].sum()) if not df.empty and "duplicate_regimen_records_before_t0" in df else 0,
            "prior_overlap_with_t0": int(df["prior_overlap_with_t0"].sum()) if not df.empty and "prior_overlap_with_t0" in df else 0,
            "line_start_order_consistent": int(df["line_start_order_consistent"].sum()) if not df.empty and "line_start_order_consistent" in df else 0,
            "treatment_sequence_clean": int(df["treatment_sequence_clean"].sum()) if not df.empty and "treatment_sequence_clean" in df else 0,
        }
        for metric, value in metrics.items():
            rows.append({"cohort": cohort_name, "metric": metric, "value": value, "note": "One t0 row per formal patient key."})
    return rows


def regimen_standardization_summary_rows(regimen: pd.DataFrame, old_selected: pd.DataFrame, new_selected: pd.DataFrame, core_old_n: int, core_new_n: int) -> list[dict[str, Any]]:
    all_rows = len(regimen)
    standardized = int(regimen["regimen_mapping_status"].eq("standardized").sum())
    manual = int(regimen["regimen_mapping_status"].eq("manual_review").sum())
    masked = int(regimen["regimen_mapping_status"].eq("masked_not_actionable").sum())
    unknown = int(regimen["regimen_mapping_status"].eq("unknown_component").sum())
    label_changed = 0
    if not new_selected.empty and {"legacy_regimen_family", "regimen_family"}.issubset(new_selected.columns):
        label_changed = int((new_selected["legacy_regimen_family"].fillna("") != new_selected["regimen_family"].fillna("")).sum())
    rows = [
        {"metric": "all_regimen_rows", "value": all_rows, "note": "All regimen rows have an explicit mapping status."},
        {"metric": "standardized_rows", "value": standardized, "note": f"{standardized / all_rows:.3f} of all regimen rows." if all_rows else ""},
        {"metric": "manual_review_rows", "value": manual, "note": f"{manual / all_rows:.3f} of all regimen rows." if all_rows else ""},
        {"metric": "masked_not_actionable_rows", "value": masked, "note": "Investigational components are masked."},
        {"metric": "unknown_component_rows", "value": unknown, "note": "Components absent from the current dictionary."},
        {"metric": "canonical_drug_set_count", "value": regimen["canonical_drug_set"].nunique(), "note": "Order-independent canonical drug sets."},
        {"metric": "regimen_family_count", "value": regimen["regimen_family"].nunique(), "note": "Family is assigned after parsing the full canonical set."},
        {"metric": "t0_label_changed_patients", "value": label_changed, "note": "Old keyword family vs 3.1 two-layer family among repaired Strict Extended t0 rows."},
        {"metric": "core_cohort_delta", "value": core_new_n - core_old_n, "note": f"old_reference={core_old_n}; repaired={core_new_n}"},
    ]
    family_counts = new_selected["regimen_family"].value_counts() if not new_selected.empty else pd.Series(dtype=int)
    total = int(family_counts.sum()) if not family_counts.empty else 0
    if total:
        top_count = int(family_counts.iloc[0])
        rows.append({"metric": "top_regimen_family_share", "value": f"{top_count / total:.3f}", "note": str(family_counts.index[0])})
        rows.append({"metric": "regimen_family_imbalance_top_to_second_ratio", "value": f"{top_count / max(int(family_counts.iloc[1]) if len(family_counts) > 1 else 1, 1):.3f}", "note": "Strict Extended t0 family imbalance."})
    return rows


def observed_regimen_distribution_rows(extended: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    if extended.empty:
        return rows
    counts = extended["regimen_family"].value_counts()
    rare_total = 0
    rare_categories = 0
    for family, count in counts.items():
        count = int(count)
        if count < SUPPRESSION_THRESHOLD:
            rare_total += count
            rare_categories += 1
            continue
        rows.append({"regimen_family": family, "n_strict_extended_t0": count, "note": "Observed t0 regimen only; not a gold standard."})
    if rare_categories:
        rows.append(
            {
                "regimen_family": f"suppressed_categories_n_lt_{SUPPRESSION_THRESHOLD}",
                "n_strict_extended_t0": rare_total,
                "note": f"{rare_categories} rare categories suppressed.",
            }
        )
    return rows


def advanced_rule_rows(selected_strict: pd.DataFrame, selected_same_day: pd.DataFrame, pending: pd.DataFrame, candidates: pd.DataFrame) -> list[dict[str, Any]]:
    relation_patient_counts = []
    for relation, group in candidates.groupby("advanced_relation", dropna=False):
        relation_patient_counts.append(
            {
                "advanced_relation": relation,
                "n_candidate_patients": count_patient_keys(group),
                "note": "Candidate has PDAC instance, prior NGS report, and regimen start.",
            }
        )
    rows = [
        {
            "advanced_rule": "strict",
            "included_relations": "confirmed_pre_t0",
            "n_selected_patients": count_patient_keys(selected_strict),
            "core_allowed": "yes",
            "note": "Main analysis requires advanced_evidence_day < t0_start_day.",
        },
        {
            "advanced_rule": "same_day_sensitivity",
            "included_relations": "confirmed_pre_t0;same_day_ambiguous",
            "n_selected_patients": count_patient_keys(selected_same_day),
            "core_allowed": "no",
            "note": "Same-day advanced evidence lacks time-of-day and is not strict Core eligible.",
        },
        {
            "advanced_rule": "pending_review",
            "included_relations": "relative_time_unknown",
            "n_selected_patients": count_patient_keys(pending),
            "core_allowed": "no",
            "note": "Advanced status exists but relative timing cannot be determined.",
        },
    ]
    return rows + relation_patient_counts


def cross_cancer_audit_rows(data: dict[str, pd.DataFrame], legacy_selected: pd.DataFrame, strict_selected: pd.DataFrame) -> list[dict[str, Any]]:
    patient = data["patient"]
    cancer = data["cancer"]
    regimen = data["regimen"]
    multi_cancer_patients = int((numeric(patient["n_cancers"]).fillna(0) > 1).sum()) if "n_cancers" in patient.columns else count_patient_keys(data["non_index_cancer"])
    index_record_counts = cancer.groupby(KEY_PATIENT, dropna=False).size()
    multi_index_patients = int((index_record_counts > 1).sum())
    regimen_keys = cancer_key_set(regimen)
    index_keys = cancer_key_set(cancer)
    regimen_non_index_rows = regimen.loc[[key not in index_keys for key in map(tuple, regimen[KEY_CANCER].astype(str).to_numpy())]]
    legacy_non_index = pd.DataFrame()
    legacy_non_pdac = pd.DataFrame()
    if not legacy_selected.empty:
        legacy_non_index = legacy_selected.loc[[key not in index_keys for key in map(tuple, legacy_selected[KEY_CANCER].astype(str).to_numpy())]]
        legacy_non_pdac = legacy_selected.loc[~legacy_selected["pdac_mapping_status"].eq("include")]
    changed = t0_changed_count(legacy_selected.loc[legacy_selected.get("pdac_mapping_status", "").eq("include")] if "pdac_mapping_status" in legacy_selected else legacy_selected, strict_selected)
    return [
        {"metric": "patients", "n": count_patient_keys(patient), "note": "Formal patient key cohort + record_id."},
        {"metric": "index_cancer_records", "n": len(cancer), "note": "Index cancer rows; no row is dropped arbitrarily."},
        {"metric": "patients_with_multiple_cancers", "n": multi_cancer_patients, "note": "patient_level_dataset.n_cancers > 1."},
        {"metric": "patients_with_multiple_index_cancer_records", "n": multi_index_patients, "note": "Requires instance-level handling."},
        {"metric": "regimen_cancer_keys_not_in_index_cancer_table", "n": len(regimen_keys - index_keys), "note": "Cross-cancer regimen keys excluded before t0 selection."},
        {"metric": "regimen_rows_not_in_index_cancer_table", "n": len(regimen_non_index_rows), "note": "Rows excluded from PDAC t0 search."},
        {"metric": "legacy_selected_non_index_cancer_patients", "n": count_patient_keys(legacy_non_index), "note": "Old patient-first script risk check."},
        {"metric": "legacy_selected_non_pdac_instance_patients", "n": count_patient_keys(legacy_non_pdac), "note": "Old selected t0 not mapped as draft PDAC include."},
        {"metric": "t0_changed_after_instance_fix_patients", "n": changed, "note": "Same patient, different cancer-instance/regimen/start/sample signature."},
        {
            "metric": "manual_review_cancer_instance_patients",
            "n": count_patient_keys(cancer.loc[cancer["pdac_instance_resolution_status"].eq("manual_review_multiple_pdac_instances")]),
            "note": "Multiple include PDAC instances cannot be automatically locked.",
        },
    ]


def t0_signature(df: pd.DataFrame) -> pd.DataFrame:
    raw_cols = KEY_PATIENT + KEY_CANCER + ["regimen_number", "regimen_number_within_cancer", "start_day", "index_ngs_sample_id"]
    cols = list(dict.fromkeys(raw_cols))
    available = [col for col in cols if col in df.columns]
    sig = df[available].copy() if not df.empty else pd.DataFrame(columns=available)
    return sig


def t0_changed_count(old: pd.DataFrame, new: pd.DataFrame) -> int:
    if old.empty or new.empty:
        return 0
    old_sig = t0_signature(old).rename(columns={col: f"old_{col}" for col in t0_signature(old).columns if col not in KEY_PATIENT})
    new_sig = t0_signature(new).rename(columns={col: f"new_{col}" for col in t0_signature(new).columns if col not in KEY_PATIENT})
    merged = old_sig.merge(new_sig, on=KEY_PATIENT, how="inner")
    if merged.empty:
        return 0
    changed = pd.Series(False, index=merged.index)
    for col in ["cohort", "record_id", "ca_seq", "regimen_number", "regimen_number_within_cancer", "start_day", "index_ngs_sample_id"]:
        old_col = f"old_{col}"
        new_col = f"new_{col}"
        if old_col in merged.columns and new_col in merged.columns:
            changed |= merged[old_col].astype(str).fillna("") != merged[new_col].astype(str).fillna("")
    return int(changed.sum())


def reconciliation_rows(
    data: dict[str, pd.DataFrame],
    old_df: pd.DataFrame,
    new_df: pd.DataFrame,
    comparison_name: str,
) -> list[dict[str, Any]]:
    old_keys = patient_key_set(old_df)
    new_keys = patient_key_set(new_df)
    rows = [
        {"comparison": comparison_name, "category": "intersection", "reason": "in_both", "n_patients": len(old_keys & new_keys)},
        {"comparison": comparison_name, "category": "old_only", "reason": "all_old_only", "n_patients": len(old_keys - new_keys)},
        {"comparison": comparison_name, "category": "new_only", "reason": "all_new_only", "n_patients": len(new_keys - old_keys)},
    ]
    candidates = t0_candidate_regimens(data["cancer"], data["cpt"], data["regimen"])
    same_day = select_t0_candidates(data, advanced_rule="same_day_sensitivity")
    pending = select_t0_candidates(data, advanced_rule="pending_review")
    locked_pdac_patients = patient_key_set(
        data["cancer"].loc[
            data["cancer"]["pdac_mapping_status"].eq("include")
            & data["cancer"]["pdac_instance_resolution_status"].eq("locked_single_pdac_instance")
        ]
    )
    candidate_patients = patient_key_set(candidates)
    same_day_keys = patient_key_set(same_day)
    pending_keys = patient_key_set(pending)
    old_only_reasons: Counter[str] = Counter()
    for key in old_keys - new_keys:
        if key not in locked_pdac_patients:
            old_only_reasons["pdac_instance_not_locked_or_not_include"] += 1
        elif key not in candidate_patients:
            old_only_reasons["no_pdac_regimen_with_prior_ngs"] += 1
        elif key in same_day_keys:
            old_only_reasons["advanced_evidence_same_day_only"] += 1
        elif key in pending_keys:
            old_only_reasons["advanced_timing_unknown"] += 1
        else:
            old_only_reasons["no_strict_pre_t0_pdac_candidate"] += 1
    new_only_reasons: Counter[str] = Counter()
    legacy_all = legacy_round3_selected_all(data)
    legacy_noninclude_keys = patient_key_set(legacy_all.loc[~legacy_all["pdac_mapping_status"].eq("include")]) if not legacy_all.empty else set()
    for key in new_keys - old_keys:
        if key in legacy_noninclude_keys:
            new_only_reasons["legacy_selected_non_pdac_instance_but_pdac_t0_found"] += 1
        else:
            new_only_reasons["strict_pdac_instance_rule_found_candidate"] += 1
    for reason, count in sorted(old_only_reasons.items()):
        rows.append({"comparison": comparison_name, "category": "old_only_reason", "reason": reason, "n_patients": count})
    for reason, count in sorted(new_only_reasons.items()):
        rows.append({"comparison": comparison_name, "category": "new_only_reason", "reason": reason, "n_patients": count})
    return rows


def flow_rows(
    data: dict[str, pd.DataFrame],
    candidates: pd.DataFrame,
    strict_extended: pd.DataFrame,
    strict_core: pd.DataFrame,
    same_day: pd.DataFrame,
    pending: pd.DataFrame,
) -> list[dict[str, Any]]:
    patient_keys = patient_key_set(data["patient"])
    index_pancreatic = patient_key_set(data["cancer"].loc[data["cancer"]["index_pancreatic_primary"]])
    pdac_include = patient_key_set(data["cancer"].loc[data["cancer"]["pdac_mapping_status"].eq("include")])
    locked = patient_key_set(
        data["cancer"].loc[
            data["cancer"]["pdac_mapping_status"].eq("include")
            & data["cancer"]["pdac_instance_resolution_status"].eq("locked_single_pdac_instance")
        ]
    )
    usable_ngs = patient_key_set(data["cpt"].loc[data["cpt"]["ngs_usable_for_t0"]])
    candidate_keys = patient_key_set(candidates)
    strict_keys = patient_key_set(strict_extended)
    core_keys = patient_key_set(strict_core)
    steps = [
        (1, "raw_patients", patient_keys, "patient_level_dataset formal patient keys."),
        (2, "index_pancreatic_primary", patient_keys & index_pancreatic, "Pancreatic index primary instance exists."),
        (3, "pdac_mapping_include", patient_keys & pdac_include, "Draft PDAC include mapping; manual mapping not auto-included."),
        (4, "single_locked_pdac_instance", patient_keys & locked, "Exactly one include PDAC cancer instance for the patient."),
        (5, "usable_ngs_time", patient_keys & locked & usable_ngs, "At least one interpretable NGS report time exists."),
        (6, "pdac_regimen_with_prior_ngs", candidate_keys, "Regimen belongs to locked PDAC instance and has NGS report before start."),
        (7, "strict_extended", strict_keys, "First legal PDAC t0 with advanced_evidence_day < t0 start."),
        (8, "strict_core", core_keys, "Strict Extended plus clean sequence and standardized observed regimen."),
    ]
    rows = []
    previous: set[tuple[str, str]] | None = None
    for order, step, keys, note in steps:
        rows.append(
            {
                "cohort_stage": "round3_1_main",
                "step_order": order,
                "step": step,
                "n_patients": len(keys),
                "excluded_from_previous": "" if previous is None else len(previous - keys),
                "notes": note,
            }
        )
        previous = keys
    rows.extend(
        [
            {
                "cohort_stage": "round3_1_sensitivity",
                "step_order": 1,
                "step": "same_day_advanced_sensitivity_extended",
                "n_patients": count_patient_keys(same_day),
                "excluded_from_previous": "",
                "notes": "Includes same_day_ambiguous advanced evidence; not strict Core eligible.",
            },
            {
                "cohort_stage": "round3_1_sensitivity",
                "step_order": 2,
                "step": "advanced_timing_pending_review",
                "n_patients": count_patient_keys(pending),
                "excluded_from_previous": "",
                "notes": "Advanced status present but relative timing unknown.",
            },
        ]
    )
    return rows


def cohort_summary_rows(
    legacy_a: pd.DataFrame,
    legacy_round3: pd.DataFrame,
    candidates: pd.DataFrame,
    strict_extended: pd.DataFrame,
    strict_core: pd.DataFrame,
    same_day: pd.DataFrame,
    pending: pd.DataFrame,
) -> list[dict[str, Any]]:
    return [
        {
            "cohort": "round2_definition_A_reference",
            "n_patients": ROUND2_DEFINITION_A_REFERENCE,
            "status": "reference_from_previous_round",
            "definition": "Old Definition A usable count from second-round report.",
        },
        {
            "cohort": "round2_definition_A_recomputed",
            "n_patients": count_patient_keys(legacy_a),
            "status": "recomputed_legacy_logic",
            "definition": "Recomputed old Definition A for reconciliation only.",
        },
        {
            "cohort": "round3_initial_extended_reference",
            "n_patients": ROUND3_INITIAL_EXTENDED_REFERENCE,
            "status": "reference_from_e7a7007",
            "definition": "Old third-round Extended draft, not reused for selection.",
        },
        {
            "cohort": "round3_initial_core_reference",
            "n_patients": ROUND3_INITIAL_CORE_REFERENCE,
            "status": "reference_from_e7a7007",
            "definition": "Old third-round Core draft, not reused for selection.",
        },
        {
            "cohort": "legacy_round3_selected_all",
            "n_patients": count_patient_keys(legacy_round3),
            "status": "legacy_recomputed_for_risk_audit",
            "definition": "Old patient-first third-round candidate selection.",
        },
        {
            "cohort": "repaired_candidate_pool",
            "n_patients": count_patient_keys(candidates),
            "status": "candidate_pool",
            "definition": "Locked PDAC instance regimen candidates with strict prior NGS; advanced relation not yet filtered.",
        },
        {
            "cohort": "strict_extended",
            "n_patients": count_patient_keys(strict_extended),
            "status": "draft_not_locked",
            "definition": "Outcome-independent repaired Extended: first PDAC t0 with confirmed_pre_t0 advanced evidence.",
        },
        {
            "cohort": "strict_core",
            "n_patients": count_patient_keys(strict_core),
            "status": "draft_not_locked",
            "definition": "Strict Extended plus clean treatment sequence and standardized non-masked regimen family.",
        },
        {
            "cohort": "same_day_sensitivity_extended",
            "n_patients": count_patient_keys(same_day),
            "status": "sensitivity_only",
            "definition": "Includes same_day_ambiguous advanced evidence; excluded from strict Core.",
        },
        {
            "cohort": "advanced_timing_pending_review",
            "n_patients": count_patient_keys(pending),
            "status": "manual_review",
            "definition": "Advanced status present but date missing or relative timing unknown.",
        },
    ]


def ngs_sensitivity_rows(strict_extended: pd.DataFrame, data: dict[str, pd.DataFrame], same_day: pd.DataFrame) -> list[dict[str, Any]]:
    earliest = attach_index_ngs(strict_extended, data["cpt"], "earliest_report_strict_before_t0")
    sample_latest = attach_index_ngs(strict_extended, data["cpt"], "latest_sample_collection_before_t0")
    if strict_extended.empty:
        diff_earliest = diff_sample = 0
    else:
        diff_earliest = int((earliest["index_ngs_sample_id"].fillna("").reset_index(drop=True) != strict_extended["index_ngs_sample_id"].fillna("").reset_index(drop=True)).sum())
        diff_sample = int((sample_latest["index_ngs_sample_id"].fillna("").reset_index(drop=True) != strict_extended["index_ngs_sample_id"].fillna("").reset_index(drop=True)).sum())
    same_day_ngs = select_t0_candidates(data, advanced_rule="strict", allow_same_day_ngs_report=True)
    return [
        {
            "strategy": "main_latest_report_strict_before_t0",
            "n_patients": count_patient_keys(strict_extended),
            "different_index_sample_vs_main": 0,
            "note": "Main analysis index NGS rule.",
        },
        {
            "strategy": "earliest_report_strict_before_t0",
            "n_patients": count_patient_keys(earliest),
            "different_index_sample_vs_main": diff_earliest,
            "note": "Sensitivity only; same t0 regimen but earliest prior report sample.",
        },
        {
            "strategy": "latest_sample_collection_before_t0",
            "n_patients": count_patient_keys(sample_latest.loc[sample_latest["index_ngs_sample_id"].notna()]) if not sample_latest.empty else 0,
            "different_index_sample_vs_main": diff_sample,
            "note": "Uses pathology procedure day before t0 when available.",
        },
        {
            "strategy": "allow_same_day_ngs_report",
            "n_patients": count_patient_keys(same_day_ngs),
            "different_index_sample_vs_main": "not_applicable",
            "note": "Allows report_day <= t0 for t0 eligibility only; main index input remains strict before t0.",
        },
        {
            "strategy": "same_day_advanced_evidence_sensitivity",
            "n_patients": count_patient_keys(same_day),
            "different_index_sample_vs_main": "not_applicable",
            "note": "Includes same-day advanced evidence but excludes it from strict Core.",
        },
    ]


def label_availability_rows(strict_extended: pd.DataFrame, strict_core: pd.DataFrame, endpoint_rows_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    standardized = int(strict_extended["regimen_mapping_status"].eq("standardized").sum()) if not strict_extended.empty else 0
    masked = int(strict_extended["regimen_mapping_status"].eq("masked_not_actionable").sum()) if not strict_extended.empty else 0
    manual = int(strict_extended["regimen_mapping_status"].isin({"manual_review", "unknown_component"}).sum()) if not strict_extended.empty else 0
    endpoint_summary = "; ".join(
        f"{row['endpoint']} post_t0_validated={row['post_t0_validated_evaluable_n']} field_present={row['field_present_evaluable_n']}"
        for row in endpoint_rows_
        if row["cohort"] == "Strict Extended"
    )
    return [
        {
            "label_family": "observed_next_regimen",
            "availability": "available_as_observed_data",
            "extended_n": count_patient_keys(strict_extended),
            "core_n": count_patient_keys(strict_core),
            "limitations": f"Descriptive observed regimen only; standardized={standardized}; masked={masked}; manual_or_unknown={manual}; not a gold standard.",
        },
        {
            "label_family": "evidence_supported_candidate_set",
            "availability": "not_available_from_BPC_alone",
            "extended_n": count_patient_keys(strict_extended),
            "core_n": count_patient_keys(strict_core),
            "limitations": "Requires external evidence snapshot, candidate treatment space, clinical constraints, and manual/structured evidence labels.",
        },
        {
            "label_family": "post_t0_outcome",
            "availability": "endpoint_specific_mixed_validation",
            "extended_n": count_patient_keys(strict_extended),
            "core_n": count_patient_keys(strict_core),
            "limitations": endpoint_summary,
        },
    ]


def field_leakage_rows() -> list[dict[str, Any]]:
    return [
        {"table": "patient", "field": "cohort/record_id", "role": "formal key only", "available_at_t0": "yes", "allowed_as_model_input": "no", "rationale": "Identifiers are linkage keys, not features."},
        {"table": "cancer", "field": "ca_histology/naaccr_histology_cd/cpt_oncotree_code", "role": "PDAC mapping", "available_at_t0": "yes", "allowed_as_model_input": "prior_only", "rationale": "May define cancer instance but final mapping requires medical review."},
        {"table": "cancer", "field": "advanced evidence fields", "role": "cohort eligibility", "available_at_t0": "pre_t0_only", "allowed_as_model_input": "prior_only", "rationale": "Strict main analysis requires advanced_evidence_day < t0."},
        {"table": "cpt", "field": "dx_cpt_rep_days", "role": "NGS availability timing", "available_at_t0": "pre_t0_only", "allowed_as_model_input": "prior_only", "rationale": "Index NGS report must be strictly before t0."},
        {"table": "regimen", "field": "t0 regimen_drugs", "role": "observed treatment label", "available_at_t0": "at_t0", "allowed_as_model_input": "no", "rationale": "The selected treatment is the label/candidate observation, not an input feature."},
        {"table": "regimen", "field": "regimen_number/regimen_number_within_cancer", "role": "line history reconstruction", "available_at_t0": "yes", "allowed_as_model_input": "prior_only", "rationale": "Use only prior history and line context; no future regimen fields."},
        {"table": "regimen", "field": "pfs*/os*/ttnt*", "role": "post-t0 outcome", "available_at_t0": "no", "allowed_as_model_input": "no", "rationale": "Outcome/follow-up fields are labels or censoring information."},
        {"table": "patient", "field": "hybrid_death_int/dob_lastalive_int/last_*", "role": "follow-up/outcome", "available_at_t0": "no", "allowed_as_model_input": "no", "rationale": "Death and last-alive/follow-up fields leak future information."},
    ]


def data_file_checksum_rows(repo_root: Path) -> list[dict[str, Any]]:
    clinical = repo_root / PANC_RELATIVE_ROOT / "clinical_data"
    rows = []
    for path in sorted(clinical.glob("*.csv")):
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            n_rows = sum(1 for _ in handle) - 1
        rows.append(
            {
                "file": path.name,
                "n_rows": max(n_rows, 0),
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return rows


def ngs_sample_count_distribution_rows(cpt: pd.DataFrame) -> list[dict[str, Any]]:
    per_patient = cpt.groupby(KEY_PATIENT, dropna=False)["cpt_genie_sample_id"].nunique().reset_index(name="sample_count_per_patient")
    rows = []
    for sample_count, group in per_patient.groupby("sample_count_per_patient", dropna=False):
        sample_count_int = int(sample_count)
        n_patients = len(group)
        rows.append(
            {
                "sample_count_per_patient": sample_count_int,
                "n_patients": n_patients,
                "n_samples": sample_count_int * n_patients,
                "note": "Aggregate only; patient IDs suppressed.",
            }
        )
    return rows


def choose_pilot_set(repo_root: Path, strict_extended: pd.DataFrame, pending: pd.DataFrame) -> list[dict[str, Any]]:
    private_dir = repo_root / "data" / "processed" / "cohort_lock_label_feasibility"
    rows: list[dict[str, Any]] = []
    strata = [
        ("strict_extended_standardized", strict_extended.loc[strict_extended["regimen_mapping_status"].eq("standardized")] if not strict_extended.empty else strict_extended),
        ("strict_extended_manual_or_masked", strict_extended.loc[~strict_extended["regimen_mapping_status"].eq("standardized")] if not strict_extended.empty else strict_extended),
        ("advanced_timing_pending_review", pending),
    ]
    for stratum, df in strata:
        if df.empty:
            continue
        sample = df.copy()
        sample["_sort_hash"] = sample.apply(lambda row: stable_hash("|".join(str(row[col]) for col in KEY_PATIENT + ["ca_seq", "start_day"])), axis=1)
        sample = sample.sort_values("_sort_hash").head(10)
        for _, row in sample.iterrows():
            rows.append(
                {
                    "cohort": row["cohort"],
                    "record_id": row["record_id"],
                    "ca_seq": row["ca_seq"],
                    "pilot_stratum": stratum,
                    "t0_start_day": row["start_day"],
                    "advanced_relation": row.get("advanced_relation", ""),
                    "regimen_family": row.get("regimen_family", ""),
                    "regimen_mapping_status": row.get("regimen_mapping_status", ""),
                }
            )
    write_private_csv(
        private_dir / "pilot_set_v0.1.csv",
        rows,
        ["cohort", "record_id", "ca_seq", "pilot_stratum", "t0_start_day", "advanced_relation", "regimen_family", "regimen_mapping_status"],
    )
    return [{"pilot_stratum": stratum, "n_patients": count} for stratum, count in Counter(row["pilot_stratum"] for row in rows).items()]


def scan_public_patient_ids(repo_root: Path) -> int:
    return len(privacy.privacy_scan_hits(repo_root))


def scan_public_small_counts(repo_root: Path) -> list[str]:
    return [
        f"{hit['file']}:{hit.get('line', '')}:{hit.get('column', '')}"
        for hit in privacy.small_count_scan_hits(repo_root)
    ]


def automated_checks(
    repo_root: Path,
    strict_extended: pd.DataFrame,
    strict_core: pd.DataFrame,
    endpoint_rows_: list[dict[str, Any]],
    flow_rows_: list[dict[str, Any]],
    regimen: pd.DataFrame,
    conclusion: str,
) -> list[dict[str, Any]]:
    checks = []

    def add(name: str, passed: bool, value: Any, detail: str) -> None:
        checks.append({"check_name": name, "status": "pass" if passed else "fail", "value": value, "detail": detail})

    add("main_cohort_max_one_decision_sample_per_patient", len(strict_extended) == count_patient_keys(strict_extended), len(strict_extended), "One selected t0 row per formal patient key.")
    add(
        "selected_t0_uses_locked_pdac_instance",
        bool(strict_extended["pdac_instance_resolution_status"].eq("locked_single_pdac_instance").all()) if not strict_extended.empty else True,
        count_patient_keys(strict_extended),
        "Strict Extended rows are selected only after locking one PDAC cancer instance.",
    )
    add(
        "index_ngs_strictly_before_t0",
        bool((strict_extended["index_ngs_report_day"] < strict_extended["start_day"]).all()) if not strict_extended.empty else True,
        count_patient_keys(strict_extended),
        "Index NGS report day must be strictly before t0.",
    )
    add(
        "advanced_evidence_strictly_before_t0",
        bool(strict_extended["advanced_relation"].eq("confirmed_pre_t0").all()) if not strict_extended.empty else True,
        count_patient_keys(strict_extended),
        "Strict main analysis requires advanced_evidence_day < t0 start.",
    )
    add(
        "same_day_advanced_not_in_strict_core",
        bool(~strict_core["advanced_relation"].eq("same_day_ambiguous").any()) if not strict_core.empty else True,
        count_patient_keys(strict_core),
        "Same-day advanced evidence is sensitivity only.",
    )
    add(
        "regimen_components_lossless",
        bool(regimen["standardized_components_lossless"].all()) if not regimen.empty else True,
        len(regimen),
        "Canonical drug set preserves all recognized raw components.",
    )
    add(
        "all_raw_regimens_have_mapping_status",
        bool(nonmissing(regimen["regimen_mapping_status"]).all()) if not regimen.empty else True,
        len(regimen),
        "Every original nonmissing regimen has an explicit mapping status.",
    )
    endpoint_max = max([int(row["field_present_evaluable_n"]) for row in endpoint_rows_ if row["cohort"] == "Strict Extended"] or [0])
    add(
        "base_cohort_not_endpoint_dependent",
        count_patient_keys(strict_extended) >= endpoint_max,
        f"extended={count_patient_keys(strict_extended)} max_endpoint_field_present={endpoint_max}",
        "Base cohorts are defined before endpoint-specific filtering.",
    )
    by_stage: dict[str, dict[int, int]] = defaultdict(dict)
    for row in flow_rows_:
        if row["cohort_stage"] == "round3_1_main":
            by_stage[row["cohort_stage"]][int(row["step_order"])] = int(row["n_patients"])
    monotonic = all(all(values[i] >= values[i + 1] for i in sorted(values)[:-1]) for values in by_stage.values())
    add("cohort_flow_counts_monotonic", monotonic, len(flow_rows_), "Main flow should be non-increasing.")
    public_hits = scan_public_patient_ids(repo_root)
    add("public_outputs_no_patient_level_ids", public_hits == 0, public_hits, "Scans public outputs for institution-prefixed GENIE identifiers.")
    small_count_hits = scan_public_small_counts(repo_root)
    add("public_csv_small_counts_suppressed", not small_count_hits, len(small_count_hits), "All public CSV count cells with 0<n<5 must be suppressed.")
    add("rule_based_conclusion_available", conclusion in {"Hold", "Conditional Go", "Go"}, conclusion, "Conclusion is derived from rule checks.")
    return checks


def derive_conclusion(
    checks_before_conclusion: list[dict[str, Any]],
    strict_extended: pd.DataFrame,
    regimen: pd.DataFrame,
    cancer: pd.DataFrame,
    endpoint_rows_: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    unresolved = []
    if any(row["status"] != "pass" for row in checks_before_conclusion):
        return "Hold", ["One or more critical automated checks failed."]
    if count_patient_keys(strict_extended) == 0:
        return "Hold", ["No interpretable strict Extended cohort could be formed."]
    standardized_rate = float(regimen["regimen_mapping_status"].eq("standardized").mean()) if not regimen.empty else 0.0
    if standardized_rate < 0.50:
        return "Hold", [f"Regimen standardized rate is too low for interpretable labels: {standardized_rate:.3f}."]
    if cancer["pdac_mapping_status"].isin({"manual_review", "insufficient_info"}).any():
        unresolved.append("PDAC mapping remains draft_not_locked; PAASC/ambiguous histology requires medical or mentor confirmation.")
    if any(row["post_t0_outcome_status"] != "t0_validated" for row in endpoint_rows_):
        unresolved.append("TTNT endpoints are field_present_not_t0_validated until time-origin confirmation is complete.")
    if count_patient_keys(strict_extended.loc[~strict_extended["regimen_mapping_status"].eq("standardized")]) > 0:
        unresolved.append("Observed regimen labels include masked/manual/unknown categories outside strict Core.")
    unresolved.append("Evidence-supported candidate-set labels require the next-stage evidence snapshot and candidate-space design.")
    unresolved.append("Track B remains frozen because ECOG/labs/dose/toxicity fields are not available as stable t0 inputs.")
    return ("Conditional Go" if unresolved else "Go"), unresolved


def build_yaml(repo_root: Path, counts: dict[str, Any], conclusion: str, unresolved: list[str]) -> None:
    unresolved_lines = "\n".join(f"  - {item}" for item in unresolved)
    text = f"""# Cohort definition {COHORT_DEFINITION_VERSION} - draft, not locked
version: {COHORT_DEFINITION_VERSION}
status: draft_not_locked
track_a_status: {conclusion.lower().replace(" ", "_")}
track_b_status: frozen
raw_data_root: data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public
formal_keys:
  patient: [cohort, record_id]
  cancer_instance: [cohort, record_id, ca_seq]
  pathology_to_ngs: [cohort, record_id, path_proc_number, path_rep_number]
main_t0_definition:
  name: repaired_definition_A_3_1
  rule: first new cancer-directed regimen for the locked PDAC cancer instance with a valid NGS report strictly before regimen start and advanced evidence strictly before regimen start
  ngs_inequality: dx_cpt_rep_days < dx_reg_start_int
  advanced_inequality: advanced_evidence_day < dx_reg_start_int
  index_ngs_strategy: latest valid NGS report strictly before t0
  status: draft_not_locked
pdac_mapping:
  version: {PDAC_MAPPING_VERSION}
  status: draft_manual_review_required
  include: OncoTree PAAD with pancreatic index primary, or adenocarcinoma-compatible histology when OncoTree is unavailable
  exclude: non-pancreatic primary or clear non-PDAC pancreatic subtype such as PAAC/UCP
  manual_review: PAASC, conflicting OncoTree codes, ambiguous histology, or multiple include PDAC instances for one patient
cohorts:
  repaired_candidate_pool_n: {counts['candidate_pool_n']}
  strict_extended_n: {counts['strict_extended_n']}
  strict_core_n: {counts['strict_core_n']}
  same_day_sensitivity_n: {counts['same_day_sensitivity_n']}
  advanced_timing_pending_review_n: {counts['pending_review_n']}
endpoint_specific_subcohorts:
  os_post_t0_validated_n: {counts['os_n']}
  pfs_i_post_t0_validated_n: {counts['pfs_i_n']}
  pfs_m_post_t0_validated_n: {counts['pfs_m_n']}
  ttnt_any_cancer_status: field_present_not_t0_validated
  ttnt_associated_cancer_status: field_present_not_t0_validated
labels:
  observed_next_regimen: available_as_observed_data_not_gold_standard
  canonical_drug_set: lossless_order_independent_components
  regimen_family: derived_after_full_component_parsing
  evidence_supported_candidate_set: not_available_from_bpc_alone_requires_next_stage_evidence_design
  post_t0_outcome: endpoint_specific_mixed_validation
privacy:
  public_outputs: aggregate_only_with_n_lt_5_suppression
  small_count_threshold: {SUPPRESSION_THRESHOLD}
  suppression_symbol: "{SUPPRESSED}"
  patient_level_intermediates: data/processed/cohort_lock_label_feasibility/ignored_by_git
unresolved_issues:
{unresolved_lines}
"""
    (repo_root / "cohort_definition_v0.1.yaml").write_text(text, encoding="utf-8")


def update_readme(repo_root: Path, counts: dict[str, Any], conclusion: str) -> None:
    en = repo_root / "README.md"
    zh = repo_root / "README.zh-CN.md"
    en_text = en.read_text(encoding="utf-8") if en.exists() else "# pdac-treatment-benchmark\n"
    zh_text = zh.read_text(encoding="utf-8") if zh.exists() else "# pdac-treatment-benchmark\n"
    en_marker = "## Round 3.1 Cohort Repair Audit"
    zh_marker = "## 第三轮 3.1 队列修复审计"
    en_section = f"""
{en_marker}

Run from the repository root:

```powershell
C:\\Users\\ASUS\\miniconda3\\envs\\ml\\python.exe code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

Main repaired outputs:

- [Cohort definition draft](cohort_definition_v0.1.yaml)
- [Round 3.1 audit report](reports/cohort_lock_label_feasibility_v0.1.md)
- [Cohort reconciliation](reports/tables/cohort_reconciliation.csv)
- [Cross-cancer t0 audit](reports/tables/cross_cancer_t0_audit.csv)
- [Advanced evidence sensitivity](reports/tables/advanced_evidence_sensitivity.csv)
- [Endpoint coverage](reports/tables/endpoint_coverage.csv)
- [Center-year distribution](reports/tables/center_year_distribution.csv)
- [Regimen mapping](code/mappings/regimen_mapping_v0.1.csv)

Current 3.1 status: {conclusion}; strict Extended n={counts['strict_extended_n']}, strict Core n={counts['strict_core_n']}. Counts in public CSVs apply n<5 suppression.
"""
    zh_section = f"""
{zh_marker}

在仓库根目录运行：

```powershell
C:\\Users\\ASUS\\miniconda3\\envs\\ml\\python.exe code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

主要修复输出：

- [队列定义草案](cohort_definition_v0.1.yaml)
- [第三轮 3.1 审计报告](reports/cohort_lock_label_feasibility_v0.1.md)
- [新旧队列核账](reports/tables/cohort_reconciliation.csv)
- [跨癌种 t0 审计](reports/tables/cross_cancer_t0_audit.csv)
- [晚期证据敏感性](reports/tables/advanced_evidence_sensitivity.csv)
- [终点覆盖](reports/tables/endpoint_coverage.csv)
- [中心-年份分布](reports/tables/center_year_distribution.csv)
- [Regimen 两层映射](code/mappings/regimen_mapping_v0.1.csv)

当前 3.1 状态：{conclusion}；严格 Extended n={counts['strict_extended_n']}，严格 Core n={counts['strict_core_n']}。公开 CSV 已执行 n<5 小样本抑制。
"""

    def replace_or_append(text: str, marker: str, section: str) -> str:
        if marker not in text:
            return text.rstrip() + "\n" + section
        before = text.split(marker, 1)[0].rstrip()
        return before + "\n" + section

    en.write_text(replace_or_append(en_text, en_marker, en_section), encoding="utf-8")
    zh.write_text(replace_or_append(zh_text, zh_marker, zh_section), encoding="utf-8")


def update_gitignore(repo_root: Path) -> None:
    path = repo_root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    additions = [
        "data/processed/cohort_lock_label_feasibility/",
        "reports/private/",
        "reports/patient_level/",
    ]
    missing = [line for line in additions if line not in text]
    if missing:
        path.write_text(text.rstrip() + "\n\n# Local patient-level review files\n" + "\n".join(missing) + "\n", encoding="utf-8")


def build_report(
    repo_root: Path,
    counts: dict[str, Any],
    conclusion: str,
    unresolved: list[str],
    cohort_rows: list[dict[str, Any]],
    endpoint_rows_: list[dict[str, Any]],
    cross_rows: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
) -> None:
    lines = [
        "# Cohort Lock and Label Feasibility Audit v0.1.3.1",
        "",
        "Generated: deterministic 3.1 rebuild; no wall-clock timestamp",
        "Cohort definition file: cohort_definition_v0.1.yaml",
        "Status: draft_not_locked",
        "",
        "## Key Repairs",
        "",
        "- t0 selection is now locked to formal PDAC cancer-instance keys before regimen, NGS, and advanced-evidence filtering.",
        "- Main advanced-evidence rule is strict: advanced_evidence_day < t0 regimen start day.",
        "- Regimen mapping now separates canonical_drug_set from regimen_family and retains all recognized components.",
        "- Endpoint availability distinguishes t0-validated OS/PFS fields from field_present_not_t0_validated TTNT fields.",
        "- Public CSV count cells with 0<n<5 are suppressed.",
        "",
        "## Cohort Accounting",
        "",
        "| Cohort | n | Status | Definition |",
        "|---|---:|---|---|",
    ]
    for row in cohort_rows:
        lines.append(f"| {row['cohort']} | {display_count(row['n_patients'])} | {row['status']} | {row['definition']} |")
    lines.extend(["", "## Cross-Cancer t0 Audit", "", "| Metric | n | Note |", "|---|---:|---|"])
    for row in cross_rows:
        lines.append(f"| {row['metric']} | {display_count(row['n'])} | {row['note']} |")
    lines.extend(["", "## Endpoint-Specific Availability in Strict Extended", "", "| Endpoint | Field-present evaluable | Post-t0 validated evaluable | Events | Censored | Status |", "|---|---:|---:|---:|---:|---|"])
    for row in endpoint_rows_:
        if row["cohort"] == "Strict Extended":
            lines.append(
                f"| {row['endpoint']} | {display_count(row['field_present_evaluable_n'])} | {display_count(row['post_t0_validated_evaluable_n'])} | {display_count(row['event_n'])} | {display_count(row['censored_n'])} | {row['post_t0_outcome_status']} |"
            )
    lines.extend(["", "## Round 2 vs Repaired Strict Extended", "", "| Category | Reason | n |", "|---|---|---:|"])
    for row in reconciliation:
        if row["comparison"] == "round2_definition_A_vs_strict_extended":
            lines.append(f"| {row['category']} | {row['reason']} | {display_count(row['n_patients'])} |")
    lines.extend(["", "## Conclusion", "", f"{conclusion}: status remains draft_not_locked."])
    lines.extend(["", "## Unresolved Items", ""])
    for item in unresolved:
        lines.append(f"- {item}")
    lines.extend(["", "Do not start model training, RAG, agents, or baseline modeling from this audit."])
    (repo_root / "reports" / "cohort_lock_label_feasibility_v0.1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_outputs(repo_root: Path) -> dict[str, Any]:
    update_gitignore(repo_root)
    data = load_data(repo_root)
    legacy_a = legacy_round2_definition_a(data)
    legacy_round3 = legacy_round3_selected_all(data)
    candidates = t0_candidate_regimens(data["cancer"], data["cpt"], data["regimen"])
    strict_extended = select_t0_candidates(data, advanced_rule="strict")
    strict_core = strict_core_from_extended(strict_extended)
    same_day = select_t0_candidates(data, advanced_rule="same_day_sensitivity")
    pending = select_t0_candidates(data, advanced_rule="pending_review")

    endpoint_rows_ = endpoint_coverage_rows("Strict Extended", strict_extended) + endpoint_coverage_rows("Strict Core", strict_core)
    endpoint_center_rows = endpoint_center_coverage_rows("Strict Extended", strict_extended)
    cross_rows = cross_cancer_audit_rows(data, legacy_round3, strict_extended)
    flow = flow_rows(data, candidates, strict_extended, strict_core, same_day, pending)
    cohort_rows_ = cohort_summary_rows(legacy_a, legacy_round3, candidates, strict_extended, strict_core, same_day, pending)
    reconciliation = reconciliation_rows(data, legacy_a, strict_extended, "round2_definition_A_vs_strict_extended")
    reconciliation += reconciliation_rows(data, legacy_round3.loc[legacy_round3["pdac_mapping_status"].eq("include")] if not legacy_round3.empty else legacy_round3, strict_extended, "round3_initial_extended_vs_strict_extended")
    ngs_rows = ngs_sensitivity_rows(strict_extended, data, same_day)
    advanced_rows = advanced_rule_rows(strict_extended, same_day, pending, candidates)
    regimen_summary = regimen_standardization_summary_rows(
        data["regimen"],
        legacy_round3.loc[legacy_round3["pdac_mapping_status"].eq("include")] if not legacy_round3.empty else legacy_round3,
        strict_extended,
        ROUND3_INITIAL_CORE_REFERENCE,
        count_patient_keys(strict_core),
    )
    pilot_summary = choose_pilot_set(repo_root, strict_extended, pending)

    tables_dir = repo_root / "reports" / "tables"
    mappings_dir = repo_root / "code" / "mappings"
    write_public_csv(tables_dir / "cohort_lock_flow_counts.csv", flow, ["cohort_stage", "step_order", "step", "n_patients", "excluded_from_previous", "notes"])
    write_public_csv(tables_dir / "cohort_summary_v0.1.csv", cohort_rows_, ["cohort", "n_patients", "status", "definition"])
    write_public_csv(tables_dir / "cohort_reconciliation.csv", reconciliation, ["comparison", "category", "reason", "n_patients"])
    write_public_csv(tables_dir / "cross_cancer_t0_audit.csv", cross_rows, ["metric", "n", "note"])
    write_public_csv(tables_dir / "advanced_evidence_sensitivity.csv", advanced_rows, ["advanced_rule", "included_relations", "n_selected_patients", "core_allowed", "advanced_relation", "n_candidate_patients", "note"])
    write_public_csv(tables_dir / "endpoint_coverage.csv", endpoint_rows_, ["cohort", "endpoint", "status_field", "time_field", "legal_status_values", "time_unit", "time_origin", "raw_event_date_recomputable", "post_t0_outcome_status", "cohort_n", "status_nonmissing_n", "illegal_status_n", "event_n", "censored_n", "time_nonmissing_n", "negative_time_n", "zero_time_n", "very_short_time_1_7_days_n", "extreme_time_gt_3650_days_n", "field_present_evaluable_n", "post_t0_validated_evaluable_n", "note"])
    write_public_csv(tables_dir / "endpoint_center_coverage.csv", endpoint_center_rows, ["cohort", "institution", "endpoint", "cohort_n", "field_present_evaluable_n", "post_t0_outcome_status"])
    write_public_csv(tables_dir / "center_year_distribution.csv", center_year_distribution_rows("Strict Extended", strict_extended), ["cohort", "institution", "index_ngs_year", "n_patients", "note"])
    write_public_csv(tables_dir / "treatment_sequence_quality.csv", treatment_sequence_rows({"Strict Extended": strict_extended, "Strict Core": strict_core, "Same-day sensitivity": same_day}), ["cohort", "metric", "value", "note"])
    write_public_csv(tables_dir / "ngs_selection_sensitivity.csv", ngs_rows, ["strategy", "n_patients", "different_index_sample_vs_main", "note"])
    write_public_csv(tables_dir / "ngs_sample_count_distribution.csv", ngs_sample_count_distribution_rows(data["cpt"]), ["sample_count_per_patient", "n_patients", "n_samples", "note"])
    write_public_csv(tables_dir / "regimen_standardization_summary.csv", regimen_summary, ["metric", "value", "note"])
    write_public_csv(tables_dir / "observed_next_regimen_distribution.csv", observed_regimen_distribution_rows(strict_extended), ["regimen_family", "n_strict_extended_t0", "note"])
    write_public_csv(tables_dir / "label_availability.csv", label_availability_rows(strict_extended, strict_core, endpoint_rows_), ["label_family", "availability", "extended_n", "core_n", "limitations"])
    write_public_csv(tables_dir / "time_leakage_field_audit.csv", field_leakage_rows(), ["table", "field", "role", "available_at_t0", "allowed_as_model_input", "rationale"])
    write_public_csv(tables_dir / "pilot_set_summary.csv", pilot_summary, ["pilot_stratum", "n_patients"])
    write_public_csv(tables_dir / "data_file_checksums.csv", data_file_checksum_rows(repo_root), ["file", "n_rows", "size_bytes", "sha256"])
    write_public_csv(mappings_dir / "pdac_mapping_v0.1.csv", pdac_mapping_rows(data["cancer"]), ["source_field", "source_value", "n_index_cancer_records", "n_patients", "include_n", "exclude_n", "manual_review_n", "insufficient_info_n", "rule_status"])
    write_public_csv(mappings_dir / "regimen_mapping_v0.1.csv", regimen_mapping_rows(data["regimen"], strict_extended), ["raw_regimen_drugs", "canonical_drug_set", "regimen_family", "mapping_status", "n_all_regimen_rows", "n_strict_t0_rows", "lossless_components", "note"])

    preliminary_checks = automated_checks(repo_root, strict_extended, strict_core, endpoint_rows_, flow, data["regimen"], "Conditional Go")
    conclusion, unresolved = derive_conclusion(preliminary_checks, strict_extended, data["regimen"], data["cancer"], endpoint_rows_)
    endpoint_by_name = {(row["cohort"], row["endpoint"]): row for row in endpoint_rows_}
    counts = {
        "candidate_pool_n": count_patient_keys(candidates),
        "strict_extended_n": count_patient_keys(strict_extended),
        "strict_core_n": count_patient_keys(strict_core),
        "same_day_sensitivity_n": count_patient_keys(same_day),
        "pending_review_n": count_patient_keys(pending),
        "os_n": endpoint_by_name[("Strict Extended", "OS")]["post_t0_validated_evaluable_n"],
        "pfs_i_n": endpoint_by_name[("Strict Extended", "PFS-I")]["post_t0_validated_evaluable_n"],
        "pfs_m_n": endpoint_by_name[("Strict Extended", "PFS-M")]["post_t0_validated_evaluable_n"],
    }
    build_yaml(repo_root, counts, conclusion, unresolved)
    update_readme(repo_root, counts, conclusion)
    build_report(repo_root, counts, conclusion, unresolved, cohort_rows_, endpoint_rows_, cross_rows, reconciliation)
    checks = automated_checks(repo_root, strict_extended, strict_core, endpoint_rows_, flow, data["regimen"], conclusion)
    write_public_csv(tables_dir / "automated_checks.csv", checks, ["check_name", "status", "value", "detail"])
    write_public_csv(tables_dir / "small_sample_suppression_check.csv", [{"check": "public_csv_small_counts_suppressed", "n_hits": len(scan_public_small_counts(repo_root)), "status": "pass" if not scan_public_small_counts(repo_root) else "fail"}], ["check", "n_hits", "status"])

    return {
        "candidate_pool_n": count_patient_keys(candidates),
        "strict_extended_n": count_patient_keys(strict_extended),
        "strict_core_n": count_patient_keys(strict_core),
        "same_day_sensitivity_n": count_patient_keys(same_day),
        "pending_review_n": count_patient_keys(pending),
        "legacy_a_n": count_patient_keys(legacy_a),
        "legacy_round3_n": count_patient_keys(legacy_round3),
        "endpoint_rows": endpoint_rows_,
        "cross_rows": cross_rows,
        "reconciliation_rows": reconciliation,
        "checks": checks,
        "conclusion": conclusion,
        "unresolved": unresolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Round 3.1 cohort lock and label feasibility audit")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = t0audit.find_repo_root(args.repo_root or Path.cwd())
    result = build_outputs(repo_root)
    print("cohort_lock_label_audit_3_1_complete")
    print(f"repo_root={repo_root}")
    print(f"legacy_round2_definition_A_n={result['legacy_a_n']}")
    print(f"legacy_round3_selected_all_n={result['legacy_round3_n']}")
    print(f"repaired_candidate_pool_n={result['candidate_pool_n']}")
    print(f"strict_extended_n={result['strict_extended_n']}")
    print(f"strict_core_n={result['strict_core_n']}")
    print(f"same_day_sensitivity_n={result['same_day_sensitivity_n']}")
    print(f"advanced_timing_pending_review_n={result['pending_review_n']}")
    failed = [row for row in result["checks"] if row["status"] != "pass"]
    print(f"automated_checks_failed={len(failed)}")
    print(f"conclusion={result['conclusion']}")


if __name__ == "__main__":
    main()
