# PDAC 开发集内部患者级训练／验证划分 v2.0

版本：v2.0_development_20261003

更新日期：20261003

状态：开发集划分及身份隔离检查已完成，名单已锁定并可复现；专家标签审核、裁定及模型评估待完成。

## 范围与当前结果

仅在已锁定的435名开发患者内实施80%／20%划分。原Core 80人、Pilot 25人及其索引候选不重抽、不覆盖；知识截止日仍为2026-09-12。这是患者用途分配，不代表临床纳入资格或监督训练样本已确定。

| 用途 | 患者数 | 主候选点数 | 各类登记记录数 |
| --- | ---: | ---: | ---: |
| 训练侧（含25名Pilot） | 348 | 656 | 1758 |
| 验证侧 | 87 | 151 | 396 |
| Core测试侧（沿用原锁） | 80 | 145 | 393 |
| extension_only（沿用原归属） | 539 | 0 | 1864 |

训练侧包含323名非Pilot患者和25名Pilot；Pilot是训练侧子集，不能重复相加。共1,054名登记患者、4,411条候选登记全部保留。主候选点及背景登记数量都不等于最终训练样本数。

## 抽样与锁定

患者键为(cohort, record_id)，同一患者的全部候选、进展扩展、治疗附录、背景病理、NGS及后续记录继承同一归属。分层沿用原锁内的机构和最早主候选时点疾病情境，不将既有情境分类改称当前临床分期。

先将已有25名Pilot固定在训练侧，再从410名非Pilot开发患者中抽取87名验证患者。各层按非Pilot患者比例，以整数部分和最大余数分配87个名额；余数并列按层名称排序。层内用固定种子20261003、用途名`development_validation`及患者键计算SHA256，排序选取，算法沿用第06阶段。验证占整个开发集20%，占可抽样的非Pilot患者21.22%；因Pilot预留，整体各层不保证恰为20%。不使用专家标签、预拟标签、实际用药、疗效、生存或分子特征选人，不按验证成绩换种子。

[配置](../../../../code/config/v2.0/development_split.json)和[内部划分锁](../../../../data/processed/v2.0/10_development_split/development_split_lock_v2.0.json)记录政策与名单。重复运行只允许复现同一分配；输入或政策改变时，在任何结果写入前报错，不提供自动删除锁或重抽选项。旧Core/Pilot锁及第06阶段所有文件保持原字节内容。此锁是流程校验，不是操作系统权限或已完成盲法的证明。

## 分布及泄漏核查

| 机构 | 开发合计 | 训练 | 验证 | 其中训练Pilot |
| --- | ---: | ---: | ---: | ---: |
| DFCI | 153 | 122 | 31 | 8 |
| MSK | 232 | 185 | 47 | 13 |
| UHN | 24 | 20 | 4 | 2 |
| VICC | 26 | 21 | 5 | 2 |

| 机构 | 索引情境 | 开发 | 训练Pilot | 训练合计 | 验证 |
| --- | --- | ---: | ---: | ---: | ---: |
| DFCI | baseline_unresectable_advanced_current_context_unconfirmed | 5 | 0 | 4 | 1 |
| DFCI | metastatic_after_diagnosis | 77 | 4 | 61 | 16 |
| DFCI | metastatic_at_diagnosis | 71 | 4 | 57 | 14 |
| MSK | baseline_unresectable_advanced_current_context_unconfirmed | 14 | 1 | 11 | 3 |
| MSK | metastatic_after_diagnosis | 114 | 6 | 91 | 23 |
| MSK | metastatic_at_diagnosis | 104 | 6 | 83 | 21 |
| UHN | baseline_unresectable_advanced_current_context_unconfirmed | 1 | 0 | 1 | 0 |
| UHN | metastatic_after_diagnosis | 12 | 1 | 10 | 2 |
| UHN | metastatic_at_diagnosis | 11 | 1 | 9 | 2 |
| VICC | metastatic_after_diagnosis | 15 | 1 | 12 | 3 |
| VICC | metastatic_at_diagnosis | 11 | 1 | 9 | 2 |

[完整分布审计](../../../../code/results/v2.0/10_development_split/development_distribution_audit_v2.0.csv)包含开发合计、训练、验证、Pilot及非Pilot训练的机构、疾病情境、病理摘要、在先NGS样本关联、面板和已记录小变异基因，零计数也保留。分子及病理只作事后描述，不用于重抽。只使用原索引点严格在先NGS关联样本；基因记录不等于致病、胚系或可操作性，缺少记录不等于阴性，病理报告可用时间未确认的限制继续保留。

开发集有326种已记录小变异基因未在验证索引样本出现；验证中有36种未在训练索引样本出现。名称见[汇总](../../../../code/results/v2.0/10_development_split/development_split_summary_v2.0.json)，不能据此宣称精准治疗亚组均衡或充分覆盖。

训练／验证、Pilot／验证、开发／Core患者交集均为0。遍历全候选登记及完整时间轴，按训练、验证、Core、extension_only四侧检查患者ID、源记录ID、事件ID、NGS样本ID；跨侧身份冲突为0，检查数见汇总。所有原候选字段及标签状态保持不变。范围限于既有PANC数据，不表示外部队列实体去重或通用模型预训练污染检查已完成。

## 使用规则与已有开发暴露

训练侧用于规则、提示词、特征及阈值开发；需要从患者数据学习的缺失值填补、标准化、特征选择及其他参数只能在训练侧拟合，然后固定应用到验证侧。所有衍生病例、方案对、问答及示例必须携带patient_key和candidate_id，按本阶段归属路由，不能只读取原第06阶段的development字段。

验证侧用于后续内部评估与方法选择；一旦用其结果调参，应记录使用历史，不能再宣称完全未接触。Pilot25人全部用于训练侧流程调试、病理展示、标签边界和审核规范；已有175条预拟标签不是专家金标准，独立专家及裁定字段不能由预拟标签补填。

此前冻结治疗目录由全部435名开发患者的药物记录投影整理，现验证患者已经参与该目录构建。因此本轮验证是在现有开发集合上新增的内部划分，不能宣称端到端从未参与开发的独立验证。沿用冻结公共证据目录，不按本轮验证分布扩充目录或重新选人；若以后要求从训练侧独立建立目录，应另设版本与实验。Core继续保持最终测试用途，不参与训练、提示词调整、规则开发或阈值选择。

正式专家标签及最终临床纳入资格尚未完成；本阶段不训练模型、不发布性能、不生成正式标签或最终训练样本数。后续获得标签后仍继承当前患者归属，报告标签缺失和排除原因，不按结果难易调换患者。

## 输出与复现

- [患者归属名单](../../../../data/processed/v2.0/10_development_split/development_patient_assignments_v2.0.csv)及同名JSONL：全登记池身份与新的用途字段。
- [训练主候选](../../../../data/processed/v2.0/10_development_split/training_main_candidates_v2.0.csv)、[验证主候选](../../../../data/processed/v2.0/10_development_split/validation_main_candidates_v2.0.csv)：候选索引及用途，不是可直接输入模型的特征包。
- [全部候选归属登记](../../../../data/processed/v2.0/10_development_split/development_candidate_registry_v2.0.jsonl)：保留原记录并附加development_split_assignment；包含后续及参考资料，禁止作为模型输入文件直接读取。
- [分层名额](../../../../code/results/v2.0/10_development_split/development_stratum_allocation_v2.0.csv)、[运行清单](../../../../code/results/v2.0/10_development_split/run_manifest.json)：输入、配置、代码、检查与输出校验和。

在项目根目录运行，数据处理只依赖标准库：

```powershell
python -B code/scripts/build_development_split_v2_0.py
python -B code/scripts/build_development_split_v2_0.py --check
python -B code/scripts/run_v2_0.py check
```

新阶段是第06阶段及既有Pilot之后的独立入口，原`run_v2_0.py all`不自动执行本阶段。`--check`为只读验证，重算名单与身份隔离、核对原文件、全部新产物及本报告的校验和与本地链接。Python版本、运行平台和运行时间记录在清单中。
