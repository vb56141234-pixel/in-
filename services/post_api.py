"""Incremental POST SET API, independent from retained v1 image endpoints."""
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import uuid
from flask import Blueprint, jsonify, request, send_file
from PIL import Image, ImageOps
from . import ai_service
from .config import LANGUAGES
from .design_config import validate_style, validate_options
from .post_model import (new_project, get_set, add_source, reorder_sources, remove_source,
                         ensure_version, get_version, migrate_legacy, require_language, new_version)

EXTENSIONS={'.jpg','.jpeg','.png','.webp'}

def register_post_api(app, workspace, read_legacy):
    api=Blueprint('post_sets',__name__,url_prefix='/api/v2')
    def save(project):
        path=workspace()/'post_project.json'
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(project,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        tmp.replace(path)
    def load():
        path=workspace()/'post_project.json'
        if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
        old=read_legacy()
        project=migrate_legacy(old) if old else new_project()
        if (workspace()/'logo.png').exists():
            project['assets']['legacy-logo']={'id':'legacy-logo','file':'logo.png','name':'logo.png'}
            project['logo'].update(mode='custom',asset='legacy-logo')
        save(project)
        return project
    def body():
        data=request.get_json(silent=True)
        if not isinstance(data,dict): raise ValueError('JSON 객체를 입력하세요.')
        return data
    def state(project):
        return jsonify(project=project,languages=LANGUAGES,ai_available=ai_service.available())

    @api.get('/project')
    def project_state(): return state(load())

    @api.patch('/settings')
    def settings():
        project=load();data=body();settings=project['settings']
        if 'language' in data:settings['language']=require_language(data['language'])
        if 'style_sample' in data:
            if not isinstance(data['style_sample'],str): raise ValueError('문체 샘플은 텍스트여야 합니다.')
            settings['style_sample']=data['style_sample'][:5000]
        settings.update(validate_options(settings | {k:v for k,v in data.items() if k in ('aspect_ratio','fit_mode','variation_enabled')}))
        if 'default_style' in data:
            if not isinstance(data['default_style'],dict): raise ValueError('디자인 설정을 확인하세요.')
            settings['default_style']=validate_style(settings['default_style'] | data['default_style'])
        save(project);return state(project)

    @api.post('/sets/<key>/sources')
    def upload_sources(key):
        project=load();post=get_set(project,key);errors=[];added=[]
        for file in request.files.getlist('files'):
            name=Path((file.filename or '').replace('\\','/')).name
            suffix=Path(name).suffix.lower()
            if len(post['source_ids'])>=10:
                errors.append({'name':name,'error':'SET당 최대 10장입니다.'});continue
            if suffix not in EXTENSIONS:
                errors.append({'name':name,'error':'JPG/PNG/WEBP만 지원합니다.'});continue
            identifier=uuid.uuid4().hex;target=workspace()/(identifier+suffix)
            try:
                file.save(target)
                if target.stat().st_size>32*1024*1024:raise ValueError('이미지는 최대 32MB입니다.')
                with Image.open(target) as image:
                    if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>40_000_000:
                        raise ValueError('지원하지 않거나 너무 큰 이미지입니다.')
                    image.verify()
                asset={'id':identifier,'name':name,'file':target.name}
                add_source(project,key,asset);added.append(identifier)
            except (OSError,ValueError,Image.DecompressionBombError):
                target.unlink(missing_ok=True);errors.append({'name':name,'error':'손상되거나 너무 큰 이미지입니다.'})
        save(project);return jsonify(project=project,errors=errors,added=added)

    @api.patch('/sets/<key>/order')
    def reorder(key):
        project=load();reorder_sources(project,key,body().get('source_ids'));save(project);return state(project)

    @api.delete('/sets/<key>/sources/<identifier>')
    def delete_source(key,identifier):
        project=load();remove_source(project,key,identifier);save(project);return state(project)

    @api.delete('/sets/<key>/sources')
    def clear_sources(key):
        project=load();remove_source(project,key);save(project);return state(project)

    @api.get('/assets/<identifier>')
    def source_preview(identifier):
        project=load();asset=project['assets'].get(identifier)
        if not asset:raise ValueError('SOURCE를 찾을 수 없습니다.')
        # Bounded thumbnail instead of decoding full-resolution originals in the browser.
        target=workspace()/(identifier+'-thumb.jpg')
        with Image.open(workspace()/asset['file']) as image:
            thumb=ImageOps.exif_transpose(image).convert('RGB');thumb.thumbnail((480,480))
            thumb.save(target,'JPEG',quality=85)
        return send_file(target,mimetype='image/jpeg',max_age=0)

    @api.post('/sets/<key>/versions/<language>')
    def manual_version(key,language):
        project=load();data=body()
        ensure_version(project,key,language,data.get('options'))
        save(project);return state(project)

    @api.patch('/sets/<key>/versions/<language>')
    def edit_version(key,language):
        project=load();version=get_version(project,key,language);data=body()
        for field,limit in (('hook',300),('caption',65000)):
            if field in data:
                if not isinstance(data[field],str):raise ValueError('문구는 텍스트여야 합니다.')
                version[field]=data[field][:limit]
        if 'hook' in data and version['slides']:version['slides'][0]['text']=version['hook']
        if 'options' in data:
            if not isinstance(data['options'],dict):raise ValueError('이미지 설정을 확인하세요.')
            version['options']=validate_options(version['options'] | data['options'])
        save(project);return state(project)

    @api.patch('/sets/<key>/versions/<language>/slides/<identifier>')
    def edit_slide(key,language,identifier):
        project=load();version=get_version(project,key,language);data=body()
        slide=next((s for s in version['slides'] if s['id']==identifier),None)
        if slide is None:raise ValueError('슬라이드를 찾을 수 없습니다.')
        if 'text' in data:
            if not isinstance(data['text'],str):raise ValueError('이미지 문구는 텍스트여야 합니다.')
            slide['text']=data['text'][:600]
            if slide is version['slides'][0]:version['hook']=slide['text'][:300]
        if 'style' in data:
            if not isinstance(data['style'],dict):raise ValueError('스타일 설정을 확인하세요.')
            slide['style']=validate_style(slide['style'] | data['style'])
        save(project);return state(project)

    @api.post('/sets/<key>/generate')
    def generate_set(key):
        from .variation_service import create_variation
        project=load();post=get_set(project,key);data=body()
        language=require_language(data.get('language',project['settings']['language']))
        kind=data.get('kind','all')
        if kind not in ('all','hook','caption','slide','design','variation'):
            raise ValueError('재생성 종류를 확인하세요.')
        options=validate_options(data.get('options',project['settings']))
        sample=project['settings']['style_sample']
        try:
            if kind=='all':
                version=new_version(project,key,language,options)
            else:
                version=deepcopy(get_version(project,key,language))
            slide=None
            if kind in ('slide','design','variation'):
                slide=next((s for s in version['slides'] if s['id']==data.get('slide_id')),None)
                if slide is None:raise ValueError('현재 이미지를 선택하세요.')
            if kind in ('all','hook','caption','slide'):
                paths=[workspace()/project['assets'][s['source_id']]['file'] for s in version['slides']]
                analysis=ai_service.analyze_sources(paths)  # Always read original SOURCE again.
                if kind=='all':
                    generated=ai_service.generate_post_content(analysis,language,sample,len(paths))
                    originals=version['slides']
                    version['slides']=[deepcopy(originals[spec['source_index']]) | {'text':spec['text'],'role':spec['role']}
                                       for spec in generated['slides']]
                    version.update(hook_candidates=generated['hook_candidates'],hook=generated['hook_candidates'][0],caption=generated['caption'])
                    for entry in version['slides']:
                        entry['variation']=create_variation(entry['source_id'],language,options['variation_enabled'])
                        if entry['variation']:
                            entry['style']=validate_style(entry['style'] | {
                                'x':50+entry['variation']['shift_x']*150,
                                'y':72+entry['variation']['shift_y']*150})
                else:
                    index=version['slides'].index(slide) if slide else 0
                    fragment=ai_service.regenerate_fragment(kind,analysis,language,sample,index,len(paths))
                    if kind=='hook':
                        version['hook_candidates']=fragment['hook_candidates']
                        version['hook']=fragment['hook_candidates'][0];version['slides'][0]['text']=version['hook']
                    elif kind=='caption':version['caption']=fragment['caption']
                    else:
                        slide['text']=fragment['text']
                        if slide is version['slides'][0]:version['hook']=slide['text'][:300]
                version['analysis']=analysis
            elif kind=='variation':
                if not version['options']['variation_enabled']:
                    raise ValueError('이 버전의 이미지 Variation을 먼저 켜세요.')
                slide['variation']=create_variation(slide['source_id'],language,True,uuid.uuid4().hex)
            else:
                variation=create_variation(slide['source_id'],language,True,uuid.uuid4().hex)
                slide['style']=validate_style(slide['style'] | {
                    'x':50+variation['shift_x']*250,'y':72+variation['shift_y']*300,
                    'gradient':75+variation['shift_x']*500,'gradient_range':55+variation['shift_y']*300})
            version.update(status='COMPLETE',error='',updated_at=datetime.now(timezone.utc).isoformat())
            post['versions'][language]=version
            post.update(status='COMPLETE',error='')
            save(project);return state(project)
        except ai_service.AIError as exc:
            post.update(status='ERROR',error=str(exc))
            save(project)
            raise

    def logo_target(project,scope):
        if scope=='project':return project['logo']
        return get_set(project,scope)['logo']

    def resolved_logo(project,key):
        logo=get_set(project,key)['logo']
        if logo['mode']=='inherit':logo=project['logo']
        asset=project['assets'].get(logo.get('asset')) if logo['mode']=='custom' else None
        return (workspace()/asset['file'] if asset else None),logo

    @api.post('/logo')
    def upload_logo():
        project=load();scope=request.form.get('scope','project');config=logo_target(project,scope)
        file=request.files.get('file')
        if not file or Path(file.filename or '').suffix.lower() not in ('.png','.webp'):
            raise ValueError('PNG 또는 WEBP 로고를 선택하세요.')
        identifier=uuid.uuid4().hex;target=workspace()/(identifier+'.png');raw=workspace()/(identifier+'.upload')
        try:
            file.save(raw)
            if raw.stat().st_size>32*1024*1024:raise ValueError('로고는 최대 32MB입니다.')
            with Image.open(raw) as image:
                if image.format not in ('PNG','WEBP') or image.width*image.height>16_000_000:
                    raise ValueError('지원하지 않거나 너무 큰 로고입니다.')
                mark=image.convert('RGBA');mark.thumbnail((1600,1600));mark.save(target,'PNG')
            project['assets'][identifier]={'id':identifier,'file':target.name,'name':Path(file.filename.replace('\\','/')).name}
            config.update(mode='custom',asset=identifier)
            save(project);return state(project)
        finally:raw.unlink(missing_ok=True)

    @api.patch('/logo')
    def edit_logo():
        project=load();data=body();scope=data.get('scope','project');config=logo_target(project,scope)
        if 'size' in data:
            size=data['size']
            if not isinstance(size,(int,float)) or isinstance(size,bool) or not 5<=size<=35:raise ValueError('로고 크기는 5–35%입니다.')
            config['size']=size
        if 'position' in data:
            if data['position'] not in ('left','center','right'):raise ValueError('로고 위치를 확인하세요.')
            config['position']=data['position']
        if 'mode' in data:
            if data['mode'] not in (('none','custom') if scope=='project' else ('none','custom','inherit')):
                raise ValueError('로고 적용 범위를 확인하세요.')
            if data['mode']=='custom' and not config['asset']:raise ValueError('먼저 로고를 업로드하세요.')
            config['mode']=data['mode']
            if config['mode']=='none':config['asset']=None
        save(project);return state(project)

    @api.post('/sets/<key>/versions/<language>/style')
    def apply_version_style(key,language):
        project=load();version=get_version(project,key,language);patch=body().get('style')
        if not isinstance(patch,dict):raise ValueError('디자인 설정을 확인하세요.')
        for slide in version['slides']:slide['style']=validate_style(slide['style'] | patch)
        save(project);return state(project)

    @api.get('/sets/<key>/versions/<language>/slides/<identifier>/image')
    def rendered_slide(key,language,identifier):
        from .image_service import render_post_image
        project=load();version=get_version(project,key,language)
        slide=next((s for s in version['slides'] if s['id']==identifier),None)
        if slide is None:raise ValueError('현재 이미지를 찾을 수 없습니다.')
        asset=project['assets'][slide['source_id']]
        logo,config=resolved_logo(project,key)
        target=workspace()/(identifier+'-v2.png')
        render_post_image(workspace()/asset['file'],target,slide['text'],slide['style'],version['options'],slide['variation'],logo,config)
        index=version['slides'].index(slide)+1
        return send_file(target,mimetype='image/png',as_attachment=request.args.get('download')=='1',
                         download_name=f'{key}_{language.upper()}_{index:02d}.png',max_age=0)

    @api.patch('/sets/<key>/versions/<language>/order')
    def reorder_slides(key,language):
        project=load();version=get_version(project,key,language);order=body().get('slide_ids')
        current={slide['id']:slide for slide in version['slides']}
        if not isinstance(order,list) or not all(isinstance(i,str) for i in order) or len(order)!=len(current) or set(order)!=set(current):
            raise ValueError('모든 슬라이드를 중복 없이 지정하세요.')
        version['slides']=[current[i] for i in order]
        for index,slide in enumerate(version['slides']):
            if index==0:slide['role']='HOOK'
            elif slide['role']=='HOOK':slide['role']='CONTENT'
        version['hook']=version['slides'][0]['text'][:300]
        save(project);return state(project)

    @api.post('/restore')
    def restore_project():
        from .post_archive import restore_post_zip
        file=request.files.get('file')
        if not file:raise ValueError('프로젝트 ZIP을 선택하세요.')
        project=restore_post_zip(file.stream,workspace());save(project)
        return state(project)

    @api.delete('/project')
    def reset_project():
        import shutil
        folder=workspace()
        for path in folder.iterdir():
            if path.is_file():path.unlink()
            elif path.is_dir():shutil.rmtree(path)
        project=new_project();save(project);return state(project)

    @api.post('/export')
    def export_project():
        from .post_archive import create_post_zip
        project=load();data=body();target=workspace()/(uuid.uuid4().hex+'-project.zip')
        try:
            create_post_zip(project,workspace(),target,data.get('scope','project'),data.get('set'),data.get('language'))
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return send_file(target,mimetype='application/zip',as_attachment=True,download_name='1028FALL_PROJECT.zip')

    app.register_blueprint(api)
