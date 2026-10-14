from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
from services.post_model import new_project, add_source, ensure_version
from services.post_archive import create_post_zip, restore_post_zip, validate_project
from services.variation_service import create_variation

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='한글 프로젝트 ');self.root=Path(self.temp.name)
        self.project=new_project()
        for key in ('A','B','C'):
            file=self.root/(key+'.png');Image.new('RGB',(300,200),(30,70,120)).save(file)
            add_source(self.project,key,{'id':key,'file':file.name,'name':key+' 원본.png'})
            for lang in ('ko','ja'):
                v=ensure_version(self.project,key,lang);v['hook']=v['slides'][0]['text']=key+lang+' 제목';v['caption']=key+lang+' 본문';v['slides'][0]['variation']=create_variation(key,lang)
    def tearDown(self):self.temp.cleanup()
    def test_phase8_full_project_roundtrip_all_languages_styles_and_sources(self):
        target=self.root/'project.zip';create_post_zip(self.project,self.root,target)
        stage=self.root/'restore';stage.mkdir()
        with target.open('rb') as stream:restored=restore_post_zip(stream,stage)
        for key in ('A','B','C'):
            for lang in ('ko','ja'):
                before=self.project['sets'][key]['versions'][lang];after=restored['sets'][key]['versions'][lang]
                self.assertEqual(before['hook'],after['hook']);self.assertEqual(before['caption'],after['caption'])
                self.assertEqual(before['slides'],after['slides']);self.assertEqual(before['options'],after['options'])
            self.assertEqual((self.root/self.project['assets'][key]['file']).read_bytes(),(stage/restored['assets'][key]['file']).read_bytes())
        self.assertEqual(restored['settings'],self.project['settings'])
    def test_phase8_rejects_traversal_missing_files_and_invalid_version(self):
        for change in ('traversal','missing','duplicate'):
            bad=deepcopy(self.project)
            if change=='traversal':bad['assets']['A']['file']='../../outside.png'
            if change=='missing':bad['assets']['A']['file']='missing.png'
            if change=='duplicate':bad['sets']['A']['source_ids']=['A','A']
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:archive.writestr('project.json',json.dumps(bad))
            stream.seek(0)
            with self.assertRaises(ValueError):restore_post_zip(stream,self.root)
            self.assertEqual(list(self.root.glob('post-restore-*')),[])
    def test_phase9_scope_hierarchy_caption_and_jpg_dimensions(self):
        for scope in ('version','set','all','project'):
            target=self.root/(scope+'.zip');create_post_zip(self.project,self.root,target,scope,'A','ja')
            with zipfile.ZipFile(target) as archive:
                names=archive.namelist();self.assertIsNone(archive.testzip())
                self.assertIn('1028FALL_PROJECT/A_SET/JA/01.jpg',names)
                self.assertEqual(archive.read('1028FALL_PROJECT/A_SET/JA/caption.txt').decode(),'Aja 본문')
                with Image.open(io.BytesIO(archive.read('1028FALL_PROJECT/A_SET/JA/01.jpg'))) as image:self.assertEqual(image.size,(1080,1350))
                if scope=='version':self.assertNotIn('1028FALL_PROJECT/A_SET/KO/01.jpg',names)
                if scope in ('version','set'):self.assertNotIn('1028FALL_PROJECT/B_SET/JA/01.jpg',names)
                else:self.assertIn('1028FALL_PROJECT/C_SET/KO/01.jpg',names)
    def test_phase8_orphaned_source_still_retained_if_old_version_uses_it(self):
        self.project['sets']['A']['source_ids']=[]
        target=self.root/'old-version.zip';create_post_zip(self.project,self.root,target)
        with target.open('rb') as stream:restored=restore_post_zip(stream,self.root)
        self.assertEqual(restored['sets']['A']['source_ids'],[])
        self.assertEqual(restored['sets']['A']['versions']['ja']['slides'][0]['source_id'],'A')
        self.assertIn('A',restored['assets'])

class LegacyMigrationTests(unittest.TestCase):
    def test_phase8_v1_zip_migrates_without_losing_captions(self):
        from services.export_service import create_zip
        from services.image_service import DEFAULT_STYLE
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'old.png';Image.new('RGB',(300,200)).save(source)
            item={'id':'old','source':'old.png','name':'구형 원본.png','title':'구형 제목','caption':'기존 본문',
                  'language':'ko','style':DEFAULT_STYLE | {'weight':'ExBold','x':40}}
            archive=root/'legacy.zip';create_zip([item],root,None,archive)
            with archive.open('rb') as stream:project=restore_post_zip(stream,root)
            version=project['sets']['A']['versions']['ko']
            self.assertEqual(version['caption'],'기존 본문');self.assertEqual(version['hook'],'구형 제목')
            self.assertEqual(version['options']['aspect_ratio'],'1:1')
            self.assertEqual(version['slides'][0]['style']['weight'],'ExtraBold')
            self.assertEqual(version['slides'][0]['style']['x'],40)
    def test_phase8_v1_overflow_rejected_before_installing_files(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:archive.writestr('project.json',json.dumps({'version':1,'items':[{}]*31}))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):restore_post_zip(stream,Path(directory))
            self.assertEqual(list(Path(directory).iterdir()),[])

class ProjectBudgetTests(unittest.TestCase):
    def test_phase8_9_export_and_import_share_size_budget(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'one.png';Image.new('RGB',(10,10)).save(source)
            project=new_project();add_source(project,'A',{'id':'one','file':source.name,'name':source.name})
            with patch('services.post_archive.MAX_PROJECT_BYTES',1):
                with self.assertRaises(ValueError):create_post_zip(project,root,root/'too-large.zip')
            self.assertFalse((root/'too-large.zip').exists())
    def test_phase8_legacy_long_captions_are_not_truncated_in_schema(self):
        from services.image_service import DEFAULT_STYLE
        from services.post_model import migrate_legacy
        items=[{'id':f'source{i}','source':f'{i}.png','name':f'{i}.png','title':'제목','caption':'문'*6000,
                'language':'ko','style':DEFAULT_STYLE.copy()} for i in range(10)]
        project=migrate_legacy(items);caption=project['sets']['A']['versions']['ko']['caption']
        # Paragraph separators count too; keep all original caption text in migration.
        self.assertEqual(caption.count('문'),60000)
        self.assertEqual(validate_project(project)['sets']['A']['versions']['ko']['caption'],caption)
