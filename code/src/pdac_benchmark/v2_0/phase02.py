"""Build full-cohort temporal records, candidate anchors, and a complete reading example."""
import json
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from .audit import write_json, write_jsonl, write_csv
from .case_view import render_case
from .decision_points import build_events, build_candidates, partition_time
from .layout import resolve_paths
from .molecular import load_molecular
from .source import read_csv, sha256
from .source_dictionary import read_synopsis

BASE = Path(__file__).resolve().parents[4]


def build(base, out, processed, config):
    source_config = json.loads((base/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    raw = base/source_config['source_root']
    phase01 = base/source_config['processed_dir']
    source_inventory = json.loads((base/source_config['results_dir']/'source_inventory.json').read_text(encoding='utf-8'))
    for item in source_inventory:
        if sha256(raw/item['file']) != item['sha256']:
            raise ValueError('Raw source changed since phase 01: ' + item['file'])
    tables, input_hashes = {}, {}
    for path in sorted((phase01/'clinical_records').glob('*.jsonl')):
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        _, original = read_csv(raw/'clinical_data'/(path.stem + '.csv'))
        if [r['fields'] for r in rows] != original:
            raise ValueError('Phase 01 records no longer match raw CSV: ' + path.name)
        tables[path.stem] = rows
        input_hashes[path.relative_to(base).as_posix()] = sha256(path)
    if len(tables) != 10:
        raise ValueError('Expected ten complete clinical tables')
    events, by_patient, cancers, cancer_days = build_events(tables)
    candidates = build_candidates(tables, by_patient, cancers, cancer_days)
    dictionary = read_synopsis(next((raw/'Documentation').glob('*.xlsx')))
    molecular, panels, molecular_counts, molecular_issues = load_molecular(raw)
    # Every clinical NGS sample is checked against its public molecular patient identifier.
    for row in tables['cancer_panel_test_level_dataset']:
        f = row['fields']
        sample = molecular.get(f['cpt_genie_sample_id'])
        if sample is None or sample['patient_id'] != f['record_id']:
            molecular_issues.append({'kind': 'clinical_molecular_sample_mismatch', 'record_id': row['record_id']})
    all_event_ids = {e['event_id'] for e in events}
    if len(all_event_ids) != len(events) or len({c['candidate_id'] for c in candidates}) != len(candidates):
        raise ValueError('Duplicate event or candidate ID')
    for c in candidates:
        assigned = [event_id for ids in c['temporal_partition'].values() for event_id in ids]
        expected = {e['event_id'] for e in by_patient[tuple(c['patient_key'])]}
        if len(assigned) != len(set(assigned)) or set(assigned) != expected:
            raise ValueError('Temporal partition drops or duplicates evidence')
    out.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    write_jsonl(processed/'timeline_events_v2.0.jsonl', events)
    write_jsonl(processed/'candidate_decision_points_v2.0.jsonl', candidates)
    write_jsonl(processed/'molecular_samples_v2.0.jsonl', molecular.values())
    write_json(processed/'gene_panels_v2.0.json', panels)
    write_json(processed/'variable_dictionary_v2.0.json', dictionary)
    flat = []
    for c in candidates:
        flat.append({'candidate_id': c['candidate_id'], 'patient_id': c['patient_key'][1], 'cohort': c['patient_key'][0], 'cancer_seq': c['cancer_seq'],
                     't0_day_first_index': c['t0_day'], 'anchor_kind': c['anchor_kind'], 'scope_at_t0': c['scope_at_t0'], 'review_tier': c['review_tier'],
                     'observed_action_drugs_raw': ' | '.join(d['name_raw'] for d in c['observed_action_drugs']),
                     'cohort_oncotree_hindsight_not_t0_feature': ' | '.join(c['cohort_oncotree_hindsight']),
                     'ngs_report_before_count': len(c['ngs_report_before']), 'explicit_ductal_pathology_procedure_before_count': len(c['explicit_ductal_pathology_procedure_before']),
                     **{name + '_count': len(ids) for name, ids in c['temporal_partition'].items()},
                     'information_issues': ' | '.join(c['information_issues']), 'training_test_eligibility': c['final_training_eligibility'],
                     'source_file': c['source']['file'], 'source_logical_row': c['source']['logical_row']})
    write_csv(processed/'candidate_decision_points_v2.0.csv', list(flat[0]), flat)
    # This is a record of observed regimens, not an evidence-backed candidate universe.
    observed = Counter(tuple(sorted(f for k, f in r['fields'].items() if k.startswith('drugs_drug_') and f)) for r in tables['regimen_cancer_level_dataset'])
    catalog = [{'observed_drugs_raw': ' | '.join(drugs), 'source_regimen_records': count,
                'contains_masked_drug': any('investigational' in d.lower() for d in drugs),
                'historical_evidence_status': 'not_searched', 'current_evidence_status': 'not_searched', 'clinical_label': 'not_defined'} for drugs, count in sorted(observed.items())]
    write_csv(processed/'observed_regimen_catalog_v2.0.csv', list(catalog[0]), catalog)
    scope_counts = dict(Counter(c['scope_at_t0'] for c in candidates))
    tier_counts = dict(Counter(c['review_tier'] for c in candidates))
    issues = Counter(x for c in candidates for x in c['information_issues'])
    # Prefer a traceable, rich example, not an unusually high mutation count or outcome.
    pool = [c for c in candidates if c['review_tier'] == 'metastatic_candidate_requires_information_review' and c['ngs_report_before'] and c['explicit_ductal_pathology_procedure_before']]
    if not pool:
        pool = [c for c in candidates if c['review_tier'] == 'metastatic_candidate_requires_information_review']
    def score(c):
        rows = by_patient[tuple(c['patient_key'])]
        markers = sum(e['kind'] in {'msi_report', 'mmr_report'} and partition_time(e, c['t0_day']) == 'confirmed_before' for e in rows)
        specimens = sum(len(e['facts']['specimens']) for e in rows if e['kind'] == 'pathology_procedure')
        return (min(markers, 2), 2 <= sum(e['kind'] == 'pathology_procedure' for e in rows) <= 8, min(specimens, 15), c['anchor_kind'] == 'regimen_start', c['candidate_id'])
    chosen = max(pool, key=score)
    pk = tuple(chosen['patient_key'])
    case = {'project_version': 'v2.0', 'purpose': 'complete_source_supported_case_demonstration_not_pilot_or_gold_label',
            'selection': 'deterministic_rich_pathology_and_predecision_ngs_example_not_representative_sampling',
            'research_scope': config['research_scope'], 'decision': chosen, 'events': by_patient[pk],
            'clinical_records': {name: [r for r in rows if (r['fields']['cohort'], r['fields']['record_id']) == pk] for name, rows in tables.items()},
            'molecular_samples': [s for s in molecular.values() if s['patient_id'] == pk[1]],
            'data_absence': ['ECOG', 'routine_liver_and_renal_function', 'complete_toxicity_history', 'pathology_main_report_issue_date']}
    write_json(processed/'complete_case_v2.0.json', case)
    render_case(case, out/'complete_case_v2.0.html', {r['field']: r for r in dictionary})
    clinical_case_rows = sum(len(rows) for rows in case['clinical_records'].values())
    summary = {'project_version': 'v2.0', 'phase': '02_decision_points', 'patients': len(tables['patient_level_dataset']),
               'clinical_records_rechecked': sum(len(rows) for rows in tables.values()), 'timeline_events': len(events),
               'regimen_records': len(tables['regimen_cancer_level_dataset']), 'candidate_anchors': len(candidates),
               'anchor_kinds': dict(Counter(c['anchor_kind'] for c in candidates)), 'scope_counts': scope_counts, 'review_tiers': tier_counts,
               'information_issue_counts': dict(issues), 'molecular': molecular_counts, 'molecular_link_issue_count': len(molecular_issues),
               'dictionary_entries': len(dictionary), 'observed_regimen_combinations': len(catalog),
               'example': {'patient_id': pk[1], 'candidate_id': chosen['candidate_id'], 't0_day': chosen['t0_day'], 'clinical_records': clinical_case_rows,
                           'pathology_reports': len(case['clinical_records']['pathology_report_level_dataset']),
                           'specimens': sum(len(e['facts']['specimens']) for e in case['events'] if e['kind'] == 'pathology_procedure')},
               'final_eligible_decision_points': None, 'expert_labels': None, 'guideline_evidence_review_completed': False}
    write_json(out/'decision_point_summary_v2.0.json', summary)
    write_json(out/'molecular_link_issues_v2.0.json', molecular_issues)
    return summary, input_hashes, source_inventory


def write_report(base, summary, config):
    notes = base/'docs/notes/v2.0'
    notes.mkdir(parents=True, exist_ok=True)
    s = summary
    labels = {'metastatic_candidate_requires_information_review': '转移性情境候选，资料仍需核查',
              'locally_advanced_candidate_requires_context_review': '局部晚期候选，当前情境仍需核查',
              'advanced_context_not_established': '尚未建立晚期治疗情境', 'outside_main_task_non_index': '非目标癌症，单独保留',
              'outside_main_task_non_PAAD_cohort': '非PAAD队列亚型，单独保留', 'time_unresolved': '日期关系待核查'}
    rows = '\n'.join(f'| {labels.get(key, key)} | {value:,} |' for key, value in s['review_tiers'].items())
    text = f'''# 候选决策点与时间轴审计报告 v2.0

版本：v2.0

更新日期：20260910

状态：完成候选锚点和资料分层初版；最终纳入与专家标签未确定。

## 目的与范围

围绕局部晚期／转移性PDAC系统治疗，重建全程记录并划分时点证据。用户确认以指定截止日期的知识重评为主，历史实际方案另行保留并要求同期和当前证据。文献截止日暂定2026-09-10，尚未完成检索或标签定义。

## 方法与来源

重新逐字段核对十张临床表，按首个目标癌症诊断日统一时间轴。整套方案开始及各药物不同开始日形成候选锚点；后加药可能只是多日给药安排，尚不能视为独立换线。药物结束日不直接生成停药决策。完整规则见[处理协议](decision_point_protocol_v2.0.md)，输入用途见[数据用途说明](source_usage_report_v2.0.md)。

## 结果

核对{s['clinical_records_rechecked']:,}条临床记录，生成{s['timeline_events']:,}个时间轴事件。{s['regimen_records']:,}条方案记录形成{s['candidate_anchors']:,}个候选锚点，其中整套方案开始{s['anchor_kinds'].get('regimen_start', 0):,}个，方案内其他药物开始{s['anchor_kinds'].get('within_regimen_drug_start', 0):,}个。

| 初步核查类别（不是最终纳入） | 锚点数 |
| --- | ---: |
{rows}

分子文件整理{s['molecular']['samples']:,}个样本、{s['molecular']['mutations']:,}条小变异、{s['molecular']['structural_variants']:,}条结构变异；保留拷贝数矩阵原值和{s['molecular']['panel_definitions']}个面板定义。关联问题{s['molecular_link_issue_count']}项。没有将变异自动标为致病、胚系或可用药靶点，也没有将未见记录当作阴性。

## 病例展示与追溯

[结构化病例示例](../../../code/results/v2.0/02_decision_points/complete_case_v2.0.html)包含{s['example']['clinical_records']}条临床原记录、{s['example']['pathology_reports']}份病理、{s['example']['specimens']}个标本及关联分子记录。原字段和空值均保留，未来信息与报告时间未知分别标记。本例用于核查阅读格式，不是pilot抽样或专家审核金标准。

[候选锚点表](../../../data/processed/v2.0/02_decision_points/candidate_decision_points_v2.0.csv)、[全量事件](../../../data/processed/v2.0/02_decision_points/timeline_events_v2.0.jsonl)、[运行清单](../../../code/results/v2.0/02_decision_points/run_manifest.json)保留来源和定位。[观察方案目录](../../../data/processed/v2.0/02_decision_points/observed_regimen_catalog_v2.0.csv)有{s['observed_regimen_combinations']}种原始组合，仅表示观察记录，指南和论文证据仍为未检索。

## 局限与下一步

ECOG、常规肝肾功能、完整毒性和减量原因未在十张临床表中提供。病理主报告签发时间未提供；影像、医生评估和标志物的事件日期不自动等于结果可用日期。同日先后未知。初始可切除性不能无条件代表后续状态，PAAD测序编码也不等于早期已经确认导管腺癌。

下一步逐项核查局部晚期情境、组织学冲突、方案调整含义和信息充分性，明确哪些标签必须带适用条件，再开展国内外指南和论文证据整理。全部候选的最终训练／测试资格仍为not_finalized，不发布未经支持的可用决策点总数。
'''
    (notes/'decision_point_audit_report_v2.0.md').write_text(text, encoding='utf-8')


def run(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    source = json.loads((BASE/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    _, processed, out = resolve_paths(BASE, {**source, 'processed_dir': config['processed_dir'], 'results_dir': config['results_dir']})
    out.mkdir(parents=True, exist_ok=True)
    manifest = {'project_version': 'v2.0', 'phase': '02_decision_points', 'status': 'running', 'started_utc': datetime.now(timezone.utc).isoformat(),
                'runtime': {'python': platform.python_version(), 'platform': platform.platform()}, 'config_file': config_path.relative_to(BASE).as_posix(),
                'config_sha256': sha256(config_path), 'source_config_sha256': sha256(BASE/'code/config/v2.0/source.json'),
                'code_sha256': {p.relative_to(BASE).as_posix(): sha256(p) for p in sorted([*(BASE/'code/src').rglob('*.py'), *(BASE/'code/scripts').glob('*.py')])}}
    write_json(out/'run_manifest.json', manifest)
    try:
        summary, input_hashes, source_inventory = build(BASE, out, processed, config)
        raw = BASE/source['source_root']
        if any(sha256(raw/i['file']) != i['sha256'] for i in source_inventory):
            raise ValueError('Raw source changed during phase 02')
        manifest.update(status='completed_with_issues' if summary['molecular_link_issue_count'] else 'completed',
                        finished_utc=datetime.now(timezone.utc).isoformat(), input_sha256=input_hashes, summary=summary,
                        output_sha256={p.relative_to(BASE).as_posix(): sha256(p) for p in sorted(processed.glob('*')) if p.is_file()})
        write_json(out/'run_manifest.json', manifest)
        write_report(BASE, summary, config)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        manifest.update(status='failed', error=str(error), finished_utc=datetime.now(timezone.utc).isoformat())
        write_json(out/'run_manifest.json', manifest)
        raise
