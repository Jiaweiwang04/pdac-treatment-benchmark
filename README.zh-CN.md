# pdac-treatment-benchmark

语言：[English](README.md) | 中文

## 项目简介

本项目构建面向晚期胰腺导管腺癌（advanced PDAC）患者的患者级证据与临床约束候选治疗识别基准。当前阶段是 BPC PANC 原始数据可行性审计，不训练模型，不输出处方或剂量，不替代医生判断。

## 数据边界

- 核心原始数据：[data/raw/](data/raw/) `AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/`
- [data/raw/](data/raw/) 为只读原始凭证，不修改、不覆盖、不提交原始患者级数据。
- [data/processed/](data/processed/) 用于后续可再生成的派生数据；默认忽略其内容，避免误提交患者级派生数据。
- Track A 与 Track B 分开：Track A 使用 BPC PANC 中稳定可获得字段；Track B 仅在获得真实 ECOG、实验室、剂量/减量和毒性等字段后建立。

## 目录结构

```text
data/
  raw/                 # 原始数据，只读，不提交
  processed/           # 可再生成派生数据，默认不提交内容
code/
  src/                 # 可复用源代码
  scripts/             # 审计、预处理、评测等脚本
  notebooks/           # 探索性 notebook
  results/             # 自动生成的聚合结果与表格
docs/
  notes/               # 研究方案、审计报告、数据分析记录
  papers/              # 论文草稿和投稿材料
  slides/              # 汇报材料
warehouse/             # 暂时闲置文件，默认不提交内容
```

## 环境

使用本项目本地配置的 Python 环境。当前审计脚本使用 `pandas` 和 `pypdf`；见 `code/requirements.txt`。

## 运行数据审计

在仓库根目录运行：

```powershell
python code/scripts/audit_raw_data.py --repo-root .
```

主要输出：

- [数据可行性审计报告](docs/notes/data_feasibility_audit_v1.md)
- [原始文件清单](code/results/data_audit/tables/file_inventory.csv)
- [字段清单](code/results/data_audit/tables/field_inventory.csv)
- [表关系清单](code/results/data_audit/tables/table_relationships.csv)
- [缺失情况汇总](code/results/data_audit/tables/missingness_summary.csv)
- [可行性统计汇总](code/results/data_audit/tables/feasibility_summary.csv)
- [分类变量汇总](code/results/data_audit/tables/categorical_summaries.csv)
- [原始数据盘点 notebook](code/notebooks/00_raw_data_inventory.ipynb)

## 项目文档

- [V3.0 研究方案](docs/notes/research_plan_pdac_treatment_benchmark_v3.0.docx)
- [数据可行性审计报告](docs/notes/data_feasibility_audit_v1.md)

## 当前状态

已完成第一轮 BPC PANC 原始数据只读审计。报告中的主键/外键、字段含义和队列规模均为第一轮候选结论，正式建队列前必须依据数据手册、变量字典和研究方案继续核验。

## 第三轮队列锁定与标签可用性审计

在仓库根目录运行：

```powershell
python code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

主要输出：

- [队列定义草案](cohort_definition_v0.1.yaml)
- [第三轮审计报告](reports/cohort_lock_label_feasibility_v0.1.md)
- [队列流程计数](reports/tables/cohort_lock_flow_counts.csv)
- [终点覆盖](reports/tables/endpoint_coverage.csv)
- [治疗序列质量](reports/tables/treatment_sequence_quality.csv)
- [NGS 选择敏感性](reports/tables/ngs_selection_sensitivity.csv)
- [标签可用性](reports/tables/label_availability.csv)
- [时间泄漏字段审计](reports/tables/time_leakage_field_audit.csv)
- [PDAC 映射](code/mappings/pdac_mapping_v0.1.csv)
- [Regimen 映射](code/mappings/regimen_mapping_v0.1.csv)
