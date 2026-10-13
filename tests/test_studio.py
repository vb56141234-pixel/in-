import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import zipfile
from PIL import Image, ImageFont
from app import create_app
from services.image_service import (square_crop, export_png, font_path,
                                    wrap_title, DEFAULT_STYLE, add_gradient)
from services.export_service import create_zip, safe_name
from services import ai_service

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='한글 폴더 ')
        self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def make_image(self,suffix):
        path=self.root/('여행 사진'+suffix)
        Image.new('RGB',(1600,900),(150,180,210)).save(path)
        return path
    def test_jpg_png_webp_square(self):
        for ext in ('.jpg','.png','.webp'):
            with self.subTest(ext=ext):
                image=square_crop(self.make_image(ext))
                self.assertEqual(image.size,(1080,1080))
                image.close()
    def test_crop_preserves_center_and_aspect(self):
        path=self.root/'crop.png'
        image=Image.new('RGB',(300,100),'red')
        for x in range(100,200):
            for y in range(100): image.putpixel((x,y),(0,255,0))
        image.save(path)
        result=square_crop(path,100)
        self.assertEqual(result.getpixel((50,50)),(0,255,0))
        self.assertEqual(result.getpixel((10,10)),(0,255,0))
    def test_korean_japanese_titles_change_pixels(self):
        source=self.make_image('.png')
        blank=self.root/'blank.png'
        export_png(source,blank)
        with Image.open(blank) as base:
            for text in ('사진 한 장의 새로운 이야기','旅の途中で見つけた景色'):
                target=self.root/(text+'.png')
                export_png(source,target,text)
                with Image.open(target) as output:
                    self.assertEqual(output.size,(1080,1080))
                    self.assertNotEqual(output.tobytes(),base.tobytes())
    def test_long_title_wrap_width(self):
        font=ImageFont.truetype(font_path(),95)
        lines=wrap_title('아주 긴 제목입니다 '+('한글 Japanese 写真 '*12),font,950)
        self.assertGreater(len(lines),2)
        self.assertTrue(all(font.getlength(line)<=950 for line in lines))
        export_png(self.make_image('.png'),self.root/'long.png','긴 제목 '*60)
        self.assertTrue((self.root/'long.png').exists())
    def test_transparent_logo_ratio_and_position(self):
        source=self.make_image('.png')
        logo=self.root/'logo.png'
        Image.new('RGBA',(200,100),(255,0,0,255)).save(logo)
        for position,x in [('left',50),('center',450),('right',850)]:
            target=self.root/(position+'.png')
            export_png(source,target,style={'logo_position':position},logo=logo)
            with Image.open(target) as result:
                self.assertEqual(result.getpixel((x,50)),(255,0,0))
                self.assertNotEqual(result.getpixel((x,150)),(255,0,0))
    def test_gradient_zero_and_full(self):
        image=Image.new('RGB',(100,100),'white')
        zero=add_gradient(image,0,50)
        full=add_gradient(image,100,50)
        self.assertEqual(zero.getpixel((50,99)),(255,255,255,255))
        self.assertEqual(full.getpixel((50,99)),(0,0,0,255))
        self.assertEqual(full.getpixel((50,0)),(255,255,255,255))
    def test_unicode_space_paths_zip_metadata(self):
        source=self.make_image('.webp')
        item=dict(id='sample',source=source.name,name=source.name,title='여행 이야기',caption='こんにちは\n새로운 여행',language='ja',style=DEFAULT_STYLE.copy())
        target=self.root/'결과 모음.zip'
        create_zip([item],self.root,None,target)
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            prefix=archive.namelist()[0].split('/')[0]
            records=json.loads(archive.read(prefix+'/captions.json'))
            self.assertEqual(records[0]['source_file'],source.name)
            self.assertEqual(records[0]['caption'],item['caption'])
            project=json.loads(archive.read(prefix+'/project.json'))
            self.assertEqual(project['items'][0]['style'],item['style'])
            self.assertEqual(archive.read(prefix+'/sources/001.webp'),source.read_bytes())
            with Image.open(io.BytesIO(archive.read(prefix+'/images/001.png'))) as image:
                self.assertEqual(image.size,(1080,1080))
            self.assertIn(item['title'],archive.read(prefix+'/captions.txt').decode())
        self.assertFalse((self.root/'export_sample.png').exists())
    def test_windows_safe_filename(self):
        result=safe_name('a:b/c\\d?<>|*". ')
        self.assertFalse(any(c in result for c in '<>:"/\\|?*'))
        self.assertFalse(result.endswith(('.', ' ')))

class APITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='스튜디오 테스트 ')
        self.app=create_app(self.temp.name)
        self.client=self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.token=session['csrf']
        self.headers={'X-Studio-Token':self.token}
    def tearDown(self): self.temp.cleanup()
    def upload(self,name='사진.jpg'):
        data=io.BytesIO();Image.new('RGB',(300,200),'blue').save(data,'JPEG');data.seek(0)
        response=self.client.post('/api/upload',data={'files':(data,name)},headers=self.headers)
        self.assertEqual(response.status_code,200)
        return response.json['items'][-1]
    def test_demo_without_key_and_manual_export(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            self.assertFalse(self.client.get('/api/state').json['ai_available'])
            item=self.upload()
            response=self.client.patch('/api/items/'+item['id'],json={'title':'우리의 가을','caption':'산책하기 좋은 날','style':{'font_size':8}},headers=self.headers)
            self.assertEqual(response.json['status'],'COMPLETE')
            image=self.client.get('/api/items/'+item['id']+'/image')
            self.assertEqual(image.status_code,200)
            with Image.open(io.BytesIO(image.data)) as output:
                self.assertEqual(output.size,(1080,1080))
            image.close()
            response=self.client.post('/api/export',headers=self.headers)
            self.assertEqual(response.status_code,200)
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                self.assertEqual(len([n for n in archive.namelist() if n.endswith('captions.json')]),1)
            response.close()
    def test_corrupt_and_unsupported_isolated(self):
        item=self.upload()
        response=self.client.post('/api/upload',data={'files':[(io.BytesIO(b'broken'),'broken.jpg'),(io.BytesIO(b'no'),'file.txt')]},headers=self.headers)
        self.assertEqual(len(response.json['errors']),2)
        self.assertEqual(len(response.json['items']),1)
        self.assertEqual(response.json['items'][0]['id'],item['id'])
    def test_reject_other_format_disguised_as_png(self):
        file=io.BytesIO();Image.new('RGB',(10,10)).save(file,'GIF');file.seek(0)
        response=self.client.post('/api/upload',data={'files':(file,'fake.png')},headers=self.headers)
        self.assertEqual(len(response.json['errors']),1)
    def test_missing_key_generation_preserves_original(self):
        item=self.upload()
        self.client.patch('/api/items/'+item['id'],json={'title':'기존 제목','caption':'기존 본문'},headers=self.headers)
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            response=self.client.post('/api/items/'+item['id']+'/generate',json={'analysis':{'subject':'sky'}},headers=self.headers)
        self.assertEqual(response.status_code,502)
        state=self.client.get('/api/state').json['items'][0]
        self.assertEqual(state['title'],'기존 제목')
        self.assertEqual(state['status'],'ERROR')
    def test_analysis_error_keeps_other_items(self):
        a=self.upload('first.jpg');b=self.upload('second.jpg')
        with patch('services.ai_service.analyze_image',side_effect=ai_service.AIError('네트워크 오류')):
            response=self.client.post('/api/items/'+a['id']+'/analyze',headers=self.headers)
        self.assertEqual(response.status_code,502)
        items=self.client.get('/api/state').json['items']
        self.assertEqual(items[0]['status'],'ERROR')
        self.assertEqual(items[1]['status'],'대기 중...')
    def test_mock_ai_generation_language_sample(self):
        item=self.upload()
        with patch('services.ai_service.generate_title_caption',return_value={'title':'旅の記録','caption':'素敵な一日です。'}) as generate:
            response=self.client.post('/api/items/'+item['id']+'/generate',json={'analysis':{'subject':'travel'},'language':'ja','sample':'短く'},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['language'],'ja')
        generate.assert_called_once_with({'subject':'travel'},'ja','短く')
    def test_security_csrf_host_and_traversal(self):
        self.assertEqual(self.client.post('/api/clear').status_code,403)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/items/unknown/image').status_code,400)
        self.upload('../bad.jpg')
        self.assertEqual(self.client.get('/api/state').json['items'][0]['name'],'bad.jpg')
    def test_validation_and_session_isolation(self):
        item=self.upload()
        response=self.client.patch('/api/items/'+item['id'],json={'style':{'font_size':float('inf')}},headers=self.headers)
        self.assertEqual(response.status_code,400)
        response=self.client.patch('/api/items/'+item['id'],json={'language':'invalid'},headers=self.headers)
        self.assertEqual(response.status_code,400)
        other=self.app.test_client();other.get('/')
        self.assertEqual(other.get('/api/state').json['items'],[])
    def test_logo_and_clear_removes_temp(self):
        self.upload()
        data=io.BytesIO();Image.new('RGBA',(100,100),(255,0,0,120)).save(data,'PNG');data.seek(0)
        response=self.client.post('/api/logo',data={'file':(data,'logo.png')},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertTrue(self.client.get('/api/state').json['logo'])
        self.client.post('/api/clear',headers=self.headers)
        state=self.client.get('/api/state').json
        self.assertFalse(state['logo']);self.assertEqual(state['items'],[])
        self.assertEqual([p for p in Path(self.temp.name).rglob('*') if p.is_file()],[])
    def test_hundred_images_metadata_without_memory_batch(self):
        for index in range(100): self.upload(f'{index}.jpg')
        state=self.client.get('/api/state').json
        self.assertEqual(len(state['items']),100)
    def test_empty_export_fails(self):
        self.assertEqual(self.client.post('/api/export',headers=self.headers).status_code,400)
    def test_api_key_never_in_state_html(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'sk-private-test-secret'}):
            self.assertNotIn(b'sk-private-test-secret',self.client.get('/').data)
            self.assertNotIn(b'sk-private-test-secret',self.client.get('/api/state').data)

class AIServiceTests(unittest.TestCase):
    def test_http_error_redacts_response_and_key(self):
        response=Mock(ok=False,status_code=401,text='sk-secret-sensitive')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'sk-secret-sensitive'}),patch('services.ai_service.requests.post',return_value=response):
            with self.assertRaises(ai_service.AIError) as error:
                ai_service.generate_title_caption({'subject':'photo'},'ko','')
        self.assertNotIn('sk-secret',str(error.exception))
        self.assertIn('401',str(error.exception))
    def test_malformed_ai_response(self):
        with patch('services.ai_service._call',return_value={'title':5,'caption':'wrong'}):
            with self.assertRaises(ai_service.AIError):
                ai_service.generate_title_caption({},'ko','')


class ProjectTests(unittest.TestCase):
    setUp=APITests.setUp
    tearDown=APITests.tearDown
    upload=APITests.upload
    def test_restore_roundtrip_with_styles_and_logo(self):
        item=self.upload()
        self.client.patch('/api/items/'+item['id'],json={'title':'가을의 이야기','caption':'旅に出よう','language':'ja','style':{'x':42,'font_size':7}},headers=self.headers)
        data=io.BytesIO();Image.new('RGBA',(30,20),(0,255,0,120)).save(data,'PNG');data.seek(0)
        self.client.post('/api/logo',data={'file':(data,'logo.png')},headers=self.headers)
        export=self.client.post('/api/export',headers=self.headers)
        contents=export.data;export.close()
        self.client.post('/api/clear',headers=self.headers)
        restored=self.client.post('/api/restore',data={'file':(io.BytesIO(contents),'프로젝트.zip')},headers=self.headers)
        self.assertEqual(restored.status_code,200,restored.json)
        self.assertTrue(restored.json['logo'])
        item=restored.json['items'][0]
        self.assertEqual(item['title'],'가을의 이야기')
        self.assertEqual(item['style']['x'],42)
        self.assertEqual(item['language'],'ja')
        response=self.client.get('/api/items/'+item['id']+'/image')
        self.assertEqual(response.status_code,200)
        response.close()
    def test_malicious_zip_path_preserves_existing_project(self):
        existing=self.upload()
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('project.json',json.dumps({'version':1,'items':[{'source':'../../outside.jpg','style':{}}]}))
            archive.writestr('../../outside.jpg',b'data')
        data.seek(0)
        response=self.client.post('/api/restore',data={'file':(data,'bad.zip')},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/state').json['items'][0]['id'],existing['id'])
        self.assertEqual(list(Path(self.temp.name).glob('**/restore-*')),[])
    def test_invalid_zip_is_reported(self):
        response=self.client.post('/api/restore',data={'file':(io.BytesIO(b'invalid'),'bad.zip')},headers=self.headers)
        self.assertEqual(response.status_code,400)

if __name__=='__main__': unittest.main()
