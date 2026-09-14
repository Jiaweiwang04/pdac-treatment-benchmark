import copy,json,shutil,tempfile,unittest
from pathlib import Path
from pdac_benchmark.v2_0.treatment_catalog import BASE,load,build
from pdac_benchmark.v2_0.catalog_release import definition_paths,verify
from pdac_benchmark.v2_0.core_coverage import audit_records
from pdac_benchmark.v2_0.regimen_screening import screen


class CatalogReleaseTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load(BASE/'code/config/v2.0/treatment_catalog.json')
        self.family=load(BASE/self.cfg['family_definitions'])
        self.alias=load(BASE/self.cfg['alias_definitions'])

    def record(self,split='development',name='Gemcitabine HCL'):
        return dict(candidate_id='one',patient_key=['P','1'],cancer_seq='1',t0_day=10,
            candidate_role='main_observed_regimen',source_record_id='reg1',source={},
            patient_split_assignment=dict(patient_split=split,core_primary_index=split=='core_test'),
            regimen_components_full_course=[dict(slot=1,name_raw=name,start_day=10,end_day=20,masked=False)])

    def populate(self,root):
        for n in definition_paths(self.cfg):
            p=root/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
        return build(root,root/self.cfg['processed_dir'],root/self.cfg['results_dir'],self.cfg,[self.record()])

    def test_freeze_is_idempotent_and_integrity_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=self.populate(root);lock=(root/self.cfg['freeze_lock']).read_bytes()
            verify(root,self.cfg)
            second=build(root,root/self.cfg['processed_dir'],root/self.cfg['results_dir'],self.cfg,[self.record()])
            self.assertEqual(first,second);self.assertEqual(lock,(root/self.cfg['freeze_lock']).read_bytes())

    def test_changed_definition_cannot_overwrite_frozen_products(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.populate(root)
            p=root/self.cfg['family_definitions'];f=load(p);f[0]['notes_zh']='changed';p.write_text(json.dumps(f),encoding='utf-8')
            product=root/self.cfg['processed_dir']/'treatment_families_v2.0.jsonl';before=product.read_bytes()
            with self.assertRaises(ValueError):verify(root,self.cfg)
            with self.assertRaises(ValueError):build(root,root/self.cfg['processed_dir'],root/self.cfg['results_dir'],self.cfg,[self.record()])
            self.assertEqual(before,product.read_bytes())

    def test_changed_development_projection_rejects_release_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.populate(root);r=self.record();r['t0_day']=11
            with self.assertRaises(ValueError):build(root,root/self.cfg['processed_dir'],root/self.cfg['results_dir'],self.cfg,[r])

    def test_changed_derived_product_fails_before_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.populate(root)
            p=root/self.cfg['processed_dir']/'treatment_families_v2.0.jsonl'
            p.write_text('{}\n',encoding='utf-8')
            with self.assertRaises(ValueError):verify(root,self.cfg)

    def test_core_unknown_treatment_never_expands_catalog(self):
        before=copy.deepcopy(self.family);r=self.record('core_test','Unknown New Core Drug')
        rows=audit_records([r],self.alias,self.family)
        self.assertEqual(rows[0]['coverage_status'],'identity_unresolved')
        self.assertIsNone(rows[0]['composition_family_id']);self.assertIsNone(rows[0]['patient_label'])
        self.assertEqual(before,self.family)
        self.assertEqual(audit_records([self.record()],self.alias,self.family),[])

    def test_unknown_development_pattern_cannot_be_silently_closed(self):
        from pdac_benchmark.v2_0.treatment_catalog import map_record
        r=self.record(name='New Drug')
        mapped=map_record(r,{'New Drug':'new_drug'},{})
        with self.assertRaises(ValueError):screen([mapped],[],[],self.family,[])

    def test_known_negative_results_and_guideline_positions_preserved(self):
        by_id={f['family_id']:f for f in self.family}
        self.assertEqual(by_id['TMZ_MONO']['evidence_direction'],'no_objective_responses')
        self.assertEqual(by_id['GEM_PAC']['evaluation_context'],'routine')
        self.assertIn('ESMO2025',by_id['GEM_PAC']['evidence_ids'])
        variants=load(BASE/self.cfg['variant_definitions'])
        off=next(v for v in variants if v['variant_id']=='OFF_CONKO003')
        self.assertFalse(off['eligible_for_variant_level_label'])
