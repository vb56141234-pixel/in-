"""POST SET aggregate; original assets and localized content never share text state."""
from copy import deepcopy
import uuid
from .config import LANGUAGES, SET_IDS, MAX_SOURCES
from .design_config import POST_STYLE, validate_options, validate_style

def new_project():
    return {'schema_version':2, 'id':uuid.uuid4().hex, 'assets':{},
            'settings':{'language':'ko','style_sample':'','default_style':deepcopy(POST_STYLE),
                        **validate_options({})},
            'logo':{'mode':'none','asset':None,'size':20,'position':'center'},
            'sets':{key:{'id':key,'source_ids':[],'source_revision':0,'versions':{},
                         'logo':{'mode':'inherit','asset':None,'size':20,'position':'center'},
                         'status':'대기 중...','error':''} for key in SET_IDS}}

def get_set(project,key):
    if key not in SET_IDS: raise ValueError('A/B/C SET를 선택하세요.')
    return project['sets'][key]

def require_language(language):
    if not isinstance(language,str) or language not in LANGUAGES: raise ValueError('지원하지 않는 작성 언어입니다.')
    return language

def add_source(project,key,asset):
    post=get_set(project,key)
    if len(post['source_ids'])>=MAX_SOURCES: raise ValueError('SET에는 최대 10장까지 추가할 수 있습니다.')
    if asset['id'] in post['source_ids']:
        raise ValueError('같은 SOURCE를 중복 추가할 수 없습니다.')
    if asset['id'] in project['assets'] and project['assets'][asset['id']]!=asset:
        raise ValueError('기존 SOURCE 원본 정보를 덮어쓸 수 없습니다.')
    project['assets'][asset['id']]=deepcopy(asset)
    post['source_ids'].append(asset['id'])
    post['source_revision']+=1

def reorder_sources(project,key,order):
    post=get_set(project,key)
    if not isinstance(order,list) or not all(isinstance(x,str) for x in order):
        raise ValueError('이미지 순서가 올바르지 않습니다.')
    if len(order)!=len(post['source_ids']) or set(order)!=set(post['source_ids']):
        raise ValueError('모든 SOURCE를 중복 없이 지정하세요.')
    if order!=post['source_ids']:
        post['source_ids']=order.copy();post['source_revision']+=1

def remove_source(project,key,identifier=None):
    post=get_set(project,key)
    if identifier is not None and identifier not in post['source_ids']:
        raise ValueError('SOURCE를 찾을 수 없습니다.')
    if identifier is None: post['source_ids']=[]
    else: post['source_ids'].remove(identifier)
    # Assets referenced by old versions intentionally survive source removal.
    post['source_revision']+=1

def new_version(project,key,language,options=None):
    require_language(language)
    post=get_set(project,key)
    if not 1<=len(post['source_ids'])<=MAX_SOURCES: raise ValueError('SOURCE 1–10장을 먼저 추가하세요.')
    return {'language':language,'hook_candidates':[],'hook':'','caption':'','analysis':None,
            'source_revision':post['source_revision'],'options':validate_options(options or project['settings']),
            'slides':[{'id':uuid.uuid4().hex,'source_id':source_id,'role':'HOOK' if index==0 else 'CONTENT',
                       'text':'','style':deepcopy(project['settings']['default_style']), 'variation':None}
                      for index,source_id in enumerate(post['source_ids'])], 'status':'MANUAL','error':''}

def ensure_version(project,key,language,options=None):
    post=get_set(project,key)
    if require_language(language) not in post['versions']:
        post['versions'][language]=new_version(project,key,language,options)
    return post['versions'][language]

def get_version(project,key,language):
    require_language(language)
    version=get_set(project,key)['versions'].get(language)
    if version is None: raise ValueError('먼저 수동 버전 또는 언어 버전을 생성하세요.')
    return version

def migrate_legacy(items):
    if len(items)>30:
        raise ValueError('기존 프로젝트가 30장을 초과합니다. 원본 ZIP을 보관하고 10장씩 SET로 분할해 주세요.')
    project=new_project()
    for index,item in enumerate(items):
        key=SET_IDS[index//10]
        asset={'id':item['id'],'file':item['source'],'name':item['name']}
        add_source(project,key,asset)
    for key,post in project['sets'].items():
        original=[i for i in items if i['id'] in post['source_ids']]
        for language in dict.fromkeys(i['language'] for i in original):
            version=new_version(project,key,language,{'aspect_ratio':'1:1','fit_mode':'crop','variation_enabled':False})
            for slide,item in zip(version['slides'],original):
                if item['language']==language:
                    slide['text']=item['title']
                    old=item['style'];adapted={k:v for k,v in old.items() if k in POST_STYLE}
                    if adapted.get('weight')=='ExBold': adapted['weight']='ExtraBold'
                    slide['style']=validate_style(adapted)
            version['hook']=version['slides'][0]['text']
            version['caption']='\n\n'.join(i['caption'] for i in original if i['language']==language and i['caption'])
            post['versions'][language]=version
    return project
