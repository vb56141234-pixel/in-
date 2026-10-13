import json
import re
import zipfile
from datetime import date
from pathlib import Path
from .image_service import export_png

def safe_name(text):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip(' .')[:70].rstrip(' .')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        name = '_'+name
    return name or 'image'

def create_zip(items, root, logo, target):
    prefix = '1028FALL_EXPORT_'+date.today().isoformat()
    captions = []
    project = {'version':1, 'items':[]}
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(items,1):
            source = Path(root)/item['source']
            filename = f'{index:03d}.png'
            output = Path(root)/('export_'+item['id']+'.png')
            try:
                export_png(source,output,item['title'],item['style'],logo)
                archive.write(output,f'{prefix}/images/{filename}')
            finally:
                output.unlink(missing_ok=True)
            record = dict(index=index, source_file=item['name'], language=item['language'],
                          title=item['title'],caption=item['caption'])
            captions.append(record)
            project['items'].append(record | {'style':item['style'], 'source':f'sources/{index:03d}{source.suffix}'})
            archive.write(source,f'{prefix}/sources/{index:03d}{source.suffix}')
        if logo and Path(logo).is_file():
            archive.write(logo, f'{prefix}/logo.png')
            project['logo'] = 'logo.png'
        archive.writestr(f'{prefix}/captions.json',json.dumps(captions,ensure_ascii=False,indent=2))
        archive.writestr(f'{prefix}/captions.txt','\n\n'.join(f"[{r['index']:03d}] {r['source_file']}\n{r['title']}\n{r['caption']}" for r in captions))
        archive.writestr(f'{prefix}/project.json',json.dumps(project,ensure_ascii=False,indent=2))
    return target
