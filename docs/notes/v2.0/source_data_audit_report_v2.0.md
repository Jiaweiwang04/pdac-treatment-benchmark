# PANC 原始数据审计报告 v2.0

版本：v2.0

更新日期：20260914

状态：completed；仅表示本阶段执行状态。

## 目的与范围

核实PANC 1.0-public原始文件、临床表结构、字段完整性、关联键、病理标本及全部治疗记录，为下一阶段决策点整理提供可追溯的起点。统计范围为原始发布集，输出用于后续候选决策点构建。

## 输入与运行记录

| 项目 | 当前记录 |
| --- | --- |
| 数据版本 | PANC 1.0-public |
| 原始路径 | 由[源配置](../../../code/config/v2.0/source.json)指定，完整路径见[运行清单](../../../code/results/v2.0/01_source_audit/run_manifest.json) |
| 文件范围 | 72个原文件；其中解析10张临床表 |
| 开始时间UTC | 2026-09-14T09:53:27.395372+00:00 |
| 完成时间UTC | 2026-09-14T09:53:30.534331+00:00 |
| Python与平台 | 3.12.14；Windows-11-10.0.26200-SP0 |
| 第三方运行依赖 | 本阶段无第三方依赖 |
| 原始文件版本依据 | [原文件清单](../../../code/results/v2.0/01_source_audit/source_inventory.json)中的SHA-256 |
| 配置、实现和检查代码依据 | [运行清单](../../../code/results/v2.0/01_source_audit/run_manifest.json)中的配置、代码和检查代码SHA-256 |

## 处理与验证方法

按原CSV字符串逐字段保留，包括空值、明确未知和真实0。按患者、癌症及事件的复合键核查关联；展开病理报告全部已填标本槽位，与声明标本数比较；登记全部方案开始记录，区分目标与非目标癌症。

导出后重新读取原CSV，与JSONL逐行核对全部原字段。运行结束前再次核对原文件内容。具体键、时间换算、异常处理与尚未实现的内容见[数据处理规则](data_processing_protocol_v2.0.md)。

## 结果

临床记录共58,947条，涉及1,109名患者、1,110条目标癌症诊断。字段逐值不一致为0，运行前后原文件变化为0。

病理共3,532份报告，每份327个原字段，展开7,627个标本，单份最多22个标本。阴性、其他癌症、原位癌及浸润癌均保留。

系统治疗记录共3,153条，其中目标癌症2,960条、非目标癌症193条。同患者、同癌症、同开始日多记录组共1组，其中目标癌症0组、非目标癌症1组。以上都是记录计数，不能直接当成独立决策点数量。

### 各表规模

| 数据类别 | 原表名称 | 记录数 | 字段数 |
| --- | --- | ---: | ---: |
| 患者 | patient_level_dataset | 1,109 | 51 |
| 目标癌症 | cancer_level_dataset_index | 1,110 | 173 |
| 非目标癌症 | cancer_level_dataset_non_index | 279 | 109 |
| 病理报告 | pathology_report_level_dataset | 3,532 | 327 |
| NGS临床记录 | cancer_panel_test_level_dataset | 1,130 | 29 |
| 系统治疗 | regimen_cancer_level_dataset | 3,153 | 102 |
| 放疗 | ca_radtx_dataset | 526 | 83 |
| 影像评估 | imaging_level_dataset | 14,520 | 42 |
| 肿瘤内科评估 | med_onc_note_level_dataset | 15,870 | 13 |
| 血清肿瘤标志物 | tm_level_dataset | 17,718 | 14 |

### 质量问题

未发现当前检查范围内的主键、关联或病理标本数量异常。

具体检查结果见[逐条质量问题](../../../code/results/v2.0/01_source_audit/quality_issues.csv)。当前检查通过仅支持表结构、原值保留及所列关联的一致性，不证明临床语义、时间可用性或治疗适用性已经正确。

## 输出与追溯

| 产物 | 使用方式 |
| --- | --- |
| [审计汇总](../../../code/results/v2.0/01_source_audit/audit_summary.json) | 本报告汇总数值的结构化来源 |
| [表结构](../../../code/results/v2.0/01_source_audit/table_schemas.json)和[字段概况](../../../code/results/v2.0/01_source_audit/field_profile.csv) | 查看字段、主键、空值、明确缺失编码和0值 |
| [临床保真记录](../../../data/processed/v2.0/01_source_audit/clinical_records) | 每条记录包含所有原字段与来源定位 |
| [病理报告索引](../../../data/processed/v2.0/01_source_audit/pathology_reports.jsonl)和[标本明细](../../../data/processed/v2.0/01_source_audit/pathology_specimens.jsonl) | 逐报告和逐标本回连完整病理字段 |
| [治疗登记CSV](../../../data/processed/v2.0/01_source_audit/treatment_record_registry.csv)和[治疗登记JSONL](../../../data/processed/v2.0/01_source_audit/treatment_record_registry.jsonl) | 全部方案记录，训练／测试可用性仍为not_evaluated |
| [运行清单](../../../code/results/v2.0/01_source_audit/run_manifest.json) | 运行状态、环境及输入和实现校验和 |

从项目根目录运行 `python -B code/scripts/run_v2_0.py audit --config code/config/v2.0/source.json` 可重新生成本报告及当前阶段结果。

## 局限与下一步

本阶段没有解析完整分子结果，也没有完成病理及临床观察的报告可用时间核实。取材日不等于病理签发日；全字段保留不等于临床信息充分。最终可用决策点和专家标签仍未确定，没有模型性能指标。

下一步对照发布指南和变量字典建立时间轴，核实PDAC支持程度、多癌症归属、方案变化和治疗情境，再定义质量分层。当前计划见[项目进度](project_status_v2.0.md)。
