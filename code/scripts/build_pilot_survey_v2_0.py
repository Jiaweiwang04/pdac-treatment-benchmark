"""Build a local mobile questionnaire example from frozen Pilot records."""
import argparse
import hashlib
import html
import json
from pathlib import Path

LABELS = {'SUPPORTED':'支持匹配','CONDITIONAL':'条件性匹配','MISMATCH':'有依据不匹配','INDETERMINATE':'无法判定'}
MISSING = {'','unknown','not stated','not stated/indeterminate','not applicable','na','n/a','none','null'}
TRANSLATIONS = {
    'Male':'男','Female':'女','Yes':'是','No':'否','Adenocarcinoma, NOS':'腺癌 NOS',
    'Stage IV':'IV 期','Stage III':'III 期','Stage II':'II 期','Pancreatic Cancer':'胰腺癌',
    'Surgical pathology':'组织病理','Cytology':'细胞学','Biopsy':'活检',
    'C25.0':'胰头（C25.0）','C25.0    Head of pancreas':'胰头（C25.0）',
    'C22.0    Liver':'肝（C22.0）','C17.0    Duodenum':'十二指肠（C17.0）',
    'F20 Peritoneal Fluid/Ascites':'腹腔液／腹水（F20）',
    'C25.9    Pancreas NOS':'胰腺（C25.9）','C48.2    Peritoneum NOS':'腹膜（C48.2）',
    'C24.0    Extrahepatic bile duct':'肝外胆管（C24.0）',
    'C49.4    Connective Subcutaneous and other soft tissues of abdomen':'腹部结缔组织、皮下及其他软组织（C49.4）',
    '8140 Adenocarcinoma NOS':'腺癌 NOS（8140）',
    'Progressing/Worsening/Enlarging':'进展／恶化／增大','Stable/No change':'稳定／无变化',
    'Responding/Improving':'缓解／改善','Improving/Responding':'缓解／改善',
    'Abdomen, Pelvis':'腹部、盆腔','Chest':'胸部',
    'Yes, the Impression states or implies there is evidence of cancer':'提示存在癌症证据',
    'Yes, the Impression/Plan states or implies there is evidence of cancer':'提示存在癌症证据',
    'Fluorouracil':'氟尿嘧啶','Oxaliplatin':'奥沙利铂','Irinotecan HCL':'伊立替康','Leucovorin':'亚叶酸',
}
def present(value):
    return value is not None and value != [] and value != {} and str(value).strip().lower() not in MISSING
def tr(value):
    return TRANSLATIONS.get(str(value),str(value))
def compact(pairs):
    return [{'label':k,'value':tr(v)} for k,v in pairs if present(v)]
def source(event):
    s=event['source'];return {'file':s['file'],'row':s.get('logical_row',s.get('physical_line'))}
def rows(path):
    return [json.loads(s) for s in path.read_text(encoding='utf8').splitlines() if s.strip()]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build(base,output,case_id,template):
    folder=base/'data/processed/v2.0/09_pilot_review'
    filenames=['pilot_decision_inputs_v2.0.jsonl','pilot_label_pairs_v2.0.jsonl','pilot_evidence_sources_v2.0.jsonl']
    case=next(c for c in rows(folder/filenames[0]) if c['case_id']==case_id)
    pairs=[p for p in rows(folder/filenames[1]) if p['case_id']==case_id]
    used={x for p in pairs for x in p['evidence_ids']}
    evidence=[e for e in rows(folder/filenames[2]) if e['evidence_id'] in used]
    d=case['diagnosis']
    summary=compact([('诊断年龄',str(d['age_dx'])+' 岁' if present(d.get('age_dx')) else None),('性别',case.get('sex')),('原发部位',d.get('ca_d_site')),('登记组织学',d.get('ca_histology')),('初诊分期',d.get('stage_dx'))])
    pathology=[]
    for e in case['pathology_procedures']:
        f=e['facts'];specimens=[]
        for s in f['specimens']:
            specimens.append({'number':s['specimen_number'],'facts':compact([('取材部位',s.get('site')),('浸润性肿瘤',s.get('invasive')),('组织学',s.get('invasive_histology')),('癌种',s.get('cancer_type')),('原位癌',s.get('in_situ')),('原位组织学',s.get('in_situ_histology'))])})
        pathology.append({'day':e['event_day'],'method':' · '.join(tr(f[k]) for k in ['procedure_type','procedure'] if present(f.get(k))),'specimens':specimens,'source':source(e)})
    prior=[]
    for r in case['prior_treatments']:
        for x in r['components']:
            dates=f"D{x['start_day']}"+(f"–D{x['end_day']}" if x.get('end_day') is not None else ' 起')
            prior.append({'name':tr(x['name_raw'].split('(')[0]),'dates':dates,'source':source(r)})
    events=[]
    types={'imaging':'影像评估','oncology_assessment':'肿瘤科评估','tumor_marker_collection':'肿瘤标志物'}
    for e in case['clinical_events_before']:
        f=e['facts'];kind=e['kind'];facts=[]
        if kind=='imaging':
            facts=compact([('检查',f.get('image_scan_type')),('扫描部位',f.get('scan_sites')),('评估',f.get('image_overall')),('癌症证据',f.get('image_ca'))])
            sites=[tr(v) for k,v in f.items() if k.startswith('image_casite') and present(v)]
            if sites:facts.append({'label':'记录病灶部位','value':'；'.join(sites)})
        elif kind=='oncology_assessment':
            facts=compact([('癌种',f.get('md_type_ca_cur')),('评估',f.get('md_ca_status')),('癌症证据',f.get('md_ca'))])
        elif kind=='tumor_marker_collection' and present(f.get('tm_num_result')):
            facts=compact([('项目',f.get('tm_type')),('结果',' '.join(str(f.get(k,'')) for k in ['tm_num_result','tm_result_units'] if present(f.get(k))))])
            if present(f.get('tm_normal_range_lower')) and present(f.get('tm_normal_range_upper')):
                facts.append({'label':'参考范围','value':str(f['tm_normal_range_lower'])+'–'+str(f['tm_normal_range_upper'])})
        if facts:events.append({'day':e['event_day'],'kind':types.get(kind,kind),'facts':facts,'source':source(e)})
    variants=[];cna=[]
    for s in case['molecular_samples']:
        for m in s['mutations']:
            f=m['fields'];variants.append({'gene':f['Hugo_Symbol'],'protein':f.get('HGVSp_Short',''),'details':compact([('核苷酸改变',f.get('HGVSc')),('参考基因组',f.get('NCBI_Build')),('变异类型',f.get('Variant_Classification')),('原状态',f.get('Mutation_Status'))]),'source':source(m)})
        for gene,v in s.get('cna_values',{}).items():
            if present(v.get('raw_value')) and v['raw_value']!='0':cna.append({'gene':gene,'value':v['raw_value']})
    reports=[{'day':e['available_day'],'panel':e['facts'].get('cpt_seq_assay_id'),'code':e['facts'].get('cpt_oncotree_code'),'source':source(e)} for e in case['ngs_reports']]
    assert all(x['day']<case['t0_day'] for x in reports)
    # Preserve the frozen proposals verbatim. Observed-regimen and outcome fields never enter the questionnaire.
    pair_fields=['pair_id','regimen_id','regimen_display_name','use_context','assessment_context','proposed_label','proposed_label_zh','rationale','unknown_conditions','unmet_conditions','evidence_ids']
    model={'version':'v2.0','form_version':'v2.0_pilot01_mobile_20260923','compiled_date':'2026-09-23','evidence_cutoff':'2026-09-12','mode':'local_preview','case_id':case_id,'t0_day':case['t0_day'],'summary':summary,'pathology':pathology,'prior_treatments':prior,'clinical_events':events,'ngs_reports':reports,'variants':variants,'cna':cna,'pairs':[{k:p[k] for k in pair_fields} for p in pairs],'evidence':evidence,'labels':LABELS}
    output.mkdir(parents=True,exist_ok=True)
    prefix='pilot_01_mobile_questionnaire_v2.0'
    json_path=output/(prefix+'.json');json_path.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    payload=json.dumps(model,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html_path=output/(prefix+'.html');html_path.write_text(template.read_text(encoding='utf8').replace('__SURVEY_DATA__',payload),encoding='utf8')
    lines=['# 单病例标签审核问卷 v2.0','','编制日期：2026-09-23；知识截止日：2026-09-12。','','病例：'+case_id+'；审核时点：D'+str(case['t0_day'])+'。D0 为首次目标癌症诊断日。','','## 病例资料']
    lines.extend('- '+x['label']+'：'+x['value'] for x in summary)
    lines+=['','## 病理','日期为取材日；展示取材记录，不推定报告签发时间。']
    for p in pathology:
        lines+=['','### D'+str(p['day'])+' '+p['method']]
        lines.extend('- 标本 '+str(s['number'])+'：'+'；'.join(x['label']+'：'+x['value'] for x in s['facts']) for s in p['specimens'])
    lines+=['','## 既往治疗']+['- '+x['dates']+'：'+x['name'] for x in prior]
    lines+=['','## 分子与评估资料']
    lines+=['- NGS：D'+str(x['day'])+'，'+x['panel'] for x in reports]
    lines+=['- '+x['gene']+' '+x['protein']+'；'+'；'.join(y['label']+'：'+y['value'] for y in x['details']) for x in variants]
    if cna:lines+=['- 离散拷贝数原始编码：'+'；'.join(x['gene']+'='+x['value'] for x in cna)]
    lines+=['- D'+str(e['day'])+' '+e['kind']+'：'+'；'.join(x['label']+'：'+x['value'] for x in e['facts']) for e in events]
    lines+=['','## 审核题目','专家编号：专家 A／专家 B。各题不预选答案。','每项选择：同意预拟标签／修改标签／暂无法审核。修改时选择四类标签之一并说明理由；暂无法审核是填写状态，不是“无法判定”标签。']
    for p in model['pairs']:
        lines+=['','### '+p['pair_id']+' '+p['regimen_display_name'],'使用情境：'+('研究性方案' if p['use_context']=='research' else '常规使用情境'),'预拟标签：'+p['proposed_label_zh'],'评价路径：'+p['assessment_context'],'判定理由：'+p['rationale']]
        lines+=['待确认条件：'+x for x in p['unknown_conditions']]
        lines+=['已知冲突：'+x for x in p['unmet_conditions']]
        lines+=['证据：'+ '；'.join(p['evidence_ids']),'判断：同意／修改／暂无法审核。','修改后的标签：支持匹配／条件性匹配／有依据不匹配／无法判定。','理由：修改必填，其余选填。','方案属性修订：选填（常规使用情境／研究性方案／需进一步核实）。']
    lines+=['','## 证据来源']
    for e in evidence:lines+=['','### '+e['evidence_id'],'['+e['title']+']('+e['url']+')',e['finding_zh'],'定位：'+e['locator']]
    lines+=['','## 样稿使用','HTML 为本地交互预览，填写结果可下载，不会在线提交。正式发布前需在问卷平台完成登录、访问控制、手机端试填和回收验证。']
    md_path=output/(prefix+'_content.md');md_path.write_text('\n'.join(lines)+'\n',encoding='utf8')
    manifest={'version':'v2.0','case_id':case_id,'pairs':len(pairs),'pathology_records':len(pathology),'specimens':sum(len(x['specimens']) for x in pathology),'source_sha256':{f:sha(folder/f) for f in filenames},'output_sha256':{p.name:sha(p) for p in [json_path,html_path,md_path]},'missing_field_policy':'omit blank and explicit unknown placeholders; retain documented negative findings and proposal conditions','published':False}
    (output/(prefix+'_manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:manifest[k] for k in ['case_id','pairs','pathology_records','specimens','published']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--template',type=Path)
    args=parser.parse_args();base=args.project_root.resolve()
    build(base,args.output_dir or base/'code/results/v2.0/10_mobile_questionnaire', 'PILOT-01',args.template or base/'code/src/pdac_benchmark/v2_0/survey_template_v2.0.html')
