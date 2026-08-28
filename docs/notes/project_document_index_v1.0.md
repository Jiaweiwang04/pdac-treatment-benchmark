# Project Document Index v1.0

## Purpose

This index provides one route from the project overview to study design, data audits, machine-readable configurations, and aggregate results.

## Process

Documents are grouped by function. Design documents describe methods and decisions, configuration files store executable definitions, and reports store generated results.

## Results

| Category | Document | Purpose | Current result |
|---|---|---|---|
| Project entry | [README.zh-CN.md](../../README.zh-CN.md) / [README.md](../../README.md) | Project overview and reproduction commands | Updated through Pilot v0.1 |
| Research plan | `research_plan_pdac_treatment_benchmark_v3.0.docx` | Study question and benchmark design | Version 3.0 |
| Raw-data audit | [data_feasibility_audit_v1.md](../../code/results/reports/data_feasibility_audit_v1.md) | Data inventory, relationships, and availability | Round 1 complete |
| Cohort feasibility | [cohort_t0_feasibility_v1.md](../../code/results/reports/cohort_t0_feasibility_v1.md) | PDAC cohort and `t0` feasibility | Round 2 complete |
| Cohort lock | [cohort_lock_label_feasibility_v0.1.md](../../code/results/reports/cohort_lock_label_feasibility_v0.1.md) | Strict cohorts, endpoints, and label availability | Extended 557; Core 475 |
| Cohort definition | [cohort_definition_v0.1.yaml](../../code/config/cohort_definition_v0.1.yaml) | Executable cohort and `t0` definition | v0.1.3.1 draft |
| Candidate design | [candidate_treatment_space_design_v0.1.md](candidate_treatment_space_design_v0.1.md) | Candidate granularity, pools, evidence, and mapping | 16 main; 11 extended |
| Candidate configuration | [candidate_treatment_space_v0.1.yaml](../../code/config/candidate_treatment_space_v0.1.yaml) | Executable candidate space and evidence registry | v0.1.1 draft |
| Label design | [evidence_constraint_label_schema_design_v0.1.md](evidence_constraint_label_schema_design_v0.1.md) | Track A label semantics and derivation | v0.1 draft |
| Label configuration | [evidence_constraint_label_schema_v0.1.yaml](../../code/config/evidence_constraint_label_schema_v0.1.yaml) | Executable label contract | v0.1 draft |
| External evidence | [external_material_intake_v0.1.md](external_material_intake_v0.1.md) | Local source admission and use | Registry validated |
| Pilot design | [pilot_label_validation_design_v0.1.md](pilot_label_validation_design_v0.1.md) | Sampling, evidence extraction, and review | Design maintained separately from execution results |
| Pilot protocol | [pilot_label_protocol_v0.1.yaml](../../code/config/pilot_label_protocol_v0.1.yaml) | Executable Pilot and review strategy | Plan A primary; Plan B fallback |
| Pilot result | [pilot_label_validation_report_v0.1.md](../../code/results/reports/pilot_label_validation_report_v0.1.md) | Aggregate Pilot validation | Automated checks passed |
| Management standards | [standards_index_v1.0.md](standards/standards_index_v1.0.md) | Local workflow and data-code management references | Indexed; source PDFs remain local |

Historical audit reports retain their original content as research records. Current status and reproduction commands are maintained in the README files.
