import hashlib
import tempfile
from pathlib import Path
import unittest
from PIL import Image
from services.image_service import render_post_image, prepare_post_canvas, post_gradient
from services.design_config import POST_STYLE, validate_style
from services.variation_service import create_variation

class PostRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='한글 디자인 ');self.root=Path(self.temp.name)
        self.source=self.root/'source.png'
        image=Image.new('RGB',(500,300));pixels=image.load()
        for y in range(300):
            for x in range(500):pixels[x,y]=(x%256,y%256,120)
        image.save(self.source)
    def tearDown(self):self.temp.cleanup()
    def test_phase6_variation_pixels_change_source_immutable_off_identical(self):
        original=hashlib.sha256(self.source.read_bytes()).digest()
        files=[]
        for language in ('ko','ja'):
            path=self.root/(language+'.png');render_post_image(self.source,path,variation=create_variation('1',language));files.append(path)
        self.assertNotEqual(files[0].read_bytes(),files[1].read_bytes())
        a=self.root/'off1.png';b=self.root/'off2.png'
        render_post_image(self.source,a,options={'variation_enabled':False},variation=create_variation('1','ko'))
        render_post_image(self.source,b,options={'variation_enabled':False},variation=create_variation('1','ja'))
        self.assertEqual(a.read_bytes(),b.read_bytes())
        self.assertEqual(original,hashlib.sha256(self.source.read_bytes()).digest())
    def test_phase7_all_ratios_and_fitting_modes(self):
        for ratio,size in [('1:1',(1080,1080)),('4:5',(1080,1350)),('9:16',(1080,1920))]:
            for mode in ('crop','fit','blur'):
                target=self.root/(ratio.replace(':','_')+mode+'.png')
                render_post_image(self.source,target,options={'aspect_ratio':ratio,'fit_mode':mode})
                with Image.open(target) as image:self.assertEqual(image.size,size)
    def test_phase7_gradient_directions(self):
        image=Image.new('RGBA',(100,100),'white')
        for direction,edge,other in [('bottom',(50,99),(50,0)),('top',(50,0),(50,99)),('left',(0,50),(99,50)),('right',(99,50),(0,50))]:
            result=post_gradient(image,POST_STYLE | {'gradient':100,'gradient_range':50,'gradient_direction':direction})
            self.assertEqual(result.getpixel(edge)[:3],(0,0,0),direction)
            self.assertEqual(result.getpixel(other)[:3],(255,255,255),direction)
    def test_phase7_design_settings_actual_render_and_validation(self):
        target=self.root/'design.jpg'
        render_post_image(self.source,target,'여행의 새로운 이야기\n日本語の見出し',
                          style={'font':'noto','weight':'Regular','color':'#c4f078','align':'left',
                                 'letter_spacing':2,'line_height':1.5,'shadow':False,'outline':0,
                                 'text_background':True,'background_opacity':65,'x':40,'y':55})
        with Image.open(target) as image:self.assertEqual(image.format,'JPEG')
        with self.assertRaises(ValueError):validate_style({'font_size':float('nan')})
        with self.assertRaises(ValueError):validate_style({'color':'red'})
