import unittest
from pdac_benchmark.v2_0.decision_points import biomarker_events, make_anchors, partition_time, scope_at


class DecisionPointTests(unittest.TestCase):
    def test_addendum_uses_report_date_not_specimen_date(self):
        row = {'record_id': 'r1', 'source': {}, 'fields': {'dx_path_proc_days': '5', 'msi_yn': 'Yes', 'msi_prepaint': '10100', 'msi_result': 'MSI-H: HIGH'}}
        events = biomarker_events(row, 10000)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['available_day'], 100)
        self.assertEqual(partition_time(events[0], 50), 'future')
        self.assertEqual(partition_time(events[0], 100), 'same_day_order_unknown')
        self.assertEqual(partition_time(events[0], 101), 'confirmed_before')

    def test_unknown_pathology_report_time_remains_unconfirmed(self):
        event = {'event_day': -5, 'available_day': None}
        self.assertEqual(partition_time(event, 0), 'event_before_availability_unconfirmed')
        self.assertEqual(partition_time({'event_day': None, 'available_day': None}, 0), 'unknown_time')

    def test_later_drug_additions_are_not_backdated_and_stops_are_not_invented(self):
        row = {'record_id': 'r2', 'fields': {'dx_reg_start_int': '10', 'drugs_drug_1': 'A', 'dx_drug_start_int_1': '10', 'dx_drug_end_int_1': '20', 'drugs_drug_2': 'Investigational Drug', 'dx_drug_start_int_2': '15', 'dx_drug_end_int_2': '15'}}
        anchors = make_anchors(row, 100)
        self.assertEqual([a['t0_day'] for a in anchors], [110, 115])
        self.assertEqual([d['name_raw'] for d in anchors[0]['observed_action_drugs']], ['A'])
        self.assertTrue(anchors[1]['observed_action_drugs'][0]['masked'])
        self.assertNotIn(120, [a['t0_day'] for a in anchors])

    def test_future_metastasis_cannot_define_earlier_metastatic_context(self):
        cancer = {'is_index': True, 'fields': {'stage_dx': 'Stage II', 'ca_resect_status': 'Resectable', 'dmets_post_dx': '1', 'dx_to_dmets_days': '90'}}
        self.assertEqual(scope_at(cancer, 0, 10), 'resectable_or_borderline_baseline_current_context_unconfirmed')
        self.assertEqual(scope_at(cancer, 0, 90), 'metastasis_same_day_needs_order_review')
        self.assertEqual(scope_at(cancer, 0, 91), 'metastatic_after_diagnosis')

    def test_baseline_combined_resectability_is_not_current_metastatic_diagnosis(self):
        cancer = {'is_index': True, 'fields': {'stage_dx': 'Stage III', 'ca_resect_status': 'Unresectable/locally advanced or metastatic'}}
        self.assertEqual(scope_at(cancer, 0, 100), 'baseline_unresectable_advanced_current_context_unconfirmed')
        self.assertEqual(scope_at({**cancer, 'is_index': False}, 0, 100), 'non_index_cancer')
