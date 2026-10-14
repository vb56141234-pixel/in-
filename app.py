"""1028FALL Studio — loopback-only local web application."""
import json
import os
import secrets
import shutil
import threading
import uuid
import webbrowser
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file, session
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from services import ai_service
from services.image_service import DEFAULT_STYLE, export_png
from services.export_service import create_zip, safe_name
from services.project_service import restore_zip, validate_style

BASE = Path(__file__).resolve().parent
load_dotenv(BASE/'.env')
EXTENSIONS = {'.jpg','.jpeg','.png','.webp'}

def create_app(data_root=None):
    app = Flask(__name__,template_folder=str(BASE/'ui/templates'),static_folder=str(BASE/'ui/static'))
    if data_root is None:
        key_path=BASE/'data'/'.session-key'
        key_path.parent.mkdir(parents=True,exist_ok=True)
        try:
            with key_path.open('x',encoding='ascii') as key_file:
                key_file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret_key=key_path.read_text(encoding='ascii').strip()
    else:
        secret_key=secrets.token_hex(32)
    app.config.update(SECRET_KEY=secret_key, MAX_CONTENT_LENGTH=2*1024*1024*1024,
                      SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_HTTPONLY=True)
    storage = Path(data_root or BASE/'data/temp')
    storage.mkdir(parents=True,exist_ok=True)
    locks = {}
    lock_guard = threading.Lock()

    def workspace():
        if 'workspace' not in session:
            session['workspace'] = uuid.uuid4().hex
            session.permanent = True
        folder = storage/session['workspace']
        folder.mkdir(exist_ok=True)
        return folder

    def read_items():
        path = workspace()/'items.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []

    def save_items(items):
        folder = workspace()
        temporary = folder/'items.tmp'
        temporary.write_text(json.dumps(items,ensure_ascii=False),encoding='utf-8')
        temporary.replace(folder/'items.json')

    def find_item(identifier):
        items = read_items()
        item = next((i for i in items if i['id']==identifier),None)
        if item is None:
            raise ValueError('이미지를 찾을 수 없습니다.')
        return items, item

    @app.before_request
    def protect_local():
        host = request.host.split(':')[0]
        if host not in ('127.0.0.1','localhost'):
            return jsonify(error='로컬 접근만 허용됩니다.'),403
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not secrets.compare_digest(request.headers.get('X-Studio-Token',''),session.get('csrf','') or '!'):
                return jsonify(error='페이지를 새로고침한 후 다시 시도하세요.'),403
        if request.path in ('/api/upload','/api/logo') and (request.content_length or 0)>32*1024*1024:
            return jsonify(error='파일이 너무 큽니다 (최대 32MB).'),413
        if request.path.startswith('/api/'):
            folder = workspace()
            with lock_guard:
                lock = locks.setdefault(folder.name,threading.RLock())
            lock.acquire()
            request.studio_lock = lock

    @app.teardown_request
    def release_lock(error):
        lock = getattr(request,'studio_lock',None)
        if lock:
            lock.release()

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc,HTTPException):
            return jsonify(error='요청이 너무 큽니다 (최대 2GB).' if exc.code==413 else exc.description),exc.code
        if isinstance(exc,(ValueError,UnidentifiedImageError,Image.DecompressionBombError)):
            return jsonify(error=str(exc) if isinstance(exc,ValueError) else '손상되거나 너무 큰 이미지입니다.'),400
        if isinstance(exc,ai_service.AIError):
            return jsonify(error=str(exc)),502
        return jsonify(error='파일 처리 오류가 발생했습니다. 이미지와 저장 공간을 확인하세요.'),500

    @app.get('/')
    def index():
        session.setdefault('csrf', secrets.token_hex(24))
        return render_template('index.html',token=session['csrf'])

    @app.get('/legacy')
    def legacy_index():
        session.setdefault('csrf', secrets.token_hex(24))
        return render_template('legacy.html',token=session['csrf'])

    @app.get('/api/state')
    def state():
        return jsonify(items=read_items(), ai_available=ai_service.available(),
                       logo=(workspace()/'logo.png').exists())

    @app.post('/api/upload')
    def upload():
        files = request.files.getlist('files')
        items = read_items()
        errors = []
        for file in files:
            name = (file.filename or '').replace('\\','/').split('/')[-1]
            suffix = Path(name).suffix.lower()
            if suffix not in EXTENSIONS:
                errors.append({'name':name,'error':'지원하지 않는 이미지 형식'}); continue
            identifier = uuid.uuid4().hex
            target = workspace()/(identifier+suffix)
            try:
                file.save(target)
                with Image.open(target) as image:
                    if image.format not in ('JPEG','PNG','WEBP'):
                        raise ValueError('지원하지 않는 이미지 형식입니다.')
                    if image.width*image.height > 40_000_000:
                        raise ValueError('이미지는 최대 4천만 픽셀까지 지원합니다.')
                    image.verify()
                items.append(dict(id=identifier,name=name,source=target.name,title='',caption='',
                                  language='ko',status='대기 중...',error='',style=DEFAULT_STYLE.copy()))
            except (OSError, ValueError,UnidentifiedImageError,Image.DecompressionBombError):
                target.unlink(missing_ok=True)
                errors.append({'name':name,'error':'손상되거나 너무 큰 이미지'})
        save_items(items)
        return jsonify(items=items,errors=errors)

    @app.post('/api/logo')
    def logo():
        file = request.files.get('file')
        if not file or Path(file.filename or '').suffix.lower() not in ('.png','.webp'):
            raise ValueError('PNG 또는 WEBP 로고를 선택하세요.')
        temporary = workspace()/'logo-upload.tmp'
        try:
            file.save(temporary)
            with Image.open(temporary) as image:
                if image.width*image.height > 16_000_000:
                    raise ValueError('로고 이미지가 너무 큽니다.')
                image.convert('RGBA').save(workspace()/'logo.png')
        finally:
            temporary.unlink(missing_ok=True)
        return jsonify(ok=True)

    @app.patch('/api/items/<identifier>')
    def update(identifier):
        items,item = find_item(identifier)
        data = request.get_json() or {}
        for key,limit in [('title',300),('caption',6000)]:
            if key in data:
                if not isinstance(data[key],str): raise ValueError('텍스트 입력이 필요합니다.')
                item[key]=data[key][:limit]
        if 'language' in data:
            if data['language'] not in ai_service.LANGUAGES: raise ValueError('지원하지 않는 언어입니다.')
            item['language']=data['language']
        if 'style' in data:
            if not isinstance(data['style'],dict): raise ValueError('스타일 설정 형식이 올바르지 않습니다.')
            item['style']=validate_style(item['style'] | data['style'])
        item['status']='COMPLETE' if item['title'].strip() else '대기 중...'
        item['error']=''
        save_items(items)
        return jsonify(item)

    @app.post('/api/items/<identifier>/analyze')
    def analyze(identifier):
        items,item=find_item(identifier)
        try:
            analysis=ai_service.analyze_image(workspace()/item['source'])
        except ai_service.AIError as exc:
            item.update(status='ERROR',error=str(exc))
            save_items(items)
            raise
        return jsonify(analysis=analysis)

    @app.post('/api/items/<identifier>/generate')
    def generate(identifier):
        items,item=find_item(identifier)
        data=request.get_json() or {}
        language=data.get('language','ko')
        if language not in ai_service.LANGUAGES: raise ValueError('지원하지 않는 언어입니다.')
        try:
            analysis=data.get('analysis')
            if not isinstance(analysis,dict): raise ValueError('이미지 분석을 먼저 실행하세요.')
            result=ai_service.generate_title_caption(analysis,language,str(data.get('sample','')))
            item.update(result,language=language,status='COMPLETE',error='')
        except ai_service.AIError as exc:
            item.update(status='ERROR',error=str(exc))
            save_items(items)
            raise
        save_items(items)
        return jsonify(item)

    @app.get('/api/items/<identifier>/image')
    def preview(identifier):
        _,item=find_item(identifier)
        path=workspace()/(identifier+'-render.png')
        export_png(workspace()/item['source'],path,item['title'],item['style'],workspace()/'logo.png')
        return send_file(path,mimetype='image/png',as_attachment=request.args.get('download')=='1',
                         download_name=safe_name(item['title'] or Path(item['name']).stem)+'.png',max_age=0)

    @app.post('/api/export')
    def export():
        items=read_items()
        if not items: raise ValueError('먼저 이미지를 업로드하세요.')
        path=workspace()/'1028FALL-export.zip'
        create_zip(items,workspace(),workspace()/'logo.png',path)
        return send_file(path,as_attachment=True,download_name=path.name)

    @app.get('/api/project')
    def project():
        return jsonify(version=1,items=read_items(),logo=(workspace()/'logo.png').exists())

    @app.post('/api/restore')
    def restore():
        file=request.files.get('file')
        if not file: raise ValueError('프로젝트 ZIP을 선택하세요.')
        items=restore_zip(file.stream,workspace())
        save_items(items)
        return jsonify(items=items,logo=(workspace()/'logo.png').exists())

    @app.post('/api/clear')
    def clear():
        folder=workspace()
        for child in folder.iterdir():
            if child.is_file(): child.unlink()
        return jsonify(ok=True)

    from services.post_api import register_post_api
    register_post_api(app, workspace, read_items)
    return app

app=create_app()

def main():
    import argparse
    from waitress import create_server
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    server=None
    for port in range(8765,8796):
        try:
            server=create_server(app,host='127.0.0.1',port=port,threads=4)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError('8765–8795 포트가 모두 사용 중입니다. 다른 Studio 창을 닫으세요.')
    address=f'http://127.0.0.1:{port}'
    print(f'1028FALL Studio: {address}\n종료하려면 Ctrl+C를 누르세요.',flush=True)
    if not args.no_browser:
        threading.Timer(1,lambda:webbrowser.open(address)).start()
    try:
        server.run()
    finally:
        server.close()

if __name__=='__main__':
    main()
