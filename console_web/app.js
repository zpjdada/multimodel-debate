'use strict';
const $ = id => document.getElementById(id);
const tokenInURL = new URLSearchParams(location.hash.slice(1)).get('token');
if (tokenInURL) { sessionStorage.setItem('council-token', tokenInURL); history.replaceState(null, '', location.pathname); }
let models = [], seats = [], selected = null, view = 'overview', data = null, timer = null;
let roundFilter = '', seatFilter = '';
let projectBrief = '';
const modeHints = {proposal:'找值得验证的新方向：说明研究范围和资源约束。',evaluate:'对一个可判真假的具体问题进行评估。',solve:'形成可执行解法：请说明资源、权限与完成标准。'};
const names = {ready:'待启动', checking:'预检中', running:'讨论中', failed:'运行失败，可续跑', interrupted:'服务曾中断，请核查日志', completed:'已完成', imported:'已有记录 · 只读'};
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function note(text='') { $('notice').textContent = text; }
async function api(path, body) {
  const res = await fetch(path, {method:body === undefined ? 'GET':'POST', headers:{Authorization:'Bearer '+(sessionStorage.getItem('council-token')||''), 'Content-Type':'application/json'}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const json = await res.json();
  if (!res.ok) { if(res.status === 401) $('login').hidden = false; throw new Error(json.error || '请求失败'); }
  return json;
}
function option(value, text) { const n=node('option',text); n.value=value; return n; }
function button(text, action, cls) { const b=node('button',text,cls); b.type='button'; b.onclick=action; return b; }
function field(label, input) { const l=node('label',label); l.append(input); return l; }
function renderSeats() {
  $('seat-number').value = seats.length;
  $('threshold').max = seats.length;
  $('threshold').value = Math.min(Number($('threshold').value), seats.length);
  $('seats').replaceChildren();
  seats.forEach((s,i) => {
    const card=node('div',undefined,'seat'), head=node('div',undefined,'seat-head');
    head.append(node('strong',`a${String(i+1).padStart(2,'0')}`));
    const radio=document.createElement('input'); radio.type='radio'; radio.name='chair'; radio.checked=!!s.chair;
    radio.onchange=()=> {seats.forEach((v,j)=>v.chair=i===j);};
    head.append(field('主持',radio));
    const grid=node('div',undefined,'grid'), select=document.createElement('select');
    select.setAttribute('aria-label',`a${i+1} 模型`);
    models.forEach(m=>select.append(option(m,m)));
    if(s.model && !models.includes(s.model))select.append(option(s.model,s.model+'（当前未发现）'));
    select.value=s.model||models[0]||''; s.model=select.value; select.onchange=()=>s.model=select.value;
    const role=document.createElement('input'); role.value=s.role; role.required=true; role.oninput=()=>s.role=role.value;
    grid.append(field('模型',select),field('分工',role));
    const focus=document.createElement('textarea'); focus.rows=2; focus.value=s.focus; focus.required=true; focus.oninput=()=>s.focus=focus.value;
    card.append(head,grid,field('独立研究重点',focus)); $('seats').append(card);
  });
}
async function listRuns() {
  const runs=await api('/api/runs'); $('runs').replaceChildren();
  if(!runs.length)$('runs').append(node('p','还没有场次，点击右上角新建。','muted'));
  for(const run of runs) { const b=button(run.title,()=>openRun(run.id),'run'+(run.id===selected?' selected':'')); b.append(node('small',names[run.status]||run.status)); $('runs').append(b); }
}
async function openRun(id) {
  const wasRunning = selected===id && ['running','checking'].includes(data?.status);
  selected=id; $('editor').hidden=true; $('detail').hidden=false;
  try {const next=await api('/api/runs/'+id);if(selected!==id)return;data=next;if(wasRunning && data.status==='completed'){view='final';note('辩论已完成，最终报告已生成。');}renderDetail(); await listRuns(); schedule();} catch(e){note(e.message);if(selected===id)timer=setTimeout(()=>openRun(id),6000);}
}
function schedule() {clearTimeout(timer); if(['running','checking'].includes(data?.status))timer=setTimeout(()=>openRun(selected),4000);}
function textBlock(text) {return node('pre',text,'text');}
function format(value) {return typeof value==='string'?value:JSON.stringify(value,null,2);}
function renderDetail() {
  const root=$('detail'); root.replaceChildren();
  const head=node('div',undefined,'section-title'); head.append(node('h2',data.title));
  if(data.id!=='current' && !['running','checking','completed'].includes(data.status)) head.append(button(data.status==='ready'?'启动辩论':'续跑失败阶段',async()=>{
    if(!confirm('将调用所选模型并产生费用，确认启动？'))return;
    try{await api('/api/runs/'+selected+'/start',{});note();await openRun(selected);}catch(e){note(e.message);}
  },'primary'));
  root.append(head,node('p',`${names[data.status]||data.status} · ${data.protocol.mode||''} · 场次 ${data.id}`,'muted'));
  root.append(node('div',data.phase||'','card phase'+(['running','checking'].includes(data.status)?' working':'')));
  if(data.error)root.append(node('p',data.error,'fail'));
  const metrics=node('div',undefined,'metrics');
  const denom=data.protocol.threshold?.denominator||data.seats.length;
  [['席位',data.seats.length],['正式发言',`${data.speeches.length}/${data.seats.length*(data.protocol.rounds||0)}`],['门槛',`${data.protocol.threshold?.numerator||'—'}/${denom}`],['通过候选',(data.audit.approved_candidates||data.audit.adopted_conclusions||data.audit.adopted_solutions||[]).length]].forEach(([label,value])=>{const m=node('div',label,'metric');m.append(node('strong',value));metrics.append(m);});
  root.append(metrics);
  const tabs=node('div',undefined,'tabs');
  [['overview','概览 / 检查'],['rounds','各轮观点'],['relations','支持与反驳'],['candidates','候选与共识'],['final','最终报告'],['logs','运行日志']].forEach(([id,label])=>tabs.append(button(label,()=>{view=id;renderDetail();},id===view?'active':'')));
  root.append(tabs);
  if(view==='overview') {
    if(data.materials?.length)root.append(node('p','本场材料：'+data.materials.join('、'),'muted'));
    for(const s of data.seats)root.append(node('div',`${s.id} ${s.chair?'· 主持 · ': '· '}${s.role}\n${s.model}`,'card text'));
    if(data.doctor.checks){const card=node('div',undefined,'card');card.append(node('h3','本场运行时预检'));for(const c of data.doctor.checks)card.append(node('p',`${c.ok?'✓':'✕'} ${c.check} — ${c.detail}`,c.ok?'pass':'fail'));root.append(card);}
    if(data.audit.complete)root.append(node('p','记录审计已完成；审计不证明引文真实或方向新颖。','muted'));
  } else if(view==='rounds'||view==='relations') {
    const filters=node('div',undefined,'filter'), rounds=document.createElement('select'), people=document.createElement('select');
    rounds.setAttribute('aria-label','筛选轮次'); people.setAttribute('aria-label','筛选席位');
    rounds.append(option('','全部轮次'));for(let r=1;r<=(data.protocol.rounds||3);r++)rounds.append(option(String(r),'第 '+r+' 轮'));
    people.append(option('','全部席位')); data.seats.forEach(s=>people.append(option(s.id,s.id+' '+s.role)));
    rounds.value=roundFilter; people.value=seatFilter;
    rounds.onchange=()=>{roundFilter=rounds.value;renderDetail();};people.onchange=()=>{seatFilter=people.value;renderDetail();};
    filters.append(rounds,people);root.append(filters);
    if(view==='rounds') {
      const speeches=data.speeches.filter(s=>(!roundFilter||String(s.metadata.round)===roundFilter)&&(!seatFilter||s.metadata.agent_id===seatFilter));
      for(const s of speeches){const card=node('details',undefined,'card');card.append(node('summary',`${s.file} · 检索 ${s.metadata.retrieval_status||'见正文'}`),textBlock(s.text));root.append(card);}
      if(!speeches.length)root.append(node('p','此筛选下还没有已保存的发言。','muted'));
    } else {
      const edges=data.relations.filter(e=>(!roundFilter||String(e.round)===roundFilter)&&(!seatFilter||e.from===seatFilter||e.to_agent===seatFilter));
      for(const e of edges){const card=node('div',undefined,'card relation '+(['support','oppose','modify'].includes(e.stance)?e.stance:''));card.append(node('strong',`${e.from} → ${e.to_agent}\n第${e.round}轮 · ${{support:'支持',oppose:'反对',modify:'修订'}[e.stance]||e.stance}`),node('div',e.claim));root.append(card);}
      if(!edges.length)root.append(node('p','互评完成后，这里会显示有原文主张的支持、反驳和修订关系。','muted'));
    }
  } else if(view==='candidates') {
    const items=data.catalog.candidates||data.catalog.conclusions||data.catalog.solutions||[];
    const scores=data.audit.candidates||data.audit.conclusions||data.audit.solutions||[];
    if(!items.length)root.append(node('p','主持尚未归并候选。','muted'));
    for(const item of items){const tally=scores.find(s=>(s.candidate_id||s.conclusion_id||s.solution_id)===item.id); const card=node('div',undefined,'card');card.append(node('h3',`${item.id} · ${item.title||item.statement}`));
      if(tally){card.append(node('p',`${tally.support}/${tally.denominator} 支持 · ${tally.threshold_met?'达到票数门槛':'未达到门槛'}`,tally.threshold_met?'pass':'fail'));const p=document.createElement('progress');p.max=tally.denominator;p.value=tally.support;const bar=node('div',undefined,'bar');bar.append(p);card.append(bar); if(tally.fatal_objections_to_review?.length)card.append(node('p','致命异议待核查：'+tally.fatal_objections_to_review.join('、'),'fail'));}
      else card.append(node('p','待独立投票与审计','muted'));
      for(const [key,label] of [['mechanism','机制'],['closest_work','最近邻'],['minimum_experiment','最小实验'],['stop_condition','停止条件']])if(item[key]){const detail=node('details');detail.append(node('summary',label),textBlock(format(item[key])));card.append(detail);}
      const full=node('details');full.append(node('summary','完整候选定义'),textBlock(format(item)));card.append(full);root.append(card);}
    if(data.audit.retrieval_partial_seats?.length)root.append(node('p','查重尚未覆盖完整：'+data.audit.retrieval_partial_seats.join('、'),'muted'));
  } else if(view==='final')root.append(textBlock(data.final||'最终报告尚未生成。'));
  else root.append(textBlock(data.log||'尚无控制台运行日志。'));
}
async function init() {
  try {
    note('正在读取模型清单与项目配置…');
    const environment=await api('/api/environment');
    $('environment').textContent=environment.ok?`${environment.version} · Python ${environment.python}`:environment.error;
    if(!environment.ok)throw new Error(environment.error);
    const [inventory,defaults]=await Promise.all([api('/api/models'),api('/api/defaults')]);
    models=inventory.models; seats=defaults.seats.map(s=>({model:s.model,role:s.role,focus:s.focus,chair:!!s.chair}));
    if(!seats.length)seats=Array.from({length:6},(_,i)=>({model:models[i%Math.max(1,models.length)],role:'研究席位 '+(i+1),focus:'独立查阅一手文献，提出可证伪机制并检验最近邻。',chair:i===2}));
    projectBrief=defaults.brief; $('rounds').value=defaults.protocol.rounds; $('mode').value=defaults.protocol.mode; $('threshold').value=defaults.protocol.threshold.numerator;
    $('mode-hint').textContent=modeHints[$('mode').value];
    $('project-materials').textContent=defaults.materials.length?`项目材料：${defaults.materials.join('、')}`:'项目中暂无材料；可从上方选择本地文件。';
    renderSeats(); await listRuns(); $('login').hidden=true; note();
  } catch(e){note(e.message);}
}
$('login-button').onclick=()=>{sessionStorage.setItem('council-token',$('token').value);init();};
$('new').onclick=()=>{clearTimeout(timer);selected=null;$('editor').hidden=false;$('detail').hidden=true;listRuns().catch(e=>note(e.message));};
$('refresh').onclick=()=>{if(selected)openRun(selected);else listRuns().catch(e=>note(e.message));};
$('reload-models').onclick=async()=>{try{const environment=await api('/api/environment');$('environment').textContent=environment.ok?`${environment.version} · Python ${environment.python}`:environment.error;if(!environment.ok)throw new Error(environment.error);models=(await api('/api/models')).models;renderSeats();note(`已读取 ${models.length} 个模型 ID。模型出现在列表中不代表供应商一定允许调用。`);}catch(e){note(e.message);}};
$('load-brief').onclick=()=>{$('brief').value=projectBrief;};
$('mode').onchange=()=>{$('mode-hint').textContent=modeHints[$('mode').value];$('threshold').value=$('mode').value==='evaluate'?Math.floor(seats.length/2)+1:Math.round(seats.length*.8);};
$('seat-number').onchange=()=>{const count=Number($('seat-number').value);if(!Number.isInteger(count)||count<3||count>12)return note('席位数须为3–12');while(seats.length<count)seats.push({model:models[seats.length%Math.max(1,models.length)]||'',role:'独立研究者',focus:'寻找不同机制与最近邻反例。',chair:false});seats=seats.slice(0,count);if(!seats.some(s=>s.chair))seats[0].chair=true;renderSeats();$('mode').onchange();};
$('materials').onchange=()=>{$('file-list').textContent=Array.from($('materials').files).map(f=>`${f.name} (${(f.size/1024).toFixed(0)} KB)`).join('；');};
async function readMaterials(){const files=Array.from($('materials').files);if(files.length>20||files.reduce((sum,f)=>sum+f.size,0)>20*1024*1024)throw new Error('材料最多20份，总大小不超过20MB');return Promise.all(files.map(file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve({name:file.name,base64:String(reader.result).split(',')[1]});reader.onerror=()=>reject(new Error('无法读取 '+file.name));reader.readAsDataURL(file);})))}
$('config').onsubmit=async event=>{event.preventDefault();const launch=event.submitter?.id==='launch';$('save').disabled=true;$('launch').disabled=true;try{const materials=await readMaterials();const run=await api('/api/runs',{title:$('title').value,fields:{question:$('question').value,background:$('background').value,known:$('known').value,constraints:$('constraints').value,extra:$('brief').value},materials,include_project_materials:$('inherit-materials').checked,mode:$('mode').value,rounds:Number($('rounds').value),threshold:Number($('threshold').value),seats});view='overview';await openRun(run.id);if(launch){await api('/api/runs/'+run.id+'/start',{});note('正在执行讨论。完成的发言会逐轮显示，结束后自动展示最终报告。');await openRun(run.id);}else note('配置与材料已保存，可以稍后启动。');}catch(e){note(e.message);}finally{$('save').disabled=false;$('launch').disabled=false;}};
init();
