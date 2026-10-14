import copy
import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image
from services import ai_service
from services.variation_service import create_variation, validate_variation

ANALYSIS={'topic':'旅行','key_information':['画像の情報'],'image_text':[], 'interest':[],
          'emotion':[],'surprise':[],'questions':[],'relationships':'connected','story_order':[0,1]}

def content(count=2):
    return {'hook_candidates':[f'新しい旅の話 {i}' for i in range(5)],'caption':'自分のペースで楽しむ旅。',
            'slides':[{'source_index':i,'role':'HOOK' if i==0 else 'CTA','text':f'景色 {i}'} for i in range(count)]}

class PostAITests(unittest.TestCase):
    def test_phase4_reads_all_images_and_embedded_text(self):
        with tempfile.TemporaryDirectory() as root:
            paths=[]
            for i in range(2):
                path=Path(root)/f'{i}.png';Image.new('RGB',(100,100)).save(path);paths.append(path)
            with patch('services.ai_service._call',return_value=copy.deepcopy(ANALYSIS)) as call:
                result=ai_service.analyze_sources(paths)
            messages=call.call_args.args[0]
            self.assertEqual(len([x for x in messages[1]['content'] if x['type']=='image_url']),2)
            self.assertIn('embedded text',messages[0]['content'])
            self.assertFalse(result['fact_check']['verified'])
    def test_phase4_hooks_and_story_exact_count(self):
        with patch('services.ai_service._call',return_value=content()) as call:
            result=ai_service.generate_post_content(ANALYSIS,'ja','短い文体',2)
        self.assertEqual(len(result['hook_candidates']),5)
        self.assertEqual(len(result['slides']),2)
        self.assertEqual(result['slides'][0]['text'],result['hook'])
        with patch('services.ai_service._call',return_value=content(1)):
            with self.assertRaises(ai_service.AIError):ai_service.generate_post_content(ANALYSIS,'ja','',2)
    def test_phase5_generation_prompt_localizes_direct_source(self):
        with patch('services.ai_service._call',return_value=content()) as call:
            ai_service.generate_post_content(ANALYSIS,'ja','',2)
        prompt=call.call_args.args[0][0]['content']
        self.assertIn('日本語',prompt);self.assertIn('not translation',prompt)
        self.assertIn('unverified source claims',prompt)
        self.assertNotIn('한국어',call.call_args.args[0][1]['content'])
    def test_phase4_partial_generation_validates_payload(self):
        with patch('services.ai_service._call',return_value={'caption':'新しい説明です。'}):
            result=ai_service.regenerate_fragment('caption',ANALYSIS,'ja','')
        self.assertEqual(set(result),{'caption'})
        with patch('services.ai_service._call',return_value={'hook_candidates':['same']*5}):
            with self.assertRaises(ai_service.AIError):ai_service.regenerate_fragment('hook',ANALYSIS,'ja','')

class VariationTests(unittest.TestCase):
    def test_phase6_off_and_bounded_language_variants(self):
        self.assertIsNone(create_variation('one','ja',False))
        ko=create_variation('one','ko');ja=create_variation('one','ja')
        self.assertNotEqual(ko,ja);self.assertEqual(ja,create_variation('one','ja'))
        self.assertNotEqual(ja,create_variation('one','ja',nonce='new'))
        self.assertEqual(validate_variation(ja),ja)
        with self.assertRaises(ValueError):validate_variation({'zoom':1.5})

class CarouselSizeTests(unittest.TestCase):
    def test_phase4_story_adapts_to_1_3_5_10_sources(self):
        for count in (1,3,5,10):
            with self.subTest(count=count),patch('services.ai_service._call',return_value=content(count)):
                result=ai_service.generate_post_content(ANALYSIS,'en','',count)
                self.assertEqual(len(result['slides']),count)
                self.assertEqual([s['source_index'] for s in result['slides']],list(range(count)))
