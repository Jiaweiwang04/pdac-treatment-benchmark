# PDAC 治疗方案标签基准 v2.0

版本：v2.0

更新日期：20260915

状态：候选队列和患者划分完成；治疗目录已冻结；25例Pilot的175条预拟标签及审核包已生成，专家审核待完成。

## 项目简介

基于 AACR GENIE BPC PANC 1.0-public 数据，构建局部晚期或转移性胰腺导管腺癌（PDAC）的治疗决策候选集合。处理流程连接病理、分子检测、治疗和疾病评估记录，按决策时间区分证据，为候选方案的证据评价及专家标注提供数据基础。

## 环境依赖

| 项目 | 要求 |
| --- | --- |
| Python | 3.12；已在 3.12.14 验证 |
| 第三方库 | 数据处理使用标准库；Word生成使用python-docx 1.2.0与lxml 6.1.1 |
| 操作系统 | 已在 Windows 11 64 位验证 |
| 硬件 | CPU，无 GPU 依赖；最低内存与磁盘需求尚未测定 |

在仓库根目录建立环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r code/requirements.txt
```

以下命令中的 `python` 指向该环境的解释器；未激活环境时可使用 `.\.venv\Scripts\python.exe`。

## 目录说明

```text
data/
  raw/                         原始发布数据，只读
  processed/v2.0/              可再生成的临床记录、时间轴和候选表
code/
  src/pdac_benchmark/v2_0/     数据处理与候选筛选模块
  scripts/                    流程入口
  config/v2.0/                数据路径及筛选规则
  tests/v2_0/                 数据保真、时间关系与分组测试
  notebooks/                  探索性分析，当前为空
  results/v2.0/               统计表、质量检查与运行来源
  requirements.txt            Python 环境说明
docs/
  notes/v2.0/                 处理协议、阶段报告及文档索引
  notes/standards/            项目管理规范
  papers/                     论文与参考材料
  slides/                     汇报材料
warehouse/archive/v1.0/       历史研究方案、统计表和报告
```

原始数据、患者级中间数据和自动生成的结果在本地保存。源码、配置、测试及项目文档纳入版本管理。

## 数据准备

按数据提供方的访问流程取得 **PANC 1.0-public** 完整发布包，保留原始名称和目录结构：

```text
data/raw/AACR GENIE Biopharma Collaborative Public/Data Releases/PANC/1.0-public/
  clinical_data/
  cBioPortal_files/
  Documentation/
```

输入位置由 [source.json](code/config/v2.0/source.json) 指定，路径相对于项目根目录解析。程序清点全部源文件，并解析十张临床表、小变异、结构变异、离散拷贝数和基因面板。字段定义和数据限制见 [数据用途说明](docs/notes/v2.0/source_usage_report_v2.0.md)。

原始值保留为字符串；空值、Unknown、0 和遮蔽编码分别处理。临床记录通过患者、癌症及事件复合键连接，时间轴以首个目标癌症诊断日为原点。方法见 [原始数据处理协议](docs/notes/v2.0/data_processing_protocol_v2.0.md) 和 [候选决策点协议](docs/notes/v2.0/decision_point_protocol_v2.0.md)。

## 运行步骤

一键运行八阶段处理和测试：

```powershell
python -B code/scripts/run_v2_0.py all
```

| 命令 | 处理内容 | 输出子目录 |
| --- | --- | --- |
| `audit` | 源文件清点、临床字段保真、病理标本及治疗登记 | `01_source_audit/` |
| `timeline` | 时间轴、治疗锚点、分子文件与变量字典 | `02_decision_points/` |
| `candidates` | NGS 时序筛选、进展记录归组 | `03_screening_candidates/` |
| `review` | 组织学限制、方案独立性与同日进展关联 | `04_candidate_review/` |
| `cohort` | 主候选、进展扩展和治疗调整分组 | `05_candidate_cohort/` |
| `split` | 患者归属、Pilot及Core索引点锁定 | `06_patient_split/` |
| `catalog` | 开发集组合筛查、证据目录及冻结验证 | `07_treatment_catalog/` |
| `coverage` | 冻结后Core实际治疗组成覆盖核查 | `08_core_coverage/` |
| `check` | 单元测试、文档链接、结果及来源一致性检查 | 检查摘要 |

单阶段运行示例：

```powershell
python -B code/scripts/run_v2_0.py audit --config code/config/v2.0/source.json
python -B code/scripts/run_v2_0.py timeline
python -B code/scripts/run_v2_0.py candidates
python -B code/scripts/run_v2_0.py review
python -B code/scripts/run_v2_0.py cohort
python -B code/scripts/run_v2_0.py split
python -B code/scripts/run_v2_0.py catalog
python -B code/scripts/run_v2_0.py coverage
python -B code/scripts/run_v2_0.py check
```

各阶段依赖前序结果；更新规则或输入后按顺序重新生成。`--config` 选择原始审计配置，其他阶段使用 `code/config/v2.0/` 下的对应配置；`-B` 关闭字节码缓存。每阶段记录源文件、配置和代码校验和。中间数据写入 `data/processed/v2.0/`，统计与运行记录写入 `code/results/v2.0/`，报告写入 `docs/notes/v2.0/`。

当前尚无模型训练命令、训练超参数或性能评估入口。

标签规则已定义，见[治疗方案标签定义](docs/notes/v2.0/treatment_label_definition_v2.0.md)：支持匹配、条件性匹配、有依据不匹配、无法判定；研究性方案显式标记，知识截止日固定为2026-09-12。Pilot已形成175条预拟标签，尚无专家金标准。

患者划分已按[划分协议与结果](docs/notes/v2.0/patient_split_protocol_v2.0.md)固定：435名开发患者、80名Core测试患者，25名Pilot从开发集中选取。Core和Pilot各患者首轮使用最早主候选，其他记录继承患者归属。`split`命令重建划分，已有锁定不允许静默重抽；真实标签和模型实验尚未完成。

候选方案整理见[目录与核查报告](docs/notes/v2.0/treatment_catalog_report_v2.0.md)。`catalog`命令重建开发集药物组合、方案家族、变体及证据清单；目录发布标识为 `v2.0_catalog_20260914`，包含64个方案家族、69条证据来源和8个变体索引；其中7个变体具备剂量日程定义，OFF仅保留研究索引。37个家族标记为研究性方案。

[开发集逐项筛查](docs/notes/v2.0/treatment_screening_report_v2.0.md)记录84种原始药物形式的处理结论。807个开发主候选中，682个与目录完整组成一致，125个保留为参考记录。该划分没有生成患者适用性标签。

目录冻结锁保存在 `data/processed/v2.0/07_treatment_catalog/treatment_catalog_lock_v2.0.json`，应随当前研究版本保留。重新运行时，程序验证方案定义、证据、药名规则、患者划分锁及开发集投影；内容改变会停止，不能删除锁来覆盖原发布版。`coverage`先验证冻结内容，再读取Core实际治疗，结果见[Core覆盖核查](docs/notes/v2.0/core_coverage_report_v2.0.md)。

## Pilot标签审核

25名Pilot患者的175条预拟标签、独立审核表、裁定表及完整资料索引见[Pilot审核协议](docs/notes/v2.0/pilot_review_protocol_v2.0.md)。两名专家分别使用独立审核表副本；预拟标签首轮可见，尚未形成专家金标准。

```powershell
python -B code/scripts/build_pilot_data_v2_0.py
python -B code/scripts/build_pilot_documents_v2_0.py --project-root . --template "C:\Users\ASUS\Desktop\医生审核包_金标准103对.docx"
```

数据重新生成后需重新生成并检查Word版面。该审核包是八阶段处理之后的独立产物。

执行 `python -B code/scripts/check_pilot_package_v2_0.py` 检查Pilot协议、文件链接及上游来源一致性。

## 当前结果

| 项目 | 数量 | 来源 |
| --- | ---: | --- |
| 原始文件 / 临床表 / 临床记录 | 72 / 10 / 58,947 | [原始数据审计](docs/notes/v2.0/source_data_audit_report_v2.0.md) |
| 患者 / 目标癌症诊断 | 1,109 / 1,110 | 同上 |
| 病理报告 / 标本 | 3,532 / 7,627 | 同上；每份报告 327 个原始字段 |
| 系统治疗记录 | 3,153 | 目标癌症 2,960，非目标癌症 193 |
| 时间轴事件 / 治疗候选锚点 | 58,019 / 3,404 | [时间轴报告](docs/notes/v2.0/decision_point_audit_report_v2.0.md) |
| 候选登记记录 | 4,411 | 包含 1,007 个进展候选组 |
| 方案起始主候选 | 952 | [候选集合报告](docs/notes/v2.0/candidate_cohort_report_v2.0.md) |
| 进展扩展组 / 治疗调整附录 | 602 / 244 | 同上 |
| 临床原字段不一致 / 源文件变化 | 0 / 0 | 原始数据审计 |

主候选表位于 `data/processed/v2.0/05_candidate_cohort/main_candidates_v2.0.csv`。完整候选登记、进展扩展、治疗附录和逐点变更证据保存在同一阶段目录。

以上计数是研究候选记录数，尚未形成最终训练资格、治疗适用性标签或专家金标准。方案开始、方案内调整和进展组对应不同记录单位；同一患者可有多个候选。病理报告可用时间、癌症归属和实际治疗意图的限制见各阶段报告。

## 常见问题排查

| 问题 | 处理方式 |
| --- | --- |
| 找不到源文件 | 核对 `source.json` 与完整发布目录 |
| 输出路径被拒绝 | 中间数据和结果分别使用对应的项目内子目录 |
| CSV 解析失败 | 根据文件名和逻辑行号核查原始记录 |
| 上游校验和不一致 | 从受影响阶段开始重新运行，避免混用不同版本结果 |
| 运行状态为 `running` 或 `failed` | 查看该阶段 `run_manifest.json` 中的错误，处理后重跑 |
| 文档或测试检查失败 | 按检查结果修正来源、规则或链接，再执行 `all` |

## 文档与复现

[文档索引](docs/notes/v2.0/project_document_index_v2.0.md) 汇总方法和结果；[项目进度](docs/notes/v2.0/project_status_v2.0.md) 记录后续研究环节。历史结果采用原版本统计口径，不参与 v2.0 计算。

新文件采用英文描述和下划线，版本号使用 `vX.Y`，日期使用 `YYYYMMDD`；固定运行入口及原始发布文件保留稳定名称。交接内容包括源码版本、环境要求、配置、数据发布版本与校验和、复现命令及结果报告。

## 联系人

维护者姓名与邮箱：待补充。
