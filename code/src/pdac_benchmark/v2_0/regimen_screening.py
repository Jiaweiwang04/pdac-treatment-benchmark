"""Explicit terminal dispositions for every development regimen pattern."""
from collections import Counter, defaultdict

TERMINAL={'included_family','reference_masked','reference_incomplete_definition',
          'reference_no_qualifying_evidence','reference_outside_treatment_scope'}


def screen(records, background, decisions, families, sources):
    from .treatment_catalog import digest
    fi={f['family_id']:f for f in families}; si={s['evidence_id'] for s in sources}
    di={tuple(d['components']):d for d in decisions}
    if len(di)!=len(decisions):raise ValueError('Duplicate screening disposition')
    for d in decisions:
        if d['disposition'] not in TERMINAL or not d['rationale_zh'] or not set(d['evidence_ids'])<=si or d['patient_label'] is not None:
            raise ValueError('Invalid screening disposition')
    for r in [*records,*background]:
        if r['masked_component_count']:
            d=dict(disposition='reference_masked',rationale_zh='药物身份匿名化；逐槽位保留，不根据医院、年代或结果猜测药名。',evidence_ids=[],search_query=None,search_date=None)
        elif r['composition_family_id']:
            f=fi[r['composition_family_id']]
            d=dict(disposition='included_family',rationale_zh='完整药物组成对应已核验人体结果或公开指南的目录家族；不表示患者适用性成立。',evidence_ids=f['evidence_ids'],search_query=None,search_date=None)
        else:
            if r['unmapped_component_count']:raise ValueError('Unmapped development drug identity')
            key=tuple(r['normalized_known_components'])
            if key not in di:raise ValueError('Unscreened development composition: '+str(key))
            d=di[key]
        r.update(screening_disposition=d['disposition'],screening_rationale_zh=d['rationale_zh'],screening_evidence_ids=d['evidence_ids'])
        if r['mapping_status']=='evidence_search_pending':r['mapping_status']='reference_only'
    groups=defaultdict(lambda:dict(main=[],history=[]))
    for name,rows in [('main',records),('history',background)]:
        for r in rows:groups[tuple(r['raw_slot_name_pattern'])][name].append(r)
    table=[]
    for pattern,g in sorted(groups.items()):
        r=(g['main'] or g['history'])[0]
        decision=di.get(tuple(r['normalized_known_components']),{}) if r['screening_disposition'] not in {'included_family','reference_masked'} else {}
        table.append(dict(raw_set_id='RS_'+digest(pattern)[:16],raw_names=list(pattern),
            normalized_known_components=r['normalized_known_components'],disposition=r['screening_disposition'],
            rationale_zh=r['screening_rationale_zh'],family_id=r['composition_family_id'],evidence_ids=r['screening_evidence_ids'],
            main_candidate_count=len(g['main']),historical_source_count=len(g['history']),
            candidate_ids=[x['candidate_id'] for x in g['main']],source_record_ids=[x['source_record_id'] for x in g['history']],
            search_expression=decision.get('search_query'),search_date=decision.get('search_date'),patient_label=None))
    return table


def write_report(base, config, rows):
    labels={'included_family':'纳入方案家族','reference_masked':'匿名身份，仅保留原记录',
        'reference_incomplete_definition':'组成不足，仅保留原记录','reference_no_qualifying_evidence':'未核验到符合标准的完整方案依据',
        'reference_outside_treatment_scope':'研究情境或给药途径不符'}
    lines=['# 开发集治疗组合纳入判定 v2.0','', '版本：v2.0','', '更新日期：20260914','',
        '状态：逐项筛查完成；患者标签尚未裁定。','', '## 范围与判定','',
        '覆盖开发集主候选点及同癌症历史疗程的全部原始药名槽位组合。家族纳入使用完整药物组成及公开人体结果或指南；未知身份、证据不足及研究范围不符的记录保留在参考清单。参考记录不生成患者治疗标签，也不因未纳入目录而判为不匹配。','',
        '检索采用药物通用名、制剂、pancreatic／PDAC及研究类型关键词，补充常见方案名、试验名并追溯原始研究。检索式记录于结构化清单；公开全文无法访问时使用可核验的原始摘要。该过程为有边界的定向证据核查，不是系统综述，未覆盖全部未发表研究或付费指南。','',
        '## 逐项结果','', '| 原始组合 | 主候选点 | 历史源记录 | 判定 | 家族／来源 | 理由 |','| --- | --- | --- | --- | --- | --- |']
    for r in rows:
        cells=[' + '.join(r['raw_names']),str(r['main_candidate_count']),str(r['historical_source_count']),labels[r['disposition']],(r['family_id'] or '—')+' / '+', '.join(r['evidence_ids']),r['rationale_zh']]
        lines.append('| '+' | '.join(x.replace('|','\\|').replace('\n',' ') for x in cells)+' |')
    lines += ['', '主候选点与历史源记录存在重叠，两列不可相加解释为独立决策点。原始疗程的时间关系、病理归属及记录定位在逐点映射和背景表中保留。','',
        '## 文件与复现','', '[结构化判定清单](../../../data/processed/v2.0/07_treatment_catalog/development_regimen_screening_v2.0.csv)包含逐项病例及源记录定位；[证据来源说明](treatment_evidence_ledger_v2.0.md)包含引用地址与读取范围。运行 `python -B code/scripts/run_v2_0.py catalog` 可复现。','']
    (base/'docs/notes/v2.0/treatment_screening_report_v2.0.md').write_text('\n'.join(lines),encoding='utf-8')
