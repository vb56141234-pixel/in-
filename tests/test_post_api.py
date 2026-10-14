import io
import tempfile
import unittest
from PIL import Image
from app import create_app

class PostAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=create_app(self.temp.name);self.client=self.app.test_client();self.client.get('/')
        with self.client.session_transaction() as session:self.token=session['csrf']
        self.headers={'X-Studio-Token':self.token}
    def tearDown(self):self.temp.cleanup()
    def project(self):return self.client.get('/api/v2/project').json['project']
    def upload(self,key='A',count=1):
        files=[]
        for i in range(count):
            image=io.BytesIO();Image.new('RGB',(400,300),(60+i,120,180)).save(image,'PNG');image.seek(0)
            files.append((image,f'한글 사진 {i}.png'))
        return self.client.post(f'/api/v2/sets/{key}/sources',data={'files':files},headers=self.headers)
    def test_phase1_three_sets_and_settings(self):
        self.assertEqual(set(self.project()['sets']),{'A','B','C'})
        self.assertEqual(self.project()['settings']['aspect_ratio'],'4:5')
        result=self.client.patch('/api/v2/settings',json={'language':'ja'},headers=self.headers)
        self.assertEqual(result.json['project']['settings']['language'],'ja')
    def test_phase2_upload_capacity_order_removal(self):
        response=self.upload(count=11);self.assertEqual(len(response.json['added']),10)
        self.assertEqual(len(response.json['errors']),1)
        project=self.project();order=project['sets']['A']['source_ids'][::-1]
        response=self.client.patch('/api/v2/sets/A/order',json={'source_ids':order},headers=self.headers)
        self.assertEqual(response.json['project']['sets']['A']['source_ids'],order)
        source=self.client.get('/api/v2/assets/'+order[0]);self.assertEqual(source.status_code,200);source.close()
        self.client.delete('/api/v2/sets/A/sources/'+order[0],headers=self.headers)
        self.assertEqual(len(self.project()['sets']['A']['source_ids']),9)
        self.assertEqual(self.project()['sets']['B']['source_ids'],[])
    def test_phase3_manual_languages_and_stale_version_preserved(self):
        self.upload(count=2)
        for language in ('ko','ja'):
            self.client.post(f'/api/v2/sets/A/versions/{language}',json={},headers=self.headers)
        project=self.project();ko=project['sets']['A']['versions']['ko']
        self.client.patch('/api/v2/sets/A/versions/ko',json={'hook':'한국어 제목','caption':'본문'},headers=self.headers)
        ja=self.project()['sets']['A']['versions']['ja'];self.assertEqual(ja['hook'],'')
        order=project['sets']['A']['source_ids']
        self.client.patch('/api/v2/sets/A/order',json={'source_ids':order[::-1]},headers=self.headers)
        result=self.project()['sets']['A']
        self.assertEqual(result['versions']['ko']['hook'],'한국어 제목')
        self.assertEqual(result['versions']['ko']['slides'][0]['source_id'],order[0])
        self.assertNotEqual(result['versions']['ko']['source_revision'],result['source_revision'])

class GenerationAPITests(unittest.TestCase):
    setUp=PostAPITests.setUp
    tearDown=PostAPITests.tearDown
    upload=PostAPITests.upload
    project=PostAPITests.project
    def test_phase4_5_language_creation_keeps_ko_and_source(self):
        from unittest.mock import patch
        from test_post_ai import ANALYSIS, content
        import copy
        self.upload(count=2)
        self.client.post('/api/v2/sets/A/versions/ko',json={},headers=self.headers)
        self.client.patch('/api/v2/sets/A/versions/ko',json={'hook':'기존 한국어','caption':'한국어 본문'},headers=self.headers)
        original=copy.deepcopy(self.project()['assets'])
        with patch('services.ai_service.analyze_sources',return_value=ANALYSIS) as analyze,patch('services.ai_service.generate_post_content',return_value=content()):
            response=self.client.post('/api/v2/sets/A/generate',json={'language':'ja'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.json)
        project=response.json['project'];self.assertEqual(project['assets'],original)
        self.assertEqual(project['sets']['A']['versions']['ko']['hook'],'기존 한국어')
        ja=project['sets']['A']['versions']['ja']
        self.assertEqual(len(ja['hook_candidates']),5);self.assertEqual(len(ja['slides']),2)
        self.assertEqual(len(analyze.call_args.args[0]),2)
        self.assertIsNotNone(ja['slides'][0]['variation'])
    def test_phase4_partial_caption_and_error_preserve_previous(self):
        from unittest.mock import patch
        from services.ai_service import AIError
        from test_post_ai import ANALYSIS
        self.upload();self.client.post('/api/v2/sets/A/versions/ko',json={},headers=self.headers)
        self.client.patch('/api/v2/sets/A/versions/ko',json={'hook':'원래 제목','caption':'원래 본문'},headers=self.headers)
        with patch('services.ai_service.analyze_sources',return_value=ANALYSIS),patch('services.ai_service.regenerate_fragment',return_value={'caption':'새 본문'}):
            response=self.client.post('/api/v2/sets/A/generate',json={'language':'ko','kind':'caption'},headers=self.headers)
        self.assertEqual(response.status_code,200)
        version=self.project()['sets']['A']['versions']['ko'];self.assertEqual(version['hook'],'원래 제목');self.assertEqual(version['caption'],'새 본문')
        with patch('services.ai_service.analyze_sources',side_effect=AIError('네트워크 오류')):
            response=self.client.post('/api/v2/sets/A/generate',json={'language':'ko'},headers=self.headers)
        self.assertEqual(response.status_code,502)
        self.assertEqual(self.project()['sets']['A']['versions']['ko'],version)
    def test_phase6_variation_and_design_local_no_ai(self):
        from unittest.mock import patch
        self.upload();self.client.post('/api/v2/sets/A/versions/ko',json={},headers=self.headers)
        slide=self.project()['sets']['A']['versions']['ko']['slides'][0]
        with patch('services.ai_service.analyze_sources') as analyze:
            response=self.client.post('/api/v2/sets/A/generate',json={'language':'ko','kind':'variation','slide_id':slide['id']},headers=self.headers)
            self.assertEqual(response.status_code,200,response.json)
            self.assertIsNotNone(response.json['project']['sets']['A']['versions']['ko']['slides'][0]['variation'])
            response=self.client.post('/api/v2/sets/A/generate',json={'language':'ko','kind':'design','slide_id':slide['id']},headers=self.headers)
            self.assertEqual(response.status_code,200)
            analyze.assert_not_called()

class EditorArchiveAPITests(unittest.TestCase):
    setUp=PostAPITests.setUp
    tearDown=PostAPITests.tearDown
    upload=PostAPITests.upload
    project=PostAPITests.project
    def manual(self,key='A',language='ko'):
        self.upload(key,count=2)
        response=self.client.post(f'/api/v2/sets/{key}/versions/{language}',json={},headers=self.headers)
        self.assertEqual(response.status_code,200)
        return response.json['project']['sets'][key]['versions'][language]
    def test_phase7_style_logo_scope_and_render(self):
        version=self.manual();slide=version['slides'][0]
        response=self.client.patch(f"/api/v2/sets/A/versions/ko/slides/{slide['id']}",json={'text':'우리의 새로운 이야기','style':{'color':'#c4f078','letter_spacing':2,'weight':'Medium'}},headers=self.headers)
        self.assertEqual(response.status_code,200)
        logo=io.BytesIO();Image.new('RGBA',(100,50),(255,0,0,140)).save(logo,'PNG');logo.seek(0)
        response=self.client.post('/api/v2/logo',data={'file':(logo,'brand.png'),'scope':'A'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['project']['sets']['A']['logo']['mode'],'custom')
        self.assertEqual(response.json['project']['logo']['mode'],'none')
        response=self.client.get(f"/api/v2/sets/A/versions/ko/slides/{slide['id']}/image")
        self.assertEqual(response.status_code,200)
        with Image.open(io.BytesIO(response.data)) as image:self.assertEqual(image.size,(1080,1350))
        response.close()
        self.client.patch('/api/v2/logo',json={'scope':'A','mode':'none'},headers=self.headers)
        self.assertEqual(self.project()['sets']['A']['logo']['mode'],'none')
    def test_phase7_carousel_order_independent_of_sources_and_languages(self):
        version=self.manual();sources=self.project()['sets']['A']['source_ids'].copy()
        order=[s['id'] for s in version['slides']][::-1]
        response=self.client.patch('/api/v2/sets/A/versions/ko/order',json={'slide_ids':order},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual([s['id'] for s in response.json['project']['sets']['A']['versions']['ko']['slides']],order)
        self.assertEqual(response.json['project']['sets']['A']['source_ids'],sources)
    def test_phase8_api_restoration_failure_does_not_overwrite(self):
        version=self.manual();before=self.project()
        result=self.client.post('/api/v2/restore',data={'file':(io.BytesIO(b'bad'),'bad.zip')},headers=self.headers)
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.project(),before)
    def test_phase8_9_api_export_reset_restore(self):
        version=self.manual()
        self.client.patch('/api/v2/sets/A/versions/ko',json={'hook':'한글 HOOK','caption':'공통 Caption'},headers=self.headers)
        result=self.client.post('/api/v2/export',json={'scope':'project'},headers=self.headers)
        self.assertEqual(result.status_code,200,result.json)
        contents=result.data;result.close()
        self.client.delete('/api/v2/project',headers=self.headers)
        self.assertEqual(self.project()['sets']['A']['source_ids'],[])
        result=self.client.post('/api/v2/restore',data={'file':(io.BytesIO(contents),'한글 프로젝트.zip')},headers=self.headers)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['project']['sets']['A']['versions']['ko']['hook'],'한글 HOOK')
        self.assertEqual(result.json['project']['sets']['A']['versions']['ko']['caption'],'공통 Caption')
    def test_phase8_same_signed_session_can_resume_with_recreated_app(self):
        self.manual();before=self.project()
        reopened=create_app(self.temp.name);reopened.config['SECRET_KEY']=self.app.config['SECRET_KEY']
        client=reopened.test_client()
        cookie=self.client.get_cookie('session');client.set_cookie('session',cookie.value)
        result=client.get('/api/v2/project')
        self.assertEqual(result.json['project'],before)
    def test_phase7_invalid_editor_objects_rejected(self):
        self.manual()
        for payload in ({'options':[]},{'options':{'aspect_ratio':[]}},{'hook':5}):
            result=self.client.patch('/api/v2/sets/A/versions/ko',json=payload,headers=self.headers)
            self.assertEqual(result.status_code,400,result.json)
        result=self.client.patch('/api/v2/settings',json={'language':[]},headers=self.headers)
        self.assertEqual(result.status_code,400)
