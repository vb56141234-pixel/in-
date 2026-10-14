"""Validated editor settings shared by project restoration and the renderer."""
import math
import re
POST_STYLE = dict(font='system', font_size=7, weight='Bold', color='#ffffff', align='center',
                  x=50, y=72, line_height=1.2, letter_spacing=0, shadow=True, outline=2,
                  text_background=False, background_color='#000000', background_opacity=45,
                  gradient=85, gradient_range=50, gradient_direction='bottom')
RATIOS = {'1:1':(1080,1080), '4:5':(1080,1350), '9:16':(1080,1920)}
FIT_MODES = ('crop','fit','blur')

def validate_style(value):
    if not isinstance(value,dict): raise ValueError('스타일은 객체여야 합니다.')
    result=POST_STYLE.copy()
    ranges={'font_size':(2,15),'x':(0,100),'y':(0,100),'line_height':(.7,2.5),
            'letter_spacing':(-2,12),'outline':(0,8),'background_opacity':(0,100),
            'gradient':(0,100),'gradient_range':(0,100)}
    enums={'font':('system','noto','gothic'),'weight':('Regular','Medium','Bold','ExtraBold','Black'),
           'align':('left','center','right'),'gradient_direction':('bottom','top','left','right')}
    for key,bounds in ranges.items():
        if key in value:
            if isinstance(value[key],bool): raise ValueError('디자인 숫자가 올바르지 않습니다.')
            try: number=float(value[key])
            except (TypeError,ValueError) as exc: raise ValueError('디자인 숫자가 올바르지 않습니다.') from exc
            if not math.isfinite(number) or not bounds[0]<=number<=bounds[1]:
                raise ValueError(f'{key} 범위를 확인하세요.')
            result[key]=number
    for key,choices in enums.items():
        if key in value:
            if value[key] not in choices: raise ValueError(f'{key} 선택을 확인하세요.')
            result[key]=value[key]
    for key in ('shadow','text_background'):
        if key in value:
            if not isinstance(value[key],bool): raise ValueError('디자인 스위치가 올바르지 않습니다.')
            result[key]=value[key]
    for key in ('color','background_color'):
        if key in value:
            if not isinstance(value[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value[key]):
                raise ValueError('색상은 #RRGGBB 형식이어야 합니다.')
            result[key]=value[key]
    return result

def validate_options(value):
    if not isinstance(value,dict): raise ValueError('이미지 설정이 올바르지 않습니다.')
    ratio=value.get('aspect_ratio','4:5');mode=value.get('fit_mode','crop')
    variation=value.get('variation_enabled',True)
    if not isinstance(ratio,str) or ratio not in RATIOS or mode not in FIT_MODES or not isinstance(variation,bool):
        raise ValueError('이미지 비율·맞춤·Variation 설정을 확인하세요.')
    return dict(aspect_ratio=ratio,fit_mode=mode,variation_enabled=variation)
