"""Candidate anchors and explicit temporal partitions; no clinical treatment labels."""
import hashlib
import json
from collections import defaultdict
from .source import number, expand_specimens


def uid(*parts):
    return 'v2.0:' + hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:24]


def offset(value, origin):
    value = number(value)
    return None if value is None or origin is None else value - origin


def relative(value, cancer_day):
    value = number(value)
    return None if value is None or cancer_day is None else value + cancer_day


def partition_time(event, t0):
    """No report result can be moved backward to its specimen collection date."""
    if t0 is None:
        return 'unknown_time'
    available = event.get('available_day')
    happened = event.get('event_day')
    if available is not None:
        return 'confirmed_before' if available < t0 else 'same_day_order_unknown' if available == t0 else 'future'
    if happened is None:
        return 'unknown_time'
    return 'event_before_availability_unconfirmed' if happened < t0 else 'same_day_order_unknown' if happened == t0 else 'future'


def scope_at(cancer, cancer_day, t0):
    if not cancer.get('is_index'):
        return 'non_index_cancer'
    if t0 is None or cancer_day is None or t0 < cancer_day:
        return 'timing_unresolved'
    f = cancer['fields']
    if f.get('stage_dx') == 'Stage IV' or f.get('ca_dmets_yn') == 'Yes':
        return 'metastatic_at_diagnosis'
    metastasis = relative(f.get('dx_to_dmets_days'), cancer_day) if f.get('dmets_post_dx') == '1' else None
    if metastasis is not None and metastasis < t0:
        return 'metastatic_after_diagnosis'
    if metastasis == t0:
        return 'metastasis_same_day_needs_order_review'
    if f.get('ca_resect_status') == 'Unresectable/locally advanced or metastatic':
        return 'baseline_unresectable_advanced_current_context_unconfirmed'
    if f.get('ca_resect_status') in {'Resectable', 'Borderline resectable'}:
        return 'resectable_or_borderline_baseline_current_context_unconfirmed'
    return 'advanced_context_unconfirmed'


def drug_components(record, cancer_day):
    f = record['fields']
    result = []
    for slot in range(1, 6):
        name = f.get(f'drugs_drug_{slot}', '')
        if not name:
            continue
        masked = 'investigational' in name.lower()
        result.append({'slot': slot, 'name_raw': name, 'start_day': relative(f.get(f'dx_drug_start_int_{slot}'), cancer_day),
                       'end_day': relative(f.get(f'dx_drug_end_int_{slot}'), cancer_day), 'masked': masked,
                       'source_fields': {'name': f'drugs_drug_{slot}', 'start': f'dx_drug_start_int_{slot}', 'end': f'dx_drug_end_int_{slot}'}})
    return result


def make_anchors(record, cancer_day):
    components = drug_components(record, cancer_day)
    start = relative(record['fields'].get('dx_reg_start_int'), cancer_day)
    days = {start}
    days.update(x['start_day'] for x in components if x['start_day'] is not None)
    anchors = []
    for day in sorted(days, key=lambda d: (d is None, d or 0)):
        anchors.append({'candidate_id': uid(record['record_id'], 'drug_start', day),
                        'source_record_id': record['record_id'], 't0_day': day,
                        'anchor_kind': 'regimen_start' if day == start else 'within_regimen_drug_start',
                        'observed_action_drugs': [x for x in components if x['start_day'] == day],
                        'regimen_components_full_course': components,
                        'stop_dates_are_candidate_treatment_change': False})
    return anchors


def biomarker_events(record, origin):
    f, results = record['fields'], []
    for family, members in {
        'pdl1': ['yn', 'prepaint', 'test', 'perc', 'tclrange', 'tcurange', 'icperc', 'iclrange', 'icurange', 'num', 'lcpsrange', 'ucpsrange', 'sum'],
        'msi': ['yn', 'prepaint', 'result', 'high', 'low'],
        'mmr': ['yn', 'prepaint', 'mlh1', 'msh2', 'msh6', 'pms2', 'result'],
    }.items():
        for slot in range(1, 4):
            suffix = '' if slot == 1 else f'_{slot}'
            names = [f'{family}_{member}{suffix}' for member in members]
            if family == 'pdl1':
                names += [f'pdl1_type{suffix}___{i}' for i in range(1, 5)]
            if family == 'mmr':
                names += [f'mmrp_det{suffix}', f'mmrd_det{suffix}']
            values = {name: f[name] for name in names if name in f}
            reported = values.get(f'{family}_yn{suffix}')
            if reported != 'Yes' and not any(value for name, value in values.items() if name != f'{family}_yn{suffix}'):
                continue
            date_field = f'{family}_prepaint{suffix}'
            day = offset(f.get(date_field), origin)
            results.append({'kind': f'{family}_report', 'event_day': day, 'available_day': day,
                            'date_fields': [date_field, 'dob_ca_dx_days'], 'facts': values, 'slot': slot})
    for slot in range(1, 6):
        names = [f'path_erprher_yn_{slot}', f'path_er_{slot}', f'path_pr_{slot}',
                 'path_herihc_1' if slot == 1 else f'path_her2ihc_{slot}',
                 'path_herish_1' if slot == 1 else f'path_her2ish_{slot}', f'path_erprher_add{slot}_int']
        values = {name: f.get(name, '') for name in names}
        if values[names[0]] != 'Yes' and not any(values[n] for n in names[1:]):
            continue
        day = offset(values[names[-1]], origin)
        results.append({'kind': 'er_pr_her2_addendum', 'event_day': day, 'available_day': day,
                        'date_fields': [names[-1], 'dob_ca_dx_days'], 'facts': values, 'slot': slot})
    for event in results:
        event.update(event_id=uid(record['record_id'], event['kind'], event['slot']), source_record_id=record['record_id'],
                     source=record['source'], cancer_attribution='pathology_report_level_specimen_attribution_unconfirmed')
    return results


def build_events(tables):
    cancers, origins = {}, {}
    for table in ['cancer_level_dataset_index', 'cancer_level_dataset_non_index']:
        for row in tables[table]:
            f = row['fields']
            pk = (f['cohort'], f['record_id'])
            cancers[(*pk, f['ca_seq'])] = {**row, 'is_index': table.endswith('_index') and not table.endswith('non_index')}
            day = number(f.get('dob_ca_dx_days'))
            if cancers[(*pk, f['ca_seq'])]['is_index'] and day is not None:
                origins[pk] = min(day, origins.get(pk, day))
    events, by_patient, cancer_days = [], defaultdict(list), {}
    for ck, row in cancers.items():
        cancer_days[ck] = offset(row['fields'].get('dob_ca_dx_days'), origins.get(ck[:2]))
    for table, records in tables.items():
        if table == 'patient_level_dataset':
            continue
        for row in records:
            f = row['fields']
            pk = (f['cohort'], f['record_id'])
            ck = (*pk, f.get('ca_seq', ''))
            kind, day, available, date_fields = table, None, None, []
            facts, attribution = {}, 'patient_only'
            if table.startswith('cancer_level_dataset'):
                kind, day, date_fields = 'cancer_diagnosis', cancer_days[ck], ['dob_ca_dx_days']
                facts = {k: f.get(k, '') for k in ['ca_type', 'ca_d_site', 'ca_histology', 'naaccr_histology_cd', 'ca_grade', 'ca_dx_how', 'stage_dx', 'summary_stage', 'ca_resect_status']}
                attribution = 'direct_cancer_key'
            elif table == 'regimen_cancer_level_dataset':
                kind, day, date_fields = 'regimen_start', relative(f.get('dx_reg_start_int'), cancer_days.get(ck)), ['dx_reg_start_int']
                facts = {'regimen_number': f['regimen_number'], 'components': drug_components(row, cancer_days.get(ck))}
                attribution = 'direct_cancer_key'
            elif table == 'pathology_report_level_dataset':
                kind, day, date_fields = 'pathology_procedure', number(f.get('dx_path_proc_days')), ['dx_path_proc_days']
                facts = {'procedure_type': f.get('path_proc_type'), 'procedure': f.get('path_proc'), 'specimens': expand_specimens(f)}
            elif table == 'cancer_panel_test_level_dataset':
                kind, date_fields = 'ngs_report', ['dob_cpt_report_days', 'dob_ca_dx_days', 'dx_cpt_rep_days']
                day = offset(f.get('dob_cpt_report_days'), origins.get(pk))
                alternative = relative(f.get('dx_cpt_rep_days'), cancer_days.get(ck))
                available = day if day == alternative else None
                facts = {k: f.get(k, '') for k in ['cpt_genie_sample_id', 'cpt_oncotree_code', 'cpt_seq_assay_id', 'sample_type', 'cpt_n_ca_seq', 'path_proc_number', 'path_rep_number']}
                facts['report_anchor_agrees'] = day is not None and day == alternative
                attribution = 'direct_cancer_key' if f.get('cpt_n_ca_seq') == '1' else 'ambiguous_cancer_key'
            elif table == 'imaging_level_dataset':
                kind, day, date_fields = 'imaging', number(f.get('dx_scan_days')), ['dx_scan_days']
                facts = {k: v for k, v in f.items() if k in ['image_scan_type', 'scan_sites', 'image_ca', 'image_overall'] or k.startswith('image_casite')}
            elif table == 'med_onc_note_level_dataset':
                kind, day, date_fields = 'oncology_assessment', number(f.get('dx_md_visit_days')), ['dx_md_visit_days']
                facts = {k: f.get(k, '') for k in ['md_type_ca_cur', 'md_ca', 'md_ca_status']}
                attribution = 'cancer_type_only'
            elif table == 'tm_level_dataset':
                kind, day, date_fields = 'tumor_marker_collection', number(f.get('dx_tm_days')), ['dx_tm_days']
                facts = {k: f.get(k, '') for k in ['tm_type', 'tm_num_result', 'tm_result_units', 'tm_normal_range_lower', 'tm_normal_range_upper']}
            elif table == 'ca_radtx_dataset':
                kind, day, date_fields = 'radiation_start', relative(f.get('dx_rt_start_days'), cancer_days.get(ck)), ['dx_rt_start_days']
                facts = {k: f.get(k, '') for k in ['rt_summ', 'rt_type', 'rt_planning', 'rt_dose', 'rt_fractions', 'rt_total_dose']}
                attribution = 'direct_cancer_key'
            event = {'event_id': uid(row['record_id'], kind), 'patient_key': list(pk), 'cancer_seq': f.get('ca_seq'),
                     'kind': kind, 'event_day': day, 'available_day': available, 'date_fields': date_fields,
                     'cancer_attribution': attribution, 'facts': facts, 'source_record_id': row['record_id'], 'source': row['source']}
            additions = [event]
            if table == 'pathology_report_level_dataset':
                additions += [{**e, 'patient_key': list(pk), 'cancer_seq': None} for e in biomarker_events(row, origins.get(pk))]
            for item in additions:
                events.append(item)
                by_patient[pk].append(item)
    for rows in by_patient.values():
        rows.sort(key=lambda e: (e['event_day'] is None, e['event_day'] or 0, e['event_id']))
    return events, by_patient, cancers, cancer_days


def build_candidates(tables, by_patient, cancers, cancer_days):
    candidates = []
    for row in tables['regimen_cancer_level_dataset']:
        f = row['fields']
        pk, ck = (f['cohort'], f['record_id']), (f['cohort'], f['record_id'], f['ca_seq'])
        for anchor in make_anchors(row, cancer_days.get(ck)):
            t0 = anchor['t0_day']
            partitions = {k: [] for k in ['confirmed_before', 'event_before_availability_unconfirmed', 'same_day_order_unknown', 'future', 'unknown_time']}
            for event in by_patient[pk]:
                partitions[partition_time(event, t0)].append(event['event_id'])
            relevant = [e for e in by_patient[pk] if e['kind'] == 'ngs_report' and e['cancer_seq'] == f['ca_seq']]
            types = sorted({e['facts']['cpt_oncotree_code'] for e in relevant})
            before_path = [e for e in by_patient[pk] if e['kind'] == 'pathology_procedure' and e['event_day'] is not None and t0 is not None and e['event_day'] < t0]
            explicit = [e['event_id'] for e in before_path if any(s['cancer_type'] == 'Pancreatic Cancer' and s['invasive'] == 'Yes' and s['invasive_histology'] == '8500 Ductal adenocarcinoma' for s in e['facts']['specimens'])]
            ngs_before = [e['event_id'] for e in relevant if partition_time(e, t0) == 'confirmed_before' and e['cancer_attribution'] == 'direct_cancer_key']
            scope = scope_at(cancers[ck], cancer_days.get(ck), t0)
            issues = ['ECOG_not_provided', 'organ_function_labs_not_provided', 'toxicity_and_dose_reduction_reasons_not_provided', 'pathology_main_report_availability_unconfirmed', 'clinical_eligibility_not_finalized']
            if scope == 'metastatic_after_diagnosis':
                issues.append('derived_metastasis_onset_requires_source_adjudication')
                onset = relative(cancers[ck]['fields'].get('dx_to_dmets_days'), cancer_days.get(ck))
                if any(e['kind'] == 'pathology_procedure' and e['event_day'] == onset and e['facts']['procedure'] == 'Surgical excision' for e in by_patient[pk]):
                    issues.append('derived_metastasis_onset_coincides_with_surgical_pathology')
            if t0 == cancer_days.get(ck):
                issues.append('diagnosis_and_action_same_day_order_unknown')
            if not ngs_before:
                issues.append('no_confirmed_predecision_ngs')
            if not explicit:
                issues.append('no_explicit_ductal_pathology_before_procedure_cutoff')
            if any(c['masked'] for c in anchor['regimen_components_full_course']):
                issues.append('investigational_drug_identity_masked')
            if any(c['start_day'] is None for c in anchor['regimen_components_full_course']):
                issues.append('component_start_day_missing')
            if sum(k[:2] == pk and c['is_index'] for k, c in cancers.items()) > 1:
                issues.append('multiple_index_cancers_pathology_attribution_needs_review')
            non_pdac = bool(types) and 'PAAD' not in types
            if scope == 'non_index_cancer':
                review = 'outside_main_task_non_index'
            elif non_pdac:
                review = 'outside_main_task_non_PAAD_cohort'
            elif scope.startswith('metastatic_') and scope != 'metastasis_same_day_needs_order_review':
                review = 'metastatic_candidate_requires_information_review'
            elif scope.startswith('baseline_unresectable'):
                review = 'locally_advanced_candidate_requires_context_review'
            elif scope == 'timing_unresolved':
                review = 'time_unresolved'
            else:
                review = 'advanced_context_not_established'
            anchor.update(patient_key=list(pk), cancer_seq=f['ca_seq'], source=row['source'], scope_at_t0=scope,
                          review_tier=review, cohort_oncotree_hindsight=types, cohort_oncotree_is_t0_feature=False,
                          explicit_ductal_pathology_procedure_before=explicit, ngs_report_before=ngs_before,
                          temporal_partition=partitions, information_issues=issues,
                          observed_action_is_input_feature=False, final_training_eligibility='not_finalized', expert_label=None)
            candidates.append(anchor)
    return candidates
