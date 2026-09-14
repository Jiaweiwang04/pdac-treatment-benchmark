# 项目文档索引 v2.0

版本：v2.0

更新日期：20260914

状态：对应八阶段处理、冻结治疗目录及标签定义。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [项目说明](../../../README.md) | 环境、数据准备、复现与结果概览 |
| [项目进度](project_status_v2.0.md) | 已完成环节与后续研究 |
| [原始数据处理协议](data_processing_protocol_v2.0.md) | 字段保真、关联键、病理标本和验证 |
| [数据用途说明](source_usage_report_v2.0.md) | 临床和分子字段的来源、用途及限制 |
| [候选决策点协议](decision_point_protocol_v2.0.md) | 时间规则、疾病范围和候选分组定义 |
| [原始数据审计报告](source_data_audit_report_v2.0.md) | 文件与记录规模、关联及字段质量 |
| [时间轴与锚点报告](decision_point_audit_report_v2.0.md) | 事件、治疗锚点及分子记录 |
| [候选筛选报告](screening_candidate_report_v2.0.md) | NGS 时序、进展归组与候选登记 |
| [候选核查报告](candidate_review_report_v2.0.md) | 组织学限制、方案独立性及同日关联 |
| [候选集合报告](candidate_cohort_report_v2.0.md) | 主候选、扩展组、附录与逐点证据 |
| [治疗方案标签定义](treatment_label_definition_v2.0.md) | 四类含义、判定边界、研究属性、知识截止日与专家审核要求 |
| [患者划分协议与结果](patient_split_protocol_v2.0.md) | 开发／Core归属、Pilot名单、索引点、分层、复现锁定及泄漏审计 |
| [候选治疗方案目录](treatment_catalog_report_v2.0.md) | 开发集药名及组合核查、方案家族、变体、证据缺口 |
| [治疗证据来源说明](treatment_evidence_ledger_v2.0.md) | 指南、论文和监管文件的日期、读取层级和结果方向 |
| [开发集治疗逐项筛查](treatment_screening_report_v2.0.md) | 84种原始记录形式的纳入或保留结论与依据 |
| [Core组成覆盖核查](core_coverage_report_v2.0.md) | 冻结时间、逐点覆盖、未覆盖记录和复现边界 |
| [结果目录](../../../code/results/v2.0/README.md) | 分阶段统计与运行来源 |

配置保存在 `code/config/v2.0/`；阶段报告由相应处理模块生成，与结果汇总及运行清单一起更新。
