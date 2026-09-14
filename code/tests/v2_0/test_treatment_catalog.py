import copy
import tempfile
import unittest
from pathlib import Path
from pdac_benchmark.v2_0.treatment_catalog import (
    BASE, load, validate_definitions, select_development, normalize_component,
    temporal_status, map_record, export_csv, build)


class TreatmentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.config=load(BASE/'code/config/v2.0/treatment_catalog.json')
        self.sources=load(BASE/self.config['source_ledger'])
        self.families=load(BASE/self.config['family_definitions'])
        self.variants=load(BASE/self.config['variant_definitions'])
        self.aliases=load(BASE/self.config['alias_definitions'])

    def component(self,name,slot=1,start=10,end=20):
        return dict(name_raw=name,slot=slot,start_day=start,end_day=end,masked=False)

    def record(self,components):
        return dict(candidate_id='c',patient_key=['P','1'],cancer_seq='1',t0_day=10,
                    candidate_role='main_observed_regimen',source_record_id='s',source={},regimen_components_full_course=components)

    def test_source_dates_and_human_results_valid(self):
        validate_definitions(self.config,self.sources,self.families,self.variants)

    def test_trial_registration_cannot_support_research_candidate(self):
        f=next(f for f in self.families if f['family_id']=='ADAGRASIB')
        s=copy.deepcopy(next(s for s in self.sources if s['evidence_id']=='ADAGRASIB'))
        s.update(source_type='trial_registration',human_results=False)
        with self.assertRaises(ValueError): validate_definitions(self.config,[s],[f],[])

    def test_cutoff_with_unknown_month_day_fails_closed(self):
        s=copy.deepcopy(self.sources[0]);s.update(publication_date='2026-09',date_precision='month')
        with self.assertRaises(ValueError): validate_definitions(self.config,[s],[],[])

    def test_core_treatment_changes_do_not_change_projection(self):
        d={'candidate_id':'dev','patient_split_assignment':{'patient_split':'development'}}
        c={'candidate_id':'core','patient_split_assignment':{'patient_split':'core_test'},'observed_action_drugs':['secret']}
        self.assertEqual(select_development([d,c]),select_development([dict(c,observed_action_drugs=['different']),d]))

    def test_formulations_and_parenthetical_aliases_stay_distinct(self):
        names=['Irinotecan HCL(Campto)','Irinotecan liposome(Onivyde)','Paclitaxel(Taxol)','Nabpaclitaxel(Abraxane)']
        values=[normalize_component(self.component(n),self.aliases,'c')['normalized_drug'] for n in names]
        self.assertEqual(values,['irinotecan','liposomal_irinotecan','paclitaxel','nab_paclitaxel'])
        self.assertEqual(normalize_component(self.component('Gemcitabine HCL(FF10832,Gemzar)'),self.aliases,'c')['normalized_drug'],'gemcitabine')

    def test_masked_instances_not_merged_and_no_family_guess(self):
        comp=[self.component('Gemcitabine HCL'),self.component('Investigational Drug',2),self.component('Investigational Drug',3)]
        r=map_record(self.record(comp),self.aliases,{('gemcitabine',):{'family_id':'GEM','catalog_status':'evidence_linked'}})
        self.assertEqual(r['mapping_status'],'masked_identity')
        self.assertIsNone(r['composition_family_id'])
        self.assertNotEqual(r['raw_components'][1]['masked_instance_id'],r['raw_components'][2]['masked_instance_id'])

    def test_sequential_and_missing_dates_not_combination_proof(self):
        self.assertEqual(temporal_status([self.component('a',start=1,end=3),self.component('b',2,5,8)],1),'no_common_recorded_interval')
        self.assertEqual(temporal_status([self.component('a',end=None)],10),'interval_incomplete')
        self.assertEqual(temporal_status([self.component('a',start=20,end=10)],20),'invalid_interval')

    def test_missing_leucovorin_not_imputed_and_variant_not_assigned(self):
        idx={tuple(f['components']):f for f in self.families}
        incomplete=self.record([self.component('Fluorouracil'),self.component('Oxaliplatin',2)])
        r=map_record(incomplete,self.aliases,idx)
        self.assertIsNone(r['composition_family_id'])
        incomplete['regimen_components_full_course'].append(self.component('Leucovorin',3))
        r=map_record(incomplete,self.aliases,idx)
        self.assertEqual(r['composition_family_id'],'OX_FF')
        self.assertIsNone(r['observed_variant_id'])
        self.assertIsNone(r['patient_label'])

    def test_csv_preserves_optional_fields(self):
        import csv
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'out.csv';export_csv(p,[{'id':'1'},{'id':'2','notes':'细节'}])
            with p.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
            self.assertEqual(rows[1]['notes'],'细节')

    def test_conflicting_regimens_and_new_approval_not_collapsed(self):
        ox=next(f for f in self.families if f['family_id']=='OX_FF')
        self.assertTrue({'CONKO003','PANCREOX'} <= set(ox['evidence_ids']))
        dara=next(f for f in self.families if f['family_id']=='DARA')
        self.assertEqual(dara['evaluation_context'],'routine')
        self.assertIn('DARA_LABEL',dara['evidence_ids'])

    def test_build_is_order_invariant_with_repeated_source_anchors(self):
        import hashlib,shutil
        a=self.record([self.component('Gemcitabine HCL')])
        a['patient_split_assignment']={'patient_split':'development'}
        b=copy.deepcopy(a);b.update(candidate_id='a',t0_day=15,candidate_role='treatment_context_appendix')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for k in ['source_ledger','family_definitions','variant_definitions','alias_definitions','disposition_definitions']:
                target=root/self.config[k];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/self.config[k],target)
            def run(records):
                s=build(root,root/'processed',root/'results',dict(self.config,catalog_frozen=False),records)
                checks={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'processed').glob('*')}
                return s,checks
            self.assertEqual(run([a,b]),run([b,a]))
