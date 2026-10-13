'use strict';
const $ = (s, root=document) => root.querySelector(s);
const token = $('meta[name="studio-token"]').content;
let items=[], ai=false, busy=false, stopped=false, toastTimer;
let saveTail=Promise.resolve();
const saves=new Map(), elements=new Map();
function toast(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,6500);}
async function api(url, options={}){
  const headers={'X-Studio-Token':token,...options.headers};
  if(options.body && !(options.body instanceof FormData)) headers['Content-Type']='application/json';
  const response=await fetch(url,{...options,headers});
  if(!response.ok){let error;try{error=(await response.json()).error;}catch{error='서버 연결 오류';}throw new Error(error);}
  return response;
}
function setBusy(value){busy=value;document.body.classList.toggle('busy',value);for(const control of document.querySelectorAll('button,input,select,textarea'))control.disabled=value;$('#stop').disabled=false;$('#generate').disabled=value||!ai;for(const b of document.querySelectorAll('.regenerate'))b.disabled=value||!ai;}
function refresh(item){const card=elements.get(item.id);if(card)$('img',card).src=`/api/items/${item.id}/image?v=${Date.now()}`;}
function status(item,text,error=''){const card=elements.get(item.id);item.status=text;const tag=$('.status',card);tag.textContent=text;tag.className='status '+(text==='COMPLETE'?'complete':text==='ERROR'?'error':text.includes('ING')?'active':'');$('.card-error',card).textContent=error;$('.card-error',card).hidden=!error;}
function values(item,card){return {title:$('.title',card).value,caption:$('.caption',card).value,language:item.language,
 style:{...item.style,font_size:Number($('.font-size',card).value),weight:$('.weight',card).value,gradient:Number($('.density',card).value),gradient_range:Number($('.extent',card).value),logo_position:$('.logo-pos',card).value}};}
function save(item){const card=elements.get(item.id);const payload=JSON.stringify(values(item,card));const operation=saveTail.then(async()=>{const updated=await(await api(`/api/items/${item.id}`,{method:'PATCH',body:payload})).json();Object.assign(item,values(item,card));status(item,updated.status);refresh(item);});saveTail=operation.catch(()=>{});return operation;}
function queueSave(item){const previous=saves.get(item.id);if(previous)clearTimeout(previous.timer);const pending={timer:setTimeout(async()=>{try{await save(item);}catch(e){toast(e.message);}finally{if(saves.get(item.id)===pending)saves.delete(item.id);}},220)};saves.set(item.id,pending);}
async function flush(){for(const [id,pending]of saves){clearTimeout(pending.timer);saves.delete(id);const item=items.find(i=>i.id===id);if(item)await save(item);}await saveTail;}
function createCard(item,index){const card=$('#card-template').content.firstElementChild.cloneNode(true);elements.set(item.id,card);$('.number',card).textContent=`IMAGE ${String(index+1).padStart(3,'0')}`;$('.filename',card).textContent=item.name;$('.title',card).value=item.title;$('.caption',card).value=item.caption;
 $('.font-size',card).value=item.style.font_size;$('.weight',card).value=item.style.weight;$('.density',card).value=item.style.gradient;$('.extent',card).value=item.style.gradient_range;$('.logo-pos',card).value=item.style.logo_position;
 $('.density-value',card).textContent=item.style.gradient+'%';$('.range-value',card).textContent=item.style.gradient_range+'%';
 for(const field of card.querySelectorAll('input,select,textarea'))field.addEventListener('input',()=>{if(busy)return;$('.density-value',card).textContent=$('.density',card).value+'%';$('.range-value',card).textContent=$('.extent',card).value+'%';queueSave(item);});
 for(const b of card.querySelectorAll('[data-dx]'))b.onclick=()=>{item.style.x=Math.max(0,Math.min(100,item.style.x+Number(b.dataset.dx)));item.style.y=Math.max(0,Math.min(100,item.style.y+Number(b.dataset.dy)));queueSave(item);};
 $('.copy',card).onclick=async()=>{try{await navigator.clipboard.writeText($('.caption',card).value);toast('본문을 복사했습니다.');}catch{toast('복사를 허용하거나 본문을 선택해 Ctrl+C를 누르세요.');}};
 $('.manual',card).onclick=()=>{$('.title',card).focus();toast('제목과 본문을 입력하면 미리보기에 자동 반영됩니다.');};
 $('.download',card).onclick=async()=>{try{await flush();const blob=await(await api(`/api/items/${item.id}/image?download=1`)).blob();download(blob,`${String(index+1).padStart(3,'0')}_${safe(item.title||item.name)}.png`);}catch(e){toast(e.message);}};
 $('.regenerate',card).disabled=!ai;$('.regenerate',card).onclick=()=>run([item]);
 $('#cards').append(card);status(item,item.status,item.error);refresh(item);
}
function render(){elements.clear();$('#cards').replaceChildren();items.forEach(createCard);$('#count').textContent=items.length;$('#empty').hidden=items.length>0;}
function safe(text){return text.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,60).replace(/[. ]+$/g,'')||'image';}
function download(blob,name){const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}
async function upload(files){if(busy)return;const supported=[...files].filter(f=>/\.(jpe?g|png|webp)$/i.test(f.name));setBusy(true);let done=0,fail=0;try{await flush();for(const file of supported){const data=new FormData();data.append('files',file);try{const result=await(await api('/api/upload',{method:'POST',body:data})).json();items=result.items;fail+=result.errors.length;}catch(e){fail++;toast(`${file.name}: ${e.message}`);}done++;$('#progress-text').textContent=`${done} / ${supported.length} 업로드`;}render();toast(`${items.length}장 준비 완료${fail?` · ${fail}장 업로드 실패`:''}`);}catch(e){toast(e.message);}finally{setBusy(false);for(const card of elements.values())$('.regenerate',card).disabled=!ai;}}
async function run(targets){if(busy||!ai)return;if(!targets.length){toast('먼저 사진을 업로드하세요.');return;}try{await flush();}catch(e){toast(e.message);return;}setBusy(true);stopped=false;$('#stop').textContent='현재 이미지 후 중지';$('#stop').hidden=false;let done=0,failed=0;const language=$('#language').value,sample=$('#sample').value;
 try{for(const item of targets){if(stopped)break;try{status(item,'ANALYZING...');const analysis=await(await api(`/api/items/${item.id}/analyze`,{method:'POST'})).json();status(item,'GENERATING...');const updated=await(await api(`/api/items/${item.id}/generate`,{method:'POST',body:JSON.stringify({analysis:analysis.analysis,language,sample})})).json();Object.assign(item,updated);const card=elements.get(item.id);$('.title',card).value=item.title;$('.caption',card).value=item.caption;status(item,'COMPLETE');refresh(item);}catch(e){failed++;status(item,'ERROR',e.message);}done++;$('#progress-text').textContent=`${done} / ${targets.length} 처리 완료 · 실패 ${failed}`;$('#progress').style.width=`${100*done/targets.length}%`;}
 toast(`${stopped?'중지됨':'처리 완료'} · 성공 ${done-failed}장 · 실패 ${failed}장`);
 }finally{setBusy(false);$('#stop').hidden=true;for(const card of elements.values())$('.regenerate',card).disabled=!ai;}}
$('#folder-button').onclick=()=>$('#folder').click();$('#files-button').onclick=()=>$('#files').click();$('#empty-upload').onclick=()=>$('#files').click();for(const id of ['folder','files'])$('#'+id).onchange=e=>{upload(e.target.files);e.target.value='';};
$('#generate').onclick=()=>run(items);$('#stop').onclick=()=>{stopped=true;$('#stop').textContent='중지 요청됨';};
$('#clear').onclick=async()=>{if(!confirm('모든 사진, 로고, 편집 결과와 임시파일을 삭제할까요?'))return;try{await flush();await api('/api/clear',{method:'POST'});items=[];render();$('#logo-button').textContent='로고 이미지 업로드';$('#progress').style.width='0';$('#progress-text').textContent='작업을 시작해 보세요';toast('임시파일을 정리했습니다.');}catch(e){toast(e.message);}};
$('#logo-button').onclick=()=>$('#logo').click();$('#logo').onchange=async e=>{if(!e.target.files[0])return;setBusy(true);try{await flush();const data=new FormData();data.append('file',e.target.files[0]);await api('/api/logo',{method:'POST',body:data});$('#logo-button').textContent='로고 변경';items.forEach(refresh);toast('로고를 적용했습니다.');}catch(error){toast(error.message);}finally{e.target.value='';setBusy(false);}};
$('#logo-position').onchange=async()=>{if(busy)return;try{await flush();for(const item of items){$('.logo-pos',elements.get(item.id)).value=$('#logo-position').value;await save(item);}}catch(e){toast(e.message);}};
$('#export').onclick=async()=>{setBusy(true);try{await flush();$('#progress-text').textContent='ZIP 생성 중…';const blob=await(await api('/api/export',{method:'POST'})).blob();download(blob,'1028FALL_EXPORT.zip');toast('원본, PNG, 캡션, 프로젝트를 ZIP으로 저장했습니다.');}catch(e){toast(e.message);}finally{setBusy(false);$('#progress-text').textContent='내보내기 작업 종료';}};
$('#project').onclick=async()=>{try{await flush();const blob=await(await api('/api/project')).blob();download(blob,'project.json');toast('프로젝트 JSON 저장 완료. 원본까지 보관하려면 ZIP을 저장하세요.');}catch(e){toast(e.message);}};
(async()=>{try{const state=await(await api('/api/state')).json();items=state.items;ai=state.ai_available;$('#mode').textContent=ai?'AI 준비 완료 · 수동 편집도 가능합니다.':'AI API 키가 설정되지 않았습니다. 현재 데모 모드로 실행 중입니다.';if(state.logo)$('#logo-button').textContent='로고 변경';render();setBusy(false);for(const card of elements.values())$('.regenerate',card).disabled=!ai;}catch(e){toast(e.message);}})();

$('#restore-button').onclick=()=>$('#restore').click();
$('#restore').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(items.length&&!confirm('현재 목록을 프로젝트로 교체할까요? 필요한 작업은 먼저 ZIP으로 저장하세요.')){e.target.value='';return;}setBusy(true);try{await flush();const data=new FormData();data.append('file',file);const state=await(await api('/api/restore',{method:'POST',body:data})).json();items=state.items;render();$('#logo-button').textContent=state.logo?'로고 변경':'로고 이미지 업로드';toast('프로젝트를 불러왔습니다.');}catch(error){toast(error.message);}finally{e.target.value='';setBusy(false);}};
