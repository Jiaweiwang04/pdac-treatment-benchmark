"""Build a development-only regimen inventory with explicit evidence provenance."""
import calendar
import hashlib
import json
import platform
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from .audit import write_csv, write_json, write_jsonl
from .layout import resolve_paths
from .source import sha256

BASE = Path(__file__).resolve().parents[4]
PHASE = '07_treatment_catalog'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def upper_date(s):
    value = s['publication_date']
    if s['date_precision'] == 'year':
        return date(int(value), 12, 31)
    if s['date_precision'] == 'month':
        y, m = map(int, value.split('-'))
        return date(y, m, calendar.monthrange(y, m)[1])
    return date.fromisoformat(value)


def validate_definitions(config, sources, families, variants):
    """Fail closed on references, cutoff, duplicate identity and unknown results."""
    si = {s['evidence_id']: s for s in sources}
    fi = {f['family_id']: f for f in families}
    if len(si) != len(sources) or len(fi) != len(families):
        raise ValueError('Duplicate evidence or family IDs')
    if len({v['variant_id'] for v in variants}) != len(variants):
        raise ValueError('Duplicate variant IDs')
    if len({tuple(f['components']) for f in families}) != len(families):
        raise ValueError('Duplicate family component identities')
    cutoff = date.fromisoformat(config['evidence_cutoff_date'])
    for s in sources:
        if upper_date(s) > cutoff:
            raise ValueError('Evidence date exceeds cutoff or its precision crosses cutoff')
        if not s['url'].startswith('https://') or not s['locator']:
            raise ValueError('Missing primary source URL or locator')
    for f in families:
        if not f['components'] or f['components'] != sorted(set(f['components'])):
            raise ValueError('Family components must be explicit and unique')
        if any(e not in si for e in f['evidence_ids']):
            raise ValueError('Missing family evidence reference')
        if f['evaluation_context'] not in {'routine', 'research'}:
            raise ValueError('Invalid assessment context')
        if f['patient_label'] is not None:
            raise ValueError('A catalog family cannot carry a patient label')
        if f['catalog_status'] == 'evidence_linked':
            allowed = [si[e] for e in f['evidence_ids'] if si[e]['verification_level'] == 'primary_source_text']
            if not any(s['human_results'] or s['source_type'] == 'guideline' for s in allowed):
                raise ValueError('Evaluable family lacks verified results or recommendation')
            if f['evaluation_context'] == 'research' and not any(s['human_results'] for s in allowed):
                raise ValueError('Research family lacks verified human results')
    for v in variants:
        if v['family_id'] not in fi or not v['evidence_ids'] or any(e not in si for e in v['evidence_ids']):
            raise ValueError('Variant reference missing')
        if v['assignment_from_component_names_alone']:
            raise ValueError('Variant cannot be inferred from drug names')


def select_development(registry):
    # No held-out treatment attribute is read by the selector.
    return sorted((c for c in registry if c['patient_split_assignment']['patient_split'] == 'development'), key=lambda c: c['candidate_id'])


def normalize_component(component, aliases, candidate_id):
    raw = component['name_raw']
    primary = raw.split('(', 1)[0].strip()
    masked = bool(component.get('masked')) or primary == 'Investigational Drug'
    identity = None if masked else aliases.get(primary)
    return dict(component, primary_name=primary, normalized_drug=identity,
                normalization_status='masked_identity' if masked else 'mapped' if identity else 'unmapped',
                masked_instance_id=f"{candidate_id}:slot:{component['slot']}" if masked else None)


def temporal_status(components, t0):
    if not components:
        return 'no_components'
    if any(isinstance(d.get('start_day'), (int, float)) and isinstance(d.get('end_day'), (int, float)) and d['end_day'] < d['start_day'] for d in components):
        return 'invalid_interval'
    starts = [d.get('start_day') for d in components]
    ends = [d.get('end_day') for d in components]
    if not all(isinstance(x, (int, float)) for x in starts + ends):
        return 'interval_incomplete'
    if max(starts) > min(ends):
        return 'no_common_recorded_interval'
    if all(x == t0 for x in starts):
        return 'aligned_recorded_starts'
    return 'overlap_with_different_starts'


def map_record(c, aliases, family_index):
    comp = [normalize_component(d, aliases, c['candidate_id']) for d in c.get('regimen_components_full_course', [])]
    signature = sorted({d['normalized_drug'] for d in comp if d['normalized_drug']})
    masked = sum(d['normalization_status'] == 'masked_identity' for d in comp)
    unmapped = sum(d['normalization_status'] == 'unmapped' for d in comp)
    timing = temporal_status(comp, c['t0_day'])
    match = family_index.get(tuple(signature)) if comp and not (masked or unmapped) else None
    status = 'masked_identity' if masked else 'unmapped_drug' if unmapped else 'composition_only_match' if match else 'evidence_search_pending'
    return dict(candidate_id=c['candidate_id'], patient_key=c['patient_key'], cancer_seq=c.get('cancer_seq'),
                t0_day=c['t0_day'], candidate_role=c['candidate_role'], source_record_id=c['source_record_id'], source=c['source'],
                raw_components=comp, raw_name_set=sorted({d['name_raw'] for d in comp}),
                raw_slot_name_pattern=sorted(d['name_raw'] for d in comp), normalized_known_components=signature,
                masked_component_count=masked, unmapped_component_count=unmapped,
                mapping_status=status, temporal_status=timing, composition_family_id=match['family_id'] if match else None,
                composition_evidence_status=match['catalog_status'] if match else None,
                observed_variant_id=None, observed_variant_status='not_determinable_from_source',
                administered_combination_confirmed=False, patient_label=None, is_model_input=False)


def export_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row)) or ['record_id']
    flat = [{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()} for row in rows]
    write_csv(path, fields, flat)


def build(base, processed, out, config, development):
    if any(c['patient_split_assignment']['patient_split'] != 'development' for c in development):
        raise ValueError('Catalog builder accepts development patients only')
    development = sorted(development, key=lambda c: c['candidate_id'])
    sources = load(base / config['source_ledger'])
    families = load(base / config['family_definitions'])
    variants = load(base / config['variant_definitions'])
    aliases = load(base / config['alias_definitions'])
    validate_definitions(config, sources, families, variants)
    main = [c for c in development if c['candidate_role'] == 'main_observed_regimen']
    eligible_cancers = {(tuple(c['patient_key']), c.get('cancer_seq')) for c in main}
    historical = [c for c in development if c.get('regimen_components_full_course') and (tuple(c['patient_key']), c.get('cancer_seq')) in eligible_cancers]
    # Same source regimen may appear at start, addition and discontinuation anchors.
    hist_sources = {}
    for c in historical:
        hist_sources.setdefault(c['source_record_id'], c)
    family_index = {tuple(f['components']): f for f in families}
    mapped = [map_record(c, aliases, family_index) for c in main]
    background = [map_record(c, aliases, family_index) for c in hist_sources.values()]
    from .regimen_screening import screen
    decisions=load(base/config['disposition_definitions'])
    screened=screen(mapped,background,decisions,families,sources)
    raw_groups = defaultdict(list)
    for r in mapped:
        raw_groups[tuple(r['raw_slot_name_pattern'])].append(r)
    raw_table = []
    for raw_names, rows in sorted(raw_groups.items()):
        r = rows[0]
        raw_table.append(dict(raw_set_id='RS_' + digest(raw_names)[:16], raw_names=list(raw_names),
            normalized_known_components=r['normalized_known_components'], main_candidate_count=len(rows),
            patient_count=len({tuple(x['patient_key']) for x in rows}), candidate_ids=[x['candidate_id'] for x in rows],
            mapping_status=r['mapping_status'], composition_family_id=r['composition_family_id'],
            evidence_status=r['composition_evidence_status'], temporal_counts=dict(Counter(x['temporal_status'] for x in rows)),
            masked_instance_count=sum(x['masked_component_count'] for x in rows),
            screening_disposition=r['screening_disposition'],screening_rationale_zh=r['screening_rationale_zh']))
    raw_aliases = {}
    for r in [*mapped, *background]:
        for d in r['raw_components']:
            raw_aliases.setdefault(d['name_raw'], dict(name_raw=d['name_raw'], primary_name=d['primary_name'],
                normalized_drug=d['normalized_drug'], normalization_status=d['normalization_status'],
                alias_parentheses_expanded=False))
    counts = Counter(r['composition_family_id'] for r in mapped if r['composition_family_id'])
    catalog = []
    for f in families:
        catalog.append(dict(f, variant_ids=[v['variant_id'] for v in variants if v['family_id'] == f['family_id']],
                            development_main_composition_count=counts[f['family_id']],
                            origin='external_evidence_and_development' if counts[f['family_id']] else 'external_evidence',
                            research_regimen=f['evaluation_context'] == 'research',
                            regulatory_status_scope='only_as_stated_in_linked_dated_sources'))
    gaps = [dict(r, followup_zh=r['screening_rationale_zh'],resolution_status='reference_only_in_this_release')
            for r in raw_table if r['mapping_status'] != 'composition_only_match']
    processed.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    products = [('treatment_families_v2.0', catalog), ('treatment_variants_v2.0', variants),
                ('treatment_evidence_sources_v2.0', sources), ('development_raw_regimen_sets_v2.0', raw_table),
                ('development_regimen_mapping_v2.0', mapped), ('development_historical_regimen_context_v2.0', background),
                ('drug_name_mapping_v2.0', list(raw_aliases.values())), ('treatment_evidence_gaps_v2.0', gaps),
                ('development_regimen_screening_v2.0',screened)]
    summary = dict(project_version='v2.0', execution_date=config['execution_date'], evidence_cutoff_date=config['evidence_cutoff_date'],
        catalog_status=config['catalog_status'], development_patients=len({tuple(c['patient_key']) for c in main}),
        development_main_candidates=len(main), development_main_raw_name_sets=len({tuple(r['raw_name_set']) for r in mapped}),
        development_main_slot_name_patterns=len(raw_groups),
        development_main_raw_drug_names=len({d['name_raw'] for c in main for d in c.get('regimen_components_full_course', [])}),
        development_same_cancer_historical_source_regimens=len(background),
        family_count=len(catalog), evidence_linked_families=sum(f['catalog_status']=='evidence_linked' for f in catalog),
        research_families=sum(f['research_regimen'] for f in catalog), variant_count=len(variants), evidence_source_count=len(sources),
        main_mapping_counts=dict(Counter(r['mapping_status'] for r in mapped)),
        main_temporal_counts=dict(Counter(r['temporal_status'] for r in mapped)),
        masked_main_candidates=sum(bool(r['masked_component_count']) for r in mapped),
        masked_components=sum(r['masked_component_count'] for r in mapped),
        evidence_gap_raw_sets=len(gaps), evidence_gap_main_candidates=sum(g['main_candidate_count'] for g in gaps),
        catalog_content_sha256=digest({'families':catalog,'variants':variants,'sources':sources}),
        development_projection_sha256=digest(mapped), observed_variants_assigned=0, patient_labels_generated=0,
        catalog_frozen=config['catalog_frozen'], core_coverage_audit_performed=False,
        release_id=config.get('release_id'),screened_raw_patterns=len(screened),
        screening_disposition_counts=dict(Counter(r['disposition'] for r in screened)),
        main_screening_disposition_counts=dict(Counter(r['screening_disposition'] for r in mapped)),
        unresolved_screening_patterns=0,
        dose_schedule_defined_variants=sum(v.get('eligible_for_variant_level_label',False) for v in variants))
    if config['catalog_frozen']:
        from .catalog_release import seal
        lock=seal(base,config,summary,background)
        summary['release_sha256']=lock['release_sha256']
    for name, rows in products:
        write_jsonl(processed / (name + '.jsonl'), rows)
        if name not in {'development_regimen_mapping_v2.0', 'development_historical_regimen_context_v2.0'}:
            export_csv(processed / (name + '.csv'), rows)
    export_csv(processed / 'development_regimen_mapping_v2.0.csv', [{k: v for k, v in r.items() if k not in {'raw_components','source'}} for r in mapped])

    write_json(out / 'treatment_catalog_summary_v2.0.json', summary)
    write_reports(base, config, summary, catalog, variants, sources, raw_table, gaps)
    from .regimen_screening import write_report
    write_report(base,config,screened)
    return summary


def write_reports(base, config, s, catalog, variants, sources, raw_table, gaps):
    docs = base / 'docs/notes/v2.0'
    docs.mkdir(parents=True, exist_ok=True)
    def table(headers, rows):
        def cell(x): return str(x).replace('|', '\\|').replace('\n', ' ')
        return '\n'.join('| ' + ' | '.join(map(cell, row)) + ' |' for row in [headers, ['---']*len(headers), *rows])
    def meta(title):
        return f'# {title} v2.0\n\n版本：v2.0\n\n更新日期：{s["execution_date"]}\n\n状态：公开证据目录已冻结；患者标签尚未裁定。\n\n'
    paths = '../../../data/processed/v2.0/07_treatment_catalog/'
    meaning = {'composition_only_match':'仅药物组成对应', 'masked_identity':'匿名药物身份未明', 'evidence_search_pending':'具体组合待补证据', 'reference_only':'仅保留原始参考记录',
        'supports_activity':'有活性或获益依据', 'comparator':'对照方案证据', 'conflicting_schedule_evidence':'不同日程证据冲突',
        'noninferior':'非劣效结果', 'superiority_not_demonstrated':'未证实优效', 'modest_benefit':'获益有限',
        'limited_activity':'有限临床活性', 'no_objective_responses':'未观察到客观缓解', 'trial_and_pooled_results_differ':'单项试验与合并结果不同',
        'guideline_option':'指南列为选项', 'benefit_not_demonstrated':'未证实获益', 'not_extracted':'尚未提取',
        'primary_source_text':'原始来源相应条款或摘要', 'bibliography_and_partial_text':'题录与部分正文', 'abstract_scope_only':'摘要范围核实',
        'guideline':'指南', 'randomized_phase_III':'随机三期研究', 'randomized_phase_II':'随机二期研究',
        'single_arm_phase_II':'单臂二期研究', 'single_arm_phase_I_II':'单臂一期／二期研究', 'phase_II':'二期研究',
        'phase_I':'一期研究', 'phase_I_II':'一期／二期研究', 'randomized_phase_I_II':'随机一期／二期研究',
        'retrospective_cohort':'回顾性队列', 'regulatory_human_results':'监管文件及人体结果', 'regulatory_update':'监管状态更新',
        'manufacturer_submission':'企业申报公示材料', 'meeting_abstract':'原始会议摘要', 'randomized_trial_subgroup':'随机研究亚组分析'}
    text = meta('候选治疗方案目录与整理报告') + '''## 目的与范围

以开发集历史治疗及公开临床证据建立候选方案目录，服务于“决策点×治疗方案”的四类标签审核。药物组成的归类、证据支持程度和患者匹配标签是三个独立层次；本报告不生成患者标签。

家族以完整药物组成定义，变体以可核验的制剂、剂量和日程定义。同一药物不同生物标志物路径保持同一家族，但后续标签须注明评价路径。研究性方案显式标记；历史证据单独登记，不自动代表截止日的优先推荐。

## 数据整理规则

主核查覆盖开发患者的全部主候选点。背景表另汇集这些患者同一癌症的已登记疗程，按源记录去重，保留前线治疗和治疗情境；其他癌症治疗不并入该背景表。背景记录的纳入资格仍保持原分层，不因进入目录核查而变成训练样本。

原药名完整保留，仅使用括号前的主名称进行显式字典映射。括号中的商品名、试验名不拆成新药；普通伊立替康与脂质体伊立替康、普通紫杉醇与白蛋白紫杉醇分别编码。匿名研究药只保留每条记录的槽位身份，不能把同名“Investigational Drug”当作同一种药。

疗程药物全集仅用于检索线索。分别核对记录区间是否重叠、开始日是否一致、时间是否缺失；区间重叠也不证明实际同期联合给药。药物完整一致时只记“组成对应”，未记录亚叶酸时不自动补齐，剂量和日程不足时不分配具体变体。模型的决策前病例输入不包含该时点实际选择的方案和后续用药信息。

## 当前结果

'''
    text += table(['项目','数量'], [[k,s[v]] for k,v in [('开发患者','development_patients'),('开发集主候选点','development_main_candidates'),('原始药名集合（同名去重）','development_main_raw_name_sets'),('药名槽位组合（保留重复匿名槽位）','development_main_slot_name_patterns'),('主候选中的原始药名','development_main_raw_drug_names'),('同癌症历史疗程源记录','development_same_cancer_historical_source_regimens'),('目录方案家族','family_count'),('已关联结果或推荐的家族','evidence_linked_families'),('研究性方案家族','research_families'),('变体记录','variant_count'),('证据来源','evidence_source_count'),('主候选中仅作参考的原始组合','evidence_gap_raw_sets'),('全部主候选及历史组合判定','screened_raw_patterns'),('可用于剂量日程定义的变体','dose_schedule_defined_variants')]])
    text += '\n\n' + table(['组成核查状态','主候选点数'], [[meaning.get(k,k),v] for k,v in s['main_mapping_counts'].items()])
    text += f'''\n\n匿名研究药涉及{s['masked_main_candidates']}个主候选点、{s['masked_components']}个药物槽位。方案家族数不能视为适用于每个患者的方案数，也不能据此相乘获得有效标签对数。所有实际治疗变体仍未分配，患者标签保持空值。

## 方案目录

'''
    si = {e['evidence_id']: e for e in sources}
    rows = []
    for f in catalog:
        refs = '；'.join(f'[{e}]({si[e]["url"]})' for e in f['evidence_ids'])
        kind = '研究性' if f['research_regimen'] else '常规情境待个体核查'
        if f['evidence_position']=='historical': kind += '；历史证据'
        rows.append([f['family_id'],f['name_zh'],kind,f['required_context_zh'],meaning.get(f['evidence_direction'],f['evidence_direction']),refs])
    text += table(['编号','方案家族','评价情境','证据适用条件','结果方向','原始依据'], rows)
    text += '\n\n### 方案变体\n\n下表定义参考文献中的具体方案。实际病例仅药物组成一致时不分配这些变体。\n\n'
    text += table(['家族','变体','区分依据','来源'],[[v['family_id'],v['name'],v['definition_zh'],'；'.join(f'[{e}]({si[e]["url"]})' for e in v['evidence_ids'])] for v in variants])
    text += '''

## 证据使用与冻结规则

知识截止日为2026-09-12，检索日期与证据发布日期分别记录。指南、原始试验、病例报告、会议摘要和监管文件按原来源区分，不自行换算成统一指南推荐等级。每条来源注明读取层级；只核实题录或研究范围的条目不能独立支持正向患者标签。未提取的推荐级别保持空值。

目录生成只接收开发患者；Core实际治疗不参与扩充。本版已固定各原始组合处理结论、目录适用条件和内容摘要，再执行独立的Core覆盖审计。冻结只约束目录版本，不代表完成专家临床裁定。审计发现未覆盖方案也不能回填同版目录；需要扩展时建立新版本并明确原测试集已被查看的事实。

美国批准范围、其他地区可及性和研究性评价分别处理。FDA的泛瘤种适应证不等于PDAC专属随机证据；家族进入目录不代表当前患者符合适应证，也不代表获得中国批准。

## 待核查与输出

'''
    text += '\n'.join('- '+x for x in config['limitations']) + '\n\n'
    text += '未纳入家族的参考项逐项保留原药名、影响点数、病例定位及判定理由；不能直接解释为方案无效或患者不匹配。全文证据条款、分子改变类型与治疗线次仍需在病例初标前核查。\n\n'
    text += '\n'.join(f'- [{label}]({paths}{name})' for label,name in [
        ('方案家族表','treatment_families_v2.0.csv'),('变体表','treatment_variants_v2.0.csv'),('原始组合完整核查表','development_raw_regimen_sets_v2.0.csv'),
        ('主候选逐点映射','development_regimen_mapping_v2.0.csv'),('药名原值与规范名对照','drug_name_mapping_v2.0.csv'),
        ('参考项清单','treatment_evidence_gaps_v2.0.csv'),('全部组合纳入判定','development_regimen_screening_v2.0.csv'),('目录冻结锁','treatment_catalog_lock_v2.0.json'),('同癌症历史疗程背景','development_historical_regimen_context_v2.0.jsonl')])
    text += '\n\n来源题录及读取范围见[证据来源说明](treatment_evidence_ledger_v2.0.md)。运行 `python -B code/scripts/run_v2_0.py catalog` 重建本阶段，运行 `python -B code/scripts/run_v2_0.py all` 复现八阶段并检查来源与文档。\n'
    (docs/'treatment_catalog_report_v2.0.md').write_text(text, encoding='utf-8')
    ledger = meta('治疗方案证据来源说明') + '## 来源与读取范围\n\n来源的简要说明用于定位证据。摘要读取不能替代全文纳排条件；尚未提取的细节不填推测值。\n\n'
    ledger += table(['来源编号','文献或文件','发布日期','类型','读取层级','定位','证据要点'],
        [[s['evidence_id'],f'[{s["title"]}]({s["url"]})',s['publication_date'],meaning.get(s['source_type'],s['source_type']),meaning.get(s['verification_level'],s['verification_level']),s['locator'],s['finding_zh']] for s in sources])
    ledger += '\n\n## 证据冲突与版本边界\n\nOFF和mFOLFOX6保持独立变体及相反结果方向；不能挑选阳性研究代表整个家族。试验注册、扩大使用许可、正式批准与临床结果不是同一类证据，须按事件日期及文件类型记录。\n\n证据清单与药名规范化是待审核研究资料，未形成专家裁定标签。目录定义、参考项处理和内容摘要已冻结，专家审核状态独立记录。结构化来源见[证据表]('+paths+'treatment_evidence_sources_v2.0.csv)。\n'
    (docs/'treatment_evidence_ledger_v2.0.md').write_text(ledger, encoding='utf-8')


def run(config_path):
    config_path = Path(config_path).resolve()
    config = load(config_path)
    source = load(BASE/'code/config/v2.0/source.json')
    raw, processed, out = resolve_paths(BASE, {**source, **config})
    out.mkdir(parents=True, exist_ok=True)
    registry = BASE/'data/processed/v2.0/06_patient_split/candidate_split_registry_v2.0.jsonl'
    lock = BASE/'data/processed/v2.0/06_patient_split/patient_split_lock_v2.0.json'
    inputs = [registry,lock,BASE/'code/config/v2.0/treatment_labels.json',*[BASE/config[k] for k in ['source_ledger','family_definitions','variant_definitions','alias_definitions','disposition_definitions']]]
    before = {p.relative_to(BASE).as_posix():sha256(p) for p in inputs}
    manifest = dict(project_version='v2.0', phase=PHASE, status='running', started_utc=datetime.now(timezone.utc).isoformat(),
        runtime=dict(python=platform.python_version(),platform=platform.platform()), config_file=config_path.relative_to(BASE).as_posix(),
        config_sha256=sha256(config_path), code_sha256={p.relative_to(BASE).as_posix():sha256(p) for p in sorted([*(BASE/'code/src').rglob('*.py'),*(BASE/'code/scripts').glob('*.py'),*(BASE/'code/tests').rglob('*.py')])})
    write_json(out/'run_manifest.json',manifest)
    try:
        if load(BASE/'code/config/v2.0/treatment_labels.json')['evidence_cutoff_date'] != config['evidence_cutoff_date']:
            raise ValueError('Label and catalog cutoff differ')
        with registry.open(encoding='utf-8') as f:
            development = select_development(json.loads(line) for line in f)
        summary = build(BASE,processed,out,config,development)
        if any(sha256(BASE/p)!=h for p,h in before.items()):
            raise ValueError('Catalog input changed during build')
        outputs = [*processed.glob('*'),out/'treatment_catalog_summary_v2.0.json',BASE/'docs/notes/v2.0/treatment_catalog_report_v2.0.md',BASE/'docs/notes/v2.0/treatment_evidence_ledger_v2.0.md',BASE/'docs/notes/v2.0/treatment_screening_report_v2.0.md']
        manifest.update(status='completed',finished_utc=datetime.now(timezone.utc).isoformat(),summary=summary,input_sha256=before,
            output_sha256={p.relative_to(BASE).as_posix():sha256(p) for p in outputs if p.is_file()})
        write_json(out/'run_manifest.json',manifest)
        print(json.dumps(summary,ensure_ascii=False,indent=2))
        return 0
    except Exception as error:
        manifest.update(status='failed',error=str(error))
        write_json(out/'run_manifest.json',manifest)
        raise
