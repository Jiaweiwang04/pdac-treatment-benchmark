# 候选治疗方案目录与整理报告 v2.0

版本：v2.0

更新日期：20260914

状态：公开证据目录已冻结；患者标签尚未裁定。

## 目的与范围

以开发集历史治疗及公开临床证据建立候选方案目录，服务于“决策点×治疗方案”的四类标签审核。药物组成的归类、证据支持程度和患者匹配标签是三个独立层次；本报告不生成患者标签。

家族以完整药物组成定义，变体以可核验的制剂、剂量和日程定义。同一药物不同生物标志物路径保持同一家族，但后续标签须注明评价路径。研究性方案显式标记；历史证据单独登记，不自动代表截止日的优先推荐。

## 数据整理规则

主核查覆盖开发患者的全部主候选点。背景表另汇集这些患者同一癌症的已登记疗程，按源记录去重，保留前线治疗和治疗情境；其他癌症治疗不并入该背景表。背景记录的纳入资格仍保持原分层，不因进入目录核查而变成训练样本。

原药名完整保留，仅使用括号前的主名称进行显式字典映射。括号中的商品名、试验名不拆成新药；普通伊立替康与脂质体伊立替康、普通紫杉醇与白蛋白紫杉醇分别编码。匿名研究药只保留每条记录的槽位身份，不能把同名“Investigational Drug”当作同一种药。

疗程药物全集仅用于检索线索。分别核对记录区间是否重叠、开始日是否一致、时间是否缺失；区间重叠也不证明实际同期联合给药。药物完整一致时只记“组成对应”，未记录亚叶酸时不自动补齐，剂量和日程不足时不分配具体变体。模型的决策前病例输入不包含该时点实际选择的方案和后续用药信息。

## 当前结果

| 项目 | 数量 |
| --- | --- |
| 开发患者 | 435 |
| 开发集主候选点 | 807 |
| 原始药名集合（同名去重） | 65 |
| 药名槽位组合（保留重复匿名槽位） | 70 |
| 主候选中的原始药名 | 28 |
| 同癌症历史疗程源记录 | 1530 |
| 目录方案家族 | 64 |
| 已关联结果或推荐的家族 | 64 |
| 研究性方案家族 | 37 |
| 变体记录 | 8 |
| 证据来源 | 69 |
| 主候选中仅作参考的原始组合 | 26 |
| 全部主候选及历史组合判定 | 84 |
| 可用于剂量日程定义的变体 | 7 |

| 组成核查状态 | 主候选点数 |
| --- | --- |
| 匿名药物身份未明 | 103 |
| 仅药物组成对应 | 682 |
| 仅保留原始参考记录 | 22 |

匿名研究药涉及103个主候选点、149个药物槽位。方案家族数不能视为适用于每个患者的方案数，也不能据此相乘获得有效标签对数。所有实际治疗变体仍未分配，患者标签保持空值。

## 方案目录

| 编号 | 方案家族 | 评价情境 | 证据适用条件 | 结果方向 | 原始依据 |
| --- | --- | --- | --- | --- | --- |
| FOLFIRINOX | FOLFIRINOX | 常规情境待个体核查 | 转移性一线；局部晚期有独立mFOLFIRINOX二期证据，须注明对应变体与研究人群。 | 有活性或获益依据 | [PRODIGE4](https://pubmed.ncbi.nlm.nih.gov/21561347/)；[ESMO2025](https://doi.org/10.1016/j.esmoop.2025.104528)；[MFOLFIRINOX](https://pubmed.ncbi.nlm.nih.gov/27022826/) |
| GEM_NAB | 吉西他滨＋白蛋白紫杉醇 | 常规情境待个体核查 | 转移性一线；后线按既往方案及对应指南条款。 | 有活性或获益依据 | [MPACT](https://pubmed.ncbi.nlm.nih.gov/24131140/)；[ESMO2025](https://doi.org/10.1016/j.esmoop.2025.104528)；[ASIA2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12546840/) |
| NALIRIFOX | NALIRIFOX | 常规情境待个体核查 | 转移性一线；不可与普通伊立替康方案互换证据。 | 有活性或获益依据 | [NAPOLI3](https://pubmed.ncbi.nlm.nih.gov/37708904/)；[ESMO2025](https://doi.org/10.1016/j.esmoop.2025.104528) |
| NALIRI_FF | 脂质体伊立替康＋氟尿嘧啶＋亚叶酸 | 常规情境待个体核查 | 既往接受吉西他滨类治疗的转移性胰腺腺癌。 | 有活性或获益依据 | [NAPOLI1](https://pubmed.ncbi.nlm.nih.gov/26615328/) |
| GEM | 吉西他滨 | 常规情境待个体核查 | 晚期系统治疗；一线和后线的推荐背景分别记录。 | 有活性或获益依据 | [ESMO2025](https://doi.org/10.1016/j.esmoop.2025.104528)；[GEST](https://pubmed.ncbi.nlm.nih.gov/23547081/) |
| FF | 氟尿嘧啶＋亚叶酸 | 常规情境待个体核查；历史证据 | 经吉西他滨治疗后的比较研究对照方案；单独审核其当前证据。 | 对照方案证据 | [CONKO003](https://pubmed.ncbi.nlm.nih.gov/24982456/)；[NAPOLI1](https://pubmed.ncbi.nlm.nih.gov/26615328/) |
| OX_FF | 奥沙利铂＋氟尿嘧啶＋亚叶酸 | 常规情境待个体核查 | 吉西他滨后线且既往未使用相应方案；日程及证据存在争议。 | 不同日程证据冲突 | [CONKO003](https://pubmed.ncbi.nlm.nih.gov/24982456/)；[ASIA2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12546840/)；[PANCREOX](https://ascopubs.org/doi/10.1200/JCO.2016.68.5776)；[ASCO2018](https://ascopubs.org/doi/10.1200/JCO.2018.78.9636) |
| GEM_CIS | 吉西他滨＋顺铂 | 常规情境待个体核查 | 优先核实胚系BRCA1/2或PALB2致病变异及晚期系统治疗情境。 | 有活性或获益依据 | [BRCA_CIS](https://pubmed.ncbi.nlm.nih.gov/31976786/) |
| S1 | 替吉奥 | 常规情境待个体核查 | 局部晚期或转移性一线；亚洲研究背景。 | 非劣效结果 | [GEST](https://pubmed.ncbi.nlm.nih.gov/23547081/) |
| GEM_S1 | 吉西他滨＋替吉奥 | 常规情境待个体核查；历史证据 | 局部晚期或转移性一线；记录总体研究未证实总生存优效。 | 未证实优效 | [GEST](https://pubmed.ncbi.nlm.nih.gov/23547081/) |
| GEM_NIMO | 吉西他滨＋尼妥珠单抗 | 常规情境待个体核查 | 充分检测支持KRAS野生型的局部晚期或转移性胰腺癌；国内批准信息据企业公示材料登记，完整推荐等级另核。 | 有活性或获益依据 | [NIMO](https://pubmed.ncbi.nlm.nih.gov/37647576/)；[NIMO_CN](https://www.nhsa.gov.cn/attach/Ypsn2023/YPSN202300211/YPSN202300211-N2.pdf) |
| GEM_ERL | 吉西他滨＋厄洛替尼 | 常规情境待个体核查；历史证据 | 不可切除晚期；历史试验依据，不按EGFR突变自动匹配。 | 获益有限 | [PA3](https://pubmed.ncbi.nlm.nih.gov/17452677/) |
| CAP_ERL | 卡培他滨＋厄洛替尼 | 研究性 | 吉西他滨治疗失败后的晚期情境。 | 有限临床活性 | [CAP_ERL](https://pubmed.ncbi.nlm.nih.gov/17947726/) |
| NABPLAGEM | 吉西他滨＋白蛋白紫杉醇＋顺铂 | 研究性 | 初治转移性胰腺腺癌；单臂探索。 | 有活性或获益依据 | [NABPLAGEM](https://pubmed.ncbi.nlm.nih.gov/31580386/) |
| GTX | 吉西他滨＋多西他赛＋卡培他滨 | 研究性 | 转移性患者；GTX及mGTX分开记录日程。 | 有限临床活性 | [GTX](https://pubmed.ncbi.nlm.nih.gov/17440727/)；[MGTX](https://pubmed.ncbi.nlm.nih.gov/20461379/) |
| OLAPARIB | 奥拉帕利维持 | 常规情境待个体核查 | 转移性胰腺腺癌；胚系BRCA1/2致病变异；一线含铂至少16周且无进展。 | 有活性或获益依据 | [ASCO2020](https://ascopubs.org/doi/10.1200/JCO.20.01364) |
| PEMBRO | 帕博利珠单抗 | 常规情境待个体核查 | 路径一：MSI-H/dMMR，二线及以后。路径二：经验证检测的TMB≥10 mut/Mb，既往治疗后进展且无满意替代方案。两个路径分别判定。 | 有活性或获益依据 | [ASCO2020](https://ascopubs.org/doi/10.1200/JCO.20.01364)；[FDA_TMB](https://www.fda.gov/drugs/drug-approvals-and-databases/fda-approves-pembrolizumab-adults-and-children-tmb-h-solid-tumors) |
| LARO | 拉罗替尼 | 常规情境待个体核查 | NTRK1/2/3致癌融合；并核实经治、替代方案和耐药限制。 | 有活性或获益依据 | [ASCO2020](https://ascopubs.org/doi/10.1200/JCO.20.01364) |
| ENTRE | 恩曲替尼 | 常规情境待个体核查 | NTRK1/2/3致癌融合；不能将其他激酶融合直接替代。 | 有活性或获益依据 | [ASCO2020](https://ascopubs.org/doi/10.1200/JCO.20.01364) |
| REPO | 瑞普替尼 | 常规情境待个体核查 | 晚期NTRK融合实体瘤，既往治疗后进展或无满意替代方案；标明既往TRK抑制剂暴露。 | 有活性或获益依据 | [FDA_REPO](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-repotrectinib-adult-and-pediatric-patients-ntrk-gene-fusion-positive) |
| DAB_TRAM | 达拉非尼＋曲美替尼 | 常规情境待个体核查 | BRAF V600E晚期实体瘤；既往治疗后进展且无满意替代方案；非V600E不得套用。 | 有活性或获益依据 | [FDA_BRAF](https://www.fda.gov/about-fda/2022-oce-annual-report/oncology-regulatory-review)；[BRAF_LABEL](https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/217514s000lbl.pdf) |
| SELP | 塞普替尼 | 常规情境待个体核查 | 晚期RET致癌融合阳性；既往系统治疗后进展或无满意替代方案。 | 有活性或获益依据 | [FDA_RET](https://pmc.ncbi.nlm.nih.gov/articles/PMC10524590/)；[RET_2026](https://www.accessdata.fda.gov/drugsatfda_docs/appletter/2026/213246Orig1s017%2C218160Orig1s007ltr.pdf) |
| TDXD | 德曲妥珠单抗 | 常规情境待个体核查 | HER2 IHC3+晚期实体瘤，既往系统治疗后且无满意替代方案；分子扩增记录不足以替代IHC。 | 有活性或获益依据 | [FDA_HER2](https://www.fda.gov/drugs/resources-information-approved-drugs/fda-grants-accelerated-approval-fam-trastuzumab-deruxtecan-nxki-unresectable-or-metastatic-her2) |
| ZENO | Zenocutuzumab | 常规情境待个体核查 | 晚期不可切除或转移性NRG1融合胰腺腺癌，既往系统治疗后进展。 | 有活性或获益依据 | [FDA_NRG1](https://www.fda.gov/drugs/drug-approvals-and-databases/drug-trials-snapshots-bizengri) |
| DARA | Daraxonrasib | 常规情境待个体核查 | 成人转移性胰腺腺癌；至少一种既往系统治疗，或不适合多药系统治疗。 | 有活性或获益依据 | [DARA_LABEL](https://www.accessdata.fda.gov/drugsatfda_docs/label/2026/220910Orig1s000lbl.pdf)；[DARA2026](https://www.nejm.org/doi/10.1056/NEJMoa2605555) |
| RUCAPARIB | 卢卡帕利维持 | 研究性 | 铂敏感晚期胰腺癌，致病胚系或体细胞BRCA1/2或PALB2；需逐项核实试验亚组。 | 有限临床活性 | [RUCAPARIB](https://pubmed.ncbi.nlm.nih.gov/33970687/) |
| SOTORASIB | 索托拉西布 | 研究性 | 既往治疗的KRAS G12C晚期胰腺癌。 | 有限临床活性 | [SOTORASIB](https://pubmed.ncbi.nlm.nih.gov/36546651/) |
| ADAGRASIB | 阿达格拉西布 | 研究性 | 既往治疗的KRAS G12C晚期胰腺癌。 | 有限临床活性 | [ADAGRASIB](https://pubmed.ncbi.nlm.nih.gov/37099736/) |
| ATEZO_COBI | 阿替利珠单抗＋考比替尼 | 研究性 | 经治晚期PDAC；二线与三线的研究臂结果分别记录。 | 有限临床活性 | [MORPHEUS](https://pubmed.ncbi.nlm.nih.gov/41741368/) |
| NIVO_IPI | 纳武利尤单抗＋伊匹木单抗 | 研究性 | 经治晚期胰腺腺癌；该试验双药组未观察到客观缓解。 | 未观察到客观缓解 | [CHECKMATE032](https://pubmed.ncbi.nlm.nih.gov/38316517/) |
| CAP | 卡培他滨 | 常规情境待个体核查；历史证据 | 晚期系统治疗；单药历史证据，当前使用位置待指南逐项核实。 | 有限临床活性 | [CAP_PHASE2](https://pubmed.ncbi.nlm.nih.gov/11773165/) |
| GEMCAP | 吉西他滨＋卡培他滨 | 常规情境待个体核查；历史证据 | 局部晚期或转移性情境；不套用术后辅助研究。 | 单项试验与合并结果不同 | [GEMCAP](https://pubmed.ncbi.nlm.nih.gov/19858379/) |
| FOLFIRI | FOLFIRI | 常规情境待个体核查 | 吉西他滨类治疗后二线，脂质体伊立替康联合方案不可及时的替代选择；采用相应指南条款。 | 有限临床活性 | [GISCAD](https://pubmed.ncbi.nlm.nih.gov/22576338/)；[ASCO2018](https://ascopubs.org/doi/10.1200/JCO.2018.78.9636) |
| FU | 氟尿嘧啶单药 | 常规情境待个体核查 | 后线低强度治疗选择；不能由单一药名推定具体推注或输注日程。 | 指南列为选项 | [ASCO2018](https://ascopubs.org/doi/10.1200/JCO.2018.78.9636) |
| NALIRI_MONO | 脂质体伊立替康单药 | 研究性 | 吉西他滨预治疗的转移性胰腺癌；该研究单药未显示总生存优势。 | 未证实获益 | [NAPOLI1](https://pubmed.ncbi.nlm.nih.gov/26615328/)；[NAPOLI1_ASIA](https://pmc.ncbi.nlm.nih.gov/articles/PMC7004519/) |
| CAPOX | 卡培他滨＋奥沙利铂 | 研究性；历史证据 | 吉西他滨治疗后的晚期胰腺癌；具体给药强度按原研究分层核查。 | 有限临床活性 | [XELOX_2008](https://pubmed.ncbi.nlm.nih.gov/18756532/) |
| GEMOX | 吉西他滨＋奥沙利铂 | 研究性；历史证据 | 吉西他滨预治疗后进展；历史二期研究，未证明与当前标准方案相比的优势。 | 有限临床活性 | [GEMOX_2006](https://pubmed.ncbi.nlm.nih.gov/16434988/) |
| GEM_CARBO | 吉西他滨＋卡铂 | 研究性；历史证据 | 初治局部晚期或转移性胰腺癌的历史研究；卡铂不能直接继承顺铂的BRCA/PALB2证据。 | 有限临床活性 | [GEM_CARBO](https://www.sciencedirect.com/science/article/pii/S092375341950518X) |
| GEM_DOC | 吉西他滨＋多西他赛 | 研究性；历史证据 | 历史随机二期研究；不能等同于吉西他滨＋白蛋白紫杉醇。 | 有限临床活性 | [CALGB89904](https://pubmed.ncbi.nlm.nih.gov/19858396/) |
| GEM_IRI | 吉西他滨＋伊立替康 | 研究性；历史证据 | 转移性胰腺癌历史随机二期研究；普通伊立替康，未证明当前推荐地位。 | 有限临床活性 | [CALGB89904](https://pubmed.ncbi.nlm.nih.gov/19858396/) |
| IROX | 伊立替康＋奥沙利铂 | 研究性；历史证据 | 二线转移性胰腺癌；随机二期研究未达到总生存主要终点。 | 未证实优效 | [IROX_TRIAL](https://pmc.ncbi.nlm.nih.gov/articles/PMC9897170/) |
| IRI_MONO | 伊立替康单药 | 研究性；历史证据 | 二线研究中的单药对照，不能套用脂质体伊立替康的联合治疗证据。 | 对照方案证据 | [IROX_TRIAL](https://pmc.ncbi.nlm.nih.gov/articles/PMC9897170/) |
| GEM_NAB_NIVO | 吉西他滨＋白蛋白紫杉醇＋纳武利尤单抗 | 研究性；历史证据 | 初治晚期胰腺癌；研究性组合，不能将化疗骨架获益归因于新增免疫治疗。 | 有限临床活性 | [GN_NIVO](https://pubmed.ncbi.nlm.nih.gov/32554514/) |
| NAB_MONO | 白蛋白紫杉醇单药 | 研究性；历史证据 | 吉西他滨预治疗患者的二期研究；不等同于吉西他滨联合方案。 | 有限临床活性 | [NAB_MONO](https://pubmed.ncbi.nlm.nih.gov/22307213/) |
| AZA_PEMBRO | 阿扎胞苷＋帕博利珠单抗 | 研究性 | 二线PDAC研究；不得从个别持久应答推导为普遍推荐。 | 有限临床活性 | [AZA_PEMBRO](https://pubmed.ncbi.nlm.nih.gov/41844546/) |
| TRAM_MONO | 曲美替尼单药 | 研究性 | 仅在明确BRAF非V600突变或融合的研究性评价路径讨论；跨瘤种证据，不能用KRAS任意突变代替。 | 有限临床活性 | [TRAM_MATCH](https://pmc.ncbi.nlm.nih.gov/articles/PMC7165046/) |
| VEMU_MONO | 维莫非尼单药 | 研究性 | BRAF V600突变；跨瘤种研究证据，PDAC亚组不能从总体结果推算。 | 有限临床活性 | [VEMU_BASKET](https://pmc.ncbi.nlm.nih.gov/articles/PMC7196502/) |
| GEMOXEL | 吉西他滨＋奥沙利铂＋卡培他滨 | 研究性；历史证据 | 转移性胰腺癌的历史随机二期研究；具体给药日程须按原文核查。 | 有活性或获益依据 | [GEMOXEL](https://pubmed.ncbi.nlm.nih.gov/25618415/) |
| GEM_NAB_CAP | 吉西他滨＋白蛋白紫杉醇＋卡培他滨 | 研究性；历史证据 | 初治转移性胰腺癌的一期研究；不同于包含顺铂的PAXG。 | 有限临床活性 | [GN_CAP](https://pubmed.ncbi.nlm.nih.gov/23053263/) |
| CAP_NAB | 卡培他滨＋白蛋白紫杉醇 | 研究性；历史证据 | 初治转移性胰腺腺癌的二期研究；不能套用联合吉西他滨的三药研究。 | 有活性或获益依据 | [CAP_NAB](https://pmc.ncbi.nlm.nih.gov/articles/PMC4783742/) |
| NAB_FF | 白蛋白紫杉醇＋氟尿嘧啶＋亚叶酸 | 研究性；历史证据 | 初治转移性胰腺癌；完整组成包含亚叶酸，研究未证明优于标准方案。 | 有活性或获益依据 | [AFUGEM](https://pubmed.ncbi.nlm.nih.gov/28397697/) |
| FU_MMC | 氟尿嘧啶＋丝裂霉素 | 研究性；历史证据 | 晚期胰腺癌历史系统治疗；不能与同步放化疗研究混用。 | 未证实优效 | [FU_MMC](https://ascopubs.org/doi/10.1200/JCO.2002.09.029) |
| GEM_FF | 吉西他滨＋氟尿嘧啶＋亚叶酸 | 研究性；历史证据 | 晚期胰腺腺癌历史二期研究；亚叶酸为完整组合的一部分。 | 有限临床活性 | [GEM_FF](https://pubmed.ncbi.nlm.nih.gov/11510033/) |
| CIS_FF | 顺铂＋氟尿嘧啶＋亚叶酸 | 研究性；历史证据 | 初治晚期胰腺腺癌的历史二期研究。 | 有限临床活性 | [CIS_FF](https://pubmed.ncbi.nlm.nih.gov/8777174/) |
| ERL_MONO | 厄洛替尼单药 | 研究性；历史证据 | 不能继承厄洛替尼＋吉西他滨的联合证据；单药试验因无效提前终止。 | 未观察到客观缓解 | [ERL_MONO](https://pubmed.ncbi.nlm.nih.gov/28702772/) |
| MMC_MONO | 丝裂霉素单药 | 研究性 | HRD晚期胰腺癌多线治疗后的研究性路径；不把任意DDR变异或VUS当作敏感标志。 | 有限临床活性 | [MMC_HRD](https://pmc.ncbi.nlm.nih.gov/articles/PMC9687686/) |
| CIS_MONO | 顺铂单药 | 研究性；历史证据 | 转移性胰腺腺癌历史研究；不直接继承顺铂联合吉西他滨证据。 | 有限临床活性 | [CIS_MONO](https://pubmed.ncbi.nlm.nih.gov/8422283/) |
| TMZ_MONO | 替莫唑胺单药 | 研究性；历史证据 | 胰腺腺癌试验中的阴性证据；不得以胰腺神经内分泌肿瘤疗效替代。 | 未观察到客观缓解 | [TMZ_MONO](https://pubmed.ncbi.nlm.nih.gov/9740547/) |
| EVERO_MONO | 依维莫司单药 | 研究性；历史证据 | 吉西他滨难治胰腺癌的阴性二期研究；不能套用神经内分泌肿瘤适应证。 | 未观察到客观缓解 | [EVERO_MONO](https://pmc.ncbi.nlm.nih.gov/articles/PMC2645085/) |
| GEM_PAC | 吉西他滨＋普通紫杉醇 | 常规情境待个体核查 | FOLFIRINOX后二线；普通紫杉醇制剂，不能替代白蛋白紫杉醇的试验证据。 | 未证实优效 | [GEMPAX](https://ascopubs.org/doi/10.1200/JCO.23.00795)；[ESMO2025](https://doi.org/10.1016/j.esmoop.2025.104528)；[ASIA2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12546840/) |
| GEM_CETUX | 吉西他滨＋西妥昔单抗 | 研究性；历史证据 | 晚期胰腺腺癌的阴性三期结果；不能用EGFR表达直接支持联合治疗。 | 未证实优效 | [S0205](https://pmc.ncbi.nlm.nih.gov/articles/PMC2917315/) |
| GEM_FU | 吉西他滨＋氟尿嘧啶 | 研究性；历史证据 | 原试验明确不含亚叶酸的双药持续输注日程；不能直接推断原病例具体日程。 | 未证实获益 | [GEM_FU](https://pubmed.ncbi.nlm.nih.gov/15986036/) |
| XELOXIRI | 卡培他滨＋奥沙利铂＋伊立替康 | 研究性 | 晚期胰腺癌一线回顾性结果；普通伊立替康，不能替换为脂质体制剂。 | 有活性或获益依据 | [XELOXIRI](https://pmc.ncbi.nlm.nih.gov/articles/PMC11905668/) |
| FOLFOX_A | 氟尿嘧啶＋亚叶酸＋奥沙利铂＋白蛋白紫杉醇 | 研究性；历史证据 | 局部晚期或转移性胰腺癌的早期研究；会议摘要读取层级，不与含贝伐珠单抗的FABLOx合并。 | 有活性或获益依据 | [FOLFOX_A](https://pmc.ncbi.nlm.nih.gov/articles/PMC4812841/) |

### 方案变体

下表定义参考文献中的具体方案。实际病例仅药物组成一致时不分配这些变体。

| 家族 | 变体 | 区分依据 | 来源 |
| --- | --- | --- | --- |
| FOLFIRINOX | PRODIGE4/ACCORD11 | 每14日；奥沙利铂85、普通伊立替康180、亚叶酸400 mg/m²；氟尿嘧啶400 mg/m²推注后2400 mg/m²持续46小时。 | [PRODIGE4](https://pubmed.ncbi.nlm.nih.gov/21561347/) |
| NALIRIFOX | NAPOLI3 | 28日周期第1、15日；脂质体伊立替康50、奥沙利铂60、亚叶酸400、氟尿嘧啶2400 mg/m²持续46小时。 | [NAPOLI3](https://pubmed.ncbi.nlm.nih.gov/37708904/) |
| GEM_NAB | MPACT | 28日周期第1、8、15日；白蛋白紫杉醇125 mg/m²和吉西他滨1000 mg/m²。 | [MPACT](https://pubmed.ncbi.nlm.nih.gov/24131140/) |
| GTX | GTX Fine | 21日周期；卡培他滨750 mg/m²每日两次第1–14日；吉西他滨750 mg/m²与多西他赛30 mg/m²第4、11日。 | [GTX](https://pubmed.ncbi.nlm.nih.gov/17440727/) |
| GTX | mGTX phase I | 多西他赛第1、8日，吉西他滨第8、15日，卡培他滨第8–21日；剂量探索各层不可混并。 | [MGTX](https://pubmed.ncbi.nlm.nih.gov/20461379/) |
| OX_FF | OFF | OFF研究名称及组成可定位；当前来源间剂量表述不一致，本版仅保留研究变体索引，不用于剂量或日程层级判定。 | [CONKO003](https://pubmed.ncbi.nlm.nih.gov/24982456/) |
| OX_FF | mFOLFOX6 PANCREOX | 每14日；奥沙利铂85、亚叶酸400 mg/m²；氟尿嘧啶400 mg/m²推注后2400 mg/m²持续46小时。 | [PANCREOX](https://ascopubs.org/doi/10.1200/JCO.2016.68.5776)；[ASCO2018](https://ascopubs.org/doi/10.1200/JCO.2018.78.9636) |
| FOLFIRINOX | mFOLFIRINOX Stein 2016 | 相对原FOLFIRINOX，普通伊立替康和氟尿嘧啶推注剂量各降低25%；不代表全部mFOLFIRINOX日程。 | [MFOLFIRINOX](https://pubmed.ncbi.nlm.nih.gov/27022826/) |

## 证据使用与冻结规则

知识截止日为2026-09-12，检索日期与证据发布日期分别记录。指南、原始试验、病例报告、会议摘要和监管文件按原来源区分，不自行换算成统一指南推荐等级。每条来源注明读取层级；只核实题录或研究范围的条目不能独立支持正向患者标签。未提取的推荐级别保持空值。

目录生成只接收开发患者；Core实际治疗不参与扩充。本版已固定各原始组合处理结论、目录适用条件和内容摘要，再执行独立的Core覆盖审计。冻结只约束目录版本，不代表完成专家临床裁定。审计发现未覆盖方案也不能回填同版目录；需要扩展时建立新版本并明确原测试集已被查看的事实。

美国批准范围、其他地区可及性和研究性评价分别处理。FDA的泛瘤种适应证不等于PDAC专属随机证据；家族进入目录不代表当前患者符合适应证，也不代表获得中国批准。

## 待核查与输出

- 最新版CSCO/NCCN完整推荐表未逐项核验；目录采用已核验的公开原始结果与公开指南条款，不能声称覆盖全部指南或全部临床试验。
- 药物组成对应不证明同期联合给药、治疗适应证或具体剂量日程；缺少组分和匿名药物均保留原值。
- 单臂、病例系列、跨瘤种与会议摘要按实际读取层级使用；患者标签仍需逐条证据与专家审核。
- OFF保留研究变体索引，剂量日程存在来源差异，本版不作变体级判定。
- 检索未达到纳入标准只表示本次来源范围内尚不能支持进入目录，不等同于治疗无效或患者标签为MISMATCH。

未纳入家族的参考项逐项保留原药名、影响点数、病例定位及判定理由；不能直接解释为方案无效或患者不匹配。全文证据条款、分子改变类型与治疗线次仍需在病例初标前核查。

- [方案家族表](../../../data/processed/v2.0/07_treatment_catalog/treatment_families_v2.0.csv)
- [变体表](../../../data/processed/v2.0/07_treatment_catalog/treatment_variants_v2.0.csv)
- [原始组合完整核查表](../../../data/processed/v2.0/07_treatment_catalog/development_raw_regimen_sets_v2.0.csv)
- [主候选逐点映射](../../../data/processed/v2.0/07_treatment_catalog/development_regimen_mapping_v2.0.csv)
- [药名原值与规范名对照](../../../data/processed/v2.0/07_treatment_catalog/drug_name_mapping_v2.0.csv)
- [参考项清单](../../../data/processed/v2.0/07_treatment_catalog/treatment_evidence_gaps_v2.0.csv)
- [全部组合纳入判定](../../../data/processed/v2.0/07_treatment_catalog/development_regimen_screening_v2.0.csv)
- [目录冻结锁](../../../data/processed/v2.0/07_treatment_catalog/treatment_catalog_lock_v2.0.json)
- [同癌症历史疗程背景](../../../data/processed/v2.0/07_treatment_catalog/development_historical_regimen_context_v2.0.jsonl)

来源题录及读取范围见[证据来源说明](treatment_evidence_ledger_v2.0.md)。运行 `python -B code/scripts/run_v2_0.py catalog` 重建本阶段，运行 `python -B code/scripts/run_v2_0.py all` 复现八阶段并检查来源与文档。
