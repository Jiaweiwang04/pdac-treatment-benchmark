# PANC 各类数据用途说明 v2.0

版本：v2.0

更新日期：20260912

状态：临床与主要分子文件已整理；证据检索、完整临床纳入及治疗标签未完成。

## 目的与来源

说明每类数据如何服务于局部晚期／转移性PDAC治疗决策研究，以及哪些字段只适合追溯、不能直接进入模型。原始发布版本PANC 1.0-public，所有文件保留原样。

字段含义依据[Analytic Data Guide](../../../data/raw/AACR%20GENIE%20Biopharma%20Collaborative%20Public/Data%20Releases/PANC/1.0-public/Documentation/GENIE%20BPC%20PANC%201.0-public%20Analytic%20Data%20Guide.pdf)、[Variable Synopsis](../../../data/raw/AACR%20GENIE%20Biopharma%20Collaborative%20Public/Data%20Releases/PANC/1.0-public/Documentation/GENIE%20BPC%20PANC%20v1.0-public%20Variable%20Synopsis.xlsx)及[Release Notes](../../../data/raw/AACR%20GENIE%20Biopharma%20Collaborative%20Public/Data%20Releases/PANC/1.0-public/Documentation/GENIE%20BPC%20PANC%20v1.0-public%20Release%20Notes.pdf)。生成的[变量字典](../../../data/processed/v2.0/02_decision_points/variable_dictionary_v2.0.json)保留原工作表、行号、字段说明及校验和。

## 临床数据用途

| 数据表 | 主要用途 | 关键限制 |
| --- | --- | --- |
| patient_level_dataset | 患者标识、性别及背景；患者级划分防止训练测试交叉 | 随访、死亡、全程事件总数是后验信息，不用于早期决策 |
| cancer_level_dataset_index | 目标癌症关联、诊断分期、初始可切除性、转移日期和组织学线索 | 原分期和组织学可能由后续资料整理；派生转移时间需要回查；初始状态不等于当前状态 |
| cancer_level_dataset_non_index | 区分其他原发癌，解释非PDAC用药与病理 | 不把同一患者的全部癌症都归为PDAC |
| pathology_report_level_dataset | 逐报告、逐标本保留部位、癌种、浸润、原位及组织学；展开附加检测 | 主报告签发日未提供；报告没有ca_seq；阴性标本和其他癌种不能删除 |
| regimen_cancer_level_dataset | 整套方案及单药开始日期、既往用药、观察方案目录和候选锚点 | 方案序号不等于治疗线数；全程成分可能后加；实际使用不等于正标签；结束和结局可能是未来信息 |
| ca_radtx_dataset | 放疗史、部位和与系统治疗的时间关系 | 开始日在先不意味着当时已知最终剂量或完成情况 |
| imaging_level_dataset | 影像部位、癌症证据及状态变化，用于情境核查 | 没有ca_seq；检查日不等于报告可用日；跨机构对少数消退病灶记录口径不同 |
| med_onc_note_level_dataset | 医生评估癌种及改善、稳定、进展等状态 | 通常每月抽取一份评估，非完整病程全文；不能据缺失推断无进展 |
| tm_level_dataset | CA19-9、CEA及其单位、参考范围与趋势 | 采样日不等于结果可用日；标志物不单独决定进展或治疗标签 |
| cancer_panel_test_level_dataset | 连接临床癌症、病理报告及分子样本；确定NGS报告日期 | 按报告日期筛选；OncoTree及检测结论不回填到早期；sample_type不自动证明该时点转移 |

病理327个原字段保留于第一阶段临床记录，第二阶段逐标本及逐检测整理，包含空值和明确缺失编码。原始公开表是结构化摘要，不包含完整医院病理报告全文，不能补写肿瘤尺寸、切缘、脉管侵犯等未提供内容。

## 分子及辅助文件用途

| 文件 | 当前使用方式 | 解释边界 |
| --- | --- | --- |
| data_clinical_sample.txt | 连接样本与患者，保留面板、样本类型及测序信息 | 含聚合PD-L1等后验摘要，不代替逐次报告时间 |
| data_mutations_extended.txt | 保留全部小变异原字段、样本、基因及坐标 | 不把数据库注释或Somatic字段自动等同于临床致病性或胚系检测结论 |
| data_sv.txt | 保留结构变异、融合或重排的原字段与来源 | 结构变异存在不等于已证实可用药靶点 |
| data_CNA.txt | 按样本保留完整基因列及原值 | 0、NA、空值与无样本列分别处理；不把缺测视为正常 |
| data_gene_matrix.txt及data_gene_panel_*.txt | 保存样本检测面板及基因覆盖列表 | 在面板上不保证所有变异类型均充分检出；无变异记录不自动视为阴性 |
| data_cna_hg19.seg | 当前保留在原始清单，供后续区段级复核 | 本阶段未解析连续拷贝数区段，不用离散CNA替代其全部信息 |
| cBioPortal其他临床、时间轴、病例列表及meta文件 | 保留原始版本与辅助定位，必要时交叉核查 | 不与同源十张临床表重复计数；未作为新的独立患者证据 |
| 数据手册、变量字典、发布说明 | 确定字段含义、关联、日期锚点及来源差异 | 文档叙述与数据冲突时记录疑点，不擅自修改源文件 |

## 临床与时间风险

数据指南第89页说明试验药可被遮蔽，结束间隔可能被设成开始间隔。第140页说明PD-L1最多三次检测，摘要阳性可能来自任意一次。第164及186页说明内科评估通常按月抽取，且不是完整病程。第173、176—177页明确NGS关联与报告日期。

发布说明指出ca_hist_adeno_squamous已纳入相关NGS OncoTree信息，因此不能直接当作早期可知组织学。影像／病理映射得到的派生转移时间要回查原证据，特别是与手术同日的情况。

手册第4页的测序年龄范围写为18—56，但样本元数据存在超过56岁的记录。本阶段不据此截断年龄或删除病例，也不自行更改该文档；该来源疑点保留待核实。

## 治疗标签如何使用这些数据

患者信息用于判断方案适用条件；实际方案用于保留历史候选；指南和论文用于建立候选方案及证据；专家审核用于修正适用性标签。观察结局、患者是否实际用过及未使用的方案，都不能单独决定正负标签。

当前资料不足以支持所有病例的无条件方案判断。需要区分已知、未知、同日先后不明和未来信息，并明确条件性标签规则。完整流程见[候选决策点协议](decision_point_protocol_v2.0.md)，当前结果见[阶段报告](decision_point_audit_report_v2.0.md)。
