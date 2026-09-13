"""Classify histology uncertainty, treatment independence and same-day progression links."""
import json
import platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .audit import write_json, write_jsonl, write_csv
from .layout import resolve_paths
from .review_inventory import evidence_inventory, stats
from .source import sha256, read_csv

BASE = Path(__file__).resolve().parents[4]
UNCERTAIN_PATTERNS = {'same_full_course_drug_set', 'fewer_full_course_drugs_subset'}


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


def same_day_links(registry):
    starts = defaultdict(list)
    for c in registry:
        if c['anchor_kind'] in {'regimen_start', 'within_regimen_drug_start'} and c['t0_day'] is not None:
            starts[(*c['patient_key'], c['cancer_seq'], c['t0_day'])].append(c['candidate_id'])
    links = {}
    for c in registry:
        if c['screening_bucket'] == 'progression_trigger_review' and 'same_day_treatment_and_progression_order_unknown' in c['information_issues']:
            targets = sorted(starts.get((*c['patient_key'], c['cancer_seq'], c['t0_day']), []))
            if not targets:
                raise ValueError('Same-day progression flag has no matching treatment anchor: ' + c['candidate_id'])
            links[c['candidate_id']] = targets
    return links


def refine_candidate(original, inventory, targets):
    c = dict(original)
    c['upstream_screening_bucket'] = original['screening_bucket']
    review = {'rule_version': 'v2.0_20260911', 'expert_review_completed': False,
              'intrinsic_clinical_missingness_is_exclusion': False,
              'independent_decision_confirmed': False,
              'pathology_report_available_before_t0': 'unconfirmed',
              'nos_paad_retention_rule_applies': False,
              'strategy_intent': 'unknown_not_imputed', 'changes': [],
              'same_day_treatment_candidate_ids': targets,
              'same_day_progression_order': 'unknown' if targets else 'not_applicable',
              'progression_is_treatment_predecision_input': False}
    if inventory is not None:
        review['evidence_inventory_id'] = original['candidate_id']
        review['histology_category_from_procedure_before'] = inventory['pathology_category']
        review['histologies_raw_before_procedure'] = inventory['histologies_raw_before_procedure']
        review['strategy_record_pattern'] = inventory['strategy_record_pattern']
        types = {r['oncotree'] for r in inventory['predecision_ngs_pathology_links']}
        if inventory['histologies_raw_before_procedure'] == ['8140 Adenocarcinoma NOS'] and types == {'PAAD'}:
            review['nos_paad_retention_rule_applies'] = True
            review['pathology_qualification'] = 'adenocarcinoma_NOS_and_predecision_PAAD_subtype_not_confirmed'
        else:
            review['pathology_qualification'] = 'retain_raw_evidence_no_new_histology_adjudication'
        if original['screening_bucket'] == 'main_regimen_start_candidate' and inventory['strategy_record_pattern'] in UNCERTAIN_PATTERNS:
            c['screening_bucket'] = 'regimen_independence_review'
            review['changes'].append('move_same_or_subset_record_to_independence_review_without_intent_evidence')
    if targets:
        c['screening_bucket'] = 'progression_linked_same_day_not_separate'
        review['changes'].append('link_same_day_progression_without_separate_decision_count')
    review['decision_counting_status'] = ('not_counted_separately_pending_order_review' if targets
                                          else 'candidate_only_not_final_independent_decision')
    c['candidate_review'] = review
    c['final_training_eligibility'] = 'not_finalized'
    c['expert_label'] = None
    return c


def build(base, processed, out, config):
    expected = {'ngs_rule': 'report_strictly_before_t0',
                'nos_and_predecision_paad': 'retain_candidate_with_pathology_limitations',
                'same_or_subset_drug_set_without_intent': 'independence_review_not_main',
                'same_day_progression': 'link_to_treatment_do_not_count_separately'}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('Configuration differs from implemented screening rules')
    input_dir = base/'data/processed/v2.0/03_screening_candidates'
    manifest_path = base/'code/results/v2.0/03_screening_candidates/run_manifest.json'
    parent_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if parent_manifest['status'] != 'completed':
        raise ValueError('screening candidate extraction has not completed')
    source_config = json.loads((base/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    inputs = {manifest_path.relative_to(base).as_posix(): sha256(manifest_path)}
    registry_path = input_dir/'screening_candidate_registry_v2.0.jsonl'
    inputs[registry_path.relative_to(base).as_posix()] = sha256(registry_path)
    if inputs[registry_path.relative_to(base).as_posix()] != parent_manifest['output_sha256'][registry_path.relative_to(base).as_posix()]:
        raise ValueError('Upstream candidate registry changed')
    registry = read_jsonl(registry_path)
    tables = {}
    for path in sorted((base/source_config['processed_dir']/'clinical_records').glob('*.jsonl')):
        rel = path.relative_to(base).as_posix()
        inputs[rel] = sha256(path)
        if inputs[rel] != parent_manifest['input_sha256'][rel]:
            raise ValueError('Source clinical records changed after screening extraction')
        tables[path.stem] = read_jsonl(path)
    inventory = evidence_inventory(registry, tables)
    by_id = {r['candidate_id']: r for r in inventory}
    # Independently expand original pathology CSV rather than trusting the event projection.
    _, raw_pathology = read_csv(base/source_config['source_root']/'clinical_data/pathology_report_level_dataset.csv')
    raw_by_patient = defaultdict(list)
    for r in raw_pathology:
        raw_by_patient[(r['cohort'], r['record_id'])].append(r)
    for r in inventory:
        observed = set()
        for p in raw_by_patient[tuple(r['patient_key'])]:
            day = p['dx_path_proc_days']
            if not day or float(day) >= r['t0_day']:
                continue
            for slot in range(1, 31):
                if p['path_ca'+str(slot)] == 'Yes' and p['path_ca_type'+str(slot)] == 'Pancreatic Cancer':
                    observed.add(p['path_ca_hist'+str(slot)])
        if sorted(observed) != r['histologies_raw_before_procedure']:
            raise ValueError('Pathology inventory disagrees with original CSV')
    links = same_day_links(registry)
    revised = [refine_candidate(c, by_id.get(c['candidate_id']), links.get(c['candidate_id'], [])) for c in registry]
    reverse = defaultdict(list)
    for progression_id, targets in links.items():
        for target in targets:
            reverse[target].append(progression_id)
    for c in revised:
        c['candidate_review']['linked_same_day_progression_candidate_ids'] = sorted(reverse[c['candidate_id']])
    if {c['candidate_id'] for c in revised} != {c['candidate_id'] for c in registry}:
        raise ValueError('Candidate identifiers were lost')
    by_new_id = {c['candidate_id']: c for c in revised}
    for before in registry:
        after = by_new_id[before['candidate_id']]
        for key in before:
            if key == 'screening_bucket':
                continue
            if before[key] != after[key]:
                raise ValueError('Review changed an upstream clinical fact: ' + key)
    processed.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(processed/'reviewed_candidate_registry_v2.0.jsonl', revised)
    write_jsonl(processed/'candidate_evidence_inventory_v2.0.jsonl', inventory)
    write_jsonl(processed/'same_day_progression_links_v2.0.jsonl', [
        {'progression_candidate_id': k, 'treatment_candidate_ids': v,
         'order': 'unknown', 'count_as_separate_decision': False, 'link_does_not_establish_predecision_availability': True}
        for k, v in sorted(links.items())])
    flat = []
    for c in revised:
        r = c['candidate_review']
        flat.append({'candidate_id': c['candidate_id'], 'patient_id': c['patient_key'][1], 'cohort': c['patient_key'][0],
                     'cancer_seq': c['cancer_seq'], 't0_day': c['t0_day'], 'anchor_kind': c['anchor_kind'],
                     'upstream_bucket': c['upstream_screening_bucket'], 'current_bucket': c['screening_bucket'],
                     'ngs_timing_status': c['screening_ngs_status'], 'pathology_qualification': r.get('pathology_qualification', 'not_reviewed_in_this_step'),
                     'pathology_report_time': r['pathology_report_available_before_t0'],
                     'nos_paad_retention_rule': r['nos_paad_retention_rule_applies'],
                     'strategy_pattern': r.get('strategy_record_pattern', 'not_reviewed_in_this_step'),
                     'strategy_intent': r['strategy_intent'],
                     'linked_treatment_candidate_ids': ' | '.join(r['same_day_treatment_candidate_ids']),
                     'counting_status': r['decision_counting_status'], 'change_reasons': ' | '.join(r['changes']),
                     'final_training_eligibility': c['final_training_eligibility'],
                     'source_file': c['source']['file'], 'source_logical_row': c['source']['logical_row']})
    for name, rows in [('reviewed_candidate_registry', flat),
                       ('reviewed_main_candidates', [r for r in flat if r['current_bucket'] == 'main_regimen_start_candidate']),
                       ('reviewed_pending_candidates', [r for r in flat if r['current_bucket'] != 'main_regimen_start_candidate'])]:
        write_csv(processed/(name+'_v2.0.csv'), list(flat[0]), rows)
    buckets = {b: {'records': len(rows), 'patients': len({tuple(c['patient_key']) for c in rows})}
               for b in sorted({c['screening_bucket'] for c in revised})
               for rows in [[c for c in revised if c['screening_bucket'] == b]]}
    nos_main_before = [c for c in revised if c['upstream_screening_bucket'] == 'main_regimen_start_candidate'
                       and c['candidate_review']['nos_paad_retention_rule_applies']]
    summary = {'project_version': 'v2.0', 'phase': '04_candidate_review', 
               'rule_authority': 'candidate_review_protocol_v2.0', 'registry_records': len(revised),
               'registry_patients': len({tuple(c['patient_key']) for c in revised}),
               'evidence_inventory_records': len(inventory), 'evidence_inventory_summary': stats(inventory),
               'upstream_main_candidates': sum(c['screening_bucket'] == 'main_regimen_start_candidate' for c in registry),
               'regimen_independence_review_added': sum(c['screening_bucket'] == 'regimen_independence_review' for c in revised),
               'independence_review_patterns': dict(Counter(c['candidate_review']['strategy_record_pattern'] for c in revised if c['screening_bucket'] == 'regimen_independence_review')),
               'same_day_progression_linked': len(links), 'same_day_link_target_buckets': dict(Counter(by_new_id[i]['screening_bucket'] for targets in links.values() for i in targets)),
               'nos_paad_original_main_records': len(nos_main_before),
               'nos_paad_original_main_current_buckets': dict(Counter(c['screening_bucket'] for c in nos_main_before)),
               'buckets': buckets, 'records_deleted': 0, 't0_or_ngs_modified': 0,
               'source_pathology_check_records': len(inventory),
               'final_eligible_decision_points': None, 'expert_labels': None,
               'expert_review_completed': False, 'clinical_missingness_caused_exclusions': 0}
    write_json(out/'candidate_review_summary_v2.0.json', summary)
    return summary, inputs


def write_report(base, s):
    labels = {'main_regimen_start_candidate': '保留的方案起始主候选',
              'regimen_independence_review': '同药／减药记录：独立策略改变待核',
              'within_regimen_change_review': '方案内药物开始：独立调整待核',
              'progression_trigger_review': '其余进展候选组：实际决策含义待核',
              'progression_linked_same_day_not_separate': '已关联同日治疗的进展组：暂不另计独立点',
              'ngs_timing_review': 'NGS时序待核', 'disease_context_review': '疾病情境或归属待核',
              'outside_main_scope_retained': '其他癌症或非PAAD队列亚型：保留追溯'}
    table = '\n'.join(f"| {labels[b]} | {v['records']:,} | {v['patients']:,} |" for b, v in s['buckets'].items())
    nos = s['nos_paad_original_main_current_buckets']
    text = f'''# 候选点核查报告 v2.0

版本：v2.0

更新日期：{datetime.now(timezone.utc).strftime('%Y%m%d')}

状态：完成候选分组核查；临床裁定和治疗标签尚未形成。

## 范围与依据

候选识别以公开数据中的病理、分子、治疗和进展记录为依据。NGS仍须严格早于候选时点；病例未来信息不进入早期输入。腺癌NOS候选保留组织学限制标记；意图不明的同药或减药记录列入独立性待核查；同日进展与治疗关联后不另计独立点。具体协议见[候选点协议](decision_point_protocol_v2.0.md)，机器配置见[核查配置](../../../code/config/v2.0/candidate_review.json)。

对{s['evidence_inventory_records']:,}条主候选、方案内调整和进展组整理逐点证据，并直接重新读取原始病理CSV，核对各候选日前取材的胰腺癌浸润组织学原文。其余记录保留第三阶段分组；没有扩大为全队列临床裁决。

## 分组规则

1. 腺癌NOS＋在先PAAD：原主候选中{s['nos_paad_original_main_records']:,}条满足候选日前取材的胰腺癌病理仅为8140 Adenocarcinoma NOS、同癌症在先NGS编码PAAD，全部保留。仍在主候选的{nos.get('main_regimen_start_candidate', 0):,}条；因同药／减药独立性规则转入待核查的{nos.get('regimen_independence_review', 0):,}条。后者不是因NOS而排除。病理亚型及主报告可用时间继续标明未知，不改写为已明确确诊PDAC。
2. 同药／减药：前后方案全程原药名集合相同{s['independence_review_patterns'].get('same_full_course_drug_set', 0):,}条，后一方案为前一方案药物子集{s['independence_review_patterns'].get('fewer_full_course_drugs_subset', 0):,}条，共{s['regimen_independence_review_added']:,}条转入独立性待核查。当前结构化治疗记录没有给出这些记录的重启、维持、减量或换线意图；没有把进展相邻或间隔较长本身升级为确定意图。药物集合比较是全程后验核查信息，不是时点模型输入，也没有把药物名称相同当成疗程重复并删除。遮蔽药物身份不自动作同药判断。
3. 同日进展：{s['same_day_progression_linked']:,}个原进展候选组已关联同患者、同癌症、同日方案或药物开始候选，记录双向关联。进展组和来源仍保留，暂不另计独立决策点；不假定进展发生在治疗之前，同日进展结果不作为已确认的治疗前信息。

## 当前结果

候选登记仍为{s['registry_records']:,}条、{s['registry_patients']:,}名患者。删除记录0条，改写候选日或NGS日期0条。

| 当前集合 | 记录／组数 | 患者 |
| --- | ---: | ---: |
{table}

表内记录分组互斥，患者可跨组，人数不能相加。候选锚点、进展组和待核查记录不是等价的独立决策单位；不能将总登记数作为最终训练样本数。方案起始主候选也不代表所有病理、疾病情境或治疗意图已确认。

## 研究局限

- 公开数据是结构化摘要，缺少完整病历及部分临床指标；评价分子、病理、既往治疗与候选方案证据匹配，不能据此宣称完成个体临床安全性或剂量可行性评价。缺失不补成正常。
- 取材日期不等于病理主报告签发日期。NOS病理不被改写为明确PDAC；在先PAAD编码作为现有分类证据保留，不能替代独立病理确认。这些限制影响候选方案的适用性解释。
- 初始可切除性不等于当前状态；派生转移日期与手术病理同日的事实已记录于逐点证据，尚未将其裁定为错误或真实转移。混合组织学及多癌症归属也未自动裁决。
- 全程药物集合变化不自动代表独立策略变化。缺少意图时保留待核查，避免推断维持、重启或换线。进展归组属于研究整理规则，实际决策日和报告可用时间可能未提供。
- NGS在先筛选、结构化记录覆盖范围及待核查分层可能带来选择偏倚。样本构成需结合分组与机构解释，候选数量不代表模型性能。
- 用药后反应和结局保留在第三阶段独立参考文件，不直接决定标签。不同来源终点的时间原点保持原定义，不能任意当作从当前候选开始的PFS或OS。尚无治疗标签、专家一致性或模型实验结果。

## 输出与复现

[最新主候选CSV](../../../data/processed/v2.0/04_candidate_review/reviewed_main_candidates_v2.0.csv)、[待核查及追溯CSV](../../../data/processed/v2.0/04_candidate_review/reviewed_pending_candidates_v2.0.csv)、[全部候选登记](../../../data/processed/v2.0/04_candidate_review/reviewed_candidate_registry_v2.0.jsonl)保留原编号、来源、分组前后变化和原因。

[逐点证据清单](../../../data/processed/v2.0/04_candidate_review/candidate_evidence_inventory_v2.0.jsonl)包含原组织学、NGS与病理关联、方案比较及日期疑点；[同日关联](../../../data/processed/v2.0/04_candidate_review/same_day_progression_links_v2.0.jsonl)保留关联关系和未知顺序。病理所有字段和标本仍位于第一阶段完整临床记录，第三阶段结局参考继续可用，均未删除。

从项目根目录运行 `python -B code/scripts/run_v2_0.py all` 重建五阶段并验证；前三阶段完成后可用 `python -B code/scripts/run_v2_0.py review` 重建本阶段。机器统计见[核查汇总](../../../code/results/v2.0/04_candidate_review/candidate_review_summary_v2.0.json)，来源和校验和见[运行清单](../../../code/results/v2.0/04_candidate_review/run_manifest.json)。

本报告记录第四阶段候选核查结果。进一步的组织学、情境分层及最新候选用途见[第五阶段报告](candidate_cohort_report_v2.0.md)。候选用途固定不等于专家临床语义审核或治疗标签完成。
'''
    (base/'docs/notes/v2.0/candidate_review_report_v2.0.md').write_text(text, encoding='utf-8')


def run(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    source = json.loads((BASE/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    raw, processed, out = resolve_paths(BASE, {**source, **config})
    inventory = json.loads((BASE/source['results_dir']/'source_inventory.json').read_text(encoding='utf-8'))
    def verify_raw():
        if any(sha256(raw/r['file']) != r['sha256'] for r in inventory):
            raise ValueError('Original source changed')
    verify_raw()
    out.mkdir(parents=True, exist_ok=True)
    manifest = {'project_version': 'v2.0', 'phase': '04_candidate_review', 'status': 'running',
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'runtime': {'python': platform.python_version(), 'platform': platform.platform()},
                'config_file': config_path.relative_to(BASE).as_posix(), 'config_sha256': sha256(config_path),
                'code_sha256': {p.relative_to(BASE).as_posix(): sha256(p) for p in sorted([*(BASE/'code/src').rglob('*.py'), *(BASE/'code/scripts').glob('*.py'), *(BASE/'code/tests').rglob('*.py')])}}
    write_json(out/'run_manifest.json', manifest)
    try:
        summary, inputs = build(BASE, processed, out, config)
        verify_raw()
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
