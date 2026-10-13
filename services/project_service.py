"""Restore our exported ZIP without extracting untrusted member paths."""
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import uuid
import zipfile
from PIL import Image
from .image_service import DEFAULT_STYLE
from .ai_service import LANGUAGES

EXTENSIONS={'.jpg','.jpeg','.png','.webp'}

def validate_style(values):
    if not isinstance(values,dict): raise ValueError('스타일 설정 형식이 올바르지 않습니다.')
    style=DEFAULT_STYLE.copy()
    for key,low,high in [('x',0,100),('y',0,100),('font_size',4,15),('gradient',0,100),('gradient_range',0,100)]:
        if key in values:
            try: value=float(values[key])
            except (TypeError,ValueError) as exc: raise ValueError('스타일 숫자를 확인하세요.') from exc
            if not low<=value<=high: raise ValueError('스타일 값 범위를 확인하세요.')
            style[key]=value
    for key,choices in [('weight',('Bold','ExBold','Black')),('logo_position',('left','center','right'))]:
        if key in values:
            if values[key] not in choices: raise ValueError('스타일 선택값이 올바르지 않습니다.')
            style[key]=values[key]
    return style

def restore_zip(upload, root):
    root=Path(root)
    with tempfile.TemporaryDirectory(dir=root,prefix='restore-') as temp:
        stage=Path(temp)
        try:
            with zipfile.ZipFile(upload) as archive:
                members=archive.infolist()
                if len(members)>1500 or sum(i.file_size for i in members)>512*1024*1024:
                    raise ValueError('프로젝트 ZIP은 압축 해제 기준 최대 512MB까지 지원합니다.')
                projects=[i for i in members if i.filename.endswith('/project.json') or i.filename=='project.json']
                if len(projects)!=1 or projects[0].file_size>2*1024*1024:
                    raise ValueError('올바른 프로젝트 ZIP을 선택하세요.')
                project=json.loads(archive.read(projects[0]).decode('utf-8'))
                if project.get('version')!=1 or not isinstance(project.get('items'),list):
                    raise ValueError('지원하지 않는 프로젝트 형식입니다.')
                if not project['items'] or len(project['items'])>1000:
                    raise ValueError('프로젝트 이미지 수는 1–1000장이어야 합니다.')
                prefix=str(PurePosixPath(projects[0].filename).parent)
                prefix='' if prefix=='.' else prefix+'/'
                def copy_member(relative, target):
                    path=PurePosixPath(relative)
                    if path.is_absolute() or '..' in path.parts or '\\' in relative:
                        raise ValueError('프로젝트의 파일 경로가 올바르지 않습니다.')
                    info=archive.getinfo(prefix+relative)
                    if info.file_size>32*1024*1024: raise ValueError('프로젝트 이미지가 32MB를 초과합니다.')
                    with archive.open(info) as source, open(target,'wb') as output:
                        shutil.copyfileobj(source,output,64*1024)
                items=[]
                for record in project['items']:
                    relative=record.get('source','')
                    suffix=PurePosixPath(relative).suffix.lower()
                    if suffix not in EXTENSIONS: raise ValueError('프로젝트 원본 이미지가 없습니다.')
                    identifier=uuid.uuid4().hex
                    name=identifier+suffix
                    copy_member(relative,stage/name)
                    with Image.open(stage/name) as image:
                        if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>40_000_000:
                            raise ValueError('지원하지 않거나 너무 큰 원본 이미지입니다.')
                        image.verify()
                    title,caption=record.get('title',''),record.get('caption','')
                    language=record.get('language','ko')
                    if not isinstance(title,str) or not isinstance(caption,str) or language not in LANGUAGES:
                        raise ValueError('프로젝트 텍스트가 올바르지 않습니다.')
                    items.append(dict(id=identifier,source=name,name=Path(str(record.get('source_file',name)).replace('\\','/')).name,
                                      title=title[:300],caption=caption[:6000],language=language,
                                      style=validate_style(record.get('style',{})),status='COMPLETE' if title else '대기 중...',error=''))
                logo=None
                if project.get('logo'):
                    copy_member(project['logo'],stage/'logo-source')
                    with Image.open(stage/'logo-source') as image:
                        if image.width*image.height>16_000_000: raise ValueError('로고가 너무 큽니다.')
                        image.convert('RGBA').save(stage/'logo.png')
                    logo=stage/'logo.png'
                for item in items:
                    (stage/item['source']).replace(root/item['source'])
                if logo:
                    logo.replace(root/'logo.png')
                else:
                    (root/'logo.png').unlink(missing_ok=True)
                return items
        except (zipfile.BadZipFile,KeyError,TypeError,AttributeError,UnicodeError,OSError,Image.DecompressionBombError) as exc:
            raise ValueError('프로젝트 ZIP이 손상되었거나 원본 파일이 없습니다.') from exc
