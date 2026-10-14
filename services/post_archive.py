"""Portable project ZIPs; strict schema validation precedes any live file replacement."""
from copy import deepcopy
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid
import zipfile
from PIL import Image
from .config import LANGUAGES, SET_IDS
from .design_config import validate_style, validate_options
from .variation_service import validate_variation
from .post_model import new_project, migrate_legacy
from .image_service import render_post_image

MAX_PROJECT_BYTES=2*1024*1024*1024

ID_PATTERN=re.compile(r'^[A-Za-z0-9_-]{1,80}$')

def text(value,limit):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('프로젝트 텍스트 형식 또는 길이가 올바르지 않습니다.')
    return value

def identifier(value):
    if not isinstance(value,str) or not ID_PATTERN.fullmatch(value):raise ValueError('프로젝트 ID가 올바르지 않습니다.')
    return value

def relative_path(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value:raise ValueError('프로젝트 경로가 올바르지 않습니다.')
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path)!=value:raise ValueError('프로젝트 경로가 올바르지 않습니다.')
    return value

def logo_config(value,assets,inherit=False):
    if not isinstance(value,dict):raise ValueError('로고 설정이 올바르지 않습니다.')
    mode=value.get('mode','none');size=value.get('size',20);position=value.get('position','center')
    if mode not in (('none','custom','inherit') if inherit else ('none','custom')):raise ValueError('로고 적용 모드가 올바르지 않습니다.')
    if not isinstance(size,(int,float)) or isinstance(size,bool) or not math.isfinite(size) or not 5<=size<=35 or position not in ('left','center','right'):
        raise ValueError('로고 크기와 위치를 확인하세요.')
    asset=value.get('asset') if mode=='custom' else None
    if mode=='custom' and (not isinstance(asset,str) or asset not in assets):raise ValueError('로고 원본이 없습니다.')
    return dict(mode=mode,asset=asset,size=size,position=position)

def validate_project(value):
    if not isinstance(value,dict) or value.get('schema_version')!=2:raise ValueError('지원하지 않는 프로젝트 형식입니다.')
    project=new_project();project['id']=identifier(value.get('id'))
    registry=value.get('assets');settings=value.get('settings');sets=value.get('sets')
    if not isinstance(registry,dict) or len(registry)>1000 or not isinstance(settings,dict) or not isinstance(sets,dict) or set(sets)!=set(SET_IDS):
        raise ValueError('프로젝트 SET 또는 SOURCE 구조를 확인하세요.')
    for key,asset in registry.items():
        identifier(key)
        if not isinstance(asset,dict) or asset.get('id')!=key:raise ValueError('SOURCE ID를 확인하세요.')
        project['assets'][key]={'id':key,'file':relative_path(asset.get('file')),'name':text(asset.get('name'),500)}
    language=settings.get('language','ko')
    if not isinstance(language,str) or language not in LANGUAGES:raise ValueError('작성 언어를 확인하세요.')
    project['settings']={'language':language,'style_sample':text(settings.get('style_sample',''),5000),
                         'default_style':validate_style(settings.get('default_style',{})),**validate_options(settings)}
    project['logo']=logo_config(value.get('logo',{}),registry)
    slide_ids=set()
    for key in SET_IDS:
        post=sets[key];target=project['sets'][key]
        if not isinstance(post,dict):raise ValueError('SET 구조를 확인하세요.')
        sources=post.get('source_ids');versions=post.get('versions');revision=post.get('source_revision',0)
        if not isinstance(sources,list) or len(sources)>10 or not all(isinstance(i,str) and i in registry for i in sources) or len(set(sources))!=len(sources):
            raise ValueError('SET의 SOURCE는 중복 없는 최대 10장이어야 합니다.')
        if type(revision) is not int or not 0<=revision<=100_000_000 or not isinstance(versions,dict):raise ValueError('SET 변경 이력을 확인하세요.')
        target.update(source_ids=sources.copy(),source_revision=revision,logo=logo_config(post.get('logo',{'mode':'inherit'}),registry,True))
        for lang,version in versions.items():
            if lang not in LANGUAGES or not isinstance(version,dict) or version.get('language')!=lang:raise ValueError('언어 VERSION을 확인하세요.')
            slides=version.get('slides');hooks=version.get('hook_candidates',[])
            if not isinstance(slides,list) or not 1<=len(slides)<=10 or not isinstance(hooks,list) or len(hooks) not in (0,5):raise ValueError('슬라이드와 HOOK 후보 수를 확인하세요.')
            result={'language':lang,'hook_candidates':[text(h,300) for h in hooks],
                    'hook':text(version.get('hook',''),300),'caption':text(version.get('caption',''),65000),
                    'options':validate_options(version.get('options',{})),'slides':[],
                    'status':'COMPLETE','error':'','analysis':version.get('analysis')}
            version_revision=version.get('source_revision',0)
            if type(version_revision) is not int or not 0<=version_revision<=100_000_000:raise ValueError('VERSION 변경 이력을 확인하세요.')
            result['source_revision']=version_revision
            if result['analysis'] is not None and not isinstance(result['analysis'],dict):raise ValueError('분석 형식을 확인하세요.')
            source_ids=set()
            for slide in slides:
                if not isinstance(slide,dict):raise ValueError('슬라이드 구조를 확인하세요.')
                sid=identifier(slide.get('id'));source=slide.get('source_id')
                if sid in slide_ids or not isinstance(source,str) or source not in registry or source in source_ids:raise ValueError('슬라이드 또는 SOURCE가 중복되거나 없습니다.')
                slide_ids.add(sid);source_ids.add(source)
                result['slides'].append({'id':sid,'source_id':source,'role':text(slide.get('role','CONTENT'),60),
                                         'text':text(slide.get('text',''),600),'style':validate_style(slide.get('style',{})),
                                         'variation':validate_variation(slide.get('variation'))})
            # First slide and hook stay coherent without silently rewriting imported content.
            if result['slides'][0]['text'][:300]!=result['hook']:
                raise ValueError('HOOK과 첫 번째 슬라이드 문구가 일치하지 않습니다.')
            target['versions'][lang]=result
        target['status']='COMPLETE' if target['versions'] else '대기 중...'
    return project

def referenced_assets(project):
    used=set()
    if project['logo']['asset']:used.add(project['logo']['asset'])
    for post in project['sets'].values():
        used.update(post['source_ids'])
        if post['logo']['asset']:used.add(post['logo']['asset'])
        for version in post['versions'].values():used.update(s['source_id'] for s in version['slides'])
    return used

def restore_post_zip(stream,root):
    root=Path(root)
    with tempfile.TemporaryDirectory(dir=root,prefix='post-restore-') as temp:
        stage=Path(temp)
        try:
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                infos=archive.infolist();names=[i.filename for i in infos]
                if len(infos)>1500 or len(set(names))!=len(names) or sum(i.file_size for i in infos)>MAX_PROJECT_BYTES:
                    raise ValueError('프로젝트 ZIP은 압축 해제 기준 최대 2GB이며 중복 파일을 허용하지 않습니다.')
                meta=[i for i in infos if i.filename=='project.json' or i.filename.endswith('/project.json')]
                if len(meta)!=1 or meta[0].file_size>2*1024*1024:raise ValueError('project.json이 포함된 프로젝트 ZIP을 선택하세요.')
                value=json.loads(archive.read(meta[0]).decode('utf-8'))
                if value.get('version')==1:
                    if not isinstance(value.get('items'),list) or len(value['items'])>30:
                        raise ValueError('구형 프로젝트는 최대 30장까지 가져옵니다. 원본 ZIP을 보관하고 SET별로 분할하세요.')
                    # Existing v1 validation runs in staging, never in the live workspace.
                    from .project_service import restore_zip
                    stream.seek(0);items=restore_zip(stream,stage);project=migrate_legacy(items)
                    if (stage/'logo.png').exists():
                        project['assets']['legacy-logo']={'id':'legacy-logo','file':'logo.png','name':'logo.png'}
                        project['logo'].update(mode='custom',asset='legacy-logo')
                    for asset in project['assets'].values():
                        original=stage/asset['file'];name=uuid.uuid4().hex+original.suffix
                        original.rename(stage/name);asset['file']=name
                else:
                    project=validate_project(value)
                    prefix=str(PurePosixPath(meta[0].filename).parent)
                    prefix='' if prefix=='.' else prefix+'/'
                    used=referenced_assets(project)
                    project['assets']={key:asset for key,asset in project['assets'].items() if key in used}
                    for asset in project['assets'].values():
                        relative=relative_path(asset['file']);suffix=PurePosixPath(relative).suffix.lower()
                        if suffix not in ('.jpg','.jpeg','.png','.webp'):raise ValueError('SOURCE 형식을 확인하세요.')
                        info=archive.getinfo(prefix+relative)
                        if info.file_size>32*1024*1024:raise ValueError('SOURCE는 각 32MB 이하여야 합니다.')
                        name=uuid.uuid4().hex+suffix
                        with archive.open(info) as source,open(stage/name,'wb') as target:shutil.copyfileobj(source,target,64*1024)
                        with Image.open(stage/name) as image:
                            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>40_000_000:raise ValueError('SOURCE가 손상되었거나 너무 큽니다.')
                            image.verify()
                        asset['file']=name
            # No existing project metadata or file is changed before all validation succeeds.
            for asset in project['assets'].values():(stage/asset['file']).replace(root/asset['file'])
            return project
        except (zipfile.BadZipFile,KeyError,TypeError,AttributeError,UnicodeError,OSError,Image.DecompressionBombError) as exc:
            raise ValueError('프로젝트 ZIP이 손상되었거나 필요한 원본 파일이 없습니다.') from exc

def subset_project(project,scope,key=None,language=None):
    if scope not in ('version','set','all','project'):raise ValueError('다운로드 범위를 확인하세요.')
    result=deepcopy(project)
    if scope in ('set','version'):
        if key not in SET_IDS:raise ValueError('다운로드할 SET를 선택하세요.')
        if scope=='version' and language not in result['sets'][key]['versions']:raise ValueError('다운로드할 언어 VERSION이 없습니다.')
        for name in SET_IDS:
            if name!=key:result['sets'][name]=new_project()['sets'][name]
        if scope=='version':result['sets'][key]['versions']={language:result['sets'][key]['versions'][language]}
    used=referenced_assets(result)
    result['assets']={key:asset for key,asset in result['assets'].items() if key in used}
    if not any(post['versions'] for post in result['sets'].values()) and scope!='project':raise ValueError('먼저 콘텐츠 버전을 만드세요.')
    return result

def create_post_zip(project,root,target,scope='project',key=None,language=None):
    root=Path(root);portable=subset_project(project,scope,key,language);prefix='1028FALL_PROJECT'
    if sum((root/asset['file']).stat().st_size for asset in portable['assets'].values())>MAX_PROJECT_BYTES:
        raise ValueError('프로젝트 원본이 2GB를 초과합니다. SET별 또는 언어 버전별로 나누어 저장하세요.')
    with tempfile.TemporaryDirectory(dir=root,prefix='post-export-') as temp:
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for asset in portable['assets'].values():
                file=root/asset['file'];relative=f"sources/{asset['id']}{file.suffix}"
                archive.write(file,f'{prefix}/{relative}');asset['file']=relative
            for name,post in portable['sets'].items():
                logo=post['logo'] if post['logo']['mode']!='inherit' else portable['logo']
                logo_asset=project['assets'].get(logo['asset']) if logo['mode']=='custom' else None
                logo_file=root/logo_asset['file'] if logo_asset else None
                for lang,version in post['versions'].items():
                    folder=f'{prefix}/{name}_SET/{lang.upper()}'
                    archive.writestr(folder+'/caption.txt',version['caption'])
                    archive.writestr(folder+'/content.json',json.dumps({'hook':version['hook'],'hook_candidates':version['hook_candidates'],
                                                                     'slides':[{'role':s['role'],'text':s['text']} for s in version['slides']]},ensure_ascii=False,indent=2))
                    for index,slide in enumerate(version['slides'],1):
                        source=root/project['assets'][slide['source_id']]['file'];output=Path(temp)/f'{name}_{lang}_{index:02d}.jpg'
                        render_post_image(source,output,slide['text'],slide['style'],version['options'],slide['variation'],logo_file,logo)
                        archive.write(output,f'{folder}/{index:02d}.jpg');output.unlink()
            archive.writestr(prefix+'/project.json',json.dumps(portable,ensure_ascii=False,indent=2,allow_nan=False))
            if sum(info.file_size for info in archive.infolist())>MAX_PROJECT_BYTES:
                raise ValueError('프로젝트가 2GB를 초과합니다. SET별 또는 언어 버전별로 나누어 저장하세요.')
    return target
