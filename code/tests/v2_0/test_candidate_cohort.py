import unittest
from pdac_benchmark.v2_0.candidate_cohort import assign_role, prior_histology_signals


def pathology(day, cancer='Pancreatic Cancer'):
    return {'event_id':str(day), 'kind':'pathology_procedure','event_day':day,'source':{},
            'facts':{'specimens':[{'invasive':'Yes','cancer_type':cancer,
                                  'invasive_histology':'8154 Mixed acinar-neuroendocrine carcinoma'}]}}


class CandidateCohortTests(unittest.TestCase):
    def test_future_and_same_day_histology_not_used(self):
        c={'t0_day':50}
        found=prior_histology_signals(c,[pathology(49),pathology(50),pathology(60),pathology(None)])
        self.assertEqual([s['event_id'] for s in found],['49'])

    def test_other_cancer_histology_does_not_trigger_pancreatic_conflict(self):
        self.assertEqual(prior_histology_signals({'t0_day':50},[pathology(40,'Lung Cancer')]),[])

    def test_missing_candidate_time_never_claims_prior_pathology(self):
        self.assertEqual(prior_histology_signals({'t0_day':None},[pathology(40)]),[])

    def test_histology_review_is_point_specific_not_patient_wide(self):
        first={'candidate_id':'early','screening_bucket':'main_regimen_start_candidate','patient_key':['P','same']}
        later={**first,'candidate_id':'later'}
        self.assertEqual(assign_role(first,{'early'},set())[0],'histology_conflict_review')
        self.assertEqual(assign_role(later,{'early'},set())[0],'main_observed_regimen')

    def test_context_case_is_not_relabelled_adjuvant_or_metastatic(self):
        c={'candidate_id':'x','screening_bucket':'main_regimen_start_candidate'}
        self.assertEqual(assign_role(c,set(),{'x'})[0],'disease_context_review')
        self.assertEqual(c['screening_bucket'],'main_regimen_start_candidate')

    def test_extension_appendix_and_linked_rows_not_counted_as_main(self):
        for bucket,expected in [('progression_trigger_review','progression_extension'),
                                ('within_regimen_change_review','treatment_context_appendix'),
                                ('regimen_independence_review','treatment_context_appendix'),
                                ('progression_linked_same_day_not_separate','linked_progression_reference')]:
            with self.subTest(bucket=bucket):
                self.assertEqual(assign_role({'candidate_id':'x','screening_bucket':bucket},set(),set())[0],expected)


if __name__=='__main__':
    unittest.main()
