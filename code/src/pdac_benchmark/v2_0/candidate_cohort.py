"""Assign candidate research roles from histology, disease context and treatment records."""
import json
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .audit import write_csv, write_json, write_jsonl
from .candidate_review import read_jsonl
from .decision_points import build_events
from .layout import resolve_paths
from .source import sha256

BASE = Path(__file__).resolve().parents[4]
PHASE = '05_candidate_cohort'
ROLE_LABELS = {
    'main_observed_regimen': '方案起始主候选',
    'progression_extension': '进展扩展病例',
    'treatment_context_appendix': '治疗调整待核查附录',
    'histology_conflict_review': '组织学归属冲突待核查',
    'disease_context_review': '疾病情境或归属待核查',
    'linked_progression_reference': '同日进展关联记录（不另计点）',
    'ngs_timing_review': 'NGS时序待核查',
    'outside_scope_reference': '范围外追溯记录',
}
BUCKET_ROLES = {
    'main_regimen_start_candidate':'main_observed_regimen',
    'progression_trigger_review':'progression_extension',
    'regimen_independence_review':'treatment_context_appendix',
    'within_regimen_change_review':'treatment_context_appendix',
    'progression_linked_same_day_not_separate':'linked_progression_reference',
    'ngs_timing_review':'ngs_timing_review',
    'disease_context_review':'disease_context_review',
    'outside_main_scope_retained':'outside_scope_reference',
}
# Source wording is a review signal only; it is never a clinical diagnosis.
FLAG_WORDS = ('neuroendocrine', 'acinar', 'adenosquamous', 'urothelial', 'mesothelioma', 'squamous cell')


def prior_histology_signals(candidate, patient_events):
    t0 = candidate['t0_day']
    if t0 is None:
        return []
    return [dict(event_id=e['event_id'], procedure_day=e['event_day'], source=e['source'], **s)
            for e in patient_events if e['kind']=='pathology_procedure'
            and e['event_day'] is not None and e['event_day'] < t0
            for s in e['facts']['specimens']
            if s['invasive']=='Yes' and s['cancer_type']=='Pancreatic Cancer'
            and any(w in s['invasive_histology'].lower() for w in FLAG_WORDS)]


def assign_role(candidate, histology_ids, context_ids):
    cid = candidate['candidate_id']
    if cid in histology_ids:
        return 'histology_conflict_review', '特殊／混合组织学仍被原表标为胰腺癌；现有癌症及标本关联不足以可靠分开，逐点待核查。'
    if cid in context_ids:
        return 'disease_context_review', '派生转移日与手术同日；现有部位、影像及评估无法充分确定本时点的晚期治疗情境，保留待核查。'
    role = BUCKET_ROLES[candidate['screening_bucket']]
    reasons = {
        'main_observed_regimen':'保留已筛选的方案起始候选；NGS严格在先。',
        'progression_extension':'保留作进展扩展病例；t0为归组起始事件日，实际决策日与独立决策含义未确认。',
        'treatment_context_appendix':'同药／减药或方案内药物开始的意图尚不清楚，保留为背景及待核查附录。',
        'linked_progression_reference':'关联同日治疗候选；同日先后未知，不单独计作决策点。',
        'ngs_timing_review':'沿用在先NGS报告未得到确认的原分层。',
        'disease_context_review':'沿用既有疾病情境或癌症归属待核查分层。',
        'outside_scope_reference':'沿用既有范围外分层，保留来源追溯。',
    }
    return role, reasons[role]


def build(base, processed, out, config):
    expected = {'ngs_rule':'report_strictly_before_t0',
                'histology_policy':'point_level_unresolved_conflicts_review_no_patient_deletion',
                'progression_role':'extension_only', 'same_or_subset_and_within_regimen_role':'appendix_only',
                'clinical_missingness_is_exclusion':False, 'expert_review_completed':False}
    if any(config.get(k)!=v for k,v in expected.items()):
        raise ValueError('Cohort configuration differs from implemented screening rules')
    parent_path = base/'code/results/v2.0/04_candidate_review/run_manifest.json'
    parent = json.loads(parent_path.read_text(encoding='utf-8'))
    if parent['status']!='completed':
        raise ValueError('Upstream review is incomplete')
    inputs = {parent_path.relative_to(base).as_posix():sha256(parent_path)}

    def read_verified(relative):
        p = base/relative
        digest = sha256(p)
        if digest != {**parent['input_sha256'], **parent['output_sha256']}.get(relative):
            raise ValueError('Upstream source changed: '+relative)
        inputs[relative] = digest
        return read_jsonl(p)

    registry = read_verified('data/processed/v2.0/04_candidate_review/reviewed_candidate_registry_v2.0.jsonl')
    inv = {r['candidate_id']:r for r in read_verified('data/processed/v2.0/04_candidate_review/candidate_evidence_inventory_v2.0.jsonl')}
    tables = {p.stem:read_verified(p.relative_to(base).as_posix())
              for p in sorted((base/'data/processed/v2.0/01_source_audit/clinical_records').glob('*.jsonl'))}
    events, by_patient, cancers, days = build_events(tables)
    event_index = {e['event_id']:e for e in events}
    histology_ids = set(config['histology_conflict_candidate_ids'])
    context_ids = set(config['context_review_candidate_ids'])
    main_ids = {c['candidate_id'] for c in registry if c['screening_bucket']=='main_regimen_start_candidate'}
    if not histology_ids <= main_ids or not context_ids <= main_ids or histology_ids & context_ids:
        raise ValueError('Configured candidate lists do not match upstream main candidates')
    signals = {c['candidate_id']:prior_histology_signals(c, by_patient[tuple(c['patient_key'])]) for c in registry}
    actual_flagged_main = {cid for cid in main_ids if signals[cid]}
    if actual_flagged_main != histology_ids:
        raise ValueError('Histology source signals differ from the configured candidate list')
    rows, ledger = [], []
    for c in registry:
        cid, pk, t0 = c['candidate_id'], tuple(c['patient_key']), c['t0_day']
        role, reason = assign_role(c, histology_ids, context_ids)
        prior_ngs = [event_index[eid] for eid in c['ngs_report_before']]
        if any(e['available_day'] is None or t0 is None or e['available_day'] >= t0 for e in prior_ngs):
            raise ValueError('NGS-before-t0 contract violated')
        if role in {'main_observed_regimen','progression_extension'} and not prior_ngs:
            raise ValueError('Main or extension lacks strictly earlier NGS')
        qualification = {
            'role':role, 'role_label':ROLE_LABELS[role], 'reason_zh':reason,
            'rule_authority':config['rule_authority'],
            'histology_source_signal':bool(signals[cid]),
            'histology_source_values':sorted({s['invasive_histology'] for s in signals[cid]}),
            'histology_signal_is_clinical_diagnosis':False,
            'predecision_oncotree_codes':sorted({e['facts']['cpt_oncotree_code'] for e in prior_ngs}),
            'pathology_report_availability':'unconfirmed_procedure_date_only',
            'clinical_missingness_is_exclusion':False,
            'final_training_eligibility':None, 'expert_label':None,
            'linked_treatment_candidate_ids':c['candidate_review']['same_day_treatment_candidate_ids'],
            'linked_progression_candidate_ids':c['candidate_review']['linked_same_day_progression_candidate_ids'],
        }
        new = {**c, 'candidate_role':role, 'cohort_review':qualification}
        if any(new[k]!=v for k,v in c.items()):
            raise ValueError('Upstream candidate fact changed')
        rows.append(new)
        if cid not in histology_ids | context_ids:
            continue
        evidence = {'candidate_id':cid,'patient_key':c['patient_key'],'cancer_seq':c['cancer_seq'],
                    't0_day':t0,'old_bucket':c['screening_bucket'],'new_role':role,'reason_zh':reason,
                    'source':c['source'], 'flagged_specimens':signals[cid],
                    'predecision_ngs_reports':prior_ngs,
                    'pathology_ngs_links':inv[cid]['predecision_ngs_pathology_links'],
                    'link_resolution':'procedure_and_report_only_no_unique_specimen_or_other_primary_assignment',
                    'other_cancer_sequences':[k[2] for k in cancers if k[:2]==pk and k[2]!=c['cancer_seq']],
                    'clinical_adjudication':None}
        if cid in context_ids:
            surgery_ids = inv[cid]['surgical_pathology_same_day_as_derived_metastasis']
            if not surgery_ids:
                raise ValueError('Configured context candidate lacks surgery coincidence evidence')
            before = [e for e in by_patient[pk] if e['event_day'] is not None and e['event_day']<t0]
            evidence.update(derived_metastasis_day=inv[cid]['derived_metastasis_day'],
                            surgical_pathology=[event_index[eid] for eid in surgery_ids],
                            all_prior_imaging=[e for e in before if e['kind']=='imaging'],
                            all_prior_oncology_assessments=[e for e in before if e['kind']=='oncology_assessment'],
                            baseline_cancer_raw=cancers[(*pk,c['cancer_seq'])],
                            absence_of_selected_organ_cue_is_not_proof_of_absence=True)
        ledger.append(evidence)
    if len({r['candidate_id'] for r in rows})!=len(registry):
        raise ValueError('Candidate loss or duplication')
    processed.mkdir(parents=True,exist_ok=True)
    out.mkdir(parents=True,exist_ok=True)
    write_jsonl(processed/'candidate_role_registry_v2.0.jsonl',rows)
    write_jsonl(processed/'candidate_reclassification_ledger_v2.0.jsonl',ledger)
    flat = [{'candidate_id':c['candidate_id'],'patient_id':c['patient_key'][1],'cohort':c['patient_key'][0],
             'cancer_seq':c['cancer_seq'],'t0_day':c['t0_day'],'role':c['candidate_role'],
             'role_zh':ROLE_LABELS[c['candidate_role']],'upstream_bucket':c['screening_bucket'],
             'reason_zh':c['cohort_review']['reason_zh'],
             'prior_oncotree_codes':' | '.join(c['cohort_review']['predecision_oncotree_codes']),
             'ngs_report_before':' | '.join(c['ngs_report_before']),
             'histology_signal_values':' | '.join(c['cohort_review']['histology_source_values']),
             'scope_at_t0':c['scope_at_t0'],
             'observed_action_drugs_raw':' | '.join(d['name_raw'] for d in c['observed_action_drugs']),
             'observed_action_usage':'reference_only_not_positive_label_or_model_input',
             'source_file':c['source']['file'],'source_logical_row':c['source']['logical_row'],
             'final_training_eligibility':'not_finalized','expert_label':''} for c in rows]
    for filename, subset in [('candidate_role_registry',flat),
                             ('main_candidates',[r for r in flat if r['role']=='main_observed_regimen']),
                             ('progression_extension',[r for r in flat if r['role']=='progression_extension']),
                             ('treatment_appendix',[r for r in flat if r['role']=='treatment_context_appendix']),
                             ('reclassified_candidates',[r for r in flat if r['candidate_id'] in histology_ids|context_ids])]:
        write_csv(processed/(filename+'_v2.0.csv'),list(flat[0]),subset)
    roles = {role:{'records':len(rs),'patients':len({tuple(r['patient_key']) for r in rs})}
             for role in ROLE_LABELS for rs in [[r for r in rows if r['candidate_role']==role]]}
    summary = {'project_version':'v2.0','phase':PHASE,'execution_date':config['execution_date'],
               'status':'candidate_roles_fixed_not_clinical_gold_standard',
               'registry_records':len(rows),'registry_patients':len({tuple(c['patient_key']) for c in rows}),'roles':roles,
               'main_before':len(main_ids),'histology_moved':len(histology_ids),'context_moved':len(context_ids),
               'reclassification_records':len(ledger),
               'appendix_upstream_buckets':dict(Counter(c['screening_bucket'] for c in rows if c['candidate_role']=='treatment_context_appendix')),
               'main_scope_counts':dict(Counter(c['scope_at_t0'] for c in rows if c['candidate_role']=='main_observed_regimen')),
               'extension_histology_signal_records':sum(bool(signals[c['candidate_id']]) for c in rows if c['candidate_role']=='progression_extension'),
               'main_and_extension_unique_patients':len({tuple(c['patient_key']) for c in rows if c['candidate_role'] in {'main_observed_regimen','progression_extension'}}),
               'records_deleted':0,'t0_or_ngs_modified':0,'clinical_missingness_caused_exclusions':0,
               'final_eligible_decision_points':None,'expert_labels':None,'expert_review_completed':False}
    write_json(out/'candidate_cohort_summary_v2.0.json',summary)
    return summary, inputs


def write_report(base, s):
    table = '\n'.join(f"| {ROLE_LABELS[k]} | {v['records']:,} | {v['patients']:,} |" for k,v in s['roles'].items())
    text = f'''# 候选集合报告 v2.0

版本：v2.0

更新日期：{datetime.now(timezone.utc).strftime('%Y%m%d')}

状态：候选分组完成；临床裁定和治疗标签尚未形成。

## 范围与分组规则

根据候选点对应的组织学、疾病情境和治疗记录，划分主候选、进展扩展及治疗调整附录。规则和指定候选编号位于[配置](../../../code/config/v2.0/candidate_cohort.json)。

## 筛选流程与数量

| 阶段 | 记录／组数 | 解释 |
| --- | ---: | --- |
| 原始系统治疗记录 | 3,153 | 目标癌症2,960，非目标癌症193 |
| 第二阶段治疗锚点 | 3,404 | 方案起始及251个方案内其他药物开始日 |
| 第三阶段登记池 | 4,411 | 加入1,007个没有后续新治疗起始记录的进展候选组 |
| 第三阶段方案起始主候选 | 1,150 | 严格在先NGS及初筛情境支持；不是最终纳入 |
| 第四阶段方案起始主候选 | {s['main_before']:,} | 将156条同药／减药记录单列 |
| 本阶段组织学归属待核查 | {s['histology_moved']:,} | 逐点移动，不按患者整体删除 |
| 本阶段情境待核查新增 | {s['context_moved']:,} | 与上述35条不重叠 |
| 本阶段方案起始主候选 | {s['roles']['main_observed_regimen']['records']:,} | 候选用途固定，标签仍待定义和审核 |

主候选的变化为994 − 35 − 7 = 952。登记池仍为{s['registry_records']:,}条、{s['registry_patients']:,}名患者，无记录删除，无候选日或NGS日期改写。详细互斥分组如下。

| 当前用途 | 记录／组数 | 患者数 |
| --- | ---: | ---: |
{table}

患者可以跨组，人数不能相加。主候选与进展扩展合计覆盖{s['main_and_extension_unique_patients']:,}名不同患者；两种记录不能合并宣称为同质的独立治疗决策或最终训练样本。未来训练／测试必须按患者隔离。

## 逐点证据与边界

35条候选的特殊／混合组织学原文均位于取材早于t0、且被原表标为Pancreatic Cancer的标本。现有病理记录缺少逐标本的癌症序号，NGS主要关联到操作／报告，不能可靠地将冲突标本分给另一原发癌。因此保留原文及证据，归入组织学归属待核查；没有把关键词命中当作非PDAC诊断。其他候选不随患者整体移出。

GENIE-MSK-P-0002071的第285日候选尤其需要区分：在先报告为PAAC，第565日才出现PAAD。后者不进入第285日的在先分子证据。该患者其余较晚候选按各自t0保留当时已有报告，不共用最早时点的判断。

7条情境疑点均保留手术病理、全部在先影像与肿瘤内科评估，未判定为辅助治疗，也未判定为确定远处转移。初始筛查使用的部分器官编码并不完备；GENIE-MSK-P-0005758有卵巢／附件部位的胰腺癌阳性病理原文，因此不在这7条中。不能将缺少指定器官信号当成没有转移，也不能将其余候选的器官线索视为已完成专家分期确认。

602个进展组固定为扩展病例，其中{s['extension_histology_signal_records']}组仍带有特殊／混合组织学原文信号，保留为解释限制，不自动视为已确认可用于训练。没有后续新治疗起始记录不等于治疗停止；归组起始日也不是已知的实际决策日。156条同药／减药及88条方案内起始共244条固定在治疗背景与待核查附录。105条同日进展保持双向关联、未知先后，不另计点。

病理主报告日期缺失时，只能说取材在先，不能声称报告当时可用。完整字段和未来随访仅供核查，不能整体作为模型输入。临床字段缺失限制了候选方案适用性的判断。历史实际用药和后续结局不是适用性标签，未用方案也不是负标签。

## 候选表与输出

候选表记录用途、时间、分组和源行号；逐点证据文件保留组织学冲突及情境核查依据。完整病理字段保存在第一阶段临床记录，分子记录和时间轴分别保存在第二阶段中间数据。

- [主候选CSV](../../../data/processed/v2.0/05_candidate_cohort/main_candidates_v2.0.csv)
- [进展扩展CSV](../../../data/processed/v2.0/05_candidate_cohort/progression_extension_v2.0.csv)
- [治疗调整附录CSV](../../../data/processed/v2.0/05_candidate_cohort/treatment_appendix_v2.0.csv)
- [42条分组变更CSV](../../../data/processed/v2.0/05_candidate_cohort/reclassified_candidates_v2.0.csv)
- [逐点变更证据](../../../data/processed/v2.0/05_candidate_cohort/candidate_reclassification_ledger_v2.0.jsonl)
- [全部候选与原分组](../../../data/processed/v2.0/05_candidate_cohort/candidate_role_registry_v2.0.jsonl)
- [结局参考](../../../data/processed/v2.0/03_screening_candidates/candidate_outcome_references_v2.0.jsonl)：仍按原定义保留，独立于决策前信息与标签。

## 复现与下一步

从项目根目录执行 `python -B code/scripts/run_v2_0.py all` 重建五阶段并核对来源、测试和文档；前四阶段已完成时可用 `python -B code/scripts/run_v2_0.py cohort` 重建本阶段。统计与来源见[汇总](../../../code/results/v2.0/05_candidate_cohort/candidate_cohort_summary_v2.0.json)和[运行清单](../../../code/results/v2.0/05_candidate_cohort/run_manifest.json)。原始文件只读，派生数据、源码、配置、结果与文档按既定规范分开。

四类标签、研究性方案标记与固定知识截止日2026-09-12已确认，见[标签定义](treatment_label_definition_v2.0.md)。下一步以候选集合整理历史实际方案及药物命名，建立国内外指南与论文证据矩阵，依定义为Pilot形成真实初标。患者归属及首轮Pilot／Core名单见[患者划分协议](patient_split_protocol_v2.0.md)。证据检索与专家审核尚未完成。
'''
    (base/'docs/notes/v2.0/candidate_cohort_report_v2.0.md').write_text(text,encoding='utf-8')


def run(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    source = json.loads((BASE/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    raw, processed, out = resolve_paths(BASE,{**source,**config})
    inventory = json.loads((BASE/source['results_dir']/'source_inventory.json').read_text(encoding='utf-8'))
    def verify_raw():
        if any(sha256(raw/r['file'])!=r['sha256'] for r in inventory):
            raise ValueError('Original source changed')
    verify_raw()
    out.mkdir(parents=True,exist_ok=True)
    manifest = {'project_version':'v2.0','phase':PHASE,'status':'running',
                'started_utc':datetime.now(timezone.utc).isoformat(),
                'runtime':{'python':platform.python_version(),'platform':platform.platform()},
                'config_file':config_path.relative_to(BASE).as_posix(),'config_sha256':sha256(config_path),
                'code_sha256':{p.relative_to(BASE).as_posix():sha256(p) for p in sorted([
                    *(BASE/'code/src').rglob('*.py'),*(BASE/'code/scripts').glob('*.py'),*(BASE/'code/tests').rglob('*.py')])}}
    write_json(out/'run_manifest.json',manifest)
    try:
        summary, inputs = build(BASE,processed,out,config)
        verify_raw()
        write_report(BASE,summary)
        outputs = [*processed.glob('*'),out/'candidate_cohort_summary_v2.0.json',
                   BASE/'docs/notes/v2.0/candidate_cohort_report_v2.0.md']
        manifest.update(status='completed',finished_utc=datetime.now(timezone.utc).isoformat(),summary=summary,
                        input_sha256=inputs,raw_source_files_rechecked=len(inventory),
                        output_sha256={p.relative_to(BASE).as_posix():sha256(p) for p in outputs if p.is_file()})
        write_json(out/'run_manifest.json',manifest)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0
    except Exception as error:
        manifest.update(status='failed',error=str(error),finished_utc=datetime.now(timezone.utc).isoformat())
        write_json(out/'run_manifest.json',manifest)
        raise
