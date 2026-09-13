"""Source-supported inventory; no clinical diagnosis, intent or report time inference."""
from collections import Counter, defaultdict
from .decision_points import relative, build_events


def evidence_inventory(registry, tables):
    focus = [c for c in registry if c['screening_bucket'] in {'main_regimen_start_candidate', 'within_regimen_change_review', 'progression_trigger_review'}]
    events, by_patient, cancers, days = build_events(tables)
    event_index = {e['event_id']: e for e in events}
    records = {r['record_id']: r for rows in tables.values() for r in rows}
    regimens = defaultdict(list)
    for e in events:
        if e['kind'] == 'regimen_start':
            regimens[(*e['patient_key'], e['cancer_seq'])].append(e)
    profile, histogram = [], Counter()
    for c in focus:
        pk, t0 = tuple(c['patient_key']), c['t0_day']
        ck = (*pk, c['cancer_seq'])
        es = by_patient[pk]
        before = [e for e in es if e['kind'] == 'pathology_procedure' and e['event_day'] is not None and e['event_day'] < t0]
        hists = sorted({s['invasive_histology'] for e in before for s in e['facts']['specimens'] if s['invasive'] == 'Yes' and s['cancer_type'] == 'Pancreatic Cancer'})
        histogram.update(hists)
        ductal = '8500 Ductal adenocarcinoma' in hists
        nos = '8140 Adenocarcinoma NOS' in hists
        category = 'explicit_ductal_before_procedure' if ductal else 'NOS_without_explicit_ductal' if nos else 'other_pancreatic_histology_only' if hists else 'no_pancreatic_invasive_histology_before'
        linked = []
        for eid in c['ngs_report_before']:
            ngs = event_index[eid]
            f = ngs['facts']
            matches = [e for e in es if e['kind'] == 'pathology_procedure'
                       and records[e['source_record_id']]['fields']['path_proc_number'] == f['path_proc_number']
                       and records[e['source_record_id']]['fields']['path_rep_number'] == f['path_rep_number']]
            linked.append({'ngs_event_id': eid, 'oncotree': f['cpt_oncotree_code'], 'report_day': ngs['available_day'],
                           'pathology_event_ids': [e['event_id'] for e in matches],
                           'histologies_raw': sorted({s['invasive_histology'] for e in matches for s in e['facts']['specimens'] if s['invasive'] == 'Yes' and s['cancer_type'] == 'Pancreatic Cancer'})})
        onset = None
        if ck in cancers and cancers[ck]['fields'].get('dmets_post_dx') == '1':
            onset = relative(cancers[ck]['fields'].get('dx_to_dmets_days'), days[ck])
        same_surgery = [e['event_id'] for e in before if onset is not None and e['event_day'] == onset and e['facts']['procedure'] == 'Surgical excision']
        surgery_after = [e['event_id'] for e in before if e['facts']['procedure'] == 'Surgical excision']
        strategy = None
        previous_ids = []
        lag = None
        if c['anchor_kind'] == 'regimen_start':
            earlier = [e for e in regimens[ck] if e['event_day'] is not None and e['event_day'] < t0]
            if not earlier:
                strategy = 'first_recorded_regimen'
            else:
                day = max(e['event_day'] for e in earlier)
                previous = [e for e in earlier if e['event_day'] == day]
                previous_ids = [e['source_record_id'] for e in previous]
                old = {x['name_raw'] for e in previous for x in e['facts']['components']}
                new = {x['name_raw'] for x in c['regimen_components_full_course']}
                if any('investigational' in x.lower() for x in old | new):
                    strategy = 'masked_identity_prevents_interpretation'
                elif old == new:
                    strategy = 'same_full_course_drug_set'
                elif new < old:
                    strategy = 'fewer_full_course_drugs_subset'
                elif old < new:
                    strategy = 'more_full_course_drugs_superset'
                else:
                    strategy = 'changed_full_course_drug_set'
        elif c['anchor_kind'] == 'within_regimen_drug_start':
            parent = next(e for e in regimens[ck] if e['source_record_id'] == c['source_record_id'])
            lag = t0 - parent['event_day'] if parent['event_day'] is not None else None
            strategy = 'within_regimen_change_reason_unrecorded'
        elif c['anchor_kind'].startswith('progression'):
            strategy = 'progression_actual_decision_time_unknown'
        profile.append({'candidate_id': c['candidate_id'], 'patient_key': c['patient_key'], 'cancer_seq': c['cancer_seq'],
                        'bucket': c['screening_bucket'], 't0_day': t0, 'pathology_category': category,
                        'histologies_raw_before_procedure': hists, 'prior_pathology_event_ids': [e['event_id'] for e in before],
                        'predecision_ngs_pathology_links': linked, 'scope_at_t0': c['scope_at_t0'],
                        'derived_metastasis_day': onset, 'surgical_pathology_same_day_as_derived_metastasis': same_surgery,
                        'prior_surgical_pathology_event_ids': surgery_after, 'strategy_record_pattern': strategy,
                        'previous_regimen_record_ids': previous_ids, 'within_regimen_start_lag_days': lag,
                        'existing_issues': c['information_issues'], 'source': c['source'],
                        'final_eligibility': 'unchanged_not_finalized', 'report_date_policy': 'procedure_before_does_not_confirm_report_before',
                        'drug_set_comparison_usage': 'retrospective_review_only_not_t0_input_or_maintenance_label'})
    return profile

def stats(rows):
    return {'records': len(rows), 'patients': len({tuple(c['patient_key']) for c in rows}),
            'pathology_categories': dict(Counter(r['pathology_category'] for r in rows)),
            'NOS_without_explicit_ductal_and_no_other_raw_histology': sum(r['histologies_raw_before_procedure'] == ['8140 Adenocarcinoma NOS'] for r in rows),
            'scope_counts': dict(Counter(r['scope_at_t0'] for r in rows)),
            'surgical_pathology_on_derived_metastasis_day': sum(bool(r['surgical_pathology_same_day_as_derived_metastasis']) for r in rows),
            'strategy_patterns': dict(Counter(r['strategy_record_pattern'] for r in rows))}
