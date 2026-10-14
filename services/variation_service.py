"""Subtle, deterministic local variation; original files are never modified."""
import hashlib
import math
import random

LIMITS={'zoom':(1,1.04),'shift_x':(-.018,.018),'shift_y':(-.018,.018),
        'brightness':(.97,1.03),'contrast':(.97,1.03),'blur':(0,.5)}

def validate_variation(value):
    if value is None:return None
    if not isinstance(value,dict):raise ValueError('Variation 설정이 올바르지 않습니다.')
    result={}
    for key,(low,high) in LIMITS.items():
        number=value.get(key,1 if key in ('zoom','brightness','contrast') else 0)
        if not isinstance(number,(int,float)) or isinstance(number,bool) or not math.isfinite(number) or not low<=number<=high:
            raise ValueError('Variation은 미세 변형 범위 안이어야 합니다.')
        result[key]=number
    result['provider']='local'
    return result

class LocalVariationProvider:
    def create(self, source_id, language, nonce='0'):
        seed=hashlib.sha256(f'{source_id}:{language}:{nonce}'.encode()).digest()
        rng=random.Random(seed)
        return validate_variation({key:round(rng.uniform(low,high),5) for key,(low,high) in LIMITS.items()})

class AIImageVariationProvider:
    """Extension point only; no synthetic image API is called by this release."""
    def create(self, source_path, language, constraints):
        raise NotImplementedError('AI 이미지 Variation 제공자는 아직 연결되지 않았습니다.')

provider=LocalVariationProvider()

def create_variation(source_id,language,enabled=True,nonce='0'):
    return provider.create(source_id,language,nonce) if enabled else None
