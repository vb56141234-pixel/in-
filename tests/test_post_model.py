import copy
import unittest
from services.post_model import *

class SetStructureTests(unittest.TestCase):
    def test_phase1_sets_are_independent(self):
        p=new_project();add_source(p,'A',{'id':'one','file':'one.jpg','name':'one.jpg'})
        self.assertEqual(p['sets']['B']['source_ids'],[])
        self.assertEqual(p['sets']['C']['versions'],{})
        self.assertEqual(p['schema_version'],2)
    def test_phase1_invalid_set_rejected(self):
        with self.assertRaises(ValueError): get_set(new_project(),'D')

class SourceManagementTests(unittest.TestCase):
    def test_phase2_capacity_reorder_and_delete(self):
        p=new_project()
        for i in range(10):add_source(p,'A',{'id':str(i),'file':f'{i}.jpg','name':f'{i}.jpg'})
        with self.assertRaises(ValueError):add_source(p,'A',{'id':'extra'})
        before=copy.deepcopy(p['assets'])
        reorder_sources(p,'A',list(reversed(p['sets']['A']['source_ids'])))
        self.assertEqual(p['assets'],before)
        with self.assertRaises(ValueError):reorder_sources(p,'A',['0']*10)
        remove_source(p,'A','9');self.assertEqual(len(p['sets']['A']['source_ids']),9)
        remove_source(p,'A');self.assertEqual(p['sets']['A']['source_ids'],[])
    def test_phase2_invalid_order_does_not_mutate(self):
        p=new_project();add_source(p,'A',{'id':'1','file':'1.jpg','name':'1.jpg'})
        before=copy.deepcopy(p)
        with self.assertRaises(ValueError):reorder_sources(p,'A',[])
        self.assertEqual(p,before)

class LanguageVersionTests(unittest.TestCase):
    def test_phase3_versions_preserve_source_and_each_other(self):
        p=new_project();add_source(p,'A',{'id':'1','file':'1.jpg','name':'사진.jpg'})
        original=copy.deepcopy(p['assets'])
        ko=ensure_version(p,'A','ko');ko['hook']='한국어';ko['slides'][0]['text']='한국어'
        ja=ensure_version(p,'A','ja');ja['hook']='日本語';ja['slides'][0]['style']['x']=30
        self.assertEqual(ko['hook'],'한국어');self.assertEqual(ko['slides'][0]['style']['x'],50)
        self.assertEqual(p['assets'],original);self.assertEqual(set(p['sets']['A']['versions']),{'ko','ja'})
        remove_source(p,'A','1')
        self.assertIn('1',p['assets']);self.assertEqual(ko['slides'][0]['source_id'],'1')
        self.assertNotEqual(ko['source_revision'],p['sets']['A']['source_revision'])
    def test_phase3_empty_set_cannot_generate(self):
        with self.assertRaises(ValueError):ensure_version(new_project(),'A','ko')
    def test_phase3_legacy_overflow_never_silently_truncated(self):
        with self.assertRaises(ValueError):migrate_legacy([{}]*31)

class ImmutableSourceTests(unittest.TestCase):
    def test_phase2_existing_source_cannot_be_replaced_or_duplicated(self):
        project=new_project();asset={'id':'source','file':'one.png','name':'one.png'}
        add_source(project,'A',asset);before=copy.deepcopy(project)
        with self.assertRaises(ValueError):add_source(project,'A',asset)
        with self.assertRaises(ValueError):add_source(project,'B',asset | {'file':'two.png'})
        self.assertEqual(project,before)
