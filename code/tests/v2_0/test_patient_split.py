import json
import tempfile
import unittest
from pathlib import Path

from pdac_benchmark.v2_0.patient_split import quota_sample,earliest_main_candidates,verify_lock,check_identity_isolation


class PatientSplitTests(unittest.TestCase):
    def test_exact_quota_and_input_order_independence(self):
        items=[{'patient_key':['P',str(i)],'stratum':['A' if i<7 else 'B','met']} for i in range(10)]
        first,quotas=quota_sample(items,4,123,'core')
        second,_=quota_sample(list(reversed(items)),4,123,'core')
        self.assertEqual(first,second)
        self.assertEqual(len(first),4)
        self.assertEqual(quotas,{('A','met'):3,('B','met'):1})

    def test_sampling_rejects_duplicate_patients(self):
        r={'patient_key':['P','same'],'stratum':['A','met']}
        with self.assertRaises(ValueError):quota_sample([r,r],1,123,'core')

    def test_pilot_is_sampled_from_remaining_patients(self):
        items=[{'patient_key':['P',str(i)],'stratum':['A','met']} for i in range(30)]
        core,_=quota_sample(items,8,123,'core')
        pilot,_=quota_sample([r for r in items if tuple(r['patient_key']) not in core],5,123,'pilot')
        self.assertEqual(len(pilot),5)
        self.assertFalse(core&pilot)

    def test_index_ignores_outcomes_labels_and_non_main_early_record(self):
        baseline={'patient_key':['P','one'],'candidate_role':'main_observed_regimen'}
        rows=[{**baseline,'candidate_id':'later','t0_day':50,'expert_label':'SUPPORTED','outcome':'excellent'},
              {**baseline,'candidate_id':'early','t0_day':10,'expert_label':None,'outcome':None},
              {**baseline,'candidate_id':'earliest_other','t0_day':1,'candidate_role':'progression_extension'}]
        self.assertEqual(earliest_main_candidates(rows)[('P','one')]['candidate_id'],'early')

    def test_lock_refuses_silent_reassignment_and_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lock.json'
            original={'patient':'A','split':'core_test'}
            path.write_text(json.dumps(original),encoding='utf-8')
            verify_lock(path,original)
            with self.assertRaises(ValueError):verify_lock(path,{'patient':'A','split':'development'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),original)

    def test_shared_sample_across_patient_splits_is_rejected(self):
        candidates=[{'patient_key':['P','A'],'source_record_id':'a','temporal_partition':{'future':['ea']}},
                    {'patient_key':['P','B'],'source_record_id':'b','temporal_partition':{'future':['eb']}}]
        assignments={('P','A'):{'split':'development'},('P','B'):{'split':'core_test'}}
        events={k:{'kind':'ngs_report','facts':{'cpt_genie_sample_id':'shared'}} for k in ['ea','eb']}
        with self.assertRaises(ValueError):check_identity_isolation(candidates,assignments,events)

    def test_multiple_candidates_of_one_patient_may_share_events(self):
        c={'patient_key':['P','A'],'source_record_id':'a','temporal_partition':{'future':['ea']}}
        result=check_identity_isolation([c,c],{('P','A'):{'split':'core_test'}},{})
        self.assertEqual(result['cross_split_identity_collisions'],0)

    def test_missing_partition_does_not_skip_full_patient_sample_audit(self):
        candidates=[{'patient_key':['P','A'],'source_record_id':'a'},
                    {'patient_key':['P','B'],'source_record_id':'b'}]
        assignments={('P','A'):{'split':'development'},('P','B'):{'split':'core_test'}}
        events={k:{'patient_key':['P',p],'kind':'ngs_report','facts':{'cpt_genie_sample_id':'shared'}}
                for k,p in [('ea','A'),('eb','B')]}
        with self.assertRaises(ValueError):check_identity_isolation(candidates,assignments,events)


if __name__=='__main__':unittest.main()
