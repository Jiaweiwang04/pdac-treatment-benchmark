"""Deterministic patient-level development/Core split with an immutable rerun lock."""
import hashlib
import json
import platform
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from .audit import write_csv,write_json,write_jsonl
from .candidate_review import read_jsonl
from .layout import resolve_paths
from .source import sha256

BASE=Path(__file__).resolve().parents[4]
PHASE='06_patient_split'
SPLITS=('development','core_test','extension_only')
NAMES={'development':'开发集','core_test':'Core测试侧','extension_only':'非主集合独立保留'}


def digest_object(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def quota_sample(items,total,seed,namespace):
    """Proportional Hamilton allocation and fixed SHA256 order, independent of row order."""
    if total<0 or total>len(items):
        raise ValueError('Sample size exceeds eligible population')
    if len({tuple(r['patient_key']) for r in items})!=len(items):
        raise ValueError('Sampling units must be unique patients')
    if not items:
        return set(),{}
    strata=defaultdict(list)
    for r in items:
        strata[tuple(r['stratum'])].append(tuple(r['patient_key']))
    n=len(items)
    quotas={s:total*len(ps)//n for s,ps in strata.items()}
    order=sorted(strata,key=lambda s:(-(total*len(strata[s])%n),s))
    for s in order[:total-sum(quotas.values())]:
        quotas[s]+=1
    chosen=set()
    for s,ps in strata.items():
        ordered=sorted(ps,key=lambda pk:(digest_object([seed,namespace,list(pk)]),pk))
        chosen.update(ordered[:quotas[s]])
    if len(chosen)!=total:
        raise ValueError('Sampling allocation did not sum to requested size')
    return chosen,quotas


def earliest_main_candidates(registry):
    grouped=defaultdict(list)
    for c in registry:
        if c['candidate_role']=='main_observed_regimen':
            if c['t0_day'] is None:
                raise ValueError('Main candidate has unknown t0')
            grouped[tuple(c['patient_key'])].append(c)
    return {pk:min(cs,key=lambda c:(c['t0_day'],c['candidate_id'])) for pk,cs in grouped.items()}


def verify_lock(path,proposed):
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=proposed:
        raise ValueError('Frozen split differs from current inputs or policy; do not overwrite. Review a versioned revision first.')


def check_identity_isolation(registry,assignments,event_index):
    """Validate identities across all roles, including future/context records."""
    owners=defaultdict(set)
    for c in registry:
        split=assignments[tuple(c['patient_key'])]['split']
        owners[('patient_id',c['patient_key'][1])].add(split)
        owners[('source_record_id',c['source_record_id'])].add(split)
        for ids in c.get('temporal_partition',{}).values():
            for eid in ids:
                owners[('event_id',eid)].add(split)
                e=event_index.get(eid)
                if e and e['kind']=='ngs_report' and e['facts'].get('cpt_genie_sample_id'):
                    owners[('sample_id',e['facts']['cpt_genie_sample_id'])].add(split)
    # Some retained out-of-scope records have no candidate temporal partition.
    # Audit the complete patient event index as well, so those records are covered.
    for eid,e in event_index.items():
        pk=tuple(e.get('patient_key',[]))
        if pk not in assignments:
            continue
        split=assignments[pk]['split']
        owners[('event_id',eid)].add(split)
        if e.get('source_record_id'):
            owners[('source_record_id',e['source_record_id'])].add(split)
        if e['kind']=='ngs_report' and e['facts'].get('cpt_genie_sample_id'):
            owners[('sample_id',e['facts']['cpt_genie_sample_id'])].add(split)
    collisions=[{'identity_kind':kind,'identity':key,'splits':sorted(v)} for (kind,key),v in owners.items() if len(v)>1]
    if collisions:
        raise ValueError('Patient/source/event/sample identity crosses splits: '+json.dumps(collisions[:3]))
    return {'cross_split_identity_collisions':0,'identities_checked':dict(Counter(kind for kind,key in owners))}


def build(base,processed,out,config):
    expected={'active_track':'A','track_b_status':'frozen','main_patient_population_expected':515,
              'core_test_patients':80,'pilot_patients':25,'pilot_is_development_subset':True,
              'index_candidate_rule':'earliest_main_t0_then_candidate_id',
              'outcomes_or_labels_used_for_selection':False,'molecular_features_used_for_selection':False,
              'sampling_algorithm':'sha256_order_with_largest_remainder_stratum_quotas',
              'stratification':['institution','earliest_main_candidate_scope_at_t0']}
    if any(config.get(k)!=v for k,v in expected.items()):
        raise ValueError('Split configuration differs from approved scope')
    inputs={}
    def manifest(relative):
        p=base/relative
        m=json.loads(p.read_text(encoding='utf-8'))
        if m['status']!='completed':
            raise ValueError('Incomplete upstream stage: '+relative)
        inputs[relative]=sha256(p)
        return m
    upstream=manifest('code/results/v2.0/05_candidate_cohort/run_manifest.json')
    timeline=manifest('code/results/v2.0/02_decision_points/run_manifest.json')
    def verified(relative,m):
        p=base/relative
        checksum=sha256(p)
        if checksum!={**m.get('input_sha256',{}),**m.get('output_sha256',{})}.get(relative):
            raise ValueError('Input changed after upstream run: '+relative)
        inputs[relative]=checksum
        return read_jsonl(p)
    registry_name='data/processed/v2.0/05_candidate_cohort/candidate_role_registry_v2.0.jsonl'
    registry=verified(registry_name,upstream)
    patient_name='data/processed/v2.0/01_source_audit/clinical_records/patient_level_dataset.jsonl'
    patient_records=verified(patient_name,upstream)
    events=verified('data/processed/v2.0/02_decision_points/timeline_events_v2.0.jsonl',timeline)
    molecular=verified('data/processed/v2.0/02_decision_points/molecular_samples_v2.0.jsonl',timeline)
    label_path=base/'code/config/v2.0/treatment_labels.json'
    inputs[label_path.relative_to(base).as_posix()]=sha256(label_path)
    labels=json.loads(label_path.read_text(encoding='utf-8'))
    if labels['evidence_cutoff_date']!=config['evidence_cutoff_date']:
        raise ValueError('Split metadata and confirmed label knowledge cutoff disagree')
    patient_lookup={(r['fields']['cohort'],r['fields']['record_id']):r for r in patient_records}
    indices=earliest_main_candidates(registry)
    if len(indices)!=config['main_patient_population_expected']:
        raise ValueError('Main patient population changed; review split scope before resampling')
    all_keys=sorted({tuple(c['patient_key']) for c in registry})
    if not set(all_keys)<=patient_lookup.keys():
        raise ValueError('Candidate patient lacks source patient record')
    items=[]
    for pk,c in sorted(indices.items()):
        institution=patient_lookup[pk]['fields'].get('institution') or 'Unknown'
        items.append({'patient_key':list(pk),'institution':institution,
                      'stratum':[institution,c['scope_at_t0']],'index_candidate_id':c['candidate_id']})
    core,core_quota=quota_sample(items,config['core_test_patients'],config['split_seed'],'core_test')
    development=[r for r in items if tuple(r['patient_key']) not in core]
    pilot,pilot_quota=quota_sample(development,config['pilot_patients'],config['split_seed'],'pilot')
    if core&pilot:
        raise ValueError('Pilot patient overlaps Core')
    item_by_key={tuple(r['patient_key']):r for r in items}
    by_patient=defaultdict(list)
    for c in registry:
        by_patient[tuple(c['patient_key'])].append(c)
    assignments={}
    for pk in all_keys:
        info=item_by_key.get(pk)
        split='core_test' if pk in core else 'development' if pk in indices else 'extension_only'
        assignments[pk]={'patient_key':list(pk),'institution':patient_lookup[pk]['fields'].get('institution') or 'Unknown',
            'split':split,'split_name_zh':NAMES[split],'pilot_member':pk in pilot,
            'index_candidate_id':indices[pk]['candidate_id'] if pk in indices else None,
            'index_t0_day':indices[pk]['t0_day'] if pk in indices else None,
            'stratum':info['stratum'] if info else None,
            'main_candidates':sum(c['candidate_role']=='main_observed_regimen' for c in by_patient[pk]),
            'all_registry_records':len(by_patient[pk]),'source':patient_lookup[pk]['source'],
            'selection_rule':config['index_candidate_rule'] if info else 'no_main_candidate_not_promoted',
            'expert_review_completed':False,'training_labels_available':False}
    selection_inputs={registry_name:inputs[registry_name],patient_name:inputs[patient_name]}
    lock={'split_version':config['split_version'],'config_sha256':digest_object(config),
          'selection_input_sha256':selection_inputs,
          'assignments':[assignments[pk] for pk in sorted(assignments)],
          'core_index_candidate_ids':sorted(indices[pk]['candidate_id'] for pk in core),
          'pilot_index_candidate_ids':sorted(indices[pk]['candidate_id'] for pk in pilot)}
    # Check before writing any derived rows. An existing lock may only be reproduced exactly.
    verify_lock(processed/'patient_split_lock_v2.0.json',lock)
    event_index={e['event_id']:e for e in events}
    isolation=check_identity_isolation(registry,assignments,event_index)
    sample_index={r['sample_id']:r for r in molecular}
    snapshots=[]
    for pk,c in sorted(indices.items()):
        previous_ngs=[event_index[eid] for eid in c['ngs_report_before']]
        if not previous_ngs or any(e['available_day'] is None or e['available_day']>=c['t0_day'] for e in previous_ngs):
            raise ValueError('Index candidate NGS is not strictly before t0')
        sample_ids=sorted({e['facts']['cpt_genie_sample_id'] for e in previous_ngs if e['facts'].get('cpt_genie_sample_id')})
        linked=[sample_index[sid] for sid in sample_ids if sid in sample_index]
        if any(s['patient_id']!=pk[1] for s in linked):
            raise ValueError('Molecular sample attributed to another patient')
        genes=sorted({m['fields']['Hugo_Symbol'] for s in linked for m in s['mutations'] if m['fields'].get('Hugo_Symbol')})
        gene_variants=sorted({(m['fields'].get('Hugo_Symbol',''),m['fields'].get('HGVSp_Short','')) for s in linked for m in s['mutations']})
        prior_paths=[event_index[eid] for eid in c['temporal_partition']['event_before_availability_unconfirmed']
                     if eid in event_index and event_index[eid]['kind']=='pathology_procedure']
        hists=sorted({s['invasive_histology'] for e in prior_paths for s in e['facts']['specimens'] if s['invasive']=='Yes' and s['cancer_type']=='Pancreatic Cancer'})
        a=assignments[pk]
        snapshots.append({'patient_key':list(pk),'candidate_id':c['candidate_id'],'split':a['split'],'pilot_member':a['pilot_member'],
            'institution':a['institution'],'scope_at_index':c['scope_at_t0'],'t0_day':c['t0_day'],
            'ngs_report_event_ids':c['ngs_report_before'],'ngs_report_days':[e['available_day'] for e in previous_ngs],
            'ngs_sample_ids':sample_ids,'unlinked_sample_ids':[sid for sid in sample_ids if sid not in sample_index],
            'oncotree_codes':c['cohort_review']['predecision_oncotree_codes'],
            'panel_ids':sorted({e['facts'].get('cpt_seq_assay_id','') for e in previous_ngs}),
            'recorded_mutation_genes':genes,'recorded_gene_protein_changes':gene_variants,
            'prior_pathology_reports':len(prior_paths),'pancreatic_histologies_raw':hists,
            'mutation_summary_is_actionability_label':False,'no_record_is_negative_result':False,
            'pathology_report_availability':'unconfirmed_procedure_date_only',
            'candidate_source':c['source']})
    snapshot_by_id={s['candidate_id']:s for s in snapshots}
    revised=[]
    for c in registry:
        a=assignments[tuple(c['patient_key'])]
        primary=c['candidate_id']==a['index_candidate_id']
        split_info={'split_version':config['split_version'],'patient_split':a['split'],
                    'pilot_patient':a['pilot_member'],'core_primary_index':a['split']=='core_test' and primary,
                    'pilot_primary_index':a['pilot_member'] and primary,
                    'development_main_candidate':a['split']=='development' and c['candidate_role']=='main_observed_regimen',
                    'use_as_supervised_sample':'not_ready_labels_missing',
                    'original_candidate_role':c['candidate_role']}
        revised.append({**c,'patient_split_assignment':split_info})
    if len(revised)!=len(registry) or any(any(after[k]!=v for k,v in before.items()) for before,after in zip(registry,revised)):
        raise ValueError('Split changed or removed an upstream candidate fact')
    processed.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    write_json(processed/'patient_split_lock_v2.0.json',lock)
    write_jsonl(processed/'patient_split_assignments_v2.0.jsonl',[assignments[pk] for pk in all_keys])
    write_jsonl(processed/'candidate_split_registry_v2.0.jsonl',revised)
    write_jsonl(processed/'index_candidate_audit_snapshots_v2.0.jsonl',snapshots)
    patient_flat=[{'patient_id':pk[1],'cohort':pk[0],**{k:a[k] for k in ['institution','split','split_name_zh','pilot_member','index_candidate_id','index_t0_day','main_candidates','all_registry_records']},
                   'index_scope':indices[pk]['scope_at_t0'] if pk in indices else '',
                   'source_file':a['source']['file'],'source_logical_row':a['source']['logical_row']}
                  for pk,a in sorted(assignments.items())]
    write_csv(processed/'patient_split_assignments_v2.0.csv',list(patient_flat[0]),patient_flat)
    flat=[]
    for c in revised:
        a=c['patient_split_assignment'];pk=tuple(c['patient_key'])
        flat.append({'candidate_id':c['candidate_id'],'patient_id':pk[1],'cohort':pk[0],
            'institution':assignments[pk]['institution'],'patient_split':a['patient_split'],
            'candidate_role':c['candidate_role'],'t0_day':c['t0_day'],'cancer_seq':c['cancer_seq'],
            'scope_at_t0':c['scope_at_t0'],'pilot_patient':a['pilot_patient'],
            'core_primary_index':a['core_primary_index'],'pilot_primary_index':a['pilot_primary_index'],
            'source_file':c['source']['file'],'source_logical_row':c['source']['logical_row'],'expert_label':''})
    for name,rs in [('candidate_split_registry',flat),
        ('development_main_candidates',[r for r in flat if r['patient_split']=='development' and r['candidate_role']=='main_observed_regimen']),
        ('core_held_out_main_candidates',[r for r in flat if r['patient_split']=='core_test' and r['candidate_role']=='main_observed_regimen']),
        ('core_index_candidates',[r for r in flat if r['core_primary_index']]),
        ('pilot_index_candidates',[r for r in flat if r['pilot_primary_index']])]:
        # The two review index lists also expose source-limited pathology and NGS summaries.
        if name in {'core_index_candidates','pilot_index_candidates'}:
            rs=[{**r,'prior_ngs_report_days':' | '.join(map(str,snapshot_by_id[r['candidate_id']]['ngs_report_days'])),
                 'oncotree_codes':' | '.join(snapshot_by_id[r['candidate_id']]['oncotree_codes']),
                 'prior_pathology_reports':snapshot_by_id[r['candidate_id']]['prior_pathology_reports'],
                 'pancreatic_histologies_raw':' | '.join(snapshot_by_id[r['candidate_id']]['pancreatic_histologies_raw']),
                 'pathology_availability':'procedure_before_report_availability_unconfirmed'} for r in rs]
        write_csv(processed/(name+'_v2.0.csv'),list(rs[0]),rs)
    strata_rows=[]
    for stratum in sorted(core_quota):
        ips=[r for r in items if tuple(r['stratum'])==stratum]
        strata_rows.append({'institution':stratum[0],'index_scope':stratum[1],'main_patients':len(ips),
                           'core_patients':core_quota[stratum],'development_patients':len(ips)-core_quota[stratum],
                           'pilot_patients':pilot_quota.get(stratum,0)})
    write_csv(out/'stratum_allocation_v2.0.csv',list(strata_rows[0]),strata_rows)
    groups={'all_main_patients':snapshots,'development':[s for s in snapshots if s['split']=='development'],
            'core_test':[s for s in snapshots if s['split']=='core_test'],'pilot':[s for s in snapshots if s['pilot_member']]}
    distribution=[]
    for name,rs in groups.items():
        categories=defaultdict(Counter)
        for r in rs:
            categories['institution'][r['institution']]+=1
            categories['scope_at_index'][r['scope_at_index']]+=1
            categories['pathology_summary']['explicit_ductal_recorded' if '8500 Ductal adenocarcinoma' in r['pancreatic_histologies_raw'] else 'NOS_recorded_without_explicit_ductal' if '8140 Adenocarcinoma NOS' in r['pancreatic_histologies_raw'] else 'other_or_unrecorded']+=1
            categories['molecular_linkage']['all_report_samples_linked' if r['ngs_sample_ids'] and not r['unlinked_sample_ids'] else 'missing_or_partial_sample_link']+=1
            categories['recorded_mutation_gene'].update(r['recorded_mutation_genes'])
            categories['panel_id'].update(r['panel_ids'])
        for feature,counts in categories.items():
            for value,count in sorted(counts.items()):
                distribution.append({'group':name,'feature':feature,'value':value,'patients':count,'denominator':len(rs),'proportion':count/len(rs)})
    write_csv(out/'split_distribution_audit_v2.0.csv',list(distribution[0]),distribution)
    unrepresented=sorted(set(g for s in snapshots for g in s['recorded_mutation_genes'])-set(g for s in groups['core_test'] for g in s['recorded_mutation_genes']))
    summary={'project_version':'v2.0','phase':PHASE,'split_version':config['split_version'],
        'execution_date':config['execution_date'],'evidence_cutoff_date':config['evidence_cutoff_date'],
        'active_track':'A','track_b_status':'frozen','main_patients':len(indices),'main_candidates':sum(len([c for c in cs if c['candidate_role']=='main_observed_regimen']) for cs in by_patient.values()),
        'registry_patients':len(assignments),'registry_records':len(registry),
        'patient_counts':dict(Counter(a['split'] for a in assignments.values())),
        'registry_record_counts':dict(Counter(c['patient_split_assignment']['patient_split'] for c in revised)),
        'main_candidate_counts':dict(Counter(c['patient_split_assignment']['patient_split'] for c in revised if c['candidate_role']=='main_observed_regimen')),
        'pilot_patients':len(pilot),'pilot_index_candidates':len(pilot),'core_index_candidates':len(core),
        'pilot_patient_all_main_candidates':sum(c['candidate_role']=='main_observed_regimen' and tuple(c['patient_key']) in pilot for c in registry),
        'strata':strata_rows,'isolation':isolation,'core_pilot_patient_overlap':len(core&pilot),
        'main_mutation_genes_not_represented_in_core':unrepresented,
        'molecular_audit_uses_only_index_predecision_report_samples':True,
        'selection_uses_outcomes_labels_or_molecular_features':False,
        'records_deleted':0,'upstream_fields_changed':0,'expert_labels':None,
        'expert_review_completed':False,'final_training_sample_count':None,
        'test_membership_locked':True,'blind_expert_test_completed':False,
        'temporal_or_source_external_test_completed':False}
    write_json(out/'patient_split_summary_v2.0.json',summary)
    return summary,inputs


def write_report(base,s,config):
    pc=s['patient_counts'];mc=s['main_candidate_counts'];rc=s['registry_record_counts']
    institution_rows=[]
    for institution in sorted({r['institution'] for r in s['strata']}):
        rs=[r for r in s['strata'] if r['institution']==institution]
        institution_rows.append('| '+institution+' | '+' | '.join(str(sum(r[k] for r in rs)) for k in ['main_patients','development_patients','core_patients','pilot_patients'])+' |')
    table='\n'.join(institution_rows)
    text=f'''# 开发集与Core测试集划分协议及结果 v2.0

版本：v2.0

更新日期：{s['execution_date']}

状态：患者归属、Core和Pilot首轮审核点已锁定；标签、专家审核与模型实验尚未完成。

## 目的与范围

本研究按患者划分515名主集合患者，包括435名开发患者和80名Core测试患者，再从开发集中抽取25名Pilot患者。主标签继续沿用[四类标签定义](treatment_label_definition_v2.0.md)，知识截止日固定为2026-09-12；划分执行日期为2026-09-13，不改变知识截止日。

规则、证据排序和RAG基线先用开发集进行方法开发；当前没有直接划定监督训练／验证比例。以后若需要监督训练，只能在开发患者内部进一步划分。Core标签及病例改写不能用于提示词调优、规则开发、训练或阈值选择。

## 划分规则与复现

患者为唯一分配单位，使用原始患者键（cohort、record_id）。先确定每名主集合患者最早的主候选，按其机构和该时点的既有疾病情境分层。每层按患者比例分配Core名额，先取整数部分，再按余数从大到小补足80名；余数相同时按层名称排序。层内以固定种子{config['split_seed']}、用途名及患者键计算SHA256，按摘要排序取前若干名。这种固定抽样不依赖输入行顺序、运行日期或随机库版本。Pilot从剩余开发患者中用同一分层规则、独立用途名抽取25名。

首轮Core和Pilot每人各选最早主候选点；同日有多个主候选时按候选编号稳定排序。这里的“最早”是筛选后最早主候选，不等于第一线治疗；不挑选后续疗效更好、标签更简单或资料更多的时点。同一患者其他主候选、进展组、病理、NGS、附录、同日关联和待核查记录全部继承同一归属。Core的其他决策点保留在测试侧，不回流开发。

分层只使用机构及索引点的既有情境分类，尚未证实为当前临床分期的分类仍保持原限制。分子结果及病理分布用于事后审计，不参与选择、不反复换种子追求分布，也不依据标签或用药结局重抽。稀疏层可能没有Core或Pilot名额，不能宣称每个亚组均被覆盖。

运行 `python -B code/scripts/run_v2_0.py split` 重建本阶段；运行 `python -B code/scripts/run_v2_0.py all` 重建七阶段并核对测试、来源及文档。配置见[划分配置](../../../code/config/v2.0/patient_split.json)，名单锁定见[锁定文件](../../../data/processed/v2.0/06_patient_split/patient_split_lock_v2.0.json)。已有锁定与输入、规则或名单不一致时程序报错，不覆盖重抽；需另行讨论有版本记录的修订。锁定是流程与校验控制，不是操作系统访问权限或已完成盲法审核的证明。

## 当前划分结果

| 用途 | 患者数 | 主候选点数 | 首轮审核点数 |
| --- | ---: | ---: | ---: |
| 开发集（含Pilot） | {pc['development']} | {mc['development']} | 尚未开展全量审核 |
| 其中Pilot | {s['pilot_patients']} | {s['pilot_patient_all_main_candidates']} | {s['pilot_index_candidates']} |
| Core测试侧 | {pc['core_test']} | {mc['core_test']} | {s['core_index_candidates']} |

Pilot是开发集子集，不能把三行相加。Core每人一个审核点，共80点；其余Core主候选保留为测试侧补充。全部952条主候选都有患者归属。最终“决策点×候选治疗方案”对数要在方案池形成后统计，80个审核点不等于80条治疗标签。

| 机构 | 主集合患者 | 开发患者 | Core患者 | Pilot患者（开发子集） |
| --- | ---: | ---: | ---: | ---: |
{table}

全部登记池{s['registry_patients']:,}名患者、{s['registry_records']:,}条记录均保留。没有主候选的{pc['extension_only']}名患者保留为extension_only，不自动纳入开发或Core。按患者归属，开发侧共有{rc['development']:,}条各类登记、Core侧{rc['core_test']:,}条、独立保留侧{rc['extension_only']:,}条；这些数字包括待核查及背景资料，不能作为训练样本数。同一个候选的原用途与患者划分是两个字段，划分不改变纳入资格。

## 分布与泄漏核查

对全部主患者及开发、Core、Pilot的最早主候选，核对机构、疾病情境、病理原文类型、在先NGS面板、样本关联和已记录小变异基因的分布，见[分布审计](../../../code/results/v2.0/06_patient_split/split_distribution_audit_v2.0.csv)。分子概况只使用该索引点严格在先NGS所关联的样本；不使用后续样本、全程综合分子阳性标志或后续结局。基因出现仅表示原小变异表有记录，不表示致病、胚系、可操作性、完整检出或方案标签；缺少记录不能当作阴性。CNA、结构变异及全部生物标志物的临床亚组解释尚未完成，不能据此宣称精准治疗亚组均衡。

主患者索引样本中有{len(s['main_mutation_genes_not_represented_in_core'])}种已记录小变异基因在本轮Core索引样本未出现，完整名称位于统计汇总。长尾覆盖缺口如实报告，不偷偷替换Core患者。未来可在与主测试分开的扩展分析中处理，需另定规则。

患者ID、源记录ID、时间轴事件ID及NGS样本ID跨患者归属的冲突为0；Pilot与Core患者交集为0。所有4,411条候选的既有字段保持不变，候选日、NGS日期、病理原文与标签空值均未改写。本轮未使用专家标签、疗效或生存结局来抽样。

开发与测试方法可以共用冻结的公共指南／论文库；不能共用测试病例标注、专家解释、病例改写或患者骨架衍生的问答。今后产生的病例改写、候选方案对及训练示例必须携带patient_key和candidate_id并继承归属。当前完成的是已有PANC记录的身份隔离核查，尚无外部队列实体去重、训练语料审计或通用模型预训练污染检测结果。

## Pilot与Core使用规则

Pilot用于完善病理展示、标签边界及审核流程；完成Pilot修订后，锁定用于Core的标签说明与证据版本，再进行Core专家审核。核心专家人数、独立复核和分歧裁定尚待讨论。若Core病例后续被确认不适于某项评价，应保留原因和原归属，不按模型表现或标签难度补选；任何替补规则先讨论并记录版本。

Track A主实验评价四类标签、证据支持、候选识别及无法判定的处理。本次是同来源队列内、按患者分组的常规测试设计，不等于证据时间外、机构外或独立来源外测试。

## 输出与后续工作

- [全部患者归属名单](../../../data/processed/v2.0/06_patient_split/patient_split_assignments_v2.0.csv)
- [开发集主候选](../../../data/processed/v2.0/06_patient_split/development_main_candidates_v2.0.csv)
- [Core测试侧全部主候选](../../../data/processed/v2.0/06_patient_split/core_held_out_main_candidates_v2.0.csv)
- [Core首轮80点](../../../data/processed/v2.0/06_patient_split/core_index_candidates_v2.0.csv)
- [Pilot首轮25点](../../../data/processed/v2.0/06_patient_split/pilot_index_candidates_v2.0.csv)
- [全部候选及患者归属](../../../data/processed/v2.0/06_patient_split/candidate_split_registry_v2.0.jsonl)
- [索引点病理与NGS核查摘要](../../../data/processed/v2.0/06_patient_split/index_candidate_audit_snapshots_v2.0.jsonl)
- [分层名额](../../../code/results/v2.0/06_patient_split/stratum_allocation_v2.0.csv)、[统计汇总](../../../code/results/v2.0/06_patient_split/patient_split_summary_v2.0.json)、[运行清单](../../../code/results/v2.0/06_patient_split/run_manifest.json)

名单已固定，下一步规范候选治疗方案、整理截止日内的权威证据、为Pilot建立可解释初标，再制作专家标签审核包。本阶段没有生成真实标签、模型输入特征包、专家金标准或模型性能结果。解释文档、配置、代码、中间数据和结果继续按项目目录规范分别保存，原始数据与第一版归档不修改。
'''
    (base/'docs/notes/v2.0/patient_split_protocol_v2.0.md').write_text(text,encoding='utf-8')


def run(config_path):
    config_path=Path(config_path).resolve()
    config=json.loads(config_path.read_text(encoding='utf-8'))
    source=json.loads((BASE/'code/config/v2.0/source.json').read_text(encoding='utf-8'))
    raw,processed,out=resolve_paths(BASE,{**source,**config})
    inventory=json.loads((BASE/source['results_dir']/'source_inventory.json').read_text(encoding='utf-8'))
    def verify_raw():
        if any(sha256(raw/r['file'])!=r['sha256'] for r in inventory):
            raise ValueError('Original raw source changed')
    verify_raw();out.mkdir(parents=True,exist_ok=True)
    manifest={'project_version':'v2.0','phase':PHASE,'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
        'runtime':{'python':platform.python_version(),'platform':platform.platform()},
        'config_file':config_path.relative_to(BASE).as_posix(),'config_sha256':sha256(config_path),
        'code_sha256':{p.relative_to(BASE).as_posix():sha256(p) for p in sorted([*(BASE/'code/src').rglob('*.py'),*(BASE/'code/scripts').glob('*.py'),*(BASE/'code/tests').rglob('*.py')])}}
    write_json(out/'run_manifest.json',manifest)
    try:
        s,inputs=build(BASE,processed,out,config);verify_raw();write_report(BASE,s,config)
        outputs=[*processed.glob('*'),*out.glob('*.csv'),out/'patient_split_summary_v2.0.json',BASE/'docs/notes/v2.0/patient_split_protocol_v2.0.md']
        manifest.update(status='completed',finished_utc=datetime.now(timezone.utc).isoformat(),summary=s,input_sha256=inputs,
                        raw_source_files_rechecked=len(inventory),output_sha256={p.relative_to(BASE).as_posix():sha256(p) for p in outputs if p.is_file()})
        write_json(out/'run_manifest.json',manifest)
        printed={k:v for k,v in s.items() if k!='main_mutation_genes_not_represented_in_core'}
        printed['unrepresented_recorded_mutation_gene_count']=len(s['main_mutation_genes_not_represented_in_core'])
        print(json.dumps(printed,ensure_ascii=False,indent=2));return 0
    except Exception as error:
        manifest.update(status='failed',finished_utc=datetime.now(timezone.utc).isoformat(),error=str(error))
        write_json(out/'run_manifest.json',manifest)
        raise
