#!/usr/bin/env python3
"""Build a private, deterministic Pilot for Track A evidence labels.

Patient-level outputs are written only below the ignored data/processed tree.
The committed report contains aggregate, small-cell-suppressed values only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_cohort_lock_label_feasibility as cohort_audit  # noqa: E402
from validate_evidence_constraint_label_schema import derive_track_a_label  # noqa: E402


KEY_PATIENT = ["cohort", "record_id"]
KEY_CANCER = ["cohort", "record_id", "ca_seq"]
KEY_DECISION = ["cohort", "record_id", "ca_seq", "t0_start_day"]
IDENTIFIER_COLUMNS = {"cohort", "record_id", "ca_seq", "sample_id", "cpt_number"}
FUSION_GENES = {"NRG1", "NTRK1", "NTRK2", "NTRK3", "RET"}
GERMLINE_ONLY_MARKERS = {"deleterious_germline_brca1_or_brca2"}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root is not a mapping: {path}")
    return value


def numeric(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def stable_hash(namespace: str, values: Iterable[Any]) -> str:
    payload = namespace + "||" + "||".join(str(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def suppress_count(value: int, threshold: int = 5) -> str:
    return f"<{threshold}" if 0 < value < threshold else str(value)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def find_raw_file(raw_root: Path, filename: str) -> Path:
    matches = list(raw_root.rglob(filename))
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one {filename}, found {len(matches)}")
    return matches[0]


def _pre_t0_result_values(
    row: pd.Series,
    prefix: str,
    result_prefix: str,
) -> tuple[list[str], list[float]]:
    t0_dob_day = numeric(row.get("t0_dob_day"))
    if t0_dob_day is None:
        return [], []
    values: list[str] = []
    diagnosis_relative_days: list[float] = []
    dob_dx_day = numeric(row.get("dob_ca_dx_days"))
    if dob_dx_day is None:
        return [], []
    for suffix in ("", "_2", "_3"):
        report_dob_day = numeric(row.get(f"{prefix}_prepaint{suffix}"))
        if report_dob_day is None or report_dob_day >= t0_dob_day:
            continue
        diagnosis_relative_days.append(report_dob_day - dob_dx_day)
        result = str(row.get(f"{result_prefix}{suffix}", "") or "").strip()
        if result and result.lower() not in {"nan", "nat", "none"}:
            values.append(result)
    return values, diagnosis_relative_days


def pathology_biomarker_summary(row: pd.Series) -> dict[str, Any]:
    msi_values, msi_days = _pre_t0_result_values(row, "msi", "msi_result")
    mmr_values, mmr_days = _pre_t0_result_values(row, "mmr", "mmr_result")
    msi_lower = [value.lower() for value in msi_values]
    mmr_lower = [value.lower() for value in mmr_values]

    msi_high = any(value.startswith("msi-h") for value in msi_lower)
    msi_nonhigh = any(value.startswith(("mss", "msi-l")) for value in msi_lower)
    dmmr = any(
        "deficient mismatch repair" in value
        or ("loss of nuclear expression" in value and not value.startswith("no loss"))
        for value in mmr_lower
    )
    pmmr = any(value.startswith("no loss") or value.endswith("proficient") for value in mmr_lower)
    has_report = bool(msi_days or mmr_days)

    if msi_high or dmmr:
        state = "positive_msi_h_or_dmmr"
    elif msi_nonhigh or pmmr:
        state = "explicit_nonpositive_requires_manual_review"
    elif has_report:
        state = "indeterminate_requires_manual_review"
    else:
        state = "unknown_no_pre_t0_linked_result"

    all_days = msi_days + mmr_days
    return {
        "msi_mmr_evidence_state": state,
        "has_pre_t0_msi_or_mmr_report": has_report,
        "latest_pathology_evidence_day": max(all_days) if all_days else None,
    }


def attach_pathology_context(selected: pd.DataFrame, data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cpt = data["raw_cpt"]
    cancer = data["raw_cancer"]
    pathology = data["pathology"]
    linked = selected.merge(
        cpt[
            KEY_CANCER
            + ["cpt_number", "path_proc_number", "path_rep_number"]
        ],
        left_on=KEY_CANCER + ["index_ngs_cpt_number"],
        right_on=KEY_CANCER + ["cpt_number"],
        how="left",
        validate="one_to_one",
    )
    linked = linked.merge(
        cancer[KEY_CANCER + ["dob_ca_dx_days"]],
        on=KEY_CANCER,
        how="left",
        validate="many_to_one",
    )
    linked = linked.merge(
        pathology,
        on=["cohort", "record_id", "path_proc_number", "path_rep_number"],
        how="left",
        validate="many_to_one",
    )
    linked["t0_dob_day"] = pd.to_numeric(linked["dob_ca_dx_days"], errors="coerce") + pd.to_numeric(
        linked["start_day"], errors="coerce"
    )
    summaries = [pathology_biomarker_summary(row) for _, row in linked.iterrows()]
    for field in summaries[0] if summaries else []:
        linked[field] = [summary[field] for summary in summaries]
    return linked


def genomic_signal_map(raw_root: Path, selected_samples: set[str]) -> dict[str, dict[str, Any]]:
    signals = {
        sample: {
            "braf_v600e": False,
            "tumor_brca_signal": False,
            "fusion_genes": set(),
        }
        for sample in selected_samples
    }
    mutations = pd.read_csv(
        find_raw_file(raw_root, "data_mutations_extended.txt"),
        sep="\t",
        dtype=str,
        low_memory=False,
    )
    mutations = mutations.loc[mutations["Tumor_Sample_Barcode"].astype(str).isin(selected_samples)].copy()
    hgvsp = mutations["HGVSp_Short"].fillna("").str.upper().str.replace("P.", "", regex=False)
    for sample in mutations.loc[mutations["Hugo_Symbol"].eq("BRAF") & hgvsp.eq("V600E"), "Tumor_Sample_Barcode"]:
        signals[str(sample)]["braf_v600e"] = True
    for sample in mutations.loc[
        mutations["Hugo_Symbol"].isin({"BRCA1", "BRCA2"}), "Tumor_Sample_Barcode"
    ]:
        signals[str(sample)]["tumor_brca_signal"] = True

    structural = pd.read_csv(
        find_raw_file(raw_root, "data_sv.txt"),
        sep="\t",
        dtype=str,
        low_memory=False,
    )
    structural = structural.loc[structural["Sample_Id"].astype(str).isin(selected_samples)].copy()
    narrative = structural[["Event_Info", "Annotation", "Comments"]].fillna("").agg(" ".join, axis=1).str.lower()
    structural = structural.loc[narrative.str.contains("fusion", regex=False)].copy()
    for _, row in structural.iterrows():
        involved = {str(row.get("Site1_Hugo_Symbol", "")), str(row.get("Site2_Hugo_Symbol", ""))} & FUSION_GENES
        if involved:
            signals[str(row["Sample_Id"])]["fusion_genes"].update(involved)

    for sample in signals:
        signals[sample]["fusion_genes"] = sorted(signals[sample]["fusion_genes"])
    return signals


def prior_treatment_summary(selected: pd.DataFrame, regimen: pd.DataFrame) -> pd.DataFrame:
    decision = selected[KEY_CANCER + ["start_day", "advanced_evidence_day"]].copy()
    pairs = decision.merge(
        regimen[KEY_CANCER + ["start_day", "regimen_family", "regimen_mapping_status"]],
        on=KEY_CANCER,
        suffixes=("_t0", "_prior"),
        how="left",
    )
    prior = pairs.loc[
        pairs["start_day_prior"].lt(pairs["start_day_t0"])
        & pairs["start_day_prior"].ge(pairs["advanced_evidence_day"])
    ].copy()
    summaries: list[dict[str, Any]] = []
    grouped = {key: group for key, group in prior.groupby(KEY_CANCER, dropna=False)}
    for _, row in selected.iterrows():
        key = tuple(row[field] for field in KEY_CANCER)
        group = grouped.get(key, pd.DataFrame())
        families = sorted(set(group.get("regimen_family", pd.Series(dtype=str)).dropna().astype(str)))
        mapping_values = set(group.get("regimen_mapping_status", pd.Series(dtype=str)).dropna().astype(str))
        summaries.append(
            {
                **{field: row[field] for field in KEY_CANCER},
                "n_prior_advanced_regimens": len(group),
                "prior_regimen_families": families,
                "has_prior_folfirinox": "FOLFIRINOX_or_variant" in families,
                "has_prior_gemcitabine_based": any(value.startswith("gemcitabine_") for value in families),
                "has_prior_platinum_based": any(
                    value in {
                        "FOLFIRINOX_or_variant",
                        "FOLFOX_or_variant",
                        "CAPOX",
                        "gemcitabine_cisplatin",
                        "gemcitabine_oxaliplatin",
                        "fluorouracil_irinotecan_oxaliplatin",
                    }
                    for value in families
                ),
                "prior_mapping_uncertain": bool(mapping_values - {"standardized"}),
            }
        )
    return pd.DataFrame(summaries)


def build_decision_context(repo_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = cohort_audit.load_data(repo_root)
    selected = cohort_audit.select_t0_candidates(data, advanced_rule="strict")
    selected = attach_pathology_context(selected, data)
    prior = prior_treatment_summary(selected, data["regimen"])
    selected = selected.merge(prior, on=KEY_CANCER, how="left", validate="one_to_one")
    raw_root = repo_root / cohort_audit.PANC_RELATIVE_ROOT
    sample_ids = set(selected["index_ngs_sample_id"].dropna().astype(str))
    signals = genomic_signal_map(raw_root, sample_ids)
    selected["braf_v600e"] = [
        signals.get(str(value), {}).get("braf_v600e", False) for value in selected["index_ngs_sample_id"]
    ]
    selected["tumor_brca_signal"] = [
        signals.get(str(value), {}).get("tumor_brca_signal", False) for value in selected["index_ngs_sample_id"]
    ]
    selected["fusion_genes"] = [
        signals.get(str(value), {}).get("fusion_genes", []) for value in selected["index_ngs_sample_id"]
    ]
    selected["t0_start_day"] = selected["start_day"]
    return selected, data


def assign_pilot_strata(context: pd.DataFrame, protocol: dict[str, Any]) -> pd.DataFrame:
    namespace = str(protocol["sample"]["stable_hash_namespace"])
    target_total = int(protocol["sample"]["target_decision_points"])
    context = context.copy()
    context["stable_order"] = [stable_hash(namespace, [row[field] for field in KEY_CANCER]) for _, row in context.iterrows()]
    context["actionable_fusion_signal"] = context["fusion_genes"].map(bool)
    context["pre_t0_msi_or_mmr_report"] = context["has_pre_t0_msi_or_mmr_report"].astype(bool)
    context["tumor_brca_signal_not_germline"] = context["tumor_brca_signal"].astype(bool)
    context["prior_folfirinox"] = context["has_prior_folfirinox"].astype(bool)
    context["prior_gemcitabine_based"] = context["has_prior_gemcitabine_based"].astype(bool)
    context["no_prior_advanced_regimen"] = context["n_prior_advanced_regimens"].eq(0)
    context["prior_mapping_uncertain"] = context["prior_mapping_uncertain"].astype(bool)

    chosen: list[pd.DataFrame] = []
    used: set[tuple[str, str, str]] = set()
    for stratum in protocol["sample"]["strata"]:
        name = str(stratum["name"])
        if name == "deterministic_fill":
            continue
        selected_so_far = sum(len(frame) for frame in chosen)
        target = min(int(stratum["target_n"]), target_total - selected_so_far)
        if target <= 0:
            break
        eligible = context.loc[context[name]].sort_values("stable_order", kind="mergesort")
        eligible = eligible.loc[
            ~eligible.apply(lambda row: tuple(str(row[field]) for field in KEY_CANCER) in used, axis=1)
        ].head(target)
        if not eligible.empty:
            eligible = eligible.copy()
            eligible["pilot_stratum"] = name
            chosen.append(eligible)
            used.update(tuple(str(row[field]) for field in KEY_CANCER) for _, row in eligible.iterrows())
        if sum(len(frame) for frame in chosen) >= target_total:
            break

    n_remaining = target_total - sum(len(frame) for frame in chosen)
    if n_remaining > 0:
        fill = context.loc[
            ~context.apply(lambda row: tuple(str(row[field]) for field in KEY_CANCER) in used, axis=1)
        ].sort_values("stable_order", kind="mergesort").head(n_remaining)
        fill = fill.copy()
        fill["pilot_stratum"] = "deterministic_fill"
        chosen.append(fill)

    pilot = pd.concat(chosen, ignore_index=True) if chosen else pd.DataFrame()
    if len(pilot) != target_total:
        raise ValueError(f"could not select configured Pilot size: {len(pilot)} != {target_total}")
    pilot = pilot.sort_values(["pilot_stratum", "stable_order"], kind="mergesort").reset_index(drop=True)
    pilot["pilot_case_code"] = [f"PILOT-{index:03d}" for index in range(1, len(pilot) + 1)]
    return pilot


def reviewer_case_summary(context: dict[str, Any]) -> dict[str, Any]:
    priority_candidates: set[str] = set()
    questions = {
        "Confirm line-of-therapy interpretation using pre-t0 history only.",
        "Do not infer Track B clinical clearance from missing safety data.",
    }
    fusion_genes = set(context["fusion_genes"])
    if fusion_genes & {"NTRK1", "NTRK2", "NTRK3"}:
        priority_candidates.add("ntrk_fusion_targeted_therapy")
        questions.add("Confirm that the structural-variant annotation represents an actionable NTRK fusion.")
    if "NRG1" in fusion_genes:
        priority_candidates.add("zenocutuzumab_nrg1_fusion")
        questions.add("Confirm NRG1 fusion actionability and prior-treatment requirements.")
    if "RET" in fusion_genes:
        priority_candidates.add("selpercatinib_ret_fusion")
        questions.add("Confirm RET fusion actionability and regulatory conditions.")
    if bool(context["braf_v600e"]):
        priority_candidates.add("dabrafenib_trametinib_braf_v600e")
        questions.add("Confirm BRAF V600E assay interpretation and later-line requirement.")
    if bool(context["has_pre_t0_msi_or_mmr_report"]):
        priority_candidates.add("pembrolizumab_msi_h_dmmr")
        questions.add("Review whether the pre-t0 MSI/MMR result satisfies, contradicts, or leaves the composite condition unresolved.")
    if bool(context["tumor_brca_signal"]):
        priority_candidates.add("olaparib_maintenance_brca")
        questions.add("Treat tumor BRCA only as a review signal; confirm that germline status remains unavailable.")
    if bool(context["has_prior_folfirinox"]):
        priority_candidates.add("gemcitabine_paclitaxel_after_folfirinox")
        questions.add("Prior FOLFIRINOX is observed; failure or intolerance remains unobserved.")
    if bool(context["has_prior_gemcitabine_based"]):
        priority_candidates.update({"liposomal_irinotecan_fluorouracil_leucovorin", "folfox_or_off"})
        questions.add("Confirm that the observed prior regimen satisfies the candidate-specific gemcitabine requirement.")
    if int(context["n_prior_advanced_regimens"]) == 0:
        priority_candidates.update({"folfirinox", "nalirifox", "gemcitabine_nab_paclitaxel", "gemcitabine_monotherapy"})
        questions.add("Confirm first-line status and avoid using the observed t0 regimen as evidence.")
    if bool(context["prior_mapping_uncertain"]):
        priority_candidates.update({"fluorouracil_leucovorin", "folfox_or_off"})
        questions.add("Resolve uncertain prior-regimen mapping before candidate exclusion.")
    return {
        "pilot_case_code": context["pilot_case_code"],
        "pilot_stratum": context["pilot_stratum"],
        "n_prior_advanced_regimens": int(context["n_prior_advanced_regimens"]),
        "prior_regimen_families": json.dumps(context["prior_regimen_families"], separators=(",", ":")),
        "msi_mmr_evidence_state": context["msi_mmr_evidence_state"],
        "braf_v600e": bool(context["braf_v600e"]),
        "tumor_brca_signal_not_germline": bool(context["tumor_brca_signal"]),
        "fusion_genes": json.dumps(context["fusion_genes"], separators=(",", ":")),
        "priority_candidate_ids": json.dumps(sorted(priority_candidates), separators=(",", ":")),
        "review_questions": json.dumps(sorted(questions), separators=(",", ":")),
    }


def line_assessment(candidate: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    allowed = set(candidate.get("line_of_therapy", {}).get("allowed", []))
    n_prior = int(context["n_prior_advanced_regimens"])
    first_allowed = "first_line" in allowed
    later_allowed = any("later_line" in value or value.startswith("maintenance_") for value in allowed)
    no_alternative_clause = any("or_no_satisfactory_alternative" in value for value in allowed)
    if first_allowed and later_allowed:
        return "satisfied", "LINE_FIRST_OR_LATER_ALLOWED"
    if first_allowed:
        return ("satisfied", "LINE_FIRST_NO_PRIOR_ADVANCED") if n_prior == 0 else ("not_satisfied", "LINE_FIRST_HAS_PRIOR_ADVANCED")
    if no_alternative_clause and n_prior == 0:
        return "manual_review", "LINE_NO_SATISFACTORY_ALTERNATIVE_STATUS_UNAVAILABLE"
    if later_allowed:
        return ("satisfied", "LINE_LATER_HAS_PRIOR_ADVANCED") if n_prior > 0 else ("not_satisfied", "LINE_LATER_NO_PRIOR_ADVANCED")
    return "manual_review", "LINE_RULE_NOT_MACHINE_RESOLVED"


def prior_assessment(candidate: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    candidate_id = str(candidate["candidate_id"])
    n_prior = int(context["n_prior_advanced_regimens"])
    uncertain = bool(context["prior_mapping_uncertain"])
    if candidate_id in {"folfirinox", "gemcitabine_nab_paclitaxel", "gemcitabine_monotherapy"}:
        return ("not_applicable", "PRIOR_NOT_REQUIRED_AT_FIRST_ADVANCED_DECISION") if n_prior == 0 else ("manual_review", "PRIOR_CONTEXT_REQUIRES_REVIEW")
    if candidate_id == "nalirifox":
        return ("not_applicable", "PRIOR_NOT_REQUIRED_AT_FIRST_ADVANCED_DECISION") if n_prior == 0 else ("not_satisfied", "PRIOR_ADVANCED_THERAPY_PRESENT_FOR_FIRST_LINE_ONLY_CANDIDATE")
    if candidate_id == "liposomal_irinotecan_fluorouracil_leucovorin":
        if context["has_prior_gemcitabine_based"]:
            return "satisfied", "PRIOR_GEMCITABINE_BASED_OBSERVED"
        return ("unknown", "PRIOR_REGIMEN_MAPPING_UNCERTAIN") if uncertain else ("not_satisfied", "PRIOR_GEMCITABINE_BASED_NOT_OBSERVED")
    if candidate_id == "folfox_or_off":
        if context["has_prior_gemcitabine_based"]:
            return "satisfied", "PRIOR_GEMCITABINE_BASED_OBSERVED"
        return ("manual_review", "PRIOR_OTHER_CONTEXT_REQUIRES_REVIEW") if n_prior > 0 else ("not_satisfied", "PRIOR_REQUIRED_NOT_OBSERVED")
    if candidate_id == "gemcitabine_paclitaxel_after_folfirinox":
        if context["has_prior_folfirinox"]:
            return "manual_review", "PRIOR_FOLFIRINOX_OBSERVED_FAILURE_OR_INTOLERANCE_UNAVAILABLE"
        return "not_satisfied", "PRIOR_FOLFIRINOX_NOT_OBSERVED"
    if candidate_id == "olaparib_maintenance_brca":
        if context["has_prior_platinum_based"]:
            return "manual_review", "PRIOR_PLATINUM_OBSERVED_NO_PROGRESSION_STATUS_UNAVAILABLE"
        return "not_satisfied", "PRIOR_PLATINUM_NOT_OBSERVED"
    if candidate_id == "fluorouracil_leucovorin":
        return ("satisfied", "PRIOR_ADVANCED_REGIMEN_OBSERVED") if n_prior > 0 else ("not_satisfied", "PRIOR_ADVANCED_REGIMEN_NOT_OBSERVED")
    if n_prior > 0:
        return "manual_review", "PRIOR_TREATMENT_OBSERVED_PROGRESSION_OR_ALTERNATIVE_STATUS_UNAVAILABLE"
    return "manual_review", "NO_PRIOR_TREATMENT_BUT_NO_SATISFACTORY_ALTERNATIVE_STATUS_UNAVAILABLE"


def biomarker_assessment(candidate: dict[str, Any], context: dict[str, Any]) -> tuple[str, str, str]:
    requirements = candidate.get("biomarker_requirements", {})
    if requirements.get("status") == "not_required":
        return "not_applicable", "BIOMARKER_NOT_REQUIRED", "not_applicable"
    markers = set(requirements.get("required_markers", []))
    if markers & GERMLINE_ONLY_MARKERS:
        if context["tumor_brca_signal"]:
            return "unknown", "TUMOR_BRCA_SIGNAL_NOT_GERMLINE_EVIDENCE", "tumor_brca_signal_not_germline"
        return "unknown", "GERMLINE_BRCA_UNAVAILABLE", "unknown"
    if "msi_h_or_dmmr" in markers:
        state = str(context["msi_mmr_evidence_state"])
        if state == "positive_msi_h_or_dmmr":
            return "satisfied", "PRE_T0_MSI_H_OR_DMMR", state
        if state.startswith("explicit_nonpositive"):
            return "manual_review", "PRE_T0_MSI_MMR_NONPOSITIVE_COMPOSITE_REQUIRES_REVIEW", state
        if state.startswith("indeterminate"):
            return "manual_review", "PRE_T0_MSI_MMR_INDETERMINATE", state
        return "unknown", "MSI_MMR_PRE_T0_RESULT_UNAVAILABLE", state
    if "tmb_h" in markers:
        return "unknown", "TMB_H_UNAVAILABLE", "unknown"
    if "nrg1_gene_fusion" in markers:
        return (("satisfied", "PRE_T0_NRG1_FUSION", "positive") if "NRG1" in context["fusion_genes"] else ("unknown", "NRG1_FUSION_NOT_ESTABLISHED", "unknown"))
    if "ntrk1_ntrk2_or_ntrk3_gene_fusion" in markers:
        has_ntrk = bool({"NTRK1", "NTRK2", "NTRK3"} & set(context["fusion_genes"]))
        return (("satisfied", "PRE_T0_NTRK_FUSION", "positive") if has_ntrk else ("unknown", "NTRK_FUSION_NOT_ESTABLISHED", "unknown"))
    if "ret_gene_fusion" in markers:
        return (("satisfied", "PRE_T0_RET_FUSION", "positive") if "RET" in context["fusion_genes"] else ("unknown", "RET_FUSION_NOT_ESTABLISHED", "unknown"))
    if "braf_v600e" in markers:
        return (("satisfied", "PRE_T0_BRAF_V600E", "positive") if context["braf_v600e"] else ("unknown", "BRAF_V600E_NOT_ESTABLISHED", "unknown"))
    if "her2_positive_ihc_3_plus" in markers:
        return "unknown", "HER2_IHC_3_PLUS_UNAVAILABLE", "unknown"
    return "manual_review", "BIOMARKER_RULE_NOT_MACHINE_RESOLVED", "manual_review"


def candidate_row(
    context: dict[str, Any],
    candidate: dict[str, Any],
    protocol: dict[str, Any],
    label_schema: dict[str, Any],
    cohort_version: str,
    candidate_version: str,
) -> dict[str, Any]:
    line_value, line_reason = line_assessment(candidate, context)
    prior_value, prior_reason = prior_assessment(candidate, context)
    biomarker_value, biomarker_reason, biomarker_state = biomarker_assessment(candidate, context)
    conditions = [
        {"condition_type": "disease_scope", "required": True, "assessment": "satisfied"},
        {"condition_type": "treatment_setting", "required": True, "assessment": "satisfied"},
        {"condition_type": "line_of_therapy", "required": True, "assessment": line_value},
        {"condition_type": "prior_treatment", "required": True, "assessment": prior_value},
        {"condition_type": "biomarker", "required": True, "assessment": biomarker_value},
    ]
    evidence_mapping = protocol["label_policy"]["candidate_evidence_status_mapping"]
    evidence_status = evidence_mapping.get(candidate.get("evidence_status"), "insufficient_evidence")
    override = label_schema.get("candidate_policy_overrides", {}).get(candidate["candidate_id"], {})
    assessment = {
        "row_validity_status": "valid",
        "required_track_a_conditions": conditions,
        "evidence_status": evidence_status,
        "maximum_track_a_label": override.get("maximum_track_a_label"),
    }
    label = derive_track_a_label(assessment)
    reason_codes = ["DISEASE_SCOPE_LOCKED_PDAC", "TREATMENT_SETTING_LOCKED_ADVANCED", line_reason, prior_reason, biomarker_reason]
    if evidence_status == "conditional":
        reason_codes.append("CANDIDATE_EVIDENCE_CONDITIONAL")
    if override.get("maximum_track_a_label") == "conditional_review":
        reason_codes.append("TRACK_A_LABEL_CEILING_CONDITIONAL_REVIEW")
    return {
        "pilot_case_code": context["pilot_case_code"],
        "cohort": context["cohort"],
        "record_id": context["record_id"],
        "ca_seq": context["ca_seq"],
        "t0_start_day": context["t0_start_day"],
        "pilot_stratum": context["pilot_stratum"],
        "candidate_id": candidate["candidate_id"],
        "row_validity_status": "valid",
        "evidence_status": evidence_status,
        "evidence_source_ids": json.dumps(candidate.get("evidence_source_ids", []), separators=(",", ":")),
        "track_a_condition_assessments": json.dumps(conditions, separators=(",", ":")),
        "track_a_evidence_constraint_label": label,
        "maximum_track_a_label": override.get("maximum_track_a_label", ""),
        "track_b_assessment_status": "frozen_unavailable",
        "clinical_clearance_status": "not_assessed_track_b_frozen",
        "reason_codes": json.dumps(reason_codes, separators=(",", ":")),
        "biomarker_evidence_state": biomarker_state,
        "prior_advanced_regimen_count": int(context["n_prior_advanced_regimens"]),
        "prior_regimen_mapping_status": "uncertain" if context["prior_mapping_uncertain"] else "standardized_or_none",
        "label_origin": "rule_derived",
        "review_status": "not_reviewed",
        "schema_version": label_schema["version"],
        "candidate_space_version": candidate_version,
        "cohort_definition_version": cohort_version,
        "pilot_protocol_version": protocol["version"],
    }


def build_public_summary(
    pilot: pd.DataFrame,
    candidate_rows: list[dict[str, Any]],
    protocol: dict[str, Any],
) -> list[dict[str, str]]:
    threshold = int(protocol["outputs"]["public_small_cell_threshold"])
    rows: list[dict[str, str]] = []

    def add(section: str, metric: str, value: str, status: str, note: str) -> None:
        rows.append({"section": section, "metric": metric, "value": value, "status": status, "note": note})

    add("artifact", "decision_points", str(len(pilot)), "pass", "Configured private Pilot size.")
    add("artifact", "patient_candidate_rows", str(len(candidate_rows)), "pass", "Every Pilot decision point crossed with every main candidate.")
    for stratum, count in Counter(pilot["pilot_stratum"]).items():
        add("sampling", str(stratum), suppress_count(count, threshold), "descriptive", "Priority strata overlap in the source cohort; assignment is without replacement.")
    for label, count in Counter(row["track_a_evidence_constraint_label"] for row in candidate_rows).items():
        add("rule_label", str(label), suppress_count(count, threshold), "draft_not_reviewed", "Rule-derived Pilot label; clinical adjudication pending.")
    add("time", "ngs_strictly_before_t0", "true", "pass", "Same-day NGS reports are excluded by the locked cohort selector.")
    add("time", "pathology_strictly_before_t0", "true", "pass", "DOB-relative pathology report dates are converted before comparison.")
    add("leakage", "current_t0_regimen_used", "false", "pass", "Label derivation uses the pre-t0 clinical context.")
    add("leakage", "post_t0_outcome_used", "false", "pass", "Outcome linkage remains a secondary analysis axis.")
    add("review", "plan_a_primary", "expert_double_review", "pending", "Two independent reviews plus disagreement adjudication.")
    add("review", "plan_b_secondary", "frozen_guideline_rulebook", "standby", "Requires documented supervisor approval and yields guideline evidence eligibility only.")
    add("review", "clinical_double_review", "pending", "pending", "Two reviewers and adjudication are required before any label freeze.")
    add("track_b", "clinical_clearance", "not_assessed", "frozen", "Track B clinical clearance remains a separate frozen axis.")
    return rows


def write_public_report(path: Path, rows: list[dict[str, str]], protocol: dict[str, Any]) -> None:
    lines = [
        "# Pilot Evidence-Label Validation Report v0.1",
        "",
        "Status: **draft, rule-derived, review pending**.",
        "",
        "## Purpose",
        "",
        "Validate Track A evidence extraction, candidate coverage, time alignment, review status, privacy, and small-cell suppression on the private Pilot.",
        "",
        "## Process",
        "",
        "The Pilot crosses 24 Strict Extended decision points with 16 main-pool candidates. Patient-level files are stored under `data/processed/`; this report contains aggregate values with counts below five suppressed.",
        "",
        "## Results",
        "",
        "| Section | Metric | Value | Status | Note |",
        "|---|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['section']} | {row['metric']} | {row['value']} | {row['status']} | {row['note']} |")
    lines.extend(
        [
            "",
            "## Review",
            "",
            "Plan A uses independent double review and disagreement adjudication. Plan B uses a supervisor-approved frozen guideline rulebook and produces `guideline_evidence_eligibility`. Track B remains `frozen`.",
            "",
            f"Protocol: `{protocol['version']}` (`code/config/pilot_label_protocol_v0.1.yaml`).",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_outputs(repo_root: Path) -> dict[str, Any]:
    protocol = load_yaml(repo_root / "code" / "config" / "pilot_label_protocol_v0.1.yaml")
    candidate_space = load_yaml(repo_root / protocol["scope"]["candidate_space_path"])
    label_schema = load_yaml(repo_root / protocol["scope"]["label_schema_path"])
    cohort = load_yaml(repo_root / protocol["scope"]["cohort_definition_path"])
    context, _ = build_decision_context(repo_root)
    pilot = assign_pilot_strata(context, protocol)

    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidate_space["candidates"]}
    candidate_ids = candidate_space[protocol["scope"]["candidate_pool_field"]]
    rows = [
        candidate_row(
            context_row.to_dict(),
            candidate_by_id[candidate_id],
            protocol,
            label_schema,
            str(cohort["version"]),
            str(candidate_space["version"]),
        )
        for _, context_row in pilot.iterrows()
        for candidate_id in candidate_ids
    ]

    output = protocol["outputs"]
    private_dir = repo_root / output["private_directory"]
    decision_fields = ["pilot_case_code"] + KEY_DECISION + [
        "pilot_stratum",
        "advanced_evidence_day",
        "index_ngs_report_day",
        "latest_pathology_evidence_day",
        "msi_mmr_evidence_state",
        "braf_v600e",
        "tumor_brca_signal",
        "fusion_genes",
        "n_prior_advanced_regimens",
        "prior_regimen_families",
        "prior_mapping_uncertain",
    ]
    decision_rows = []
    for _, row in pilot.iterrows():
        item = {field: row.get(field, "") for field in decision_fields}
        item["fusion_genes"] = json.dumps(item["fusion_genes"], separators=(",", ":"))
        item["prior_regimen_families"] = json.dumps(item["prior_regimen_families"], separators=(",", ":"))
        decision_rows.append(item)
    write_csv(private_dir / output["private_decision_points"], decision_rows, decision_fields)

    linkage_fields = ["pilot_case_code"] + KEY_DECISION + ["index_ngs_sample_id", "index_ngs_cpt_number"]
    linkage_rows = [{field: row.get(field, "") for field in linkage_fields} for _, row in pilot.iterrows()]
    write_csv(private_dir / output["private_case_linkage"], linkage_rows, linkage_fields)

    case_index_rows = [reviewer_case_summary(row.to_dict()) for _, row in pilot.iterrows()]
    case_index_fields = list(case_index_rows[0]) if case_index_rows else []
    write_csv(private_dir / output["private_reviewer_case_index"], case_index_rows, case_index_fields)

    candidate_fields = list(rows[0]) if rows else []
    write_csv(private_dir / output["private_patient_candidate_rows"], rows, candidate_fields)
    review_fields = [
        "pilot_case_code",
        "candidate_id",
        "track_a_evidence_constraint_label",
        "biomarker_evidence_state",
        "reason_codes",
        "reviewer_1_label",
        "reviewer_1_reason",
        "reviewer_2_label",
        "reviewer_2_reason",
        "adjudicated_label",
        "adjudication_reason",
        "review_status",
    ]
    review_rows = [
        {
            **{
                field: row[field]
                for field in [
                    "pilot_case_code",
                    "candidate_id",
                    "track_a_evidence_constraint_label",
                    "biomarker_evidence_state",
                    "reason_codes",
                ]
            },
            "review_status": "not_reviewed",
        }
        for row in rows
    ]
    write_csv(private_dir / output["private_review_template"], review_rows, review_fields)

    summary = build_public_summary(pilot, rows, protocol)
    write_csv(repo_root / output["public_summary_table"], summary, ["section", "metric", "value", "status", "note"])
    write_public_report(repo_root / output["public_report"], summary, protocol)
    return {
        "decision_points": len(pilot),
        "candidate_rows": len(rows),
        "candidate_count": len(candidate_ids),
        "private_directory": str(private_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    result = build_outputs(args.repo_root.resolve())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
