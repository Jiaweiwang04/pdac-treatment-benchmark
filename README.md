# PDAC 治疗方案标签基准 v2.0

版本：v2.0  
更新日期：20260910  
状态：目录符合GA09第2.1节；原始数据审计及候选时间轴初版完成，最终临床纳入和标签未定稿。

## 项目简介

基于AACR GENIE BPC PANC数据，整理治疗时点的完整病理和临床证据，建立候选治疗方案及专家审核标签，供后续训练和测试使用。当前已完成原始数据清点、字段保真、时间轴、候选决策锚点及主要分子文件整理，尚未形成最终可用决策点或专家金标准。研究重点为局部晚期／转移性PDAC系统治疗，按指定知识截止日重评，并保留历史实际方案及其证据任务。

正式项目位于 `D:\Jiawei_Wang\Projects\Python\pdac-treatment-benchmark`。本文件为唯一项目入口；详细说明见[文档索引](docs/notes/v2.0/project_document_index_v2.0.md)、[处理规则](docs/notes/v2.0/data_processing_protocol_v2.0.md)及[项目进度](docs/notes/v2.0/project_status_v2.0.md)。

## 环境依赖

| 项目 | 当前要求或已验证环境 |
| --- | --- |
| Python | 3.12；本机验证版本3.12.14 |
| 第三方依赖 | 当前阶段仅使用标准库，依赖说明见[code/requirements.txt](code/requirements.txt) |
| 操作系统 | 本机验证为Windows 11，64位 |
| 硬件 | CPU运行，无GPU依赖；最低内存及磁盘容量未做基准测试 |
| 环境追溯 | 每次审计记录Python、平台、代码、配置和测试文件校验和 |

新机器可用 `py -3.12 -m venv .venv` 建立环境，然后将下文 `python` 替换为 `.venv\Scripts\python.exe`。当前无需安装第三方包；已有环境不必重建。

## 目录说明

目录按本地[GA09第2.1节](docs/notes/standards/ga09_data_code_management.pdf)执行。版本隔离放在规范目录内部。

```text
pdac-treatment-benchmark/
├─ data/
│  ├─ raw/                          原始发布文件，只读
│  └─ processed/v2.0/               可重新生成的中间数据
├─ code/
│  ├─ src/pdac_benchmark/v2_0/       正式源码
│  ├─ scripts/                     运行与检查入口
│  ├─ notebooks/                   探索性分析，当前为空
│  ├─ config/v2.0/                 路径和实验配置
│  ├─ tests/v2_0/                  数据保真及目录保护测试
│  ├─ results/v2.0/                审计结果、运行清单和检查结果
│  └─ requirements.txt             依赖及版本说明
├─ docs/
│  ├─ notes/v2.0/                  规则、进度、审计及迁移记录
│  ├─ notes/standards/             原规范和索引
│  ├─ papers/                      论文和参考材料
│  └─ slides/                      汇报材料
├─ warehouse/archive/v1.0/         旧版冻结结果及解释材料
└─ README.md                      项目入口
```

`code/config/`和`code/tests/`用于进一步隔离配置与验证代码；不改变规范规定的一级目录。Git、Python环境、编辑器设置和LICENSE保留。[本次目录整改记录](docs/notes/v2.0/repository_layout_record_v2.0.md)说明旧位置和新位置。

## 数据准备

[配置文件](code/config/v2.0/source.json)指定当前输入：

```text
data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public
```

此目录包含 `clinical_data/`、`cBioPortal_files/`和`Documentation/`等原始发布材料，版本为PANC 1.0-public。迁移前已与此前使用的外部源逐一比较72个文件，内容一致；没有修改原始文件。换机器时应放入相同版本的原始发布材料，配置相对于项目根目录解析。

当前清点全部文件，解析十张临床表及小变异、结构变异、离散CNA和基因面板；连续拷贝数区段尚未解析。临床原字段、病理报告及标本、治疗登记存入 `data/processed/v2.0/01_source_audit/`；字段概况、质量问题、来源清单及统计汇总存入 `code/results/v2.0/01_source_audit/`。

所有派生数据必须写入独立目录。程序在写文件前检查输入和输出位置，拒绝写入原始目录、越出项目目录或混用中间数据与结果目录。

## 运行步骤

从正式项目根目录运行一条命令，重建原始审计、时间轴及候选点，再执行测试和文档、目录检查：

```text
python -B code/scripts/run_v2_0.py all
```

需要分开执行时：

```text
python -B code/scripts/run_v2_0.py audit --config code/config/v2.0/source.json
python -B code/scripts/run_v2_0.py timeline
python -B code/scripts/run_v2_0.py candidates
python -B code/scripts/run_v2_0.py check
```

`all`依次执行三个阶段、测试和文档检查；`candidates`重建Track A候选分层；`timeline`重建第二阶段；`audit`仅更新派生数据及[唯一审计报告](docs/notes/v2.0/source_data_audit_report_v2.0.md)；`check`核查关键处理行为、目录、文档链接和运行来源。`--config`可选择项目内配置文件；`-B`避免生成字节码缓存。从其他工作目录运行时使用入口脚本的绝对路径，数据相对路径仍以项目根目录解析。

第二阶段见[数据用途说明](docs/notes/v2.0/source_usage_report_v2.0.md)、[候选点协议](docs/notes/v2.0/decision_point_protocol_v2.0.md)、[阶段报告](docs/notes/v2.0/decision_point_audit_report_v2.0.md)及[完整病例示例](code/results/v2.0/02_decision_points/complete_case_v2.0.html)。候选锚点及分子记录存入data/processed/v2.0/02_decision_points；病例网页和统计存入code/results/v2.0/02_decision_points。

尚无训练命令、模型参数或正式评测入口。本阶段不自动判定最终可用决策点，不生成治疗适用性标签。

本轮只推进Track A，Track B冻结；NGS报告必须严格早于候选时点。最新筛选口径、主候选与进展待核查数量见[Track A报告](docs/notes/v2.0/track_a_candidate_report_v2.0.md)。第三阶段数据位于data/processed/v2.0/03_track_a_candidates，统计和清单位于code/results/v2.0/03_track_a_candidates。ECOG等Track B字段缺失不作为本轮排除理由。

## 当前结果

以下是[原始数据审计汇总](code/results/v2.0/01_source_audit/audit_summary.json)，不代表模型性能或可用样本数。

| 项目 | 数量或状态 |
| --- | --- |
| 原文件、临床表、临床记录 | 72个、10张、58,947条 |
| 患者、目标癌症诊断 | 1,109名、1,110条 |
| 病理 | 3,532份报告、7,627个标本；每份保留327个原字段 |
| 治疗记录 | 3,153条；目标癌症2,960条，非目标癌症193条 |
| 原字段逐值不一致、源文件变化 | 均为0 |
| 第二阶段 | 58,019个时间轴事件；3,404个候选锚点（含251个方案内其他药物开始日），均未完成最终纳入 |
| 最终可用决策点、专家标签、模型指标 | 尚未确定或生成 |

方案记录不能直接视为独立治疗决策。完整保留字段也不等于临床信息充分；病理报告可用时间、治疗情境和关键缺失仍待核实。

## 常见问题排查

| 情况 | 处理方式 |
| --- | --- |
| 找不到源文件 | 核对配置及data/raw中的发布目录，勿改名或补写原始字段 |
| 使用了旧命令或路径 | 使用本页code/scripts入口，旧根目录src、configs、tests、outputs已移除 |
| 输出路径被拒绝 | 中间数据应在data/processed/v2.0的子目录，结果应在code/results/v2.0的子目录 |
| CSV解析失败 | 按异常中的文件及逻辑行定位，保留原值，不截断或补列 |
| 运行清单为running或failed | 检查错误与质量问题，不把部分产物当成完成 |
| 检查失败 | 按输出修正目录、链接、来源或处理问题，再运行all |
| 旧归档内链接失效 | 冻结文档保留历史文字；查阅当前入口及迁移记录定位 |

## 版本与交接

v1.0仅保留结果及解释材料，位于[warehouse归档](warehouse/archive/v1.0/README.md)，不参与新版本计算。既有Git历史保留，当前更改尚未提交；复现应保留运行清单的代码、配置和测试校验和，不能仅依赖HEAD。

后续先核查临床情境、组织学和信息充分性，明确最终可用决策点及条件性标签规则，再整理指南及论文证据、候选方案和初标、pilot专家审核以及训练／测试划分。尚未进行对外发送或交接。

## 联系人

负责人姓名、邮箱及交接负责人尚未提供，待明确后补全。
