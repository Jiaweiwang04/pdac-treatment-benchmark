# PDAC候选治疗排序Benchmark实验进度报告 v1.0

报告日期：2026-09-02  
代码基线：`c5bbf7160da149b92d9725dbb09513fc4d5edd85`（`Add dataset schma`）

## 目的

本项目面向晚期、不可切除或转移性胰腺导管腺癌（PDAC），构建患者级候选治疗证据与临床约束排序Benchmark。研究以决策时间点`t0`前已经可获得的信息为输入，对预先定义的候选治疗方案进行结构化评估。

主要目标是形成可复现的Track A候选排序数据与评价流程。`observed_next_regimen`记录医生实际选择，`evidence_label`表示候选方案的证据与Track A条件支持度，`outcome_label`表示OS和PFS等辅助结局。三类标签分别存储和使用。

## 过程

### 数据与管理

主要数据来源为AACR GENIE Biopharma Collaborative PANC `1.0-public`。原始数据保存在`data/raw/`，患者级派生数据保存在被Git忽略的`data/processed/`，公开结果仅包含经过隐私扫描和小样本抑制的聚合信息。

外部指南、监管数据库和药物资料通过[外部材料登记表](../../config/external_material_registry_v0.1.yaml)记录来源、用途、许可和隐私边界。患者级分子报告示例保持隔离状态，未进入项目处理流程。

### 队列与时间点

项目依次完成原始数据审计、队列与`t0`可行性审计以及第三轮队列修复审计。当前[队列定义](../../config/cohort_definition_v0.1.yaml)使用正式癌症实例键，要求有效NGS报告和晚期证据均严格早于`t0`治疗开始时间。

Strict Extended用于Track A主分析，Strict Core在此基础上增加治疗序列清晰和regimen标准化条件。队列构建与OS、PFS等结局是否可用相互独立。

### 候选治疗空间

[候选治疗空间v0.1.1](../../config/candidate_treatment_space_v0.1.yaml)包含16个主池候选和11个扩展池候选。候选以临床可解释、数据可映射和样本量可支持的粒度表达。

当前技术规则包括：FOLFIRINOX与mFOLFIRINOX作为同一候选的变体；NALIRIFOX独立表达；普通irinotecan与liposomal irinotecan分离；维持治疗与活动治疗分离；NTRK候选以互斥单药类别表达；观察到的BPC regimen仅通过[candidate-regimen crosswalk](../mappings/candidate_regimen_crosswalk_v0.1.csv)用于对齐。

4.1.1六项技术问题已经通过配置、validator和测试确认。候选空间仍为`draft_not_locked`，临床确认和正式指南快照仍属于冻结条件。

### 标签与Pilot

[证据与约束标签Schema](../../config/evidence_constraint_label_schema_v0.1.yaml)定义Track A证据状态、候选条件状态、标签推导、缺失值处理和来源追踪。Track B所需的ECOG、实验室、器官功能、剂量、毒性和详细禁忌证数据尚未形成稳定输入，因此保持`frozen`。

Pilot从Strict Extended中选择24个决策点，并与16个主池候选交叉形成384条patient-candidate记录。程序完成`t0`前证据提取、条件判断、规则标签、隐私检查和小样本抑制。Pilot标签当前为`rule_derived`和`not_reviewed`。

复核方案A为两名临床专家独立复核及分歧裁决。方案B为导师批准后冻结指南、监管文件和候选特异性证据规则，生成`guideline_evidence_eligibility`。

### 训练数据准备

[Patient-Candidate数据集Schema](../../config/patient_candidate_dataset_schema_v0.1.yaml)已经定义7类数据契约：决策点数据集、候选主表、patient-candidate特征表、observed regimen辅助标签、evidence/constraint主要标签、outcome辅助结局表和患者级split manifest。

特征表仅包含`t0`前Track A信息和候选属性。患者标识仅用于内部关联；实际`t0`治疗、后续治疗、OS/PFS/TTNT、随访信息、未来分子结果和复核标签均不作为模型输入。未来数据切分以患者为单位，同一患者的全部候选行继承同一split。

### 质量验证

当前代码执行了完整pytest、候选空间validator、标签Schema validator、外部材料validator、Patient-Candidate数据集Schema validator和Pilot validator。隐私扫描、小样本扫描和Markdown链接检查纳入自动验证流程。

## 结果

### 当前量化结果

| 模块 | 当前结果 | 状态 |
|---|---:|---|
| Strict Extended | 557个决策点 | `draft_not_locked`，Track A `conditional_go` |
| Strict Core | 475个决策点 | `draft_not_locked` |
| OS | 557个可评估决策点 | `t0_validated` |
| PFS-I | 533个可评估决策点 | `t0_validated` |
| PFS-M | 533个可评估决策点 | `t0_validated` |
| 主候选池 | 16项 | v0.1.1，`draft_not_locked` |
| 扩展候选池 | 11项 | v0.1.1，`draft_not_locked` |
| candidate-regimen crosswalk | 46条聚合关系 | validator通过 |
| Pilot | 24个决策点、384条候选记录 | 规则派生，等待复核 |
| Pilot规则标签 | `conditional_review` 241；`exclude` 94；`consider` 49 | `draft_not_reviewed` |
| 完整patient-candidate规模 | 预计8,912行（557×16） | Schema预期，尚未生成 |
| Track A | 可继续 | `conditional_go` |
| Track B | 当前不可用 | `frozen` |

### 已完成产物

1. 三轮数据与队列审计已经形成安全聚合报告和可执行队列定义。
2. PDAC映射、regimen标准化和candidate-regimen crosswalk已经形成。
3. 候选治疗空间v0.1.1、证据来源登记和4.1.1技术修订已经完成。
4. Track A证据与约束标签Schema和Pilot复核协议已经形成。
5. Pilot的24个决策点和384条规则派生记录已经生成并通过自动检查。
6. Patient-Candidate训练数据Schema已经形成，特征、标签、结局和split边界已经分离。
7. 项目目录、README、文档索引、validator、测试、隐私扫描和小样本抑制流程已经规范化。

### 当前验证结果

仓库迁移后，本机外部材料根路径已更新为`D:\Jiawei_Wang\复旦实验室\数据`。完整pytest结果为`118 passed`；候选空间、标签Schema、外部材料、Patient-Candidate数据集Schema和Pilot共5个专项validator全部通过；隐私扫描和小样本扫描命中数均为0。

### 当前阶段

项目已完成数据可行性、队列定义、候选空间、标签Schema、Pilot自动生成和训练数据契约设计，当前处于“证据标签确认与训练数据物化前”的准备阶段。

正式patient-candidate训练表、患者级train/validation/test切分、物化特征泄漏审计和模型训练均尚未开始。Pilot规则标签用于流程验证，尚未成为正式医学标签。

### 主要风险与边界

1. 候选空间尚未完成临床冻结，PAASC、模糊组织学和部分候选的当前指南角色仍需医学确认。
2. Track B缺失限制了完整临床适用性、安全性和禁忌证判断。
3. 医生实际选择反映观察性治疗事实，也受到数据库未记录因素影响，因此作为辅助标签使用。
4. OS和PFS包含删失与随访差异，当前作为辅助生存结局使用。
5. 规则派生Pilot标签尚待专家复核或导师批准的指南规则方案确认。
6. 患者级产物保持私有，公开结果继续执行聚合输出和`n<5`抑制。

### 下一阶段

1. 导师确认Pilot标签路线：专家双重复核为方案A，冻结指南规则为方案B。
2. 根据确认路线完成Pilot标签复核与差异分析。
3. 冻结候选空间的开发版本和正式证据来源快照。
4. 生成557个决策点与16个主池候选对应的8,912行开发性patient-candidate特征表和独立标签表。
5. 冻结患者级split manifest，完成物化特征泄漏审计。
6. 在标签来源和适用边界明确后开展开发性基线训练。

当前最需要导师确认的问题是：在临床专家双重复核近期难以落实时，是否批准启用冻结指南、监管文件和候选特异性证据规则作为方案B，生成仅表示证据适用性的开发标签，用于后续数据集构建和基线训练。
