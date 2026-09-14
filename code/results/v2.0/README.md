# 实验结果目录 v2.0

版本：v2.0

更新日期：20260914

状态：八阶段数据整理、候选分组、患者划分与治疗目录结果。

| 目录 | 结果 |
| --- | --- |
| `01_source_audit/` | 源文件清单、字段统计、质量问题、表结构与审计汇总 |
| `02_decision_points/` | 时间轴及候选锚点统计、分子关联问题 |
| `03_screening_candidates/` | NGS 时序筛选及进展归组统计 |
| `04_candidate_review/` | 候选证据核查和同日进展关联统计 |
| `05_candidate_cohort/` | 候选集合与用途分组统计 |
| `06_patient_split/` | 患者划分、分层名额、分布审计与来源统计 |
| `07_treatment_catalog/` | 开发集逐项筛查、冻结治疗目录和证据来源统计 |
| `08_core_coverage/` | 冻结后Core实际治疗组成覆盖统计及来源 |

各阶段 `run_manifest.json` 记录执行状态、输入、配置及代码校验和。`documentation_check_v2.0.json` 保存测试和文档核查摘要。

候选表、临床记录和事件索引见 [中间数据目录](../../../data/processed/v2.0/)。研究方法与阶段结果见 [文档索引](../../../docs/notes/v2.0/project_document_index_v2.0.md)，复现命令见 [项目说明](../../../README.md)。

候选治疗方案阶段的汇总与来源保存在 `07_treatment_catalog/`；[目录报告](../../../docs/notes/v2.0/treatment_catalog_report_v2.0.md)说明组成映射、证据边界和保留项；[Core覆盖报告](../../../docs/notes/v2.0/core_coverage_report_v2.0.md)单列冻结后核查结果。
