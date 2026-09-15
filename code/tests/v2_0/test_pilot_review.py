"""Regression checks for temporal leakage, raw pathology and review status."""
import json,unittest
from pathlib import Path

BASE=Path(__file__).resolve().parents[3]
def rows(name):
    p=BASE/'data/processed/v2.0/09_pilot_review'/name
    return [json.loads(x) for x in p.read_text(encoding='utf8').splitlines()]

class PilotReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=rows('pilot_decision_inputs_v2.0.jsonl')
        cls.cases=rows('pilot_case_source_records_v2.0.jsonl')
        cls.pairs=rows('pilot_label_pairs_v2.0.jsonl')

    def test_frozen_25_index_cases_and_candidate_range(self):
        self.assertEqual(len(self.inputs),25)
        registry=BASE/'data/processed/v2.0/06_patient_split/candidate_split_registry_v2.0.jsonl'
        if registry.exists():
            expected={r['candidate_id'] for r in map(json.loads,registry.read_text(encoding='utf8').splitlines()) if r['patient_split_assignment']['pilot_primary_index']}
            self.assertEqual(expected,{x['candidate_id'] for x in self.inputs})
        self.assertEqual(len(self.pairs),175)
        self.assertEqual(len({p['pair_id'] for p in self.pairs}),175)
        for c in self.inputs:
            self.assertIn(sum(p['case_id']==c['case_id'] for p in self.pairs),[6,7,8])

    def test_ngs_and_regimen_components_strictly_prior(self):
        for c in self.inputs:
            for n in c['ngs_reports']:
                self.assertLess(n['available_day'],c['t0_day']);self.assertEqual(n['cancer_seq'],c['cancer_seq'])
            for r in c['prior_treatments']:
                self.assertEqual(r['cancer_seq'],c['cancer_seq'])
                for d in r['components']:
                    self.assertLess(d['start_day'],c['t0_day'])
                    self.assertTrue(d['end_day'] is None or d['end_day']<c['t0_day'])

    def test_future_mmr_not_in_early_case_input(self):
        case=next(c for c in self.inputs if c['case_id']=='PILOT-06')
        self.assertFalse(any(e['kind']=='mmr_report' for e in case['clinical_events_before']))
        self.assertNotIn('mmr_result',json.dumps(case))
        source=next(c for c in self.cases if c['case_id']=='PILOT-06')
        self.assertTrue(any(e['kind']=='mmr_report' for e in source['events_after']))

    def test_prior_marker_records_preserved_and_radiation_totals_excluded(self):
        for c,original in zip(self.inputs,self.cases):
            expected={e['event_id'] for e in original['events_before'] if e['kind']=='tumor_marker_collection'}
            actual={e['event_id'] for e in c['clinical_events_before'] if e['kind']=='tumor_marker_collection'}
            self.assertEqual(expected,actual)
            self.assertNotIn('rt_total_dose',json.dumps(c))

    def test_followup_additions_are_not_index_composition(self):
        for cid,fid in [('PILOT-09','CAP'),('PILOT-25','FU')]:
            observed=[p for p in self.pairs if p['case_id']==cid and p['observed_regimen']]
            self.assertEqual([p['regimen_id'] for p in observed],[fid])
        for c in self.inputs:
            self.assertNotIn('candidate',c);self.assertNotIn('events_after',c);self.assertNotIn('all_clinical_records',c)

    def test_complete_pathology_and_zero_variants_are_distinct(self):
        self.assertEqual(sum(len(c['pathology_procedures']) for c in self.inputs),66)
        self.assertEqual(sum(len(p['facts']['specimens']) for c in self.inputs for p in c['pathology_procedures']),132)
        for c,original in zip(self.inputs,self.cases):
            self.assertEqual(c['pathology_procedures'],[p['event'] for p in original['pathology_before']])
        self.assertEqual(sum(len(s['mutations']) for c in self.inputs for s in c['molecular_samples']),218)
        for cid in ['PILOT-13','PILOT-21']:
            self.assertEqual(next(p for p in self.pairs if p['case_id']==cid and p['regimen_id']=='GEM_NIMO')['proposed_label'],'INDETERMINATE')

    def test_other_cancer_not_counted_as_pancreatic_prior(self):
        c=next(c for c in self.inputs if c['case_id']=='PILOT-13')
        self.assertNotIn('Cyclophosphamide',json.dumps(c['prior_treatments']))
        self.assertNotIn('Methotrexate',json.dumps(c['prior_treatments']))

    def test_expert_and_adjudication_results_remain_blank(self):
        reviews=rows('pilot_independent_reviews_v2.0.jsonl');adj=rows('pilot_adjudications_v2.0.jsonl')
        self.assertEqual(len(reviews),350);self.assertEqual(len(adj),175)
        self.assertTrue(all(r['reviewed_label'] is None for r in reviews))
        self.assertTrue(all(r['final_label'] is None for r in adj))
        self.assertTrue(all(p['reviewed_label'] is None for p in self.pairs))

    def test_preliminary_labels_keep_unknowns_and_research_context(self):
        self.assertEqual(sum(p['use_context']=='research' for p in self.pairs),27)
        for p in self.pairs:
            if p['proposed_label']=='CONDITIONAL':self.assertTrue(p['unknown_conditions'])
            if p['proposed_label']=='MISMATCH':self.assertTrue(p['unmet_conditions'])
            if p['catalog_family_id']:self.assertTrue(p['evidence_ids'])
        p=next(p for p in self.pairs if p['case_id']=='PILOT-23' and p['regimen_id']=='GEM_CIS')
        self.assertEqual(p['proposed_label'],'INDETERMINATE')
