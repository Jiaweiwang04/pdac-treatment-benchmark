"""Generate a safe aggregate crosswalk from the existing BPC regimen mapping."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import privacy_checks as privacy


OUTPUT_FIELDS = [
    "regimen_family",
    "canonical_drug_set",
    "candidate_id",
    "mapping_relation",
    "mapping_status",
    "reason",
    "manual_review_required",
    "observed_rows",
    "strict_t0_rows",
]


def mapping_targets(family: str, canonical: str, status: str) -> list[dict[str, Any]]:
    if status == "masked_not_actionable" or "investigational_drug" in canonical:
        return [{"candidate_id": "masked_investigational_regimen_review", "relation": "masked_or_unresolvable", "status": "masked_or_unresolvable", "reason": "Investigational component is masked; no concrete drug is inferred.", "manual": True}]
    if family == "FOLFIRINOX_or_variant":
        return [{"candidate_id": "folfirinox", "relation": "variant", "status": "observed_variant", "reason": "Full recognized component set matches FOLFIRINOX; dose or modification detail is unavailable.", "manual": False}]
    if family == "gemcitabine_nab_paclitaxel":
        return [{"candidate_id": "gemcitabine_nab_paclitaxel", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches the named candidate.", "manual": False}]
    if family == "gemcitabine_monotherapy":
        return [{"candidate_id": "gemcitabine_monotherapy", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches single-agent gemcitabine.", "manual": False}]
    if family == "5FU_liposomal_irinotecan_leucovorin":
        return [{"candidate_id": "liposomal_irinotecan_fluorouracil_leucovorin", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches the post-gemcitabine candidate.", "manual": False}]
    if family == "5FU_liposomal_irinotecan":
        return [{"candidate_id": "liposomal_irinotecan_fluorouracil_leucovorin", "relation": "partial", "status": "observed_partial", "reason": "Liposomal irinotecan and fluorouracil are present but leucovorin is not confirmed in this raw component set.", "manual": True}]
    if family == "5FU_leucovorin":
        return [{"candidate_id": "fluorouracil_leucovorin", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches fluorouracil plus leucovorin.", "manual": False}]
    if family in {"FOLFOX_or_variant", "fluorouracil_oxaliplatin", "CAPOX"}:
        reason = "Fluorouracil, leucovorin, and oxaliplatin or a recognized component variant are present; clinical context separates FOLFOX from OFF-like use."
        if family == "CAPOX":
            reason = "Capecitabine is a fluoropyrimidine prodrug and the observed oxaliplatin combination is a variant of the fluoropyrimidine/oxaliplatin candidate; clinical setting remains unresolved."
        return [{"candidate_id": "folfox_or_off", "relation": "variant", "status": "observed_variant", "reason": reason, "manual": True}]
    if family == "FOLFIRI" or family == "fluorouracil_irinotecan":
        return [{"candidate_id": "folfiri_or_irinotecan_fluoropyrimidine", "relation": "variant", "status": "observed_variant", "reason": "Ordinary irinotecan is kept separate from liposomal irinotecan; line and clinical role are not fully available.", "manual": True}]
    if family == "gemcitabine_cisplatin":
        return [{"candidate_id": "gemcitabine_cisplatin_hrd", "relation": "partial", "status": "observed_partial", "reason": "Observed component set is compatible with an HRD-context candidate, but biomarker and line conditions are not in this mapping.", "manual": True}]
    if family == "gemcitabine_capecitabine":
        return [{"candidate_id": "gemcitabine_capecitabine", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches the extended candidate; current role remains pending review.", "manual": True}]
    if family == "capecitabine_monotherapy":
        return [{"candidate_id": "capecitabine_monotherapy", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches the extended single-agent candidate; observed use is not a gold standard.", "manual": True}]
    if family == "PARP_inhibitor":
        return [{"candidate_id": "olaparib_maintenance_brca", "relation": "partial", "status": "observed_drug_only", "reason": "Olaparib is observed, but maintenance role, germline BRCA status, and prior platinum response are not encoded in regimen mapping.", "manual": True}]
    if family == "immune_checkpoint_inhibitor":
        return [
            {"candidate_id": "pembrolizumab_msi_h_dmmr", "relation": "partial", "status": "observed_drug_only", "reason": "Pembrolizumab is observed but MSI-H/dMMR status is not encoded in regimen mapping.", "manual": True},
            {"candidate_id": "pembrolizumab_tmb_h", "relation": "partial", "status": "observed_drug_only", "reason": "Pembrolizumab is observed but TMB-H status is not encoded in regimen mapping.", "manual": True},
        ]
    if family == "gemcitabine_oxaliplatin":
        return [{"candidate_id": "gemcitabine_oxaliplatin", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches the extended candidate; current role remains pending review.", "manual": True}]
    if family == "gemcitabine_erlotinib":
        return [{"candidate_id": "gemcitabine_erlotinib", "relation": "exact", "status": "observed_exact", "reason": "Canonical set exactly matches the extended legacy/context candidate.", "manual": True}]
    if family == "non_pdac_context_or_endocrine":
        return [{"candidate_id": "not_applicable", "relation": "not_candidate", "status": "not_candidate", "reason": "Observed regimen is endocrine or non-PDAC context and is excluded from the PDAC candidate space.", "manual": False}]
    if family in {"targeted_or_biologic_other", "recognized_other_combination", "other_nos", "irinotecan_monotherapy", "liposomal_irinotecan_monotherapy"}:
        return [{"candidate_id": "evidence_insufficient_direct_treatment", "relation": "ambiguous", "status": "manual_review", "reason": "Observed components do not establish a current named PDAC candidate or required clinical role.", "manual": True}]
    return [{"candidate_id": "evidence_insufficient_direct_treatment", "relation": "ambiguous", "status": "manual_review", "reason": "No deterministic candidate mapping is justified from the aggregate regimen mapping.", "manual": True}]


def generate(input_path: Path, output_path: Path) -> int:
    rows: list[dict[str, Any]] = []
    with input_path.open(encoding="utf-8", newline="") as handle:
        for source in csv.DictReader(handle):
            family = str(source.get("regimen_family", ""))
            canonical = str(source.get("canonical_drug_set", ""))
            status = str(source.get("mapping_status", ""))
            for target in mapping_targets(family, canonical, status):
                rows.append(
                    {
                        "regimen_family": family,
                        "canonical_drug_set": canonical,
                        "candidate_id": target["candidate_id"],
                        "mapping_relation": target["relation"],
                        "mapping_status": target["status"],
                        "reason": target["reason"],
                        "manual_review_required": str(bool(target["manual"])).lower(),
                        "observed_rows": source.get("n_all_regimen_rows", ""),
                        "strict_t0_rows": source.get("n_strict_t0_rows", ""),
                    }
                )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: privacy.public_cell(field, row.get(field, ""), row) for field in OUTPUT_FIELDS})
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.repo_root.resolve()
    count = generate(root / "code/results/mappings/regimen_mapping_v0.1.csv", root / "code/results/mappings/candidate_regimen_crosswalk_v0.1.csv")
    print(f"generated_crosswalk_rows={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
