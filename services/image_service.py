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
