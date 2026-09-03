# PDAC Treatment Benchmark

语言：[English](README.md) | 中文

## 项目简介

本项目面向晚期、不可切除或转移性胰腺导管腺癌（PDAC），构建患者级候选治疗证据与临床约束排序基准。基准使用决策时间点 `t0` 前可获得的信息，对预先定义的候选治疗方案进行结构化评估。

## 研究设计

每条评估记录对应一个Strict Extended队列决策点和一个主池候选方案。标签分为三类：

| 标签 | 用途 |
|---|---|
| `observed_next_regimen` | 描述医生实际选择，用于辅助对齐与行为基线 |
| `evidence_label` | 表示指南、监管证据及Track A可观察条件支持度，是候选排序的主要目标 |
| `outcome_label` | 表示OS、PFS等随访结局，用于生存分析和辅助评估 |

Track A覆盖稳定的 `t0` 前疾病、NGS、biomarker和既往治疗信息。Track B覆盖ECOG、实验室、器官功能、剂量调整、毒性和详细禁忌证，当前状态为`frozen`。

## 当前结果

| 模块 | 结果 | 状态 |
|---|---|---|
| 严格队列 | Strict Extended 557人；Strict Core 475人 | `conditional_go` |
| 结局覆盖 | OS 557人；PFS-I 533人；PFS-M 533人 | 已完成审计 |
| 候选治疗空间 | 主池16项；扩展池11项 | `draft_not_locked` |
| 标签Schema | Track A证据与约束标签v0.1 | `draft_not_locked` |
| Pilot | 24个决策点 × 16个候选，共384行 | 规则派生，等待复核 |
| 复核方案A | 双专家独立复核与分歧裁决 | 首选方案 |
| 复核方案B | 冻结指南规则生成`guideline_evidence_eligibility` | 导师确认后启用 |

## 环境依赖

当前验证环境：

- Python 3.11.15
- pandas 3.0.3
- pypdf 6.14.2
- PyYAML 6.0.3
- pytest 9.1.1

安装依赖：

```powershell
python -m pip install -r code/requirements.txt
```

## 目录说明

```text
data/
  raw/                 # 原始数据凭证
  processed/           # 可再生成的患者级派生数据
code/
  src/                 # 可复用源代码
  scripts/             # 审计、生成和验证入口
  notebooks/           # 探索性分析
  config/              # 队列、候选、标签和Pilot配置
  tests/               # 自动化测试
  results/
    mappings/          # PDAC、regimen和候选交叉映射
    reports/           # 可公开的聚合报告与表格
    data_audit/        # 自动生成的数据审计结果
docs/
  notes/               # 研究方案与设计决策
    standards/         # 本地项目管理规范索引
  papers/              # 论文材料
  slides/              # 汇报材料
warehouse/             # 暂存材料
```

## 数据准备

原始数据位于：

```text
data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/
```

`data/raw/`保存原始数据版本，`data/processed/`保存可再生成的患者级产物，`code/results/reports/`保存执行小样本抑制后的聚合结果。外部材料登记在[external_material_registry_v0.1.yaml](code/config/external_material_registry_v0.1.yaml)，本机路径登记在`code/config/local_external_sources.yaml`。

## 运行步骤

### 1. 数据审计

```powershell
python code/scripts/audit_raw_data.py --repo-root .
python code/scripts/audit_cohort_t0_feasibility.py --repo-root .
python code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

### 2. 候选治疗空间

```powershell
python code/scripts/generate_candidate_regimen_crosswalk.py --repo-root .
python code/scripts/validate_candidate_treatment_space.py --repo-root .
```

### 3. 标签Schema与外部证据

```powershell
python code/scripts/validate_evidence_constraint_label_schema.py --repo-root .
python code/scripts/validate_external_material_registry.py --repo-root .
python code/scripts/validate_patient_candidate_dataset_schema.py --repo-root .
```

### 4. Pilot生成与验证

```powershell
python code/scripts/build_pilot_evidence_labels.py --repo-root .
python code/scripts/validate_pilot_evidence_labels.py --repo-root .
```

### 5. 自动化测试

```powershell
python -m pytest code/tests/test_candidate_treatment_space.py code/tests/test_evidence_constraint_label_schema.py code/tests/test_external_material_registry.py code/tests/test_patient_candidate_dataset_schema.py code/tests/test_pilot_evidence_labels.py -q
```

## 主要产物

- [队列定义](code/config/cohort_definition_v0.1.yaml)
- [第一轮数据审计](code/results/reports/data_feasibility_audit_v1.md)
- [候选治疗空间](code/config/candidate_treatment_space_v0.1.yaml)
- [标签Schema](code/config/evidence_constraint_label_schema_v0.1.yaml)
- [Patient-Candidate数据集Schema](code/config/patient_candidate_dataset_schema_v0.1.yaml)
- [Patient-Candidate数据集设计](docs/notes/patient_candidate_dataset_schema_design_v0.1.md)
- [Pilot协议](code/config/pilot_label_protocol_v0.1.yaml)
- [候选-Regimen Crosswalk](code/results/mappings/candidate_regimen_crosswalk_v0.1.csv)
- [队列审计报告](code/results/reports/cohort_lock_label_feasibility_v0.1.md)
- [Pilot聚合报告](code/results/reports/pilot_label_validation_report_v0.1.md)
- [中文实验进度报告](code/results/reports/experiment_progress_report_v1.0.md)
- [项目文档索引](docs/notes/project_document_index_v1.0.md)

## 下一阶段

训练数据契约已定义但尚未生成数据。方案A完成专家复核后形成专家裁决标签，方案B在导师确认后形成指南证据适用性标签。经确认的标签将用于生成patient-candidate表、冻结患者级切分、执行泄漏检查和基线训练。

## 第三轮 3.1 队列修复审计

在仓库根目录运行：

```powershell
C:\Users\ASUS\miniconda3\envs\ml\python.exe code/scripts/audit_cohort_lock_label_feasibility.py --repo-root .
```

主要修复输出：

- [队列定义草案](code/config/cohort_definition_v0.1.yaml)
- [第三轮 3.1 审计报告](code/results/reports/cohort_lock_label_feasibility_v0.1.md)
- [新旧队列核账](code/results/reports/tables/cohort_reconciliation.csv)
- [跨癌种 t0 审计](code/results/reports/tables/cross_cancer_t0_audit.csv)
- [晚期证据敏感性](code/results/reports/tables/advanced_evidence_sensitivity.csv)
- [终点覆盖](code/results/reports/tables/endpoint_coverage.csv)
- [中心-年份分布](code/results/reports/tables/center_year_distribution.csv)
- [Regimen 两层映射](code/results/mappings/regimen_mapping_v0.1.csv)

当前 3.1 状态：Conditional Go；严格 Extended n=557，严格 Core n=475。公开 CSV 已执行 n<5 小样本抑制。
