"""Screen candidate decisions by NGS timing and evidence availability."""
import json
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .audit import write_csv, write_json, write_jsonl
from .decision_points import build_events, partition_time, scope_at, uid
from .layout import resolve_paths
from .source import sha256

BASE = Path(__file__).resolve().parents[4]
MAIN_TIERS = {'metastatic_candidate_requires_information_review',
              'locally_advanced_candidate_requires_context_review'}
NON_SCREENING_CLINICAL_ISSUES = {'ECOG_not_provided', 'organ_function_labs_not_provided',
                  'toxicity_and_dose_reduction_reasons_not_provided', 'clinical_eligibility_not_finalized'}
PROGRESS = 'Progressing/Worsening/Enlarging'
RESET = {'Stable/No change', 'Improving/Responding', 'Mixed'}


def ngs_gate(events, cancer_seq, t0):
    """An aligned, unambiguous report must be strictly before t0, never same-day."""
    relevant = [e for e in events if e['kind'] == 'ngs_report' and cancer_seq is not None
                and e['cancer_seq'] == cancer_seq]
    valid = [e for e in relevant if e['cancer_attribution'] == 'direct_cancer_key'
             and e['facts'].get('report_anchor_agrees') is True and e['available_day'] is not None]
    before = [e['event_id'] for e in valid if t0 is not None and e['available_day'] < t0]
    if before:
        return 'confirmed_before', sorted(before)
    if t0 is None:
        return 'decision_time_unknown', []
    if any(e['available_day'] == t0 for e in valid):
        return 'same_day_order_unknown', []
    if any(e['available_day'] > t0 for e in valid):
        return 'only_later_confirmed_reports', []
    return 'report_date_or_cancer_link_unconfirmed', []


def assessment(event):
    f = event['facts']
    if event['kind'] == 'imaging':
        return f.get('image_overall', ''), f.get('image_ca', '').startswith('Yes,')
    if event['kind'] == 'oncology_assessment':
        return f.get('md_ca_status', ''), (f.get('md_type_ca_cur') == 'Pancreatic Cancer'
                and f.get('md_ca', '').startswith('Yes,'))
    return '', False


def final_progression_groups(events, starts, chronology_incomplete=False):
    """Group terminal-course progression records, retaining every evidence row.

    Groups are for adjudication, not confirmed independent decision episodes.
    A non-progressing assessment between progression dates opens a new group.
    Unknown assessments do not split a group. No arbitrary time window is used.
    """
    by_day, ledger = defaultdict(list), []
    for e in events:
        if e['kind'] in {'imaging', 'oncology_assessment'}:
            by_day[e['event_day']].append(e)
    groups, active, reset_pending = [], None, False
    for day in sorted(by_day, key=lambda x: (x is None, x or 0)):
        daily = by_day[day]
        qualifying = []
        reset_today = any(assessment(e)[0] in RESET for e in daily)
        for e in daily:
            status, cancer_present = assessment(e)
            if status != PROGRESS:
                continue
            if not cancer_present:
                relation = 'progression_cancer_evidence_conflict'
            elif day is None:
                relation = 'progression_date_unknown'
            elif any(s > day for s in starts):
                relation = 'later_treatment_start_recorded'
            elif day in starts:
                relation = 'same_day_treatment_order_unknown'
            else:
                relation = 'no_later_treatment_start_recorded'
            item = {'event_id': e['event_id'], 'event_day': day, 'kind': e['kind'],
                    'source_record_id': e['source_record_id'], 'source': e['source'],
                    'facts_raw': e['facts'], 'later_start_relation': relation,
                    'treatment_chronology_incomplete': chronology_incomplete,
                    'candidate_id': None}
            ledger.append(item)
            if relation in {'no_later_treatment_start_recorded', 'same_day_treatment_order_unknown'}:
                qualifying.append(item)
        if qualifying:
            if active is None or reset_pending:
                active = {'t0_day': day, 'evidence': [], 'intervening_nonprogression_assessment': reset_pending,
                          'same_day_assessment_conflict': False}
                groups.append(active)
            active['evidence'].extend(qualifying)
            active['same_day_assessment_conflict'] |= reset_today
            reset_pending = False
        elif reset_today and active is not None:
            reset_pending = True
    return groups, ledger


def progression_candidates(by_patient, cancers, cancer_days, treatment_candidates):
    cancer_keys, treatments = defaultdict(list), defaultdict(list)
    for ck, cancer in cancers.items():
        if cancer['is_index']:
            cancer_keys[ck[:2]].append(ck)
    for c in treatment_candidates:
        treatments[(*c['patient_key'], c['cancer_seq'])].append(c)
    results, all_evidence = [], []
    for pk, events in sorted(by_patient.items()):
        keys = cancer_keys.get(pk, [])
        ck = keys[0] if len(keys) == 1 else None
        seq = ck[2] if ck else None
        actions = treatments.get(ck, []) if ck else [c for key in keys for c in treatments[key]]
        starts = sorted({c['t0_day'] for c in actions if c['t0_day'] is not None})
        incomplete = any(c['t0_day'] is None or 'component_start_day_missing' in c['information_issues'] for c in actions)
        groups, ledger = final_progression_groups(events, starts, incomplete)
        for item in ledger:
            item.update(patient_key=list(pk), cancer_seq=seq,
                        cancer_attribution='single_index_cancer_context_inferred' if ck else 'ambiguous_index_cancer',
                        possible_index_cancer_seqs=[key[2] for key in keys])
        for group in groups:
            t0 = group['t0_day']
            evidence = group['evidence']
            identity = uid('terminal_progression_review', pk, seq, t0)
            for item in evidence:
                item['candidate_id'] = identity
            types = sorted({e['facts']['cpt_oncotree_code'] for e in events
                            if e['kind'] == 'ngs_report' and e['cancer_seq'] == seq})
            scope = scope_at(cancers[ck], cancer_days[ck], t0) if ck else 'cancer_attribution_unresolved'
            if types and 'PAAD' not in types:
                tier = 'outside_main_task_non_PAAD_cohort'
            elif scope in {'metastatic_at_diagnosis', 'metastatic_after_diagnosis'}:
                tier = 'metastatic_candidate_requires_information_review'
            elif scope.startswith('baseline_unresectable'):
                tier = 'locally_advanced_candidate_requires_context_review'
            else:
                tier = 'advanced_context_not_established'
            issues = ['progression_event_date_is_not_confirmed_decision_date',
                      'progression_report_availability_unconfirmed',
                      'progression_group_is_not_confirmed_independent_decision',
                      'no_later_start_does_not_mean_treatment_stopped',
                      'pathology_main_report_availability_unconfirmed']
            if ck is None:
                issues.append('multiple_index_cancers_progression_attribution_unconfirmed')
            if any(key[:2] == pk and not cancer['is_index'] for key, cancer in cancers.items()):
                issues.append('other_cancers_imaging_attribution_requires_review')
            if incomplete:
                issues.append('treatment_start_chronology_incomplete')
            if not any(s < t0 for s in starts):
                issues.append('no_confirmed_prior_treatment_start')
            if any(i['later_start_relation'] == 'same_day_treatment_order_unknown' for i in evidence):
                issues.append('same_day_treatment_and_progression_order_unknown')
            if group['same_day_assessment_conflict']:
                issues.append('same_day_progression_and_nonprogression_assessments')
            if group['intervening_nonprogression_assessment']:
                issues.append('new_group_after_nonprogression_requires_episode_review')
            if scope == 'metastatic_after_diagnosis':
                issues.append('derived_metastasis_onset_requires_source_adjudication')
            before_path = [e['event_id'] for e in events if e['kind'] == 'pathology_procedure'
                           and e['event_day'] is not None and e['event_day'] < t0
                           and any(s['cancer_type'] == 'Pancreatic Cancer' and s['invasive'] == 'Yes'
                                   and s['invasive_histology'] == '8500 Ductal adenocarcinoma'
                                   for s in e['facts']['specimens'])]
            if not before_path:
                issues.append('no_explicit_ductal_pathology_before_procedure_cutoff')
            results.append({'candidate_id': identity, 'patient_key': list(pk), 'cancer_seq': seq,
                            't0_day': t0, 't0_semantics': 'earliest_progression_event_in_review_group_not_actual_decision',
                            'anchor_kind': 'progression_without_later_recorded_start',
                            'source_record_id': evidence[0]['source_record_id'], 'source': evidence[0]['source'],
                            'progression_evidence_event_ids': [i['event_id'] for i in evidence],
                            'progression_group_last_event_day': max(i['event_day'] for i in evidence),
                            'scope_at_t0': scope, 'review_tier': tier,
                            'cohort_oncotree_hindsight': types, 'cohort_oncotree_is_t0_feature': False,
                            'explicit_ductal_pathology_procedure_before': before_path,
                            'observed_action_drugs': [], 'regimen_components_full_course': [],
                            'information_issues': issues, 'observed_action_is_input_feature': False,
                            'final_training_eligibility': 'not_finalized', 'expert_label': None})
        all_evidence.extend(ledger)
    return results, all_evidence


def assign_screening_group(c, events):
    c = dict(c)
    status, before = ngs_gate(events, c['cancer_seq'], c['t0_day'])
    c['ngs_report_before'] = before
    c['screening_ngs_status'] = status
    c['information_issues'] = [i for i in c['information_issues'] if i not in NON_SCREENING_CLINICAL_ISSUES]
    if c['review_tier'].startswith('outside_main_task_'):
        bucket = 'outside_main_scope_retained'
    elif c['review_tier'] not in MAIN_TIERS:
        bucket = 'disease_context_review'
    elif not before:
        bucket = 'ngs_timing_review'
    elif c['anchor_kind'] == 'within_regimen_drug_start':
        bucket = 'within_regimen_change_review'
        c['information_issues'].append('independent_strategy_change_unconfirmed')
    elif c['anchor_kind'] == 'progression_without_later_recorded_start':
        bucket = 'progression_trigger_review'
    else:
        bucket = 'main_regimen_start_candidate'
    c['screening_bucket'] = bucket
    c['independent_decision_confirmed'] = False
    c['final_training_eligibility'] = 'not_finalized'
    c['expert_label'] = None
    return c


def make_outcome_reference(c, events, tables_by_patient):
    """Trace-only outcomes have their own artifact and never determine labels."""
    records = tables_by_patient[tuple(c['patient_key'])]
    endpoints = []
    for table in ['patient_level_dataset', 'cancer_level_dataset_index', 'regimen_cancer_level_dataset']:
        for r in records.get(table, []):
            f = r['fields']
            if table != 'patient_level_dataset' and f['ca_seq'] != c['cancer_seq']:
                continue
            if table == 'regimen_cancer_level_dataset' and r['record_id'] != c['source_record_id']:
                continue
            fields = {k: v for k, v in f.items() if k.startswith(('os_', 'pfs_', 'tt_', 'ttnt_', 'last_', 'dob_last', 'hybrid_death', 'enroll_hospice', 'age_death', 'age_last'))}
            endpoints.append({'table': table, 'source_record_id': r['record_id'], 'source': r['source'], 'fields_raw': fields})
    return {'candidate_id': c['candidate_id'], 'patient_key': c['patient_key'],
            'purpose': 'followup_reference_only_not_input_or_label',
            'endpoint_origin': 'retain_each_source_definition_do_not_treat_all_as_time_from_this_decision',
            'later_assessment_event_ids': [e['event_id'] for e in events if e['kind'] in {'imaging', 'oncology_assessment'}
                                           and c['t0_day'] is not None and e['event_day'] is not None and e['event_day'] > c['t0_day']],
            'same_day_assessment_event_ids': [e['event_id'] for e in events if e['kind'] in {'imaging', 'oncology_assessment'}
                                              and c['t0_day'] is not None and e['event_day'] == c['t0_day']],
            'source_endpoints': endpoints, 'outcomes_define_treatment_label': False}


def build(base, processed, out, config):
    if config['ngs_timing_rule'] != 'report_strictly_before_t0':
        raise ValueError('Unsupported NGS timing rule')
    source = json.loads((base/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    phase2 = json.loads((base/'code/config/v2.0/decision_points.json').read_text(encoding='utf-8'))
    candidate_path = base/phase2['processed_dir']/'candidate_decision_points_v2.0.jsonl'
    event_path = base/phase2['processed_dir']/'timeline_events_v2.0.jsonl'
    phase2_manifest_path = base/phase2['results_dir']/'run_manifest.json'
    phase2_manifest = json.loads(phase2_manifest_path.read_text(encoding='utf-8'))
    if phase2_manifest['status'] != 'completed':
        raise ValueError('Phase 02 must complete before 候选筛选 screening')
    inputs = {str(p.relative_to(base).as_posix()): sha256(p) for p in [candidate_path, event_path, phase2_manifest_path]}
    for p in [candidate_path, event_path]:
        if inputs[p.relative_to(base).as_posix()] != phase2_manifest['output_sha256'][p.relative_to(base).as_posix()]:
            raise ValueError('Phase 02 input changed: ' + p.name)
    candidates = [json.loads(line) for line in candidate_path.open(encoding='utf-8')]
    tables, tables_by_patient = {}, defaultdict(lambda: defaultdict(list))
    for p in sorted((base/source['processed_dir']/'clinical_records').glob('*.jsonl')):
        inputs[p.relative_to(base).as_posix()] = sha256(p)
        if inputs[p.relative_to(base).as_posix()] != phase2_manifest['input_sha256'][p.relative_to(base).as_posix()]:
            raise ValueError('Clinical records changed after Phase 02')
        tables[p.stem] = [json.loads(line) for line in p.open(encoding='utf-8')]
        for r in tables[p.stem]:
            tables_by_patient[(r['fields']['cohort'], r['fields']['record_id'])][p.stem].append(r)
    _, by_patient, cancers, cancer_days = build_events(tables)
    # Rebuilding events must reproduce the upstream source records exactly.
    rebuilt = {e['event_id']: e for events in by_patient.values() for e in events}
    upstream = {e['event_id']: e for e in (json.loads(line) for line in event_path.open(encoding='utf-8'))}
    if rebuilt != upstream:
        raise ValueError('Rebuilt timeline differs from the upstream artifact')
    added, evidence = progression_candidates(by_patient, cancers, cancer_days, candidates)
    registry = [assign_screening_group(c, by_patient[tuple(c['patient_key'])]) for c in candidates + added]
    for c in registry:
        c['outcome_reference_id'] = c['candidate_id']
    if len({c['candidate_id'] for c in registry}) != len(registry):
        raise ValueError('Duplicate 候选筛选 candidate identity')
    for c in registry:
        for ident in c['ngs_report_before']:
            if not (rebuilt[ident]['available_day'] < c['t0_day'] and rebuilt[ident]['cancer_seq'] == c['cancer_seq']):
                raise ValueError('NGS timing or attribution leakage')
    outcomes = [make_outcome_reference(c, by_patient[tuple(c['patient_key'])], tables_by_patient) for c in registry]
    processed.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(processed/'screening_candidate_registry_v2.0.jsonl', registry)
    write_jsonl(processed/'progression_evidence_v2.0.jsonl', evidence)
    write_jsonl(processed/'candidate_outcome_references_v2.0.jsonl', outcomes)
    flat = [{'candidate_id': c['candidate_id'], 'patient_id': c['patient_key'][1], 'cohort': c['patient_key'][0],
             'cancer_seq': c['cancer_seq'], 't0_day': c['t0_day'], 'anchor_kind': c['anchor_kind'],
             'screening_bucket': c['screening_bucket'], 'ngs_timing_status': c['screening_ngs_status'],
             'ngs_before_count': len(c['ngs_report_before']), 'scope_review_tier': c['review_tier'],
             'observed_drugs_raw': ' | '.join(x['name_raw'] for x in c['observed_action_drugs']),
             'progression_evidence_count': len(c.get('progression_evidence_event_ids', [])),
             'information_issues': ' | '.join(c['information_issues']), 'independent_decision_confirmed': False,
             'final_training_eligibility': 'not_finalized', 'source_file': c['source']['file'],
             'source_logical_row': c['source']['logical_row']} for c in registry]
    for name, selected in [('screening_candidate_registry', flat),
                           ('screening_main_candidates', [r for r in flat if r['screening_bucket'] == 'main_regimen_start_candidate']),
                           ('screening_review_candidates', [r for r in flat if r['screening_bucket'] != 'main_regimen_start_candidate'])]:
        write_csv(processed/(name + '_v2.0.csv'), list(flat[0]), selected)
    buckets = {key: {'candidates': len(group), 'patients': len({tuple(c['patient_key']) for c in group})}
               for key in sorted({c['screening_bucket'] for c in registry})
               for group in [[c for c in registry if c['screening_bucket'] == key]]}
    summary = {'project_version': 'v2.0', 'phase': '03_screening_candidates', 
               'ngs_rule': config['ngs_timing_rule'], 'upstream_treatment_anchors': len(candidates),
               'progression_evidence_records': len(evidence), 'new_progression_review_groups': len(added),
               'progression_evidence_relations': dict(Counter(e['later_start_relation'] for e in evidence)),
               'registry_records': len(registry), 'registry_patients': len({tuple(c['patient_key']) for c in registry}),
               'buckets': buckets, 'ngs_timing_statuses': dict(Counter(c['screening_ngs_status'] for c in registry)),
               'progression_groups_by_bucket': dict(Counter(c['screening_bucket'] for c in registry if c['anchor_kind'].startswith('progression_'))),
               'final_eligible_decision_points': None, 'expert_labels': None,
               'regimen_independence_adjudicated': False, 'progression_decision_dates_adjudicated': False,
               'counts_are_review_records_not_final_decisions': True}
    write_json(out/'screening_summary_v2.0.json', summary)
    return summary, inputs


def write_report(base, summary):
    s = summary
    labels = {'main_regimen_start_candidate': '方案起始主候选：方案起始，NGS明确在先',
              'within_regimen_change_review': 'NGS在先，但方案内药物开始是否为独立调整待核',
              'progression_trigger_review': 'NGS在先、初步符合范围的进展候选组，决策日待核',
              'ngs_timing_review': '初步符合研究范围，但NGS未确认在先',
              'disease_context_review': '当前疾病情境或归属待核',
              'outside_main_scope_retained': '其他癌症或非PAAD队列亚型，保留追溯'}
    rows = '\n'.join(f"| {labels[key]} | {value['candidates']:,} | {value['patients']:,} |" for key, value in s['buckets'].items())
    text = f'''# 候选点筛选报告 v2.0

版本：v2.0

更新日期：{datetime.now(timezone.utc).strftime('%Y%m%d')}

状态：NGS严格在先的候选分层与进展证据归组完成；独立决策、疾病情境和最终训练资格待核查。

## 目的与规则

NGS报告必须明确早于决策锚点；同日不自动视为在先，报告日期与癌症关联需确认。病理、分期、当前疾病情境与既往治疗仍需核查。完整规则见[候选点协议](decision_point_protocol_v2.0.md)，配置见[候选筛选配置](../../../code/config/v2.0/screening.json)。

## 方法与来源

使用第一阶段完整临床原值和第二阶段候选、时间轴，重建事件并逐条比较一致性。已有方案内后加药仅进入调整待核查集合，不冒充独立治疗决策。方案开始仍是候选锚点，维持、重启、换线与单纯给药间隔的最终判定尚未完成。

进展证据依据变量字典Variable Synopsis第466—467行、820—822行：仅Progressing/Worsening/Enlarging且癌症证据为Yes的记录用于产生候选。影像没有ca_seq；内科评估有癌种但没有唯一癌症键，按单一目标癌症进行候选关联，多癌症与影像归属保留疑点。Mixed、标志物升高、PFS事件标记和死亡不单独定义进展。

若同癌症存在更晚的方案或药物开始记录，该进展保留为历史证据，不新增“无后续开始”的候选。同日治疗与进展保留顺序未知；开始日期缺失单独标记。没有后续开始记录不等于治疗已经停止，也不等于没有继续原方案。

最后一段未见新治疗开始的观察期间，连续进展记录归为待核查组；中间出现稳定、改善或Mixed的评估后再次进展，另开待核查组。未知评估不切组；同日相反评估标记冲突。分组使用最早进展事件日，不因后续NGS到达而把时点向后移。分组不代表临床上已确认独立的进展或治疗决策；检查日期也不等于报告可用日或实际决策日。

## 当前数量

原治疗锚点{s['upstream_treatment_anchors']:,}个。审查{s['progression_evidence_records']:,}条明确写有进展的原始评估，新增{s['new_progression_review_groups']:,}个进展待核查组。登记总计{s['registry_records']:,}条，涉及{s['registry_patients']:,}名患者。

| 集合（均非最终训练资格） | 候选记录／组 | 患者 |
| --- | ---: | ---: |
{rows}

各集合按候选记录互斥，同一患者可以出现在多个集合，患者数不能相加。进展候选组与方案开始锚点的性质不同，不能把登记总数当作独立决策点总数。

## 输出与结局使用

[主候选表](../../../data/processed/v2.0/03_screening_candidates/screening_main_candidates_v2.0.csv)只包含初步符合研究范围、NGS严格在先的方案起始候选。[其余待核查和追溯表](../../../data/processed/v2.0/03_screening_candidates/screening_review_candidates_v2.0.csv)保留方案内调整、进展组、NGS和疾病情境疑点及范围外记录。

[完整候选登记](../../../data/processed/v2.0/03_screening_candidates/screening_candidate_registry_v2.0.jsonl)保留来源和病理索引；[进展证据明细](../../../data/processed/v2.0/03_screening_candidates/progression_evidence_v2.0.jsonl)保留全部原评估、来源行、是否有后续开始及候选组编号。

[结局参考文件](../../../data/processed/v2.0/03_screening_candidates/candidate_outcome_references_v2.0.jsonl)单独保存后续评估索引及患者、癌症、该方案的原始终点字段。不同终点的时间原点和事件定义保持原义，不自动换算为当前候选的疗效、PFS或OS，不因无后续治疗记录补造停药或死亡。结局用于案例回顾，不进入事前模型输入或专家候选标签判断。原始病理327个字段和全部标本仍保留于第一阶段，未删除。

## 复现与边界

运行 `python -B code/scripts/run_v2_0.py all` 重建五个阶段并检查；前两阶段已完成时可运行 `python -B code/scripts/run_v2_0.py candidates`。统计见[机器汇总](../../../code/results/v2.0/03_screening_candidates/screening_summary_v2.0.json)，来源见[运行清单](../../../code/results/v2.0/03_screening_candidates/run_manifest.json)。

NGS在先只是必要条件，不证明病理、疾病情境、方案独立性或患者安全性均已确认。主候选和进展候选均未形成专家标签；最终训练／测试资格仍为not_finalized。下一步核查组织学、当前局部晚期／转移性证据及调整和进展组的决策含义。
'''
    (base/'docs/notes/v2.0/screening_candidate_report_v2.0.md').write_text(text, encoding='utf-8')


def run(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    source = json.loads((BASE/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    raw, processed, out = resolve_paths(BASE, {**source, **config})
    inventory = json.loads((BASE/source['results_dir']/'source_inventory.json').read_text(encoding='utf-8'))
    for item in inventory:
        if sha256(raw/item['file']) != item['sha256']:
            raise ValueError('Raw source changed before 候选筛选 screening')
    out.mkdir(parents=True, exist_ok=True)
    manifest = {'project_version': 'v2.0', 'phase': '03_screening_candidates', 'status': 'running',
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'runtime': {'python': platform.python_version(), 'platform': platform.platform()},
                'config_file': config_path.relative_to(BASE).as_posix(), 'config_sha256': sha256(config_path),
                'code_sha256': {p.relative_to(BASE).as_posix(): sha256(p) for p in sorted([*(BASE/'code/src').rglob('*.py'), *(BASE/'code/scripts').glob('*.py'), *(BASE/'code/tests').rglob('*.py')])}}
    write_json(out/'run_manifest.json', manifest)
    try:
        summary, inputs = build(BASE, processed, out, config)
        for item in inventory:
            if sha256(raw/item['file']) != item['sha256']:
                raise ValueError('Raw source changed during 候选筛选 screening')
        manifest.update(status='completed', finished_utc=datetime.now(timezone.utc).isoformat(), summary=summary,
                        input_sha256=inputs, raw_source_files_rechecked=len(inventory),
                        output_sha256={p.relative_to(BASE).as_posix(): sha256(p) for p in sorted(processed.glob('*')) if p.is_file()})
        write_json(out/'run_manifest.json', manifest)
        write_report(BASE, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        manifest.update(status='failed', error=str(error), finished_utc=datetime.now(timezone.utc).isoformat())
        write_json(out/'run_manifest.json', manifest)
        raise
