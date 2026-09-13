import unittest
from pdac_benchmark.v2_0.candidate_review import refine_candidate, same_day_links


def candidate(ident='r', patient='P', seq='1', day=10, kind='regimen_start', bucket='main_regimen_start_candidate'):
    return {'candidate_id': ident, 'patient_key': ['PANC', patient], 'cancer_seq': seq, 't0_day': day,
            'anchor_kind': kind, 'screening_bucket': bucket, 'information_issues': [],
            'ngs_report_before': ['ngs'], 'final_training_eligibility': 'not_finalized', 'expert_label': None}


def inventory(pattern='changed_full_course_drug_set'):
    return {'histologies_raw_before_procedure': ['8140 Adenocarcinoma NOS'],
            'pathology_category': 'NOS_without_explicit_ductal', 'strategy_record_pattern': pattern,
            'predecision_ngs_pathology_links': [{'oncotree': 'PAAD'}]}


class CandidateReviewTests(unittest.TestCase):
    def test_nos_is_retained_without_turning_it_into_confirmed_pdac_or_known_report_date(self):
        before = candidate()
        after = refine_candidate(before, inventory(), [])
        self.assertEqual(after['screening_bucket'], 'main_regimen_start_candidate')
        review = after['candidate_review']
        self.assertTrue(review['nos_paad_retention_rule_applies'])
        self.assertEqual(review['pathology_report_available_before_t0'], 'unconfirmed')
        self.assertFalse(review['expert_review_completed'])
        self.assertEqual(after['ngs_report_before'], before['ngs_report_before'])
        self.assertEqual(after['t0_day'], before['t0_day'])

    def test_overlapping_nos_and_independence_rules_preserve_record_but_change_review_bucket(self):
        for pattern in ['same_full_course_drug_set', 'fewer_full_course_drugs_subset']:
            before = candidate()
            after = refine_candidate(before, inventory(pattern), [])
            self.assertEqual(after['screening_bucket'], 'regimen_independence_review')
            self.assertTrue(after['candidate_review']['nos_paad_retention_rule_applies'])
            self.assertEqual(after['candidate_id'], before['candidate_id'])
            self.assertEqual(after['candidate_review']['strategy_intent'], 'unknown_not_imputed')
        after = refine_candidate(candidate(), inventory('masked_identity_prevents_interpretation'), [])
        self.assertEqual(after['screening_bucket'], 'main_regimen_start_candidate')

    def test_nos_with_other_histology_or_without_paad_does_not_get_clean_nos_retention_annotation(self):
        r = inventory()
        r['histologies_raw_before_procedure'].append('8560 Adenosquamous carcinoma')
        self.assertFalse(refine_candidate(candidate(), r, [])['candidate_review']['nos_paad_retention_rule_applies'])
        r = inventory()
        r['predecision_ngs_pathology_links'] = []
        self.assertFalse(refine_candidate(candidate(), r, [])['candidate_review']['nos_paad_retention_rule_applies'])

    def test_same_day_link_never_crosses_patient_cancer_or_date_and_does_not_backdate_progression(self):
        p = candidate('p', kind='progression_without_later_recorded_start', bucket='progression_trigger_review')
        p['information_issues'] = ['same_day_treatment_and_progression_order_unknown']
        registry = [p, candidate('ok'), candidate('other_patient', patient='Q'), candidate('other_cancer', seq='2'), candidate('future', day=11)]
        self.assertEqual(same_day_links(registry), {'p': ['ok']})
        revised = refine_candidate(p, None, ['ok'])
        self.assertEqual(revised['screening_bucket'], 'progression_linked_same_day_not_separate')
        self.assertEqual(revised['t0_day'], 10)
        self.assertFalse(revised['candidate_review']['progression_is_treatment_predecision_input'])
        self.assertEqual(revised['candidate_review']['same_day_progression_order'], 'unknown')
        with self.assertRaises(ValueError):
            same_day_links([p, candidate('future', day=11)])
