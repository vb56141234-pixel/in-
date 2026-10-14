'use strict';
const $ = (selector, root=document) => root.querySelector(selector);
const token = $('meta[name="studio-token"]').content;
let project=null, languages={}, ai=false, busy=false, activeSet='A', fileTarget='A', logoTarget='project';
const views={}, selectedSlides={}, pending=new Map();
let saveTail=Promise.resolve(), saveError=null, toastTimer;
const styleFields=[
 ['font','FONT','select',[['system','시스템 CJK'],['noto','Noto CJK'],['gothic','맑은 고딕']]],
 ['font_size','FONT SIZE (%)','number',2,15,.5],
 ['weight','FONT WEIGHT','select',['Regular','Medium','Bold','ExtraBold','Black']],
 ['color','TEXT COLOR','color'],['align','TEXT ALIGN','select',[['left','왼쪽'],['center','가운데'],['right','오른쪽']]],
 ['x','가로 위치 (%)','number',0,100,1],['y','세로 위치 (%)','number',0,100,1],
 ['line_height','행간','number',.7,2.5,.1],['letter_spacing','자간 (px)','number',-2,12,.5],
 ['shadow','Shadow','checkbox'],['outline','Outline (px)','number',0,8,1],
 ['text_background','텍스트 배경','checkbox'],['background_color','배경 색상','color'],
 ['background_opacity','배경 불투명도 (%)','range',0,100,1],
 ['gradient','Gradient 농도 (%)','range',0,100,1],['gradient_range','Gradient 범위 (%)','range',0,100,1],
 ['gradient_direction','Gradient 방향','select',[['bottom','하단'],['top','상단'],['left','왼쪽'],['right','오른쪽']]]
];
function element(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,7000);}
async function api(path,options={}){
 const headers={'X-Studio-Token':token,...options.headers};
 if(options.body && !(options.body instanceof FormData)) headers['Content-Type']='application/json';
 const response=await fetch('/api/v2'+path,{...options,headers});
 if(!response.ok){let error;try{error=(await response.json()).error;}catch{error='서버 연결 오류';}throw new Error(error);}
 return response;
}
async function json(path,method='GET',body){return (await api(path,{method,body:body===undefined?undefined:JSON.stringify(body)})).json();}
function versionPath(key,language){return `/sets/${key}/versions/${language}`;}
function viewedLanguage(key){return views[key]||project.settings.language;}
function version(key=activeSet){return project?.sets[key].versions[viewedLanguage(key)];}
function selected(key=activeSet){const v=version(key);if(!v)return null;return v.slides.find(s=>s.id===selectedSlides[`${key}:${viewedLanguage(key)}`])||v.slides[0];}
function setBusy(value){busy=value;document.body.classList.toggle('busy',value);for(const node of document.querySelectorAll('button,input,select,textarea'))node.disabled=value||(!ai&&node.hasAttribute('data-ai'));}
function updateProject(result){project=result.project;}
function commit(record){
 const operation=saveTail.then(async()=>{const result=await json(record.path,'PATCH',record.payload);updateProject(result);saveError=null;$('#save-status').textContent='로컬 저장됨';if(record.refresh)record.refresh();});
 saveTail=operation.catch(error=>{saveError=error;$('#save-status').textContent='저장 실패';toast(error.message);});
 return operation;
}
function queueSave(key,path,payload,refresh){
 const old=pending.get(key);if(old)clearTimeout(old.timer);
 const merged=old&&old.path===path?{...old.payload,...payload}:payload;
 if(old?.payload.style&&payload.style)merged.style={...old.payload.style,...payload.style};
 const record={path,payload:structuredClone(merged),refresh};
 record.timer=setTimeout(()=>{if(pending.get(key)===record)pending.delete(key);commit(record).catch(()=>{});},300);
 pending.set(key,record);$('#save-status').textContent='저장 중…';
}
async function flush(){
 const records=[...pending.values()];pending.clear();
 for(const record of records){clearTimeout(record.timer);await commit(record);}
 await saveTail;if(saveError)throw saveError;
}
async function action(callback,message='처리 중…'){
 if(busy)return;setBusy(true);$('#progress-text').textContent=message;
 try{await flush();await callback();$('#progress-text').textContent='작업 완료';}
 catch(error){toast(error.message);$('#progress-text').textContent='오류 · '+error.message;}
 finally{setBusy(false);}
}
function refreshSlide(key,language,identifier){
 const card=document.getElementById('slide-'+identifier);if(!card)return;
 const v=project.sets[key].versions[language];const slide=v?.slides.find(s=>s.id===identifier);if(!slide)return;
 const preview=$('.slide-preview',card);preview.style.aspectRatio=v.options.aspect_ratio.replace(':',' / ');
 $('.position-marker',card).style.left=slide.style.x+'%';$('.position-marker',card).style.top=slide.style.y+'%';
 $('img',card).src='/api/v2'+versionPath(key,language)+`/slides/${identifier}/image?v=${Date.now()}`;
}
function refreshVersion(key,language){const v=project.sets[key].versions[language];if(v)v.slides.forEach(s=>refreshSlide(key,language,s.id));}
function selectSet(key){activeSet=key;for(const node of document.querySelectorAll('[data-set]'))node.classList.toggle('selected',node.dataset.set===key);for(const node of document.querySelectorAll('.post-set'))node.classList.toggle('active',node.dataset.key===key);syncEditor();}
function syncEditor(){
 if(!project)return;const s=selected(),v=version();const style=s?.style||project.settings.default_style;
 $('#editor-target').textContent=s?`${activeSet} SET / ${viewedLanguage(activeSet).toUpperCase()} / IMAGE ${String(v.slides.indexOf(s)+1).padStart(2,'0')}`:'새 버전 기본 디자인';
 for(const [key] of styleFields){const field=$(`[data-style="${key}"]`);if(field.type==='checkbox')field.checked=style[key];else field.value=style[key];const out=field.parentElement.querySelector('output');if(out)out.textContent=style[key];}
 for(const card of document.querySelectorAll('.slide-card'))card.classList.toggle('selected',card.id==='slide-'+s?.id);
}
function editorValues(){const result={};for(const [key,,type]of styleFields){const node=$(`[data-style="${key}"]`);result[key]=type==='checkbox'?node.checked:(type==='number'||type==='range'?Number(node.value):node.value);}return result;}
function editorChange(){
 if(busy||!project)return;const style=editorValues(),s=selected(),key=activeSet,language=viewedLanguage(key);
 if(s){const id=s.id;s.style={...style};queueSave('slide-'+id,versionPath(key,language)+`/slides/${id}`,{style},()=>refreshSlide(key,language,id));}
 else queueSave('defaults','/settings',{default_style:style});
}
function buildEditor(){
 const grid=element('div',undefined,'pair');$('#style-editor').append(grid);
 for(const [key,label,type,choices,max,step]of styleFields){
  const wrapper=element('label',label),input=element(type==='select'?'select':'input');input.dataset.style=key;
  if(type==='select'){for(const choice of choices){const [value,text]=Array.isArray(choice)?choice:[choice,choice];const option=element('option',text);option.value=value;input.append(option);}}
  else{input.type=type;if(type==='number'||type==='range'){input.min=choices;input.max=max;input.step=step;}}
  if(type==='checkbox'){wrapper.className='check';wrapper.prepend(input);}else wrapper.append(input);
  if(type==='range'){wrapper.append(element('output'));wrapper.style.gridColumn='1 / -1';}
  input.oninput=()=>{if((type==='number')&&(!input.validity.valid||input.value===''))return;const out=wrapper.querySelector('output');if(out)out.textContent=input.value;editorChange();};grid.append(wrapper);
 }
}
function pickFiles(id,key=activeSet){fileTarget=key;$('#'+id).click();}
async function upload(files,key){
 const list=[...files].filter(f=>/\.(jpe?g|png|webp)$/i.test(f.name));
 await action(async()=>{let failures=[];for(let i=0;i<list.length;i++){
  $('#progress-text').textContent=`${key} SET · ${i+1} / ${list.length} SOURCE 업로드`;
  const data=new FormData();data.append('files',list[i]);
  try{const result=await(await api(`/sets/${key}/sources`,{method:'POST',body:data})).json();updateProject(result);failures.push(...result.errors.map(e=>e.name+': '+e.error));}catch(e){failures.push(list[i].name+': '+e.message);}
 }render();selectSet(key);toast(failures.length?failures.join(' / '):`${key} SET SOURCE 준비 완료`);},'SOURCE 업로드 중…');
}
async function manual(key=activeSet){const language=$('#language').value;await action(async()=>{updateProject(await json(versionPath(key,language),'POST',{options:options()}));views[key]=language;render();selectSet(key);},'수동 콘텐츠 버전 만들기…');}
function options(){return {aspect_ratio:$('#aspect').value,fit_mode:$('#fit').value,variation_enabled:$('#variation').checked};}
async function generate(key,language,kind='all',slideId){
 if(!language){toast('먼저 언어 버전을 만드세요.');return;}
 await action(async()=>{
  try{updateProject(await json(`/sets/${key}/generate`,'POST',{language,kind,slide_id:slideId,options:options()}));views[key]=language;render();selectSet(key);toast(`${key} / ${language.toUpperCase()} · ${kind==='all'?'새 콘텐츠 버전':kind} 생성 완료`);}
  catch(error){const state=await json('/project');updateProject(state);render();throw error;}
 },kind==='all'?`${key} SET · SOURCE 전체 분석 → ${languages[language]} 콘텐츠 구성 중…`:`${key} SET · ${kind} 다시 생성 중…`);
}
function renderSources(section,key,post){
 const strip=$('.sources',section);
 post.source_ids.forEach((id,index)=>{
  const asset=project.assets[id],thumb=element('div',undefined,'source-thumb');thumb.draggable=true;thumb.dataset.id=id;thumb.title=asset.name;
  const image=element('img');image.src='/api/v2/assets/'+id;image.alt=asset.name;image.loading='lazy';image.draggable=false;
  const remove=element('button','×','delete-source');remove.setAttribute('aria-label',asset.name+' 삭제');
  remove.onclick=()=>action(async()=>{updateProject(await json(`/sets/${key}/sources/${id}`,'DELETE'));render();},'SOURCE 삭제 중…');
  thumb.append(image,element('span',String(index+1).padStart(2,'0'),'source-index'),remove);
  thumb.ondragstart=e=>{if(busy){e.preventDefault();return;}thumb.classList.add('dragging');e.dataTransfer.setData('text/plain',JSON.stringify({key,id}));};
  thumb.ondragend=()=>thumb.classList.remove('dragging');thumb.ondragover=e=>{if(!busy)e.preventDefault();};
  thumb.ondrop=e=>{e.preventDefault();if(busy)return;let from;try{from=JSON.parse(e.dataTransfer.getData('text/plain'));}catch{return;}if(from.key!==key||from.id===id)return;
   action(async()=>{const order=[...project.sets[key].source_ids],start=order.indexOf(from.id),end=order.indexOf(id);if(start<0||end<0)return;order.splice(start,1);order.splice(end,0,from.id);updateProject(await json(`/sets/${key}/order`,'PATCH',{source_ids:order}));render();},'SOURCE 순서 저장 중…');};
  strip.append(thumb);
 });
}
function moveSlide(key,language,id,offset){action(async()=>{const order=project.sets[key].versions[language].slides.map(s=>s.id),index=order.indexOf(id),next=index+offset;if(next<0||next>=order.length)return;[order[index],order[next]]=[order[next],order[index]];updateProject(await json(versionPath(key,language)+'/order','PATCH',{slide_ids:order}));render();},'Carousel 순서 변경 중…');}
function renderSlide(section,key,language,slide,index,v){
 const card=$('#slide-template').content.firstElementChild.cloneNode(true);card.id='slide-'+slide.id;
 $('.slide-number',card).textContent='IMAGE '+String(index+1).padStart(2,'0');$('.role',card).textContent=slide.role;
 $('.source-name',card).textContent=project.assets[slide.source_id].name;$('.slide-text',card).value=slide.text;
 $('.slide-text',card).oninput=e=>{const text=e.target.value;queueSave('slide-'+slide.id,versionPath(key,language)+`/slides/${slide.id}`,{text},()=>{refreshSlide(key,language,slide.id);if(index===0)$('.hook',section).value=project.sets[key].versions[language].hook;});};
 card.onclick=()=>{activeSet=key;selectedSlides[`${key}:${language}`]=slide.id;selectSet(key);};
 $('.regenerate-text',card).onclick=()=>generate(key,language,'slide',slide.id);
 $('.regenerate-design',card).onclick=()=>generate(key,language,'design',slide.id);
 $('.regenerate-variation',card).onclick=()=>generate(key,language,'variation',slide.id);
 $('.slide-download',card).onclick=()=>exportImage(key,language,slide.id,index+1);
 $('.slide-prev',card).onclick=()=>moveSlide(key,language,slide.id,-1);$('.slide-next',card).onclick=()=>moveSlide(key,language,slide.id,1);
 const preview=$('.slide-preview',card);let dragging=false,dragStyle;
 preview.onpointerdown=e=>{if(busy)return;e.preventDefault();selectedSlides[`${key}:${language}`]=slide.id;selectSet(key);dragging=true;dragStyle={...project.sets[key].versions[language].slides.find(s=>s.id===slide.id).style};preview.setPointerCapture(e.pointerId);preview.classList.add('dragging');};
 preview.onpointermove=e=>{if(!dragging)return;const bounds=preview.getBoundingClientRect();dragStyle.x=Math.max(0,Math.min(100,(e.clientX-bounds.left)/bounds.width*100));dragStyle.y=Math.max(0,Math.min(100,(e.clientY-bounds.top)/bounds.height*100));$('.position-marker',card).style.left=dragStyle.x+'%';$('.position-marker',card).style.top=dragStyle.y+'%';};
 const finish=()=>{if(!dragging)return;dragging=false;preview.classList.remove('dragging');const current=project.sets[key].versions[language].slides.find(s=>s.id===slide.id);current.style=dragStyle;queueSave('slide-'+slide.id,versionPath(key,language)+`/slides/${slide.id}`,{style:dragStyle},()=>refreshSlide(key,language,slide.id));syncEditor();};
 preview.onpointerup=finish;preview.onpointercancel=finish;
 preview.onkeydown=e=>{const direction={ArrowLeft:'left',ArrowRight:'right',ArrowUp:'up',ArrowDown:'down'}[e.key];if(direction){e.preventDefault();selectedSlides[`${key}:${language}`]=slide.id;selectSet(key);nudge(direction);}};
 $('.slides',section).append(card);refreshSlide(key,language,slide.id);
}
function render(){
 $('#workspace').replaceChildren();
 for(const [key,post] of Object.entries(project.sets)){
  if(!views[key])views[key]=post.versions[project.settings.language]?project.settings.language:(Object.keys(post.versions)[0]||project.settings.language);
  const language=viewedLanguage(key),v=post.versions[language],section=$('#set-template').content.firstElementChild.cloneNode(true);section.dataset.key=key;
  $('.set-select b',section).textContent=key;$('.set-select',section).onclick=()=>selectSet(key);
  $('.source-count',section).textContent=`${post.source_ids.length} / 10 SOURCE`;
  $('.set-status',section).textContent=post.error?'ERROR':(v?.status||'대기 중...');
  $('.set-error',section).hidden=!post.error;$('.set-error',section).textContent=post.error;
  $('.set-add',section).onclick=()=>pickFiles('one-file',key);$('.set-multiple',section).onclick=()=>pickFiles('many-files',key);$('.set-folder',section).onclick=()=>pickFiles('folder-files',key);
  $('.set-clear',section).onclick=()=>{if(!confirm(`${key} SET의 현재 SOURCE 목록을 비울까요? 기존 언어 버전은 보존됩니다.`))return;action(async()=>{updateProject(await json(`/sets/${key}/sources`,'DELETE'));render();},'SOURCE 목록 정리 중…');};
  $('.set-manual',section).onclick=()=>manual(key);renderSources(section,key,post);
  for(const lang of Object.keys(post.versions)){const tab=element('button',lang.toUpperCase(),lang===language?'selected':'');tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(lang===language));tab.onclick=()=>action(async()=>{views[key]=lang;render();selectSet(key);},'언어 버전 전환');$('.version-tabs',section).append(tab);}
  $('.version-empty',section).hidden=!!v;$('.version-content',section).hidden=!v;
  $('#workspace').append(section);
  if(v){
   $('.version-info',section).textContent=`${languages[language]} · ${v.options.aspect_ratio} · ${v.options.fit_mode} · Variation ${v.options.variation_enabled?'ON':'OFF'}`;
   $('.stale-warning',section).hidden=v.source_revision===post.source_revision;
   $('.hook',section).value=v.hook;$('.caption',section).value=v.caption;
   $('.hook',section).oninput=e=>queueSave('version-'+key+language,versionPath(key,language),{hook:e.target.value},()=>refreshSlide(key,language,v.slides[0].id));
   v.hook_candidates.forEach((hook,index)=>{const candidate=element('button',`${index+1}. ${hook}`,hook===v.hook?'selected':'');candidate.onclick=()=>action(async()=>{updateProject(await json(versionPath(key,language),'PATCH',{hook}));render();},'HOOK 적용');$('.hook-candidates',section).append(candidate);});
   $('.caption',section).oninput=e=>queueSave('caption-'+key+language,versionPath(key,language),{caption:e.target.value});
   $('.regenerate-hook',section).onclick=()=>generate(key,language,'hook');$('.regenerate-caption',section).onclick=()=>generate(key,language,'caption');
   $('.copy-caption',section).onclick=async()=>{try{await navigator.clipboard.writeText($('.caption',section).value);toast('Caption을 복사했습니다.');}catch{toast('Caption을 선택하고 Ctrl+C를 누르세요.');}};
   $('.analysis pre',section).textContent=v.analysis?JSON.stringify(v.analysis,null,2):'수동 버전입니다. AI 분석 및 외부 사실 확인을 수행하지 않았습니다.';
   v.slides.forEach((slide,index)=>renderSlide(section,key,language,slide,index,v));
  }
 }
 selectSet(activeSet);setBusy(busy);
}
function nudge(direction){const s=selected(),v=version();if(!s||busy)return;const width=1080,height={'1:1':1080,'4:5':1350,'9:16':1920}[v.options.aspect_ratio];s.style.x=Math.max(0,Math.min(100,s.style.x+(direction==='left'?-1:direction==='right'?1:0)*1000/width));s.style.y=Math.max(0,Math.min(100,s.style.y+(direction==='up'?-1:direction==='down'?1:0)*1000/height));syncEditor();editorChange();}
function download(blob,name){const url=URL.createObjectURL(blob),a=element('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
async function exportImage(key,language,id,index){await action(async()=>{const blob=await(await api(versionPath(key,language)+`/slides/${id}/image?download=1`)).blob();download(blob,`${key}_${language.toUpperCase()}_${String(index).padStart(2,'0')}.png`);},'이미지 다운로드 준비 중…');}
async function exportZip(scope){await action(async()=>{const blob=await(await api('/export',{method:'POST',body:JSON.stringify({scope,set:activeSet,language:viewedLanguage(activeSet)})})).blob();download(blob,`1028FALL_${scope}_${activeSet}.zip`);toast('ZIP 저장 완료. Instagram에는 직접 업로드하세요.');},'이미지와 Caption을 ZIP으로 만드는 중…');}
function syncLogo(){const config=$('#logo-scope').value==='project'?project.logo:project.sets[$('#logo-scope').value].logo;$('#logo-size').value=config.size;$('#logo-position').value=config.position;}
function wire(){
 buildEditor();for(const node of document.querySelectorAll('[data-set]'))node.onclick=()=>selectSet(node.dataset.set);
 $('#add-one').onclick=()=>pickFiles('one-file');$('#add-many').onclick=()=>pickFiles('many-files');$('#add-folder').onclick=()=>pickFiles('folder-files');
 for(const id of ['one-file','many-files','folder-files'])$('#'+id).onchange=e=>{const files=[...e.target.files],target=fileTarget;e.target.value='';upload(files,target);};
 for(const node of document.querySelectorAll('[data-move]'))node.onclick=()=>nudge(node.dataset.move);
 $('#language').onchange=()=>{queueSave('language','/settings',{language:$('#language').value});};
 $('#sample').oninput=()=>queueSave('sample','/settings',{style_sample:$('#sample').value});
 for(const id of ['aspect','fit','variation'])$('#'+id).onchange=()=>queueSave('options','/settings',options());
 $('#generate').onclick=()=>generate(activeSet,$('#language').value);$('#language-version').onclick=$('#generate').onclick;$('#manual').onclick=()=>manual();
 $('#regenerate-set').onclick=()=>generate(activeSet,viewedLanguage(activeSet));
 $('#apply-options').onclick=()=>action(async()=>{if(!version())throw new Error('먼저 언어 버전을 만드세요.');updateProject(await json(versionPath(activeSet,viewedLanguage(activeSet)),'PATCH',{options:options()}));render();},'현재 버전 이미지 설정 적용 중…');
 $('#apply-style').onclick=()=>action(async()=>{if(!version())throw new Error('먼저 언어 버전을 만드세요.');updateProject(await json(versionPath(activeSet,viewedLanguage(activeSet))+'/style','POST',{style:editorValues()}));render();},'현재 버전 디자인 적용 중…');
 $('#save-default-style').onclick=()=>action(async()=>{updateProject(await json('/settings','PATCH',{default_style:editorValues()}));toast('새 버전 기본 디자인을 저장했습니다.');},'기본 디자인 저장 중…');
 $('#logo-scope').onchange=()=>syncLogo();$('#logo-upload').onclick=()=>{logoTarget=$('#logo-scope').value;$('#logo-file').click();};
 $('#logo-file').onchange=e=>{const file=e.target.files[0];e.target.value='';if(!file)return;action(async()=>{const data=new FormData();data.append('file',file);data.append('scope',logoTarget);updateProject(await(await api('/logo',{method:'POST',body:data})).json());render();},'로고 적용 중…');};
 const editLogo=patch=>action(async()=>{updateProject(await json('/logo','PATCH',{scope:$('#logo-scope').value,...patch}));render();syncLogo();},'로고 설정 저장 중…');
 $('#logo-delete').onclick=()=>editLogo({mode:'none'});$('#logo-inherit').onclick=()=>{if($('#logo-scope').value==='project'){toast('먼저 A/B/C 적용 범위를 선택하세요.');return;}editLogo({mode:'inherit'});};
 $('#logo-size').onchange=()=>editLogo({size:Number($('#logo-size').value)});$('#logo-position').onchange=()=>editLogo({position:$('#logo-position').value});
 $('#download-version').onclick=()=>exportZip('version');$('#download-set').onclick=()=>exportZip('set');$('#download-all').onclick=()=>exportZip('all');$('#download-project').onclick=()=>exportZip('project');
 $('#save-json').onclick=()=>action(async()=>download(new Blob([JSON.stringify(project,null,2)],{type:'application/json'}),'project.json'),'프로젝트 설정 저장 중…');
 $('#restore').onclick=()=>$('#project-file').click();$('#project-file').onchange=e=>{const file=e.target.files[0];e.target.value='';if(!file)return;if(!confirm('현재 작업을 저장한 프로젝트로 교체할까요? 필요한 작업은 먼저 ZIP으로 저장하세요.'))return;action(async()=>{const data=new FormData();data.append('file',file);updateProject(await(await api('/restore',{method:'POST',body:data})).json());for(const key of ['A','B','C'])delete views[key];syncSettings();render();toast('SOURCE와 모든 언어 버전을 복원했습니다.');},'프로젝트 불러오는 중…');};
 $('#new-project').onclick=()=>{if(!confirm('현재 프로젝트의 SOURCE와 모든 언어 버전·임시파일을 지울까요? 먼저 ZIP을 저장하세요.'))return;action(async()=>{updateProject(await json('/project','DELETE'));for(const key of ['A','B','C'])delete views[key];syncSettings();render();},'현재 작업 파일 정리 중…');};
}
function syncSettings(){const s=project.settings;$('#language').value=s.language;$('#sample').value=s.style_sample;$('#aspect').value=s.aspect_ratio;$('#fit').value=s.fit_mode;$('#variation').checked=s.variation_enabled;syncLogo();}
(async()=>{wire();setBusy(true);try{const state=await json('/project');project=state.project;languages=state.languages;ai=state.ai_available;for(const [value,label]of Object.entries(languages)){const option=element('option',label);option.value=value;$('#language').append(option);}$('#mode').textContent=ai?'AI 준비 완료 · SOURCE 기반 언어 버전 생성':'AI API 키가 없습니다. 데모 모드 · 수동 편집/디자인/저장 가능';syncSettings();render();}catch(error){toast(error.message);$('#mode').textContent=error.message;}finally{setBusy(false);}})();
