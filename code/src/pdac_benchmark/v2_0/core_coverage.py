"""Read held-out observed treatment only after validating the frozen catalog."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .audit import write_json, write_jsonl
from .catalog_release import verify
from .layout import resolve_paths
from .source import sha256
from .treatment_catalog import load, map_record, export_csv

BASE=Path(__file__).resolve().parents[4]
PHASE='08_core_coverage'


def audit_records(records, aliases, families):
    index={tuple(f['components']):f for f in families}
    mapped=[]
    for c in sorted(records,key=lambda c:c['candidate_id']):
        a=c['patient_split_assignment']
        if a['patient_split']!='core_test' or c['candidate_role']!='main_observed_regimen':
            continue
        r=map_record(c,aliases,index)
        r['core_primary_index']=a['core_primary_index']
        r['coverage_status']='composition_covered' if r['composition_family_id'] else 'identity_unresolved' if r['masked_component_count'] or r['unmapped_component_count'] else 'composition_not_covered'
        if r['mapping_status']=='evidence_search_pending':r['mapping_status']='outside_frozen_catalog'
        r['audit_only']=True
        mapped.append(r)
    return mapped


def run(base=BASE):
    config=load(base/'code/config/v2.0/treatment_catalog.json')
    lock=verify(base,config)  # This must precede opening the held-out registry.
    audit_started=datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(lock['frozen_at_utc'])>datetime.fromisoformat(audit_started):
        raise ValueError('Catalog freeze timestamp lies after audit start')
    source=load(base/'code/config/v2.0/source.json')
    _,processed,out=resolve_paths(base,{**source,'processed_dir':'data/processed/v2.0/'+PHASE,'results_dir':'code/results/v2.0/'+PHASE})
    registry=base/'data/processed/v2.0/06_patient_split/candidate_split_registry_v2.0.jsonl'
    inputs={n:sha256(base/n) for n in lock['payload']['definition_sha256']}
    inputs[config['freeze_lock']]=sha256(base/config['freeze_lock'])
    inputs[registry.relative_to(base).as_posix()]=sha256(registry)
    frozen_files={p.relative_to(base).as_posix():sha256(p) for p in (base/config['processed_dir']).glob('*') if p.is_file()}
    with registry.open(encoding='utf-8') as f:
        records=(json.loads(l) for l in f)
        mapped=audit_records(records,load(base/config['alias_definitions']),load(base/config['family_definitions']))
    def counts(rows):
        total=len(rows);covered=sum(r['coverage_status']=='composition_covered' for r in rows)
        return dict(candidates=total,patients=len({tuple(r['patient_key']) for r in rows}),
            coverage_counts=dict(Counter(r['coverage_status'] for r in rows)),
            covered_fraction_of_all=covered/total if total else None,
            temporal_counts=dict(Counter(r['temporal_status'] for r in rows)))
    summary=dict(project_version='v2.0',release_id=config['release_id'],release_sha256=lock['release_sha256'],
        catalog_frozen_at_utc=lock['frozen_at_utc'],audit_started_at_utc=audit_started,
        core_main=counts(mapped),core_primary=counts([r for r in mapped if r['core_primary_index']]),
        core_supplemental=counts([r for r in mapped if not r['core_primary_index']]),
        catalog_modified_by_audit=False,patient_labels_generated=0,
        metric_scope='observed_drug_composition_only_not_clinical_appropriateness_or_model_performance')
    verify(base,config)
    for n,h in {**inputs,**frozen_files}.items():
        if sha256(base/n)!=h:raise ValueError('Input changed during held-out coverage audit: '+n)
    processed.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    write_jsonl(processed/'core_regimen_coverage_v2.0.jsonl',mapped)
    export_csv(processed/'core_regimen_coverage_v2.0.csv',[{k:v for k,v in r.items() if k not in {'raw_components','source'}} for r in mapped])
    write_json(out/'core_coverage_summary_v2.0.json',summary)
    doc=base/'docs/notes/v2.0/core_coverage_report_v2.0.md'
    lines=['# Core实际治疗组成覆盖核查 v2.0','','版本：v2.0','','更新日期：20260914','',
        '状态：冻结后覆盖核查完成；未生成患者标签。','','## 范围与方法','',
        '核查冻结目录是否包含Core实际记录的完整药物组成。执行前验证目录定义、开发集结果及冻结摘要；运行后复核全部冻结文件。匿名药物不推定身份，缺少组分不补齐，Core结果不参与修改同版目录。','',
        f"目录：{config['release_id']}；内容标识：`{lock['release_sha256']}`。冻结时间UTC：{lock['frozen_at_utc']}；本次核查开始UTC：{audit_started}。",'',
        '## 覆盖结果','','| 核查范围 | 点数 | 组成覆盖 | 身份未明 | 组成未覆盖 | 全部点中覆盖比例 |','| --- | --- | --- | --- | --- | --- |']
    for key,label in [('core_main','全部主候选'),('core_primary','首轮独立索引点'),('core_supplemental','补充主候选')]:
        s=summary[key];c=s['coverage_counts']
        lines.append(f"| {label} | {s['candidates']} | {c.get('composition_covered',0)} | {c.get('identity_unresolved',0)} | {c.get('composition_not_covered',0)} | {s['covered_fraction_of_all']:.1%} |")
    lines+=['','比例分母包含匿名及未覆盖点。组成覆盖不表示适应证、时间情境、分子条件、剂量日程或患者标签正确，不能作为模型准确率。','',
        '## 未覆盖记录','','| 候选编号 | 原始药物 | 状态 |','| --- | --- | --- |']
    zh={'identity_unresolved':'匿名或未规范化药物身份','composition_not_covered':'完整组成未进入冻结目录'}
    for r in mapped:
        if r['coverage_status']!='composition_covered':
            raw=' + '.join(r['raw_slot_name_pattern']).replace('|','\\|')
            lines.append(f"| {r['candidate_id']} | {raw} | {zh[r['coverage_status']]} |")
    lines+=['','## 输出与后续使用','',
        '[逐点覆盖表](../../../data/processed/v2.0/08_core_coverage/core_regimen_coverage_v2.0.csv)及对应JSONL保存原记录与来源。该表属于审计材料，不并入决策前病例输入，也不用于扩展已冻结目录。后续目录扩展须建立独立版本并记录测试治疗已查看的边界。','',
        '运行 `python -B code/scripts/run_v2_0.py coverage` 可重新核查；它会拒绝未冻结或内容已变更的目录。','']
    doc.write_text('\n'.join(lines),encoding='utf-8')
    outputs=[*processed.glob('*'),out/'core_coverage_summary_v2.0.json',doc]
    manifest=dict(project_version='v2.0',phase=PHASE,status='completed',started_utc=audit_started,
        finished_utc=datetime.now(timezone.utc).isoformat(),summary=summary,input_sha256={**inputs,**frozen_files},
        code_sha256={p.relative_to(base).as_posix():sha256(p) for p in sorted([*(base/'code/src').rglob('*.py'),*(base/'code/scripts').glob('*.py'),*(base/'code/tests').rglob('*.py')])},
        output_sha256={p.relative_to(base).as_posix():sha256(p) for p in outputs if p.is_file()})
    write_json(out/'run_manifest.json',manifest)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0
