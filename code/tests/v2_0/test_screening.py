import unittest
from pdac_benchmark.v2_0.screening import assign_screening_group, final_progression_groups, ngs_gate


def ngs(day, cancer='1', direct=True, agrees=True):
    return {'event_id': 'ngs:' + str(day) + ':' + cancer, 'kind': 'ngs_report',
            'cancer_seq': cancer, 'available_day': day,
            'cancer_attribution': 'direct_cancer_key' if direct else 'ambiguous_cancer_key',
            'facts': {'report_anchor_agrees': agrees}}


def imaging(day, status='Progressing/Worsening/Enlarging', ident=None):
    return {'event_id': ident or 'image:' + str(day), 'kind': 'imaging', 'event_day': day,
            'source_record_id': 'raw:' + str(day), 'source': {'file': 'fixture.csv', 'logical_row': 2},
            'facts': {'image_overall': status, 'image_ca': 'Yes, the Impression states or implies there is evidence of cancer'}}


class ScreeningTests(unittest.TestCase):
    def test_ngs_is_strictly_before_and_same_cancer_with_agreeing_dates(self):
        self.assertEqual(ngs_gate([ngs(10)], '1', 11)[0], 'confirmed_before')
        self.assertEqual(ngs_gate([ngs(10)], '1', 10), ('same_day_order_unknown', []))
        self.assertEqual(ngs_gate([ngs(10)], '1', 9), ('only_later_confirmed_reports', []))
        for event in [ngs(1, cancer='2'), ngs(1, direct=False), ngs(1, agrees=False), ngs(None)]:
            self.assertEqual(ngs_gate([event], '1', 10)[1], [])
        self.assertEqual(ngs_gate([ngs(1)], '1', None)[1], [])

    def test_repeated_progression_groups_without_shifting_after_ngs(self):
        groups, ledger = final_progression_groups([imaging(10), imaging(12), imaging(15)], [1])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['t0_day'], 10)
        self.assertEqual(len(groups[0]['evidence']), 3)
        self.assertEqual(len(ledger), 3)
        self.assertEqual(ngs_gate([ngs(11)], '1', groups[0]['t0_day'])[1], [])

    def test_later_drug_start_prevents_terminal_progression_candidate(self):
        groups, ledger = final_progression_groups([imaging(10), imaging(21)], [1, 20])
        self.assertEqual([g['t0_day'] for g in groups], [21])
        self.assertEqual(ledger[0]['later_start_relation'], 'later_treatment_start_recorded')

    def test_same_day_treatment_not_invented_as_before_progression(self):
        groups, ledger = final_progression_groups([imaging(10)], [10])
        self.assertEqual(len(groups), 1)
        self.assertEqual(ledger[0]['later_start_relation'], 'same_day_treatment_order_unknown')

    def test_nonprogression_assessment_splits_review_groups_and_same_day_conflict_flags(self):
        groups, _ = final_progression_groups([imaging(10), imaging(20, 'Stable/No change'), imaging(30)], [1])
        self.assertEqual([g['t0_day'] for g in groups], [10, 30])
        self.assertTrue(groups[1]['intervening_nonprogression_assessment'])
        groups, _ = final_progression_groups([imaging(10), imaging(10, 'Mixed', 'other')], [1])
        self.assertTrue(groups[0]['same_day_assessment_conflict'])

    def test_unknown_dates_and_cancer_evidence_not_silently_accepted(self):
        bad = imaging(10)
        bad['facts']['image_ca'] = 'No, no evidence'
        groups, ledger = final_progression_groups([imaging(None), bad], [1], True)
        self.assertEqual(groups, [])
        self.assertEqual(len(ledger), 2)
        self.assertTrue(all(x['treatment_chronology_incomplete'] for x in ledger))

    def test_missing_safety_fields_and_treatment_adjustments_are_separate(self):
        base = {'cancer_seq': '1', 't0_day': 10,
                'review_tier': 'metastatic_candidate_requires_information_review',
                'anchor_kind': 'regimen_start', 'information_issues': ['ECOG_not_provided', 'pathology_main_report_availability_unconfirmed']}
        c = assign_screening_group(base, [ngs(1)])
        self.assertEqual(c['screening_bucket'], 'main_regimen_start_candidate')
        self.assertNotIn('ECOG_not_provided', c['information_issues'])
        self.assertIn('pathology_main_report_availability_unconfirmed', c['information_issues'])
        self.assertFalse(c['independent_decision_confirmed'])
        self.assertIsNone(c['expert_label'])
        self.assertEqual(assign_screening_group({**base, 'anchor_kind': 'within_regimen_drug_start'}, [ngs(1)])['screening_bucket'], 'within_regimen_change_review')
        self.assertEqual(assign_screening_group({**base, 'anchor_kind': 'progression_without_later_recorded_start'}, [ngs(1)])['screening_bucket'], 'progression_trigger_review')
        self.assertEqual(assign_screening_group(base, [ngs(10)])['screening_bucket'], 'ngs_timing_review')
