# BPC PANC 原始数据可行性审计 v1

- 生成时间：2026-07-31T10:09:26
- 仓库根目录：`D:\代码集\Python\pdac-treatment-benchmark`
- 原始数据目录：`data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public`
- 审计边界：只读扫描 PANC 1.0-public；不清洗、不建模、不输出患者级记录。

## 1. 数据包概况

- 文件数：72
- 总大小：41.603 MB
- 文件格式计数：.csv=11, .pdf=4, .seg=1, .txt=54, .xlsx=2
- 聚合唯一患者数（patient_level_dataset.record_id）：1109
- 聚合唯一 NGS 样本数（cpt_genie_sample_id）：1130

## 2. 已检查项目材料

- README.md: 仓库 README 仅含项目名。
- V3.0研究方案: 已用 DOCX 标准库解析；确认四类候选状态和 Track A/B 边界。
- GA01-研究的基本流程步骤.pdf: 文件存在；本环境无 PDF 文本解析器，正文待确认。
- GA09-数据与代码管理规范.pdf: 文件存在；本环境无 PDF 文本解析器，正文待确认。
- BPC PANC README: ReadMe.txt 可用 UTF-8 读取，提供 AACR/Synapse/包说明链接。
- 数据字典: 解析到 827 个变量名映射；仍需人工核验列含义。
- 数据许可或使用说明: 未在可机读文本中完整确认；需核对 AACR/Synapse 官方条款及 PDF 手册。

## 3. 文件和数据表说明

完整清单位于 `code/results/data_audit/tables/file_inventory.csv`。核心表主题由文件路径和字段名启发式推断，待数据字典复核。
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/case_lists/cases_all.txt`: delimited_text, rows=5, cols=2, theme=metadata_or_case_list
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/case_lists/cases_cna.txt`: delimited_text, rows=5, cols=2, theme=metadata_or_case_list
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/case_lists/cases_cnaseq.txt`: delimited_text, rows=5, cols=2, theme=metadata_or_case_list
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/case_lists/cases_Pancreatic_Cancer.txt`: delimited_text, rows=5, cols=2, theme=metadata_or_case_list
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/case_lists/cases_sequenced.txt`: delimited_text, rows=5, cols=2, theme=metadata_or_case_list
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/case_lists/cases_sv.txt`: delimited_text, rows=5, cols=2, theme=metadata_or_case_list
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`: delimited_text, rows=1109, cols=35, theme=patient
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`: delimited_text, rows=1130, cols=9, theme=sample_or_ngs_test
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`: delimited_text, rows=1109, cols=7, theme=outcome_or_followup
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`: delimited_text, rows=1002, cols=121, theme=treatment
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_CNA.txt`: delimited_text, rows=1003, cols=964, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_cna_hg19.seg`: delimited_text, rows=26118, cols=6, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_matrix.txt`: delimited_text, rows=1130, cols=3, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_DFCI-ONCOPANEL-1.txt`: delimited_text, rows=3, cols=2, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_DFCI-ONCOPANEL-2.txt`: delimited_text, rows=3, cols=2, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_DFCI-ONCOPANEL-3.1.txt`: delimited_text, rows=3, cols=2, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_DFCI-ONCOPANEL-3.txt`: delimited_text, rows=3, cols=2, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_MSK-IMPACT341.txt`: delimited_text, rows=3, cols=2, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_MSK-IMPACT410.txt`: delimited_text, rows=3, cols=2, theme=genomic
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_panel_MSK-IMPACT468.txt`: delimited_text, rows=3, cols=2, theme=genomic
- 其余 52 个文件见 CSV 清单。

## 4. 主键、外键及表关系

关系均为候选关系，不作为正式 join 规则。必须用数据手册/变量字典确认后才能用于队列构建。
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID`; unique_count equals row_count (1109) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`SAMPLE_ID`; unique_count equals row_count (1130) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PATIENT_ID`; unique_count equals row_count (1109) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PATIENT_ID`; unique_count equals row_count (1002) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_matrix.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_matrix.txt`.`SAMPLE_ID`; unique_count equals row_count (1130) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_sample_acquisition.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_sample_acquisition.txt`.`SAMPLE_ID`; unique_count equals row_count (1130) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`cpt_genie_sample_id` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`cpt_genie_sample_id`; unique_count equals row_count (1130) and no missing values
- possible_composite_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`record_id+cpt_genie_sample_id` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`record_id+cpt_genie_sample_id`; ID-like fields; composite uniqueness requires formal confirmation.
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/manifest.csv`.`ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/manifest.csv`.`ID`; unique_count equals row_count (10) and no missing values
- candidate_primary_key: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/patient_level_dataset.csv`.`record_id` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/patient_level_dataset.csv`.`record_id`; unique_count equals row_count (1109) and no missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`PATIENT_ID`; 1109 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PATIENT_ID`; 1109 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PATIENT_ID`; 1002 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_cancer_diagnosis.txt`.`PATIENT_ID`; 1109 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_imaging.txt`.`PATIENT_ID`; 1094 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_labtest.txt`.`PATIENT_ID`; 937 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_medonc.txt`.`PATIENT_ID`; 1100 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_pathology.txt`.`PATIENT_ID`; 1109 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_sample_acquisition.txt`.`PATIENT_ID`; 1109 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_sequencing.txt`.`PATIENT_ID`; 1109 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`PATIENT_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_treatment.txt`.`PATIENT_ID`; 1034 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_gene_matrix.txt`.`SAMPLE_ID`; 1130 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_mutations_extended.txt`.`Tumor_Sample_Barcode`; 1087 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_sv.txt`.`Sample_Id`; 194 overlapping distinct non-missing values
- shared_identifier_candidate: `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_sample.txt`.`SAMPLE_ID` -> `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_sample_acquisition.txt`.`SAMPLE_ID`; 1130 overlapping distinct non-missing values
- 其余 168 条候选关系见 `code/results/data_audit/tables/table_relationships.csv`。

## 5. 患者、样本、治疗、分子和结局覆盖

- 唯一患者数：1109
- index cancer 行数：1110
- 有 NGS 检测记录的患者数：1109
- 有治疗 regimen 记录的患者数：1037
- 同时有 NGS 和治疗记录的患者数：1037
- cBioPortal 样本数：1130
- 多 NGS 检测患者数：20
- 多治疗 regimen 患者数：816

组织学、分期、转移、可切除状态和机构分布的聚合统计见 `code/results/data_audit/tables/categorical_summaries.csv`；小于阈值的类别已合并隐藏。

## 6. 关键字段缺失情况

完整字段级缺失率见 `code/results/data_audit/tables/missingness_summary.csv`。以下仅列关键字段：
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`CA_DMETS_YN`: missing=612/1109 (0.551849)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`CA_HISTOLOGY`: missing=401/1109 (0.361587)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_patient.txt`.`CA_RESECT_STATUS`: missing=1/1109 (0.000902)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_cancer_diagnosis.txt`.`CA_HISTOLOGY`: missing=523/1389 (0.37653)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_timeline_imaging.txt`.`INSTITUTION`: missing=0/14520 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/ca_radtx_dataset.csv`.`institution`: missing=0/526 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/ca_radtx_dataset.csv`.`record_id`: missing=0/526 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_index.csv`.`ca_dmets_yn`: missing=613/1110 (0.552252)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_index.csv`.`ca_histology`: missing=402/1110 (0.362162)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_index.csv`.`ca_resect_status`: missing=1/1110 (0.000901)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_index.csv`.`institution`: missing=0/1110 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_index.csv`.`record_id`: missing=0/1110 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_index.csv`.`stage_dx_iv`: missing=0/1110 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_non_index.csv`.`ca_dmets_yn`: missing=266/279 (0.953405)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_non_index.csv`.`ca_histology`: missing=121/279 (0.433692)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_non_index.csv`.`institution`: missing=0/279 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_level_dataset_non_index.csv`.`record_id`: missing=0/279 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`cpt_genie_sample_id`: missing=0/1130 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`dx_cpt_rep_days`: missing=0/1130 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`institution`: missing=0/1130 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/cancer_panel_test_level_dataset.csv`.`record_id`: missing=0/1130 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/imaging_level_dataset.csv`.`institution`: missing=0/14520 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/imaging_level_dataset.csv`.`record_id`: missing=0/14520 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/med_onc_note_level_dataset.csv`.`institution`: missing=0/15870 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/med_onc_note_level_dataset.csv`.`record_id`: missing=0/15870 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/pathology_report_level_dataset.csv`.`institution`: missing=0/3532 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/pathology_report_level_dataset.csv`.`record_id`: missing=0/3532 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/patient_level_dataset.csv`.`institution`: missing=0/1109 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/patient_level_dataset.csv`.`record_id`: missing=0/1109 (0.0)
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/clinical_data/regimen_cancer_level_dataset.csv`.`dx_reg_start_int`: missing=0/3153 (0.0)

## 7. 时间顺序和数据泄漏风险

- 有 NGS 与 regimen 相对时间字段的患者数：1037
- NGS 报告早于或等于最早 regimen 的患者数：100
- NGS 报告晚于最早 regimen 的患者数：937
- 上述只是第一轮聚合检查。正式 t0 必须按具体治疗决策点逐例对齐，不能用结局字段、停药字段或未来随访字段构造输入。

潜在泄漏字段示例：
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PFS_I_ADV_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PFS_M_ADV_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PFS_I_ADV_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`PFS_M_ADV_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`OS_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival.txt`.`OS_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`OS_1794_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_IMAGING_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_MED_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`OS_1794_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_IMAGING_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_MED_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`OS_1794_961_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_961_IMAGING_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_961_MED_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`OS_1794_961_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_961_IMAGING_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_961_MED_MONTHS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`OS_1794_1181_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned
- `data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/cBioPortal_files/data_clinical_supp_survival_treatment.txt`.`PFS_1794_1181_IMAGING_STATUS`: potential_future_or_outcome_field; exclude from t0 inputs unless time-aligned

## 8. 数据质量问题

- 未在表级摘要中发现完全重复行；仍需在正式建队列时检查业务键重复。
- 宽基因矩阵中的动态样本列名已脱敏汇总，避免在审计产物中泄露样本级标识。
- PDF 数据手册和流程文档因环境缺少 PDF 解析器，本轮只确认文件存在和校验值，正文待人工或合规工具复核。

## 9. Track A 可行性

初步可行，但只能作为 Track A 病例骨架和分子/治疗/结局描述基准。BPC PANC 提供患者、癌种、NGS、治疗、影像/随访和部分生存/PFS 相关字段；是否可纳入还需逐患者确认 PDAC 组织学、晚期/复发/转移状态、NGS<=t0、既往治疗可解释性和结局时间位置。

## 10. Track B 当前条件

当前 PANC 原始包不足以建立完整 Track B。V3.0 方案要求 Track B 具备决策时点附近 ECOG、关键实验室、给药/减量和毒性字段；本轮文件名和字段级审计未确认这些字段在 BPC PANC 中完整存在。不得用跨数据源伪拼接补齐。

## 11. Pilot、Core、Extended 现实定义与估计规模

- Pilot：从通过 Track A 初筛的患者中人工抽取 20-30 例，用于修订 schema 和审计时间线。
- Core：优先选择字段完整、NGS 早于候选决策点、治疗和结局可解释的 50-80 例人工复核病例；真实可达规模待 t0 逐例审计后锁定。
- Extended：可从剩余通过 Track A 机器审计的患者形成；当前保守上界可参考“同时有 NGS 和治疗记录的患者数”，但这不是正式队列规模。

## 12. 尚需确认的问题

- PDF 数据手册、GA01 基本流程、GA09 数据与代码管理规范的正文需要进一步读取或人工核对。
- 数据许可/使用限制需从 AACR/Synapse 官方条款和包内说明正式确认；当前 README 仅提供来源链接和数据包简介。
- 字段含义、缺失编码、相对日期定义、药物遮蔽规则和机构差异需以变量字典/数据手册为准。
- 四类候选状态的标签细则需继续从 V3.0 全文和后续标注指南中固化为机器可读规则。

## 13. 下一步建议

1. 先补齐 PDF 文档解析或人工摘录，确认数据字典、许可和时间字段定义。
2. 基于本审计输出制定 Track A 初筛 SQL/脚本，但仍不要训练模型。
3. 手工核验 10-20 个非敏感、去标识病例时间线，只输出聚合问题清单。
4. 明确 t0 定义后再做时间泄漏审计和候选池冻结。
