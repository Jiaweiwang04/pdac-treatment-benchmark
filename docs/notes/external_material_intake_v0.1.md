# External Material Intake v0.1

## Purpose

This document records the provenance, admission status, and project use of local materials under `D:\复旦实验室\数据`. The tracked registry is [external_material_registry_v0.1.yaml](../../code/config/external_material_registry_v0.1.yaml), and machine-specific paths are stored in `code/config/local_external_sources.yaml`.

## Process

Each material is assessed for source identity, version, file hash, licensing, clinical relevance, privacy risk, and intended use. Admitted sources receive a claim-specific role in the evidence registry. Deferred and quarantined sources remain recorded with their review status.

## Results

| Source | Status | Project use |
|---|---|---|
| `aacr_bpc_panc_1_0_public` | available | primary cohort and treatment data; local copy matches the external source inventory |
| `nhc_antitumor_guidance_2025` | admitted | China practice and regulatory context for `gemcitabine_erlotinib` |
| `nmpa_marketed_drugs_snapshot_20250624` | admitted | drug-name normalization and historical market-status cross-check |
| `nmpa_trial_registry_snapshot` | deferred | future trial-registry protocol |
| `csco_2026_archive` | reviewed | archive contains 21 files and no pancreatic-cancer guideline |
| `drugbank_5_1_18_academic_archive` | license review | ingestion and redistribution review |
| `molecular_report_input_output_examples` | quarantined | identifier-bearing molecular-report examples |

The NHC 2025 source is registered as `official_practice_guidance` and linked to the extended candidate `gemcitabine_erlotinib`. The source records the pancreatic-cancer use context and the China exceptional-use governance requirement.

Large source archives, licensed databases, and patient-level examples remain in local storage. Git contains source metadata, hashes, admission decisions, and claim-specific links.

## Validation

```powershell
python code/scripts/validate_external_material_registry.py --repo-root .
python code/scripts/validate_external_material_registry.py --repo-root . --skip-local
python -m pytest code/tests/test_external_material_registry.py -q
```

The standard validation checks registry structure and local source hashes. The `--skip-local` mode checks the tracked registry in environments without the local source collection.
