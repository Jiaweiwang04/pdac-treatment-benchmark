"""Build proposed Pilot labels and time-qualified review inputs from frozen development data."""
import json,sys,hashlib,copy,argparse
from pathlib import Path
from collections import Counter

def build(base,output):
    B=Path(base).resolve();output=Path(output).resolve()
    sys.path.insert(0,str(B/'code/src'))
    from pdac_benchmark.v2_0.treatment_catalog import load,map_record
    from pdac_benchmark.v2_0.catalog_release import verify
    def read(n):
        with (B/n).open(encoding='utf-8') as f:
            for l in f:yield json.loads(l)
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    cfg=load(B/'code/config/v2.0/treatment_catalog.json');lock=verify(B,cfg)
    aliases=load(B/cfg['alias_definitions'])
    cs=[r for r in read('data/processed/v2.0/06_patient_split/candidate_split_registry_v2.0.jsonl') if r['patient_split_assignment']['pilot_primary_index']]
    pilot_keys={tuple(c['patient_key']) for c in cs}
    events=[e for e in read('data/processed/v2.0/02_decision_points/timeline_events_v2.0.jsonl') if tuple(e['patient_key']) in pilot_keys]
    snap=[s for s in read('data/processed/v2.0/06_patient_split/index_candidate_audit_snapshots_v2.0.jsonl') if s['pilot_member']]
    pks={tuple(c['patient_key']) for c in cs}
    clinical={}
    for p in (B/'data/processed/v2.0/01_source_audit/clinical_records').glob('*.jsonl'):
        clinical[p.stem]=[r for r in read(p.relative_to(B)) if tuple(r['source']['primary_key_values'][:2]) in pks]
    record={r['record_id']:r for rs in clinical.values() for r in rs}
    sids={sid for s in snap for sid in s['ngs_sample_ids']}
    mol={m['sample_id']:m for m in read('data/processed/v2.0/02_decision_points/molecular_samples_v2.0.jsonl') if m['sample_id'] in sids}
    def name(ds):return ' + '.join(d['name_raw'].split('(')[0] for d in ds)
    cases=[]
    for i,c in enumerate(cs,1):
        t0=c['t0_day'];pk=c['patient_key'];seq=c['cancer_seq']
        es=[e for e in events if e['patient_key']==pk]
        ngs=[e for e in es if e['event_id'] in c['ngs_report_before']]
        assert ngs and all(e['available_day']<t0 and e['cancer_seq']==seq for e in ngs)
        pre=[];post=[];same=[];unknown=[]
        for e in es:
            dest=unknown if e['event_day'] is None else pre if e['event_day']<t0 else same if e['event_day']==t0 else post
            dest.append(e)
        sort=lambda rs: sorted(rs,key=lambda e:(e['event_day'] if e['event_day'] is not None else 10**9,e['event_id']))
        pre=sort(pre);post=sort(post);same=sort(same)
        regimes=[]
        for e in pre:
            if e['kind']!='regimen_start':continue
            d=copy.deepcopy(e)
            d['facts']['components']=[x for x in d['facts']['components'] if x['start_day'] is not None and x['start_day']<t0]
            for x in d['facts']['components']:
                if x['end_day'] is None or x['end_day']>=t0:x['end_day']=None
            regimes.append(d)
        path=[dict(event=e,raw=record[e['source_record_id']]) for e in pre if e['kind']=='pathology_procedure']
        patient=next(r for r in clinical['patient_level_dataset'] if r['fields']['record_id']==pk[1])
        cancer=next(r for r in clinical['cancer_level_dataset_index'] if r['fields']['record_id']==pk[1] and r['fields']['ca_seq']==seq)
        x=dict(case_id=f'PILOT-{i:02d}',patient_key=pk,candidate_id=c['candidate_id'],t0_day=t0,cancer_seq=seq,
            scope_at_t0=c['scope_at_t0'],candidate=c,patient=patient,cancer=cancer,
            ngs_reports=ngs,molecular_samples=[mol[e['facts']['cpt_genie_sample_id']] for e in ngs if e['facts']['cpt_genie_sample_id'] in mol],
            pathology_before=path,regimens_before=regimes,events_before=pre,events_same_day=same,events_after=post,events_unknown=unknown,
            all_clinical_records={k:[r for r in rs if r['fields']['record_id']==pk[1]] for k,rs in clinical.items()},
            proposed_label=None,reviewed_label=None,review_status='pending_review')
        cases.append(x)
    
    families={f['family_id']:f for f in load(B/cfg['family_definitions'])}
    sources={e['evidence_id']:e for e in load(B/cfg['source_ledger'])}
    family_index={tuple(f['components']):f for f in families.values()}
    selection_path=Path(__file__).resolve().parents[3]/'config/v2.0/pilot_review_selection.json'
    selections=load(selection_path)['selection']
    assert len(cases)==len(selections)==25
    LABELS={'SUPPORTED':'支持匹配','CONDITIONAL':'条件性匹配','MISMATCH':'有依据不匹配','INDETERMINATE':'无法判定'}
    def shortname(ds):return '＋'.join(d['name_raw'].split('(')[0] for d in ds)
    def refs(c):return [e['event_id'] for e in c['ngs_reports']]+[e['event_id'] for e in c['regimens_before'] if e['cancer_seq']==c['cancer_seq']]
    def annotate(c,fid):
        rs=[e for e in c['regimens_before'] if e['cancer_seq']==c['cancer_seq']]
        drugs={d['name_raw'].split('(')[0] for e in rs for d in e['facts']['components']}
        gem='Gemcitabine HCL' in drugs; iri='Irinotecan HCL' in drugs; ox='Oxaliplatin' in drugs
        masked=any(d['masked'] for e in rs for d in e['facts']['components'])
        kras=[m for s in c['molecular_samples'] for m in s['mutations'] if m['fields']['Hugo_Symbol']=='KRAS']
        variant='、'.join(m['fields']['HGVSp_Short'] for m in kras)
        label='CONDITIONAL';unknown=[];unmet=[];matched=[]
        context='';why='';ev=[];factrefs=refs(c)
        prior_text='；'.join(f"D{e['event_day']} {shortname(e['facts']['components'])}" for e in rs) or '未记录同癌症既往系统治疗'
        mets=c['scope_at_t0']!='baseline_unresectable_advanced_current_context_unconfirmed'
        direct=c['scope_at_t0']=='metastatic_at_diagnosis'
        # Clinical observations retain their source time qualifications; no post-index response is consulted.
        pd=[e for e in c['events_before'] if e['kind'] in ['oncology_assessment','imaging'] and 'Progressing' in str(e['facts']) and (not rs or e['event_day']>rs[-1]['event_day'])]
        if pd:factrefs.append(pd[-1]['event_id'])
        if fid=='OBS':
            label='INDETERMINATE';context='原始实际药物记录的身份与证据可解释性'
            why='原记录为'+shortname(c['candidate']['observed_action_drugs'])+'。'
            why+= '匿名药物身份不能恢复，无法定位完整方案及适用证据。' if any(d['masked'] for d in c['candidate']['observed_action_drugs']) else '完整组成未进入冻结目录；不能补写缺失组分或借用近似方案的疗效证据。'
            unknown=['完整方案身份或本组成的适用证据'];factrefs=[c['candidate']['source_record_id']]
        else:
            f=families[fid];ev=f['evidence_ids'];context=f['required_context_zh']
            if fid=='GEM_NIMO':
                if kras:
                    label='MISMATCH';why=f'在先NGS记录KRAS {variant}，与所评价的KRAS野生型路径存在明确冲突。该判断不推广至尼妥珠单抗的其他联合方案。'
                    unmet=['KRAS野生型'];factrefs=[e['event_id'] for e in c['ngs_reports']]+[m['source'] for m in kras]
                else:
                    label='INDETERMINATE';why='未有可确认的KRAS野生型结论；既往已接受治疗，当前证据与经治情境的对应关系亦未建立。小变异表缺少KRAS记录不能代替野生型检测结论。'
                    unknown=['KRAS完整检测结论','经治情境下的适用路径']
            elif fid=='DARA':
                matched=['成人','同癌症既往系统治疗'] if rs else ['成人']
                if rs and direct:
                    label='SUPPORTED';why='初诊转移性胰腺腺癌的记录与同癌症既往系统治疗均有来源，符合所引美国适应证的相关条件；该路径不限定特定RAS位点。'
                else:
                    unknown=['确认候选日仍属转移性胰腺腺癌'];why='已有同癌症系统治疗史。若确认当前仍为转移性胰腺腺癌，则可按该美国适应证评价；派生疾病情境或初诊不可切除状态不能单独完成这一确认。'
            elif fid in ['PEMBRO','TDXD','OLAPARIB','GEM_CIS','RUCAPARIB']:
                if fid=='PEMBRO':
                    unknown=['可定位至时点前的MSI-H/dMMR，或经验证的TMB高结果','对应路径要求的经治、进展及替代方案情境']
                    why='尚无时点前明确的MSI-H/dMMR或合格TMB高结论。若相应标志物和路径条件得到确认，可形成证据匹配；不能用PD-L1、突变条数或后续MMR结果代替。'
                elif fid=='TDXD':
                    unknown=['HER2 IHC 3+','经治且无满意替代方案'];why='在先样本有ERBB2离散拷贝数2记录，可作为进一步核查线索，但不能替代HER2 IHC 3+。若IHC及后线条件均获确认，可按泛瘤种路径评价。'
                    factrefs += [s['cna_source'] for s in c['molecular_samples']]
                else:
                    selected=[m for s in c['molecular_samples'] for m in s['mutations'] if m['fields']['Hugo_Symbol'] in ['BRCA1','BRCA2','PALB2','ATM']]
                    variant_text='；'.join(m['fields']['Hugo_Symbol']+' '+m['fields']['HGVSp_Short'] for m in selected)
                    why='在先记录'+variant_text+'；当前仅保留原变异，不视作已确认的致病或胚系结果。'
                    if fid=='GEM_CIS':
                        unknown=['胚系BRCA1/2或PALB2致病变异','与所引晚期治疗研究匹配的既往治疗情境']
                        why+='所引随机二期研究纳入未经治疗的晚期病例；本例已有晚期含铂治疗记录，当前经治路径未建立。ATM改变不能替代BRCA/PALB2条件。';label='INDETERMINATE'
                    elif fid=='OLAPARIB':
                        unknown=['胚系BRCA1/2致病变异','转移性一线含铂至少16周且无进展的维持时点']
                        why+='还需核实一线含铂时长及无进展维持情境，不能把既往任何含铂暴露等同于POLO条件。'
                    else:
                        unknown=['符合研究要求的BRCA1/2或PALB2致病变异及胚系或体细胞来源','铂敏感且进入维持阶段']
                        why+='若确认相应致病变异和铂敏感维持情境，可讨论研究性路径；不等同于常规维持推荐。'
                    factrefs += [m['source'] for m in selected]
                    # A documented later-line progression is incompatible with an immediate maintenance label;
                    # deficient variant interpretation also precludes confidently assigning MISMATCH to every path.
                    if fid in ['OLAPARIB','RUCAPARIB'] and pd:
                        label='INDETERMINATE';why+='候选前另有进展记录，本时点能否对应维持策略未建立，现不能形成可靠的条件性匹配。'
            elif fid in ['NIVO_IPI','GEM_NAB_NIVO']:
                label='INDETERMINATE';unknown=['能够支持本情境的正向研究路径']
                why='该研究有已发表人体结果，但双免疫组未观察到客观缓解，不能凭已使用或存在论文给出研究性支持。' if fid=='NIVO_IPI' else '该三药一期研究的总体结论不支持进一步研究；不能将化疗双药的依据转移给加入纳武利尤单抗后的三药组合。'
            elif fid=='CAP_ERL':
                matched=['有吉西他滨暴露'] if gem else []
                unknown=['确认吉西他滨失败后的后线情境','确认时点前评估及癌症归属']
                why='已有吉西他滨用药记录；若确认其失败后的晚期治疗情境，可按所引小规模二期研究讨论。该路径不要求EGFR突变阳性。'
                if not gem:label='INDETERMINATE';why='现有治疗记录尚不能定位到吉西他滨失败后的研究路径。'
            elif fid=='NABPLAGEM':
                unknown=['确认属于初治转移性胰腺腺癌'];why='未记录同癌症既往系统治疗。若核实初治转移性情境，可讨论此单臂探索方案；药物三联不等同于标准双药方案。'
            elif fid in ['FOLFIRINOX','NALIRIFOX','S1','GEMCAP']:
                unknown=['确认当前疾病情境','确认初治或符合对应一线研究的治疗史'];why='当前登记中未记录同癌症既往系统治疗，但未记录不等于完整确认初治。若当前情境及治疗史核实符合所引一线研究，可支持相应方案。'
                if fid=='GEMCAP':why+='原研究与合并分析的总生存结论分别保留。'
                if rs:
                    label='INDETERMINATE';unknown=['与本次经治状态对应的适用路径'];why='已有同癌症系统治疗暴露，本次的加药、减强度或再挑战意图未明确，不能直接套用初治研究。'
            elif fid in ['GEM_NAB','GEM_PAC','GEM']:
                if not rs:
                    unknown=['确认初治转移性情境'];why='无已记录的同癌症既往系统治疗；若核实初治及当前转移性情境，可按一线证据评价。'
                elif gem and fid=='GEM_NAB':
                    label='INDETERMINATE';unknown=['继续、加药或再挑战的策略意图及对应证据'];why='既往已有吉西他滨类暴露，本次是继续、加药或再挑战尚未明确，不能直接套用初治或FOLFIRINOX失败后的推荐。'
                elif iri and ox:
                    matched=['已有普通伊立替康、奥沙利铂及氟尿嘧啶暴露'];unknown=['确认完整既往方案及其失败后的后线情境','确认候选日疾病状态']
                    why='存在普通伊立替康、奥沙利铂及氟尿嘧啶暴露；若完整方案及其失败后的情境获得确认，可按相应后线条款评价。'
                    if 'Leucovorin' not in drugs:why+='原记录未见亚叶酸，不能自行命名为完整FOLFIRINOX。'
                else:
                    label='INDETERMINATE';unknown=['既往治疗身份及对应后线证据'];why='既往治疗记录尚不能明确对应所引一线或后线适用路径。'
            elif fid=='NALIRI_FF':
                if gem:
                    matched=['有吉西他滨暴露'];unknown=['确认吉西他滨之后需要后续治疗的情境','确认当前转移性疾病状态']
                    why='已有吉西他滨类暴露，具备核对该后线路径的基础；需确认当前治疗情境。不能用普通伊立替康的既往使用替代脂质体制剂身份。'
                else:
                    label='INDETERMINATE';unknown=['匿名既往治疗是否含吉西他滨'];why='既往疗程含匿名组分，不能确认吉西他滨暴露，也不能据未记录判定其从未使用。'
            elif fid=='FOLFIRI':
                if gem:
                    unknown=['对应吉西他滨后线情境','脂质体伊立替康联合方案不可及的替代使用路径'];why='吉西他滨暴露已记录；若符合该后线及替代使用路径，可按指南评价普通伊立替康联合方案。'
                    if iri:label='INDETERMINATE';why+='同时已有普通伊立替康暴露，再使用的具体路径尚未建立。'
                else:
                    label='INDETERMINATE';unknown=['本次再用普通伊立替康的适用依据'];why='已有普通伊立替康暴露，未建立当前再用FOLFIRI的具体证据路径；不能仅凭药物组成一致判为支持。'
            elif fid=='OX_FF':
                label='INDETERMINATE';unknown=['具体给药日程','冲突试验结果与本病例的对应关系'];why='相同药物组成可对应不同给药日程；OFF与mFOLFOX6试验结论存在差异，当前未定义可判定的变体，不能给出统一正向标签。'
            elif fid=='CAP':
                label='INDETERMINATE';unknown=['本次维持、减强度或后线策略的适用证据'];why='有历史单药人体证据，但本次治疗的策略意图和当前证据路径未建立。不能把前序稳定或实际使用直接解释为维持治疗支持。'
            elif fid=='FU':
                unknown=['确认相应后线单药治疗路径'];why='已有同癌症系统治疗史；若确认本次采用指南所述后线单药路径，可进行匹配评价。原药名不能确定给药日程。'
            else:raise ValueError('No reviewed annotation rule '+fid)
        assert why and (label!='CONDITIONAL' or unknown) and (label!='MISMATCH' or unmet)
        return dict(assessment_context=context,proposed_label=label,proposed_label_zh=LABELS[label],rationale=why,
            matched_conditions=matched,unmet_conditions=unmet,unknown_conditions=unknown,
            conditional_statement=('若'+ '、'.join(unknown)+'得到符合路径的确认，则可支持所评价情境。') if label=='CONDITIONAL' else None,
            mismatch_reason=why if label=='MISMATCH' else None,indeterminate_reason=why if label=='INDETERMINATE' else None,
            evidence_ids=ev,patient_fact_refs=factrefs,prior_regimen_summary=prior_text,
            reviewed_label=None,reviewer_id=None,reviewed_at=None,review_comment=None,review_status='pending_review')
    pairs=[]
    for c,selection in zip(cases,selections):
        assert c['candidate_id']==selection['candidate_id'] and c['case_id']==selection['case_id']
        fs=selection['regimen_ids'];assert 6<=len(fs)<=8 and len(fs)==len(set(fs))
        mapped=map_record({**c['candidate'],'regimen_components_full_course':c['candidate']['observed_action_drugs']},aliases,family_index)
        course=map_record(c['candidate'],aliases,family_index)
        for j,fid in enumerate(fs,1):
            p=dict(pair_id=f"{c['case_id']}-T{j:02d}",case_id=c['case_id'],patient_key=c['patient_key'],candidate_id=c['candidate_id'],
                t0_day=c['t0_day'],patient_split='development',candidate_role='main_observed_regimen',
                regimen_id=fid if fid!='OBS' else 'OBS_'+c['case_id'],catalog_family_id=fid if fid!='OBS' else None,
                regimen_display_name=families[fid]['name_zh'] if fid!='OBS' else shortname(c['candidate']['observed_action_drugs']),
                use_context=families[fid]['evaluation_context'] if fid!='OBS' else None,
                observed_regimen=fid==mapped['composition_family_id'] or fid=='OBS',
                matches_full_course_composition=fid==course['composition_family_id'] if fid!='OBS' else None,
                catalog_release_id=cfg['release_id'],catalog_release_sha256=lock['release_sha256'],
                evidence_cutoff_date=cfg['evidence_cutoff_date'],label_definition_version='v2.0',
                annotation_status='proposed_for_expert_review',**annotate(c,fid))
            pairs.append(p)
        c['pair_ids']=[p['pair_id'] for p in pairs if p['case_id']==c['case_id']]
        assert mapped['composition_family_id'] in fs or 'OBS' in fs,'Observed treatment omitted '+c['case_id']
    P=output/'data/processed/v2.0/09_pilot_review';P.mkdir(parents=True,exist_ok=True)
    def write_jsonl(p,rs):p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rs),encoding='utf-8')
    write_jsonl(P/'pilot_label_pairs_v2.0.jsonl',pairs)
    # Full clinical evidence stays a traceability artifact; it is never the model input.
    write_jsonl(P/'pilot_case_source_records_v2.0.jsonl',cases)
    used=sorted({e for p in pairs for e in p['evidence_ids']})
    write_jsonl(P/'pilot_evidence_sources_v2.0.jsonl',[sources[e] for e in used])
    summary=dict(project_version='v2.0',patients=len(cases),decision_points=len(cases),pairs=len(pairs),
        pairs_per_patient=dict(Counter(len(c['pair_ids']) for c in cases)),
        proposed_label_counts=dict(Counter(p['proposed_label'] for p in pairs)),
        use_context_counts=dict(Counter(p['use_context'] or 'unresolved' for p in pairs)),
        catalog_families=len({p['catalog_family_id'] for p in pairs if p['catalog_family_id']}),
        observed_regimen_pairs=sum(p['observed_regimen'] for p in pairs),
        pathology_reports_before_procedure=sum(len(c['pathology_before']) for c in cases),pathology_specimens_before_procedure=sum(len(p['event']['facts']['specimens']) for c in cases for p in c['pathology_before']),
        evidence_sources=len(used),expert_reviews_completed=0,adjudications_completed=0,
        expert_count=2,proposed_labels_visible=True,gold_standard_created=False,
        catalog_release_sha256=lock['release_sha256'])
    O=output/'code/results/v2.0/09_pilot_review';O.mkdir(parents=True,exist_ok=True)
    (O/'pilot_review_summary_v2.0.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    
    
    # Whitelist decision material; raw longitudinal fields never become model inputs.
    inputs=[]
    for c in cases:
        cf=c['cancer']['fields']
        x={k:c[k] for k in ['case_id','patient_key','candidate_id','t0_day','cancer_seq','scope_at_t0']}
        x['diagnosis']={k:cf[k] for k in ['age_dx','ca_d_site','ca_histology','stage_dx']}
        x['diagnosis_source']=c['cancer']['source']
        x['sex']=c['patient']['fields'].get('naaccr_sex_code','')
        x['ngs_reports']=c['ngs_reports']
        x['pathology_procedures']=[p['event'] for p in c['pathology_before']]
        x['prior_treatments']=[]
        for e in c['regimens_before']:
            if e['cancer_seq']!=c['cancer_seq']:continue
            z={k:e[k] for k in ['event_id','event_day','available_day','cancer_seq','cancer_attribution','source']}
            z['components']=e['facts']['components'];x['prior_treatments'].append(z)
        x['clinical_events_before']=[e for e in c['events_before'] if e['kind'] in ['imaging','oncology_assessment','tumor_marker_collection','mmr_report']]
        x['radiation_starts_before']=[dict(event_id=e['event_id'],event_day=e['event_day'],available_day=e['available_day'],source=e['source'],radiation_type=e['facts'].get('rt_type')) for e in c['events_before'] if e['kind']=='radiation_start' and e['cancer_seq']==c['cancer_seq']]
        x['molecular_samples']=[{k:s.get(k) for k in ['sample_id','mutations','structural_variants','cna_values','panel_assignments','coverage_interpretation','source','cna_source']} for s in c['molecular_samples']]
        x['time_qualification']='procedure_or_visit_before_t0_does_not_confirm_report_availability'
        inputs.append(x)
    write_jsonl(P/'pilot_decision_inputs_v2.0.jsonl',inputs)
    write_jsonl(P/'pilot_independent_reviews_v2.0.jsonl',[dict(pair_id=p['pair_id'],expert_id=expert,reviewed_label=None,review_comment=None,reviewed_at=None,review_status='pending_review') for p in pairs for expert in ['expert_1','expert_2']])
    write_jsonl(P/'pilot_adjudications_v2.0.jsonl',[dict(pair_id=p['pair_id'],expert_1_label=None,expert_2_label=None,final_label=None,adjudication_reason=None,adjudicator=None,adjudicated_at=None,status='pending_independent_reviews') for p in pairs])
    summary['small_variant_records']=sum(len(s['mutations']) for c in cases for s in c['molecular_samples'])
    summary['independent_review_slots']=2*len(pairs)
    summary['compiled_date']='2026-09-15'
    summary['open_scope_items']=['ROS1_fusion_function_and_candidate_path_not_adjudicated','historical_calendar_and_contemporary_availability_unconfirmed']
    (O/'pilot_review_summary_v2.0.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    manifest=dict(project_version='v2.0',catalog_release_sha256=lock['release_sha256'],input_sha256={},output_sha256={})
    paths=['data/processed/v2.0/06_patient_split/candidate_split_registry_v2.0.jsonl','data/processed/v2.0/06_patient_split/patient_split_lock_v2.0.json','data/processed/v2.0/02_decision_points/timeline_events_v2.0.jsonl','data/processed/v2.0/02_decision_points/molecular_samples_v2.0.jsonl']
    paths += [str(p.relative_to(B)).replace('\\','/') for p in (B/'data/processed/v2.0/01_source_audit/clinical_records').glob('*.jsonl')]
    for n in paths:manifest['input_sha256'][n]=sha(B/n)
    manifest['selection_sha256']=sha(selection_path)
    for p in P.glob('*.jsonl'):manifest['output_sha256'][str(p.relative_to(output)).replace('\\','/')]=sha(p)
    (O/'pilot_data_manifest_v2.0.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path)
    args=parser.parse_args();sys.stdout.reconfigure(encoding='utf8')
    print(json.dumps(build(args.project_root,args.output_root or args.project_root),ensure_ascii=False,indent=2))
