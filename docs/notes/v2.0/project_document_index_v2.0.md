# PDAC 项目文档索引 v2.0

版本：v2.0  
更新日期：20260910  
状态：文档与实际目录按GA09第2.1节同步整改。

## 目的与适用范围

提供正式v2.0文档索引，明确文件职责、版本及维护方式。依据[GA01研究流程](../standards/ga01_research_workflow.pdf)第4至7节及附录二第二项记录来源、方法、结果和问题；依据[GA09数据与代码管理](../standards/ga09_data_code_management.pdf)第2.1、2.2和2.4节管理目录、命名及项目入口。

用户提供的第2.1节截图明确了执行要求。本轮修正上一轮仅记录目录差异而未整改的问题，不再沿用根目录src、configs、tests、outputs和archive。

## 当前文档

| 文档 | 职责 | 维护方式 |
| --- | --- | --- |
| [项目入口](../../../README.md) | 环境、目录、数据、复现、排错和联系人 | 随实际配置和阶段更新 |
| [项目进度](project_status_v2.0.md) | 已完成、待完成及依据 | 不提前标记完成 |
| [处理规则](data_processing_protocol_v2.0.md) | 原值、关联、病理、时间及验证边界 | 与代码同步 |
| [审计报告](source_data_audit_report_v2.0.md) | 当前运行结果及来源 | 由审计入口自动生成 |
| [前两次清理记录](repository_cleanup_record_v2.0.md) | 历史处理范围、计数和保护措施 | 历史事实保持，定位链接更新 |
| [本次目录整改记录](repository_layout_record_v2.0.md) | 规范目录及本次迁移核对 | 按迁移清单记录 |
| [旧版归档说明](../../../warehouse/archive/v1.0/README.md) | 解释历史结果 | 冻结结果及内部目录保持 |

新增第二阶段文档：[各类数据用途](source_usage_report_v2.0.md)、[候选决策点协议](decision_point_protocol_v2.0.md)、[候选点与时间轴报告](decision_point_audit_report_v2.0.md)。[完整病例示例](../../../code/results/v2.0/02_decision_points/complete_case_v2.0.html)是由数据生成的实验产物，不是已审定的pilot标签包。

第三阶段文档：[Track A候选点筛选报告](track_a_candidate_report_v2.0.md)，包含NGS时序门槛、候选分层、进展归组、结局用途及当前统计。

## 命名与内容规则

正式叙述文档放在 `docs/notes/v2.0/`，文件名采用英文下划线描述加`_v2.0.md`，需要日期时使用YYYYMMDD；文首写明版本、更新日期和状态。

方法文档说明输入、处理、输出及异常；结果文档说明口径、来源、验证和局限；进度文档区分完成与计划。稳定入口README和机器读取文件采用固定名称，版本由目录或结构化字段表达。原始发布文件、规范及冻结旧材料保留原名。

## 目录执行规则

原始数据只读存放于data/raw，中间数据存放于data/processed，正式源码位于code/src，辅助入口位于code/scripts，探索分析位于code/notebooks，实验结果位于code/results，依赖写入code/requirements.txt。配置和测试独立放在code/config、code/tests。

论文和汇报材料分别归入docs/papers、docs/slides；旧版冻结结果及解释资料位于warehouse/archive/v1.0。版本隔离在规范目录内部完成，不能另建根目录替代规范位置。

## 检查与维护

运行 `python -B code/scripts/run_v2_0.py all`，完成审计及检查；单独核查使用 `python -B code/scripts/run_v2_0.py check`。检查覆盖目录存在性、旧根目录移除、中间数据与结果分离、文档命名及元数据、本地链接、报告计数和实现来源。

机器检查之外还需核对内容与阶段是否准确。目录符合要求不等于临床语义或标签已经通过验证。当前没有训练结果或专家金标准。
