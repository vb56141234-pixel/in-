"""Disk-based, bounded image composition; no images leave the machine here."""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

SIZE = 1080
DEFAULT_STYLE = dict(x=50, y=72, font_size=9, weight='Bold', gradient=85,
                     gradient_range=50, logo_position='center')

def square_crop(path, size=SIZE):
    with Image.open(path) as image:
        return ImageOps.fit(ImageOps.exif_transpose(image).convert('RGB'), (size, size),
                            method=Image.Resampling.LANCZOS)

def font_path(weight='Bold'):
    custom = os.getenv('STUDIO_FONT')
    if custom and Path(custom).is_file():
        return custom
    win = Path(os.getenv('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [win/'malgunbd.ttf', win/'YuGothB.ttc', win/'meiryob.ttc',
                  Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'),
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError('한글·일본어 지원 폰트가 없습니다. .env에 STUDIO_FONT 경로를 설정하세요.')

def add_gradient(image, density=85, extent=50):
    layer = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(layer)
    height = image.height
    start = int(height * (1 - extent/100))
    if extent > 0:
        for y in range(start, height):
            alpha = int(255 * density/100 * (y-start)/max(1, height-start-1))
            draw.line((0, y, image.width, y), fill=(0, 0, 0, alpha))
    return Image.alpha_composite(image.convert('RGBA'), layer)

def wrap_title(title, font, max_width):
    # Break at spaces where possible; CJK and long words break by glyph.
    lines = []
    for paragraph in title.split('\n'):
        current = ''
        for char in paragraph:
            proposed = current + char
            if font.getlength(proposed) > max_width and current:
                split = current.rfind(' ')
                if split > len(current)//2:
                    lines.append(current[:split])
                    current = current[split+1:] + char
                else:
                    lines.append(current.rstrip())
                    current = char.lstrip()
            else:
                current = proposed
        lines.append(current.rstrip())
    return lines

def add_title(image, title, style):
    if not title.strip():
        return image
    size = round(image.width * style['font_size']/100)
    font_file = font_path(style['weight'])
    font = ImageFont.truetype(font_file, size)
    lines = wrap_title(title, font, int(image.width*.90))
    # Reduce automatically to fit long manually supplied titles inside the square.
    while (len(lines) * size * 1.24 > image.height*.75 or len(lines) > 4) and size > 24:
        size -= 2
        font = ImageFont.truetype(font_file, size)
        lines = wrap_title(title, font, int(image.width*.90))
    text = '\n'.join(lines)
    draw = ImageDraw.Draw(image)
    stroke = max(1, round(size*.02))
    # Windows fonts may only provide Bold; use a slightly thicker outline for heavier weights.
    if style['weight'] in ('ExBold', 'Black'):
        stroke += 1 if style['weight'] == 'ExBold' else 2
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=int(size*.18), stroke_width=stroke)
    width, height = box[2]-box[0], box[3]-box[1]
    x = max(24, min(image.width-width-24, image.width*style['x']/100-width/2))
    y = max(24, min(image.height-height-24, image.height*style['y']/100-height/2))
    draw.multiline_text((x+3, y+4), text, font=font, fill=(0,0,0,180), spacing=int(size*.18), align='center', stroke_width=stroke)
    draw.multiline_text((x, y), text, font=font, fill='white', spacing=int(size*.18), align='center', stroke_width=stroke, stroke_fill=(15,15,15))
    return image

def add_logo(image, logo_path, position='center'):
    if not logo_path or not Path(logo_path).is_file():
        return image
    with Image.open(logo_path) as source:
        logo = ImageOps.exif_transpose(source).convert('RGBA')
    logo.thumbnail((int(image.width*.24), int(image.height*.12)), Image.Resampling.LANCZOS)
    x = {'left': 40, 'center': (image.width-logo.width)//2,
         'right': image.width-logo.width-40}[position]
    image.alpha_composite(logo, (x, 40))
    return image

def export_png(source, target, title='', style=None, logo=None):
    settings = DEFAULT_STYLE | (style or {})
    image = add_gradient(square_crop(source), settings['gradient'], settings['gradient_range'])
    image = add_title(image, title, settings)
    image = add_logo(image, logo, settings['logo_position'])
    image.convert('RGB').save(target, 'PNG')
    image.close()
    return target

# Version-aware renderer. Legacy square rendering above remains unchanged.
from PIL import ImageEnhance, ImageFilter, ImageColor
from .design_config import RATIOS, POST_STYLE, validate_style, validate_options
from .variation_service import validate_variation

def post_font(style,size):
    custom=os.getenv('STUDIO_FONT')
    if custom and Path(custom).is_file():return ImageFont.truetype(custom,size)
    regular=style['weight'] in ('Regular','Medium')
    win=Path(os.getenv('WINDIR','C:/Windows'))/'Fonts'
    noto=Path('/usr/share/fonts/opentype/noto')/('NotoSansCJK-Regular.ttc' if regular else 'NotoSansCJK-Bold.ttc')
    gothic=win/('malgun.ttf' if regular else 'malgunbd.ttf')
    alternatives=[noto,gothic] if style['font']=='noto' else [gothic,noto]
    alternatives.extend([win/('YuGothR.ttc' if regular else 'YuGothB.ttc'),win/('meiryo.ttc' if regular else 'meiryob.ttc')])
    for path in alternatives:
        if path.is_file():return ImageFont.truetype(str(path),size)
    return ImageFont.truetype(font_path(),size)

def prepare_post_canvas(source,options,variation=None):
    width,height=RATIOS[options['aspect_ratio']]
    var=validate_variation(variation) if options['variation_enabled'] else None
    var=var or dict(zoom=1,shift_x=0,shift_y=0,brightness=1,contrast=1,blur=0)
    with Image.open(source) as original:
        image=ImageOps.exif_transpose(original).convert('RGB')
    mode=options['fit_mode'];zoom=var['zoom']
    if mode=='crop':
        resized=ImageOps.fit(image,(round(width*zoom),round(height*zoom)),
                            method=Image.Resampling.LANCZOS,centering=(.5+var['shift_x'],.5+var['shift_y']))
        left=(resized.width-width)//2;top=(resized.height-height)//2
        canvas=resized.crop((left,top,left+width,top+height));resized.close()
    else:
        if mode=='blur':
            canvas=ImageOps.fit(image,(width,height),method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(24+var['blur']*10))
        else:canvas=Image.new('RGB',(width,height),(18,21,24))
        foreground=ImageOps.contain(image,(round(width*zoom),round(height*zoom)),method=Image.Resampling.LANCZOS)
        x=round((width-foreground.width)/2+var['shift_x']*width)
        y=round((height-foreground.height)/2+var['shift_y']*height)
        canvas.paste(foreground,(x,y));foreground.close()
    image.close()
    if var['brightness']!=1:canvas=ImageEnhance.Brightness(canvas).enhance(var['brightness'])
    if var['contrast']!=1:canvas=ImageEnhance.Contrast(canvas).enhance(var['contrast'])
    return canvas.convert('RGBA')

def post_gradient(image,style):
    density=style['gradient']/100;extent=style['gradient_range']/100
    if density==0 or extent==0:return image
    direction=style['gradient_direction'];horizontal=direction in ('left','right')
    length=image.width if horizontal else image.height
    ramp=Image.new('L',(length,1))
    # alpha increases toward the chosen edge, within the requested range.
    pixels=[]
    for position in range(length):
        fraction=position/max(1,length-1)
        if direction in ('top','left'):fraction=1-fraction
        pixels.append(round(255*density*max(0,(fraction-(1-extent))/extent)))
    ramp.putdata(pixels)
    if not horizontal:ramp=ramp.transpose(Image.Transpose.ROTATE_90).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    mask=ramp.resize(image.size)
    overlay=Image.new('RGBA',image.size,(0,0,0,0));overlay.putalpha(mask)
    return Image.alpha_composite(image,overlay)

def _line_width(text,font,spacing):
    return max(0,font.getlength(text)+max(0,len(text)-1)*spacing)

def _post_lines(text,font,spacing,max_width):
    # Word-aware wrapping with a glyph fallback for CJK and long words.
    lines=[]
    for paragraph in text.split('\n'):
        current=''
        for char in paragraph:
            if current and _line_width(current+char,font,spacing)>max_width:
                split=current.rfind(' ')
                if split>len(current)//2:
                    lines.append(current[:split]);current=current[split+1:]+char
                else:lines.append(current.rstrip());current=char.lstrip()
            else:current+=char
        lines.append(current.rstrip())
    return lines

def post_text(image,text,style):
    if not text.strip():return image
    size=round(image.width*style['font_size']/100)
    spacing=style['letter_spacing']*image.width/1080
    font=post_font(style,size)
    lines=_post_lines(text,font,spacing,image.width*.90)
    while (len(lines)*size*style['line_height']>image.height*.8 or max((_line_width(t,font,spacing) for t in lines),default=0)>image.width*.90) and size>16:
        size-=2;font=post_font(style,size);lines=_post_lines(text,font,spacing,image.width*.90)
    line_step=round(size*style['line_height'])
    stroke=round(style['outline'])
    widths=[_line_width(line,font,spacing) for line in lines]
    width=max(widths,default=0);height=line_step*len(lines)
    x=max(22,min(image.width-width-22,image.width*style['x']/100-width/2))
    y=max(22,min(image.height-height-22,image.height*style['y']/100-height/2))
    if style['text_background']:
        overlay=Image.new('RGBA',image.size)
        fill=ImageColor.getrgb(style['background_color'])+(round(255*style['background_opacity']/100),)
        ImageDraw.Draw(overlay).rounded_rectangle((x-14,y-10,x+width+14,y+height+10),radius=10,fill=fill)
        image=Image.alpha_composite(image,overlay)
    draw=ImageDraw.Draw(image)
    for index,line in enumerate(lines):
        offset={'left':0,'center':(width-widths[index])/2,'right':width-widths[index]}[style['align']]
        tx=x+offset;ty=y+index*line_step
        if spacing==0:
            if style['shadow']:draw.text((tx+3,ty+4),line,font=font,fill=(0,0,0,190),anchor='lt',stroke_width=stroke)
            draw.text((tx,ty),line,font=font,fill=style['color'],anchor='lt',stroke_width=stroke,stroke_fill='#111111')
        else:
            for char in line:
                if style['shadow']:draw.text((tx+3,ty+4),char,font=font,fill=(0,0,0,190),anchor='lt',stroke_width=stroke)
                draw.text((tx,ty),char,font=font,fill=style['color'],anchor='lt',stroke_width=stroke,stroke_fill='#111111')
                tx+=font.getlength(char)+spacing
    return image

def render_post_image(source,target,text='',style=None,options=None,variation=None,logo=None,logo_config=None):
    style=validate_style(style or {});options=validate_options(options or {})
    image=prepare_post_canvas(source,options,variation)
    image=post_gradient(image,style);image=post_text(image,text,style)
    if logo and Path(logo).is_file():
        config=logo_config or {'size':20,'position':'center'}
        with Image.open(logo) as original:mark=original.convert('RGBA')
        mark.thumbnail((round(image.width*config['size']/100),round(image.height*.14)),Image.Resampling.LANCZOS)
        x={'left':35,'center':(image.width-mark.width)//2,'right':image.width-mark.width-35}[config['position']]
        image.alpha_composite(mark,(x,35));mark.close()
    rgb=image.convert('RGB')
    if Path(target).suffix.lower() in ('.jpg','.jpeg'):rgb.save(target,'JPEG',quality=95,subsampling=0)
    else:rgb.save(target,'PNG')
    rgb.close();image.close()
    return target
