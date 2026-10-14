"""Developer-only server with deterministic AI fixtures. No external AI requests."""
import json
from pathlib import Path
import re
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from flask import jsonify, request
from waitress import create_server
from app import create_app
from services import ai_service

calls=[];fail_next=False

def fake_call(messages,max_tokens=1200):
    global fail_next
    prompt=messages[0]['content'];calls.append(prompt)
    if prompt.startswith('Analyze ALL'):
        if fail_next:
            fail_next=False
            raise ai_service.AIError('테스트용 AI 네트워크 실패')
        count=sum(part['type']=='image_url' for part in messages[1]['content'])
        return {'topic':'fixture source story','key_information':['unverified source statement'],
                'image_text':[],'interest':[],'emotion':[],'surprise':[],'questions':[],
                'relationships':'ordered source images','story_order':list(range(count))}
    lang='ja' if '日本語' in prompt else 'en' if 'English' in prompt else 'ko'
    label={'ja':'日本の新しい物語','en':'A new source story','ko':'새로운 원본 이야기'}[lang]
    hooks=[f'{label} {len(calls)}-{i}' for i in range(5)]
    if 'slides (exactly' in prompt:
        data=json.loads(messages[1]['content']);count=len(data['source_analysis']['story_order'])
        return {'hook_candidates':hooks,'caption':label+' caption',
                'slides':[{'source_index':i,'role':'HOOK' if j==0 else 'CONTENT','text':f'{label} slide {j}'} for j,i in enumerate(reversed(range(count)))]}
    if 'hook_candidates: exactly' in prompt:return {'hook_candidates':hooks}
    if 'caption: one complete' in prompt:return {'caption':label+' new caption'}
    return {'text':label+' regenerated slide'}

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='studio-browser-ai-') as root:
        app=create_app(root)
        ai_service.available=lambda:True
        ai_service._call=fake_call
        @app.post('/__fixture/fail')
        def trigger_failure():
            global fail_next
            fail_next=True
            return jsonify(ok=True)
        @app.get('/__fixture/calls')
        def recorded_calls():return jsonify(calls=calls)
        server=create_server(app,host='127.0.0.1',port=8781,threads=4)
        print('Fixture server: http://127.0.0.1:8781',flush=True)
        try:server.run()
        finally:server.close()
