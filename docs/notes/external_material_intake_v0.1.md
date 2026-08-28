# External material intake v0.1

## Scope

This intake records local materials made available under `D:\复旦实验室\数据` without copying large, licensed, copyrighted, or patient-level artifacts into Git. The tracked source of truth is `config/external_material_registry_v0.1.yaml`; the machine-specific path map is `config/local_external_sources.yaml` and is ignored by Git.

This intake does not change the Strict Extended 557 or Strict Core 475 cohorts, reselect `t0`, create patient-candidate labels, unfreeze Track B, or start training.

## Admission decisions

- `aacr_bpc_panc_1_0_public`: already present under the ignored raw-data path. The external and repository-local PANC copies each contain 72 files, 43,623,426 bytes, and the same relative path set. No duplicate copy was made.
- `nhc_antitumor_guidance_2025`: admitted for claim-specific supplementary China practice and regulatory context. The official notice was published on 2026-01-26. The reviewed pancreatic-cancer passage supports only the existing extended `gemcitabine_erlotinib` candidate context and does not create a new candidate or clinical-clearance label.
- `nmpa_marketed_drugs_snapshot_20250624`: admitted only for drug-name normalization and historical market-status cross-checking. It is a 2025-06-24 snapshot, is not efficacy evidence, and cannot establish current approval without live verification.
- `nmpa_trial_registry_snapshot`: deferred until a trial-registry protocol is defined. Trial registration does not establish efficacy.
- `csco_2026_archive`: not admitted because the 21-file archive has no pancreatic-cancer guideline. Other tumor-specific or supportive-care guidelines cannot substitute for a PDAC guideline.
- `drugbank_5_1_18_academic_archive`: not admitted because project-specific ingestion and redistribution rights have not been verified. It is not a clinical-efficacy source.
- `molecular_report_input_output_examples`: quarantined. Archive metadata shows identifier-bearing individual molecular reports, so the material must not be read, copied, extracted, indexed, or used by this project.

## Candidate-space use

The NHC 2025 source is registered as `official_practice_guidance` and linked only to `gemcitabine_erlotinib`, which remains in the extended pool with manual review and current-role uncertainty. The guidance records the FDA first-line pancreatic-cancer context and explicitly notes that the indication is not approved in China and requires exceptional-use governance and informed consent. This source does not promote the candidate to the main pool.

## Validation

Run the tracked-policy and local-presence checks with:

```powershell
python -B code/scripts/validate_external_material_registry.py --repo-root .
python -B -m unittest tests.test_external_material_registry
```

Use `--skip-local` when validating a clone that does not have the machine-specific external materials.
