"""Offline, complete-case reading view with explicit timing and source information."""
import html
import json
from .decision_points import partition_time

LABELS = {'cohort': '队列', 'record_id': '患者编号', 'institution': '机构', 'age_dx': '诊断年龄', 'naaccr_sex_code': '性别',
          'ca_seq': '癌症序号', 'ca_type': '癌种', 'ca_histology': '登记组织学', 'ca_grade': '登记分级', 'ca_d_site': '原发部位',
          'stage_dx': '诊断分期', 'summary_stage': '概括分期', 'ca_resect_status': '初次治疗前可切除性',
          'path_proc_number': '病理操作编号', 'path_rep_number': '报告编号', 'path_proc_type': '标本检查类别', 'path_proc': '取材方式',
          'path_site1': '第1标本部位', 'dx_path_proc_days': '取材日（相对日）', 'path_num_spec': '声明标本数',
          'dx_reg_start_int': '方案开始距所属癌症诊断日', 'regimen_drugs': '全程方案药物原文', 'regimen_number': '方案记录编号',
          'cpt_oncotree_code': 'NGS癌种编码', 'cpt_genie_sample_id': '分子样本编号', 'cpt_seq_assay_id': '检测面板',
          'Hugo_Symbol': '基因', 'HGVSp_Short': '蛋白改变', 'Variant_Classification': '变异类别', 'Mutation_Status': '原始变异状态'}
TABLE_NAMES = {'patient_level_dataset': '患者背景', 'cancer_level_dataset_index': '目标癌症诊断', 'cancer_level_dataset_non_index': '其他癌症诊断',
               'regimen_cancer_level_dataset': '系统治疗', 'pathology_report_level_dataset': '完整病理报告', 'cancer_panel_test_level_dataset': 'NGS报告',
               'ca_radtx_dataset': '放疗', 'imaging_level_dataset': '影像', 'med_onc_note_level_dataset': '肿瘤内科评估', 'tm_level_dataset': '肿瘤标志物'}
PARTS = {'confirmed_before': '报告日期明确早于决策日', 'event_before_availability_unconfirmed': '事件在先，报告可用时间未确认',
         'same_day_order_unknown': '同日，先后顺序未知', 'future': '决策后信息', 'unknown_time': '日期未知'}
KINDS = {'cancer_diagnosis': '癌症诊断', 'regimen_start': '方案开始', 'pathology_procedure': '病理取材', 'ngs_report': 'NGS报告',
         'pdl1_report': 'PD-L1报告', 'msi_report': 'MSI报告', 'mmr_report': 'MMR报告', 'er_pr_her2_addendum': 'ER/PR/HER2附加报告',
         'imaging': '影像', 'oncology_assessment': '肿瘤内科评估', 'tumor_marker_collection': '肿瘤标志物采样', 'radiation_start': '放疗开始'}
SCOPES = {'metastatic_at_diagnosis': '诊断时已有转移记录', 'metastatic_after_diagnosis': '诊断后转移（依据数据集派生日期，待核查原证据）'}


def esc(value):
    if value is None:
        return '<span class="missing">未知（未确定）</span>'
    if value == '':
        return '<span class="missing">原字段为空</span>'
    return html.escape(str(value))


def grid(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + cell + '</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def raw_fields(fields, dictionary):
    rows = []
    for field, value in fields.items():
        label = LABELS.get(field, dictionary.get(field, {}).get('label', field))
        rows.append([esc(label), '<code>' + html.escape(field) + '</code>', esc(value)])
    return grid(['字段含义', '原字段', '原值（空值也保留）'], rows)


def locate(record):
    s = record['source']
    return esc(s['file']) + '；逻辑行 ' + esc(s.get('logical_row', s.get('physical_line'))) + '；记录 ' + esc(record.get('record_id', record.get('source_record_id', '')))


def render_case(case, path, dictionary):
    point, records, events = case['decision'], case['clinical_records'], case['events']
    t0 = point['t0_day']
    patient = records['patient_level_dataset'][0]['fields']
    diagnosis = next(r['fields'] for r in records['cancer_level_dataset_index'] if r['fields']['ca_seq'] == point['cancer_seq'])
    title = '结构化病例示例 v2.0'
    sections = []
    def section(title, body, ident):
        sections.append(f'<section id="{ident}"><h2>{title}</h2>{body}</section>')
    intro = '<p>用于核对数据整理和阅读格式，尚未生成治疗适用性标签。本例按资料丰富程度选择，不代表pilot抽样结果。</p>'
    intro += grid(['项目', '原始记录／当前状态'], [
        [esc('患者编号'), esc(patient['record_id'])], [esc('机构／性别'), esc(patient.get('institution')) + ' / ' + esc(patient.get('naaccr_sex_code'))],
        [esc('诊断年龄'), esc(diagnosis.get('age_dx'))], [esc('决策锚点'), f'首个目标癌症诊断后第 {t0} 天；' + ('整套方案开始' if point['anchor_kind'] == 'regimen_start' else '方案内其他药物开始')],
        [esc('诊断时分期／初始可切除性'), esc(diagnosis.get('stage_dx')) + ' / ' + esc(diagnosis.get('ca_resect_status'))],
        [esc('该时点情境分层'), esc(SCOPES.get(point['scope_at_t0'], point['scope_at_t0']))],
        [esc('数据集派生的首次转移间隔'), esc(diagnosis.get('dx_to_dmets_days')) + ' 天（相对该癌症诊断日）'],
        [esc('登记组织学（可用日期未确认）'), esc(diagnosis.get('ca_histology'))],
        [esc('缺失的治疗适用性资料'), esc('ECOG、常规肝肾功能、毒性与减量原因未在本批临床表提供；不补成正常')]])
    intro += '<p class="note">时间均相对于首个目标癌症诊断日。当前知识重评只更新指南和论文依据，不允许使用患者在决策之后才出现的信息。病理取材日不等于主报告签发日。</p>'
    if 'derived_metastasis_onset_coincides_with_surgical_pathology' in point['information_issues']:
        intro += '<p class="note">本例的派生转移日期与一次手术病理取材同日，需要回查具体部位和原始证据；不能仅凭这个日期认定当时已发生远处转移。完整病理及后续记录列在下方。</p>'
    section('病例与决策时点', intro, 'overview')
    counts = [[esc(PARTS[name]), str(len(ids))] for name, ids in point['temporal_partition'].items()]
    section('信息时间核查', grid(['时间类别', '事件数'], counts) + '<p>“报告日期明确在先”只证明时间顺序；癌症归属、检测对象和临床适用性仍需核查。全程登记字段也可能由后续资料补录，不能自动作为时点输入。</p>', 'timing')
    therapies = []
    for row in records['regimen_cancer_level_dataset']:
        e = next(e for e in events if e['source_record_id'] == row['record_id'] and e['kind'] == 'regimen_start')
        for c in e['facts']['components']:
            relation = '开始日在决策前' if c['start_day'] is not None and c['start_day'] < t0 else '本次／未来开始，不能作既往治疗' if c['start_day'] is not None else '日期未知'
            end = str(c['end_day']) if c['end_day'] is not None and c['end_day'] < t0 and not c['masked'] else '此时尚不能确认／被遮蔽'
            therapies.append([esc(row['fields']['ca_seq']), esc(row['fields']['regimen_number']), esc(c['name_raw']), esc(c['start_day']), esc(end), esc(relation)])
    section('治疗经历与本次观察方案', '<p>药物逐个列出开始日；后加药不回填到整套方案首日。实际用药仅是观察事实，尚无指南支持或适用性标签。</p>' + grid(['癌症', '方案编号', '药物原名', '开始日', '决策前可确认的结束日', '与决策的关系'], therapies), 'therapy')
    path_html = []
    for row in records['pathology_report_level_dataset']:
        ev = next(e for e in events if e['source_record_id'] == row['record_id'] and e['kind'] == 'pathology_procedure')
        fields = row['fields']
        badge = PARTS[partition_time(ev, t0)]
        heading = f'报告 {fields["path_proc_number"]}/{fields["path_rep_number"]} · 取材第{ev["event_day"]}天 · {badge}'
        specimens = [[str(s['specimen_number']), esc(s['site']), esc(s['invasive']), esc(s['cancer_type']), esc(s['invasive_histology']), esc(s['in_situ']), esc(s['in_situ_histology'])] for s in ev['facts']['specimens']]
        body = '<p>' + esc(fields.get('path_proc_type')) + ' / ' + esc(fields.get('path_proc')) + '；主报告可用时间：未提供。</p>'
        body += grid(['标本', '部位', '浸润癌', '癌种', '浸润组织学', '原位癌', '原位组织学'], specimens)
        markers = [e for e in events if e['source_record_id'] == row['record_id'] and e['kind'].endswith(('_report', '_addendum'))]
        for marker in markers:
            body += '<h4>' + esc(KINDS[marker['kind']]) + ' · ' + esc(PARTS[partition_time(marker, t0)]) + ' · 报告第' + esc(marker['available_day']) + '天</h4>'
            body += raw_fields(marker['facts'], dictionary)
        if not markers:
            body += '<p>该报告没有可展开的附加检测记录；这不等于检测阴性。</p>'
        body += '<p class="source">' + locate(row) + '</p>'
        body += '<details><summary>展开全部 ' + str(len(fields)) + ' 个原字段，包括空值</summary>' + raw_fields(fields, dictionary) + '</details>'
        path_html.append('<article class="pathology"><h3>' + esc(heading) + '</h3>' + body + '</article>')
    section('完整病理与附加检测', ''.join(path_html), 'pathology')
    molecular_html = []
    for sample in case['molecular_samples']:
        ngs = [e for e in events if e['kind'] == 'ngs_report' and e['facts']['cpt_genie_sample_id'] == sample['sample_id']]
        timing = '；'.join(PARTS[partition_time(e, t0)] + '（报告第' + str(e['available_day']) + '天）' for e in ngs)
        body = '<h3>' + esc(sample['sample_id']) + '</h3><p>' + esc(timing) + '</p>'
        body += '<p>面板：' + esc(sample['metadata'].get('SEQ_ASSAY_ID')) + '。以下仅整理原始分子观察，未判定致病性、胚系来源或可用药物。未记录的变异不能自动记为阴性。</p>'
        body += grid(['基因', '蛋白改变', '类别', '原始变异状态'], [[esc(r['fields'].get('Hugo_Symbol')), esc(r['fields'].get('HGVSp_Short')), esc(r['fields'].get('Variant_Classification')), esc(r['fields'].get('Mutation_Status'))] for r in sample['mutations']])
        body += '<p>结构变异记录：' + str(len(sample['structural_variants'])) + '。拷贝数矩阵保留 ' + str(len(sample['cna_values'])) + ' 个基因条目，原始0、NA和空值分别保留。</p>'
        details = '<h4>全部变异原字段及来源</h4>'
        for row in sample['mutations'] + sample['structural_variants']:
            details += '<p class="source">' + locate(row) + '</p>' + raw_fields(row['fields'], dictionary)
        details += '<h4>完整拷贝数矩阵列</h4>' + grid(['基因', '原值', '源文件物理行'], [[esc(gene), esc(v['raw_value']), str(v['physical_line'])] for gene, v in sample['cna_values'].items()])
        details += '<h4>面板及覆盖记录</h4><pre>' + html.escape(json.dumps(sample['panel_assignments'], ensure_ascii=False, indent=2)) + '</pre>'
        body += '<details><summary>展开完整分子记录</summary>' + details + '</details>'
        molecular_html.append(body)
    section('分子检测', ''.join(molecular_html) or '<p>没有关联的公开分子样本。</p>', 'molecular')
    timeline_rows = []
    for e in sorted(events, key=lambda e: (e['event_day'] is None, e['event_day'] or 0, e['event_id'])):
        facts = {k: v for k, v in e['facts'].items() if v and k not in {'specimens', 'components'}}
        timeline_rows.append([esc(e['event_day']), esc(KINDS.get(e['kind'], e['kind'])), esc(PARTS[partition_time(e, t0)]), esc(json.dumps(facts, ensure_ascii=False)), '<code>' + esc(e['source_record_id']) + '</code>'])
    section('全程时间轴（包含明确标记的未来信息）', '<details><summary>展开全部 ' + str(len(events)) + ' 个事件</summary>' + grid(['事件日', '类别', '时点关系', '记录摘要', '来源记录编号'], timeline_rows) + '</details>', 'timeline')
    allraw = []
    for name, rows in records.items():
        if name == 'pathology_report_level_dataset':
            continue
        content = ''.join('<h4>记录 ' + str(i) + '</h4><p class="source">' + locate(row) + '</p>' + raw_fields(row['fields'], dictionary) for i, row in enumerate(rows, 1))
        allraw.append('<details><summary>' + TABLE_NAMES[name] + '：' + str(len(rows)) + ' 条完整原记录</summary>' + content + '</details>')
    section('全部临床原记录与来源', '<p>此处是全程追溯附录，含结局、后续随访和未来治疗。不能整体作为早期决策的模型输入。病理全部原字段已列在病理章节。</p>' + ''.join(allraw), 'sources')
    nav = ''.join('<a href="#' + k + '">' + v + '</a>' for k, v in [('overview','病例摘要'),('therapy','治疗经历'),('pathology','完整病理'),('molecular','分子检测'),('timeline','时间轴'),('sources','原始记录')])
    css = '''body{margin:0;background:#f4f6f8;color:#172b3a;font:15px/1.7 "Microsoft YaHei",sans-serif}header{background:#163c52;color:#fff;padding:32px max(calc((100% - 1120px)/2),24px)}header h1{margin:0;font-size:28px}nav{display:flex;gap:20px;flex-wrap:wrap;margin-top:18px}nav a{color:#d9edf5}main{max-width:1120px;margin:26px auto;padding:0 24px}section{background:white;padding:26px;margin-bottom:22px;border:1px solid #dce3e7;border-radius:8px}h2{font-size:22px;margin:0 0 18px}h3{font-size:17px}h4{margin:18px 0 10px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}th{background:#e9f0f4;text-align:left}td,th{padding:10px 12px;border:1px solid #dce3e7;vertical-align:top;overflow-wrap:anywhere}td code{font-size:11px}td:first-child{min-width:65px}.missing{color:#697780}.note{padding:14px;background:#fff5db;border-left:4px solid #c79326}.source{font-size:12px;color:#586b79;overflow-wrap:anywhere}.pathology{padding:18px;border:1px solid #b7cbd7;border-radius:5px;margin:20px 0}details{margin:14px 0;border:1px solid #dce3e7;padding:12px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}@media print{header{padding:16px}main{padding:0}section{break-inside:auto;border:0}details{break-inside:auto}nav{display:none}}'''
    path.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><style>' + css + '</style><header><h1>' + title + '</h1><div>PANC 1.0-public · 首个目标癌症诊断日为第0天 · 文献截止日暂定2026-09-10</div><nav>' + nav + '</nav></header><main>' + ''.join(sections) + '</main></html>', encoding='utf-8')
