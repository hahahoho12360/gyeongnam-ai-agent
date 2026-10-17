const API=(window.APP_CONFIG&&window.APP_CONFIG.API_BASE_URL)||'http://127.0.0.1:8000';
const $=s=>document.querySelector(s);
let regions=[],conversationId=null,editingId=null,currentRows=[],selectionVersion=0,activeMetric='population_total',dashboardCharts={},activeRegionId=null,appliedStart='',appliedEnd='',comparisonQuestion='';
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function api(path,opt={}){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),150000);try{const privateRequest=/^\/api\/(data(?:\/|$)|conversations(?:\/|$)|chat(?:\/|$))/.test(path)&&path!=='/api/data/metrics';const authHeaders=privateRequest?await window.personalAuthHeaders():{};let r=await fetch(API+path,{...opt,signal:controller.signal,headers:{'Content-Type':'application/json',...authHeaders,...(opt.headers||{})}});if(r.status===401&&privateRequest){const refreshed=await window.personalAuthHeaders(true);r=await fetch(API+path,{...opt,signal:controller.signal,headers:{'Content-Type':'application/json',...refreshed,...(opt.headers||{})}})}if(!r.ok){let detail;try{const body=await r.json();detail=body.detail;if(body.request_id&&typeof detail==='string')detail+=' (요청 번호: '+body.request_id+')'}catch{detail='서버 응답 오류'}throw new Error(typeof detail==='string'?detail:`요청을 처리하지 못했어요 (${r.status}).`)}return await r.json()}catch(e){if(e.name==='AbortError')throw new Error('응답이 오래 걸리고 있어요. 잠시 후 다시 시도해 주세요.');if(e instanceof TypeError)throw new Error('서버 연결이 끊겼거나 응답을 받지 못했어요. 입력 내용은 보존됩니다. 잠시 후 다시 시도해 주세요.');throw e}finally{clearTimeout(timer)}}
function setStatus(id,text,state=''){const e=$(id);e.textContent=text;e.dataset.state=state;}
function waitNotice(id,text){return setTimeout(()=>{if($(id).dataset.state==='busy')setStatus(id,text,'busy')},8000)}
const PERIOD_MIN='2022-10';
function lastClosedMonth(now=new Date()){const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit'}).formatToParts(now);let year=Number(parts.find(x=>x.type==='year').value),month=Number(parts.find(x=>x.type==='month').value)-1;if(month===0){year--;month=12}return `${year}-${String(month).padStart(2,'0')}`;}
function setPeriodBounds(minimum=PERIOD_MIN,maximum=lastClosedMonth()){const start=$('#startMonth'),end=$('#endMonth');start.min=minimum;start.max=end.value&&end.value>=minimum&&end.value<=maximum?end.value:maximum;end.min=start.value&&start.value>=minimum&&start.value<=maximum?start.value:minimum;end.max=maximum;}
$('#startMonth').onchange=$('#endMonth').onchange=$('#startMonth').onfocus=$('#endMonth').onfocus=()=>setPeriodBounds();
function clearOverview(note='AI에게 지역을 질문하거나 아래에서 법정읍·면·동을 선택해 주세요.'){selectionVersion++;activeRegionId=null;comparisonQuestion='';dashboardCharts={};questionPool=[];questionHistory=[];showQuestions();$('#activeRegion').textContent='아직 선택한 지역이 없어요.';$('#selectionOrigin').textContent=note;$('#chatRegion').textContent='';for(const id of ['summary','periodInfo','comparisonInfo','metricTabs'])$('#'+id).innerHTML='';for(const id of ['benchmarkNote','indexMethodology','freshness','chartStatus'])$('#'+id).textContent='';for(const id of ['startMonth','endMonth','periodApply','periodReset','csvBtn','jsonBtn'])$('#'+id).disabled=true;$('#startMonth').value=$('#endMonth').value='';drawCharts([]);setStatus('#summaryStatus','');}

function fmt(v){return v==null?'—':typeof v==='number'?v.toLocaleString('ko-KR',{maximumFractionDigits:2}):String(v)}
// Render Markdown from escaped text only; never trust model-generated HTML.
function inline(t){return esc(t).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');}
function markdown(text){let out='',list=false,code=false,table=false;for(const line of String(text).split('\n')){if(line.trim().startsWith('```')){if(list){out+='</ul>';list=false}if(table){out+='</tbody></table>';table=false}out+=code?'</code></pre>':'<pre><code>';code=!code;continue}if(code){out+=esc(line)+'\n';continue}if(/^\s*\|/.test(line)){if(/^\s*\|[\s:|\-]+$/.test(line))continue;if(!table){out+='<table><tbody>';table=true}out+='<tr>'+line.trim().replace(/^\||\|$/g,'').split('|').map(c=>'<td>'+inline(c.trim())+'</td>').join('')+'</tr>';continue}if(table){out+='</tbody></table>';table=false}const bullet=line.match(/^\s*(?:[-*]|\d+[.)])\s+(.+)/);if(bullet){if(!list){out+='<ul>';list=true}out+='<li>'+inline(bullet[1])+'</li>';continue}if(list){out+='</ul>';list=false}const h=line.match(/^#{1,6}\s+(.+)/);out+=h?'<h3>'+inline(h[1])+'</h3>':line.trim()?'<p>'+inline(line)+'</p>':''}if(list)out+='</ul>';if(table)out+='</tbody></table>';if(code)out+='</code></pre>';return out;}
function addMsg(role,text){$('.welcome')?.remove();const d=document.createElement('div');d.className='msg '+role;if(role==='assistant')d.innerHTML=markdown(text);else d.textContent=text;$('#messages').appendChild(d);$('#messages').scrollTop=$('#messages').scrollHeight;}
async function loadSourceStatus(){
  setStatus('#sourceOperationStatus','데이터 소스 상태를 확인하고 있어요…','busy');$('#sourceStatusBtn').disabled=true;const timer=waitNotice('#sourceOperationStatus','서버 응답을 기다리고 있어요…');
  const card=$('#sourceStatusCard'),summary=$('#readinessSummary'),list=$('#sourceStatusList');
  card.hidden=false; summary.textContent='확인 중…'; list.innerHTML='';
  try{
    const [ready,status]=await Promise.all([api('/api/meta/readiness'),api('/api/meta/source-status')]);
    // Show only the approved API sources used for the Changwon submission.
    const excludedSources=new Set(['household_birth_death','other_real_estate','onbid','kosis']);
    const visibleSources=(ready.sources||[]).filter(src=>!excludedSources.has(src.key));
    const configured=visibleSources.filter(x=>x.configured).length,total=visibleSources.length;
    summary.textContent=`DB ${ready.db_mode} · OpenAI ${ready.openai_configured?'설정됨':'미설정'} · 공공데이터 ${ready.public_data_key_configured?'키 설정됨':'키 미설정'} · 소스 ${configured}/${total} 준비`;
    const latest={}; (status||[]).forEach(x=>{if(x.source&&!latest[x.source])latest[x.source]=x});
    list.innerHTML=visibleSources.map(src=>{const st=latest[src.key];const state=st?(st.status||'기록됨'):(src.configured?'설정됨·아직 실행기록 없음':'설정 필요');const when=st&&(st.finished_at||st.started_at)?` · ${esc(st.finished_at||st.started_at)}`:'';return `<div class="row"><span><b>${esc(src.label)}</b><br><small>${esc(src.cadence)} · ${esc(state)}${when}</small></span></div>`}).join('');
    setStatus('#sourceOperationStatus',`확인 완료 · ${configured}/${total}개 소스 설정과 최근 수집 기록을 확인했어요. 설정 완료가 전체 수집 완료를 뜻하지는 않아요.`,'success');
  }catch(err){summary.textContent='소스 상태 확인 오류: '+err.message;setStatus('#sourceOperationStatus','확인 오류 · '+err.message,'error')}finally{clearTimeout(timer);$('#sourceStatusBtn').disabled=false}
}

function fillDistricts(){const districts=[...new Set(regions.map(r=>r.sigungu||'창원시'))];$('#districtSelect').innerHTML='<option value="">구 선택</option>'+districts.map(d=>`<option>${esc(d)}</option>`).join('');fillRegions();}
function fillRegions(id){const rows=regions.filter(r=>(r.sigungu||'창원시')===$('#districtSelect').value);$('#regionSelect').innerHTML='<option value="">읍·면·동 선택</option>'+rows.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('');if(id)$('#regionSelect').value=id;}
function chooseRegion(id,origin='직접 선택'){const r=regions.find(r=>r.id===id);if(!r)return;if(activeRegionId!==id)clearOverview('선택한 지역 자료를 불러올 준비가 되었어요.');selectionVersion++;activeRegionId=id;$('#districtSelect').value=r.sigungu||'창원시';fillRegions(id);$('#selectionOrigin').textContent=origin;$('#analysisTarget').value='region';$('#chatRegion').textContent=r.full_name||r.name;}
async function loadRegions(){setStatus('#regionStatus','지역 목록을 불러오고 있어요…','busy');regions=await api('/api/analytics/regions');fillDistricts();populateDataRegions();if(activeRegionId)chooseRegion(activeRegionId,$('#selectionOrigin').textContent);setStatus('#regionStatus','구와 법정읍·면·동을 선택해 주세요.');}
function unitFor(spec){if(spec.unit)return spec.unit;if(/인구/.test(spec.title||''))return '명';if(/매매|가격|전세/.test(spec.title||''))return /㎡/.test(spec.title||'')?'원/㎡':'원';if(/상가|사업체/.test(spec.title||''))return '개';return '지표값';}
function drawChart(spec,index){
 const svg=$(`#chart${index}`);svg.innerHTML='';svg.toggleAttribute('hidden',!spec);
 svg.previousElementSibling?.classList.contains('chart-endpoints')&&svg.previousElementSibling.remove();
 svg.nextElementSibling?.classList.contains('chart-starts')&&svg.nextElementSibling.remove();
 if(!spec?.labels?.length)return;
 const colors=['#008f9e','#4778ed','#ad72ce','#e59149'],sets=spec.datasets||[],valid=v=>typeof v==='number'&&Number.isFinite(v);
 const vals=sets.flatMap(s=>(s.data||[]).filter(valid));
 const W=700,H=320,L=90,R=90,T=65,B=75,min=vals.length?Math.min(...vals):0,max=vals.length?Math.max(...vals):1,range=max-min||1,ns='http://www.w3.org/2000/svg';
 const elem=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;svg.appendChild(el);return el};
 const x=i=>L+(W-L-R)*i/Math.max(1,spec.labels.length-1),y=v=>H-B-(H-T-B)*(v-min)/range;
 elem('text',{x:L,y:23,fill:'currentColor','font-size':16,'font-weight':700},spec.title||'비교 추세');elem('text',{x:8,y:40,fill:'currentColor','font-size':12},unitFor(spec));
 for(let j=0;j<4;j++){const v=min+range*j/3;elem('line',{x1:L,x2:W-R,y1:y(v),y2:y(v),stroke:'#b6cad0','stroke-opacity':.35});}
 // Endpoint labels are actual observations, not y-axis tick values.
 const labelSide=(last)=>{
  const endpoint=last?spec.labels.length-1:0,px=x(endpoint),tx=last?W-R+24:L-24;
  const entries=sets.map((set,i)=>({set,i,v:set.data?.[endpoint]})).map(e=>({...e,actual:valid(e.v),wanted:valid(e.v)?y(e.v):T+20+e.i*20})).sort((a,b)=>a.wanted-b.wanted);
  const gap=18,top=T-8,bottom=H-B+8;
  entries.forEach((e,i)=>{e.pos=Math.max(e.wanted,i?entries[i-1].pos+gap:top)});
  if(entries.length&&entries.at(-1).pos>bottom){entries.at(-1).pos=bottom;for(let i=entries.length-2;i>=0;i--)entries[i].pos=Math.min(entries[i].pos,entries[i+1].pos-gap)}
  for(const e of entries){
   const color=colors[e.i%4];
   if(e.actual)elem('polyline',{points:`${px},${y(e.v)} ${last?px+10:px-10},${e.pos} ${last?tx-4:tx+4},${e.pos}`,fill:'none',stroke:color,'stroke-width':1,'stroke-opacity':.8});
   const label=elem('text',{x:tx,y:e.pos+4,'text-anchor':last?'start':'end',fill:color,'font-size':12,'font-weight':700,'class':'chart-endpoint-label','data-side':last?'end':'start','aria-label':`${e.set.label} ${spec.labels[endpoint]} ${e.actual?metricFormat(e.v,spec.metric):'자료 없음'} ${unitFor(spec)}`},e.actual?metricFormat(e.v,spec.metric):'—');
   const tip=document.createElementNS(ns,'title');tip.textContent=label.getAttribute('aria-label');label.appendChild(tip);
  }
 };
 elem('text',{x:12,y:23,fill:'currentColor','font-size':11},'시작값');elem('text',{x:W-12,y:23,'text-anchor':'end',fill:'currentColor','font-size':11},'종료값');
 [...new Set([0,Math.floor((spec.labels.length-1)/2),spec.labels.length-1])].forEach(i=>elem('text',{x:x(i),y:H-B+25,'text-anchor':'middle',fill:'currentColor','font-size':12},spec.labels[i]));
 sets.forEach((set,si)=>{let segment=[];const flush=()=>{if(segment.length)elem('polyline',{points:segment.join(' '),fill:'none',stroke:colors[si%4],'stroke-width':si?2:3});segment=[]};
 (set.data||[]).forEach((v,i)=>{if(!valid(v)){flush();return}segment.push(`${x(i)},${y(v)}`);const dot=elem('circle',{cx:x(i),cy:y(v),r:3,fill:colors[si%4],tabindex:0});const tip=document.createElementNS(ns,'title');tip.textContent=`${set.label} · 저장 월 ${spec.labels[i]} · ${metricFormat(v,spec.metric)} ${unitFor(spec)}${set.source_dates?.[i]?' · 실제 자료 기준 '+set.source_dates[i]:''}`;dot.setAttribute('aria-label',tip.textContent);dot.appendChild(tip)});flush();elem('text',{x:L+(si%2)*290,y:H-20-Math.floor(si/2)*18,fill:colors[si%4],'font-size':11},set.label||`비교 ${si+1}`)});
 labelSide(false);labelSide(true);
 if(!vals.length)elem('text',{x:W/2,y:150,'text-anchor':'middle',fill:'currentColor','font-size':14},'선택 기간의 자료가 없습니다.');
}
function drawCharts(charts=[]){drawChart(charts[0],0);drawChart(charts[1],1)}
async function fetchSummary(keepPeriod=false){const id=activeRegionId;if(!id)return;const version=selectionVersion;const query=new URLSearchParams({answer_mode:$('#answerMode').value});if(comparisonQuestion)query.set('question',comparisonQuestion);if(keepPeriod){if($('#startMonth').value)query.set('start_month',$('#startMonth').value);if($('#endMonth').value)query.set('end_month',$('#endMonth').value)}const x=await api(`/api/analytics/regions/${id}/dashboard?${query}`);if(version!==selectionVersion)return;for(const id of ['startMonth','endMonth','periodApply','periodReset','csvBtn','jsonBtn'])$('#'+id).disabled=false;appliedStart=x.start_month||'';appliedEnd=x.end_month||'';$('#startMonth').value=appliedStart;$('#endMonth').value=appliedEnd;setPeriodBounds(x.period_min||PERIOD_MIN,x.period_max||lastClosedMonth());$('#periodNote').textContent=`시작월 ${x.start_month||'—'} · 종료월 ${x.end_month||'자료 없음'} 기준 · 기본 최근 12개월 · 저장 기간 ${x.available_start||'—'} ~ ${x.available_end||'—'} · 선택 가능 ${x.period_min||PERIOD_MIN} ~ ${x.period_max||lastClosedMonth()} · 빈 달은 0이 아닙니다.`;const s=x.summary||{},m=s.metrics||{},d=s.derived||{},idx=s.indexes||{},r=s.region||{};$('#activeRegion').textContent=r.full_name||r.name||id;$('#chatRegion').textContent=r.full_name||r.name||id;const charts=x.charts||[],labels=charts[0]?.labels||[];const trend=charts[0]?.datasets?.[0]?.data||[],numeric=trend.filter(v=>typeof v==='number');const tr=numeric.length<2?'자료 부족':numeric.at(-1)>numeric[0]?'증가':numeric.at(-1)<numeric[0]?'감소':'유지';$('#periodInfo').innerHTML=[['분석 기간',s.period|| (labels.length?labels[0]+' ~ '+labels.at(-1):'—')],['월별 자료 개수',s.count??labels.length],['관측 인구 추세',tr]].map(([k,v])=>`<div>${esc(k)}<b>${esc(v)}</b></div>`).join('');renderBenchmarks(x.benchmarks||[],x.start_month,x.end_month);$('#benchmarkNote').textContent=`비교월 ${x.benchmark_month||'—'} · 창원 평균은 유효 법정읍·면·동 값의 산술평균입니다. 창원시 전체 비율·총계와 다릅니다. 결측값은 제외합니다. 0은 실제 집계값이고 —는 자료 없음입니다. 법정동은 행정동·생활권과 범위가 다를 수 있어요. 작은 인구에서 나온 0%·100%를 지역 전체의 특성으로 단정하지 마세요. 100명·세대 미만 안내는 화면 해석을 돕는 기준이며 통계 제외 기준이 아닙니다.`;dashboardCharts=x.metric_charts||{};questionPool=x.question_candidates||[];questionHistory=[];showQuestions();renderMetricTabs(x.metric_definitions||[]);const im=s.index_meta||{};$('#indexMethodology').textContent=`창원시 내 상대평가 · 비교월 ${im.comparison_month||'—'} · 모집단 ${im.comparison_region_count??'—'}곳 · 프로젝트 정의 지수(공식 통계 아님)`;const f=s.freshness||{};$('#freshness').textContent=`기준 ${f.source_as_of||'—'} · 수집 ${f.fetched_at||'—'} · 메타데이터 분류 ${f.data_confidence||'—'}`;const c=x.comparison||{},tags=[];[['유사 지역',c.peers],['무작위 비교 지역',c.seeded_random]].forEach(([label,rows])=>(rows||[]).forEach(r=>tags.push(`<span><b>${esc(label)}</b> ${esc(r.full_name||r.name)}</span>`)));$('#comparisonInfo').innerHTML='<b>자동 비교군'+(c.topic_label?' · '+esc(c.topic_label):'')+'</b><div class="comparison-tags">'+tags.join('')+'</div><small>유사 지역은 질문 주제에 맞춰 선택해요. 같은 지역·월·질문은 같은 비교군을 보여줘요.'+(c.topic_data_unavailable?' 해당 주제 자료가 부족해 종합 지표로 비교했어요.':'')+'</small>';showMetric();}
let pendingChat=null;
async function send(message,retry=false){
 if($('#sendBtn').disabled)return;
 const target=$('#analysisTarget').value,version=selectionVersion;
 const draft={message,conversation_id:conversationId,region_id:activeRegionId,answer_mode:$('#answerMode').value,analysis_target:target};
 const signature=JSON.stringify(draft);
 if(!pendingChat||(!retry&&pendingChat.signature!==signature))pendingChat={signature,body:{...draft,request_id:crypto.randomUUID()},message};
 const request=pendingChat;
 if(!retry)addMsg('user',message);
 $('#chatInput').value='';$('#loading').hidden=false;$('#sendBtn').disabled=true;
 try{
  const x=await api('/api/chat',{method:'POST',body:JSON.stringify(request.body)});
  if(x.conversation_id)conversationId=x.conversation_id;
  pendingChat=null;addMsg('assistant',x.answer);$('#toolLog').textContent=JSON.stringify(x.tools_used||[],null,2);
  try{
   if(x.resolved_region&&version===selectionVersion){if(!regions.some(r=>r.id===x.resolved_region.id))regions.push(x.resolved_region);chooseRegion(x.resolved_region.id,'채팅에서 선택됨');comparisonQuestion=message;await loadSummary();}
   if(target==='personal'&&version===selectionVersion)$('#chatRegion').textContent='내 기록 분석';
   await loadConversations();
  }catch(e){$('#toolLog').textContent+='\n답변은 완료됐지만 부가 화면 갱신에 실패했어요. '+e.message;}
 }catch(e){
  addMsg('assistant','요청 오류: '+e.message);
  if(!$('#chatInput').value.trim())$('#chatInput').value=request.message;
  const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent='같은 질문 다시 시도';
  button.onclick=()=>{if(pendingChat!==request)return;send(request.message,true)};
  $('#messages').lastElementChild.appendChild(button);
 }finally{$('#loading').hidden=true;$('#sendBtn').disabled=false;}
}
$('#chatForm').onsubmit=e=>{e.preventDefault();const t=$('#chatInput').value.trim();if(t)send(t)};$('#chatInput').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#chatForm').requestSubmit()}};
let questionPool=[],questionHistory=[];
function shuffled(list){const out=[...list];for(let i=out.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[out[i],out[j]]=[out[j],out[i]]}return out;}
function friendlyQuestion(q){
 const topic=q.label.replace(/ (현황|비교|해석|추세|증감)$/,'');
 const intent=q.label.split(' ').at(-1),focus=({현황:'요즘 어떤 모습인지',비교:'다른 지역과 비교하면 어떤 특징이 있는지',해석:'우리 생활과 어떤 관련이 있는지',추세:'그동안 어떻게 달라졌는지',증감:'변화가 눈에 띄는지'})[intent]||'어떤 특징이 있는지';
 return `${topic}에 대해 궁금해요. 어떤 동네인지 먼저 소개하고, ${focus} 관련 자료를 함께 살펴보며 알기 쉽게 알려줘. 생활에 도움이 되는 특징과 최근 지역 소식도 함께 소개해줘.`;
}
function showQuestions(){
 const groups=[['주민등록 인구','주민등록 세대 수','세대당 인구','남성 인구','여성 인구'],['청년 인구(20~39세)','20세 미만 인구','60세 이상 인구','0~9세 인구','10~19세 인구'],['1인세대 수','청년 1인세대','60세 이상 1인세대','남성 1인세대','여성 1인세대'],['매매 거래량','아파트 ㎡당 가격','전세 거래량','월세 거래량','월세 중앙값'],['업소 수','카페·커피 업소 수','음식점 업소 수','편의점 업소 수','의료·건강 관련 업소 수','교육 관련 업소 수','공동주택 단지 수','건축물 수','30년 이상 건축물 수']];const fallback=groups.flatMap((g,i)=>g.flatMap(label=>['현황','비교','해석'].map(intent=>({id:label+intent,domain:String(i),label:label+' '+intent,prompt:label+'의 저장자료 유무와 실제 기준일을 먼저 확인하고 '+intent+'해줘. 자료가 없으면 추정하지 말고 알려줘. 현황 자료로 과거 추세를 추정하지 마.'}))));
 const pool=questionPool.length?questionPool:fallback;let available=shuffled(pool.filter(q=>!questionHistory.includes(q.id)));if(available.length<Math.min(5,pool.length)){questionHistory=questionHistory.slice(-5);available=shuffled(pool.filter(q=>!questionHistory.includes(q.id)));if(available.length<5)available=shuffled(pool)}
 const picks=[],domains=new Set();for(const q of available){if(!domains.has(q.domain)){picks.push(q);domains.add(q.domain)}if(picks.length===5)break}for(const q of available){if(picks.length===5)break;if(!picks.includes(q))picks.push(q)}
 questionHistory=[...questionHistory,...picks.map(q=>q.id)].slice(-25);
 $('#questionChips').innerHTML=picks.map((q,i)=>`<button type="button" data-question="${i}" title="${esc(q.domain+' · '+friendlyQuestion(q))}">${esc(q.label)}</button>`).join('');
 $('#questionChips').querySelectorAll('button').forEach(b=>b.onclick=()=>{const q=picks[Number(b.dataset.question)],region=regions.find(r=>r.id===activeRegionId);$('#analysisTarget').value='region';$('#chatInput').value=`${region?.full_name||region?.name||'[궁금한 법정읍·면·동 이름]'}의 ${friendlyQuestion(q)}`;$('#chatInput').focus()});
 $('#shuffleQuestions').title=questionPool.length?`선택 지역·기간에 유효한 질문 ${questionPool.length}개 중 분야를 나누어 표시합니다.`:'지역을 조회하면 저장자료에 맞는 질문을 제안합니다.';
}
$('#shuffleQuestions').onclick=showQuestions;showQuestions();
function metricFormat(value,key){return value==null?'—':key==='sale_price_per_m2'?Math.trunc(value).toLocaleString('ko-KR'):key.endsWith('_share')&&value>0&&value<0.005?'<0.01':fmt(value);}
function basisText(b){if(!b)return '';return b.denominator!=null?`${b.numerator_label} ${fmt(b.numerator)}${b.unit} / ${b.denominator_label} ${fmt(b.denominator)}${b.unit}`:`주민등록 ${fmt(b.count)}${b.unit}`;}
function renderBenchmarks(rows,startMonth,endMonth){
 evidenceItems=[];closeIndexDetail();
 const isIndex=k=>Boolean(INDEX_GUIDES[k]);
 const score=(v,k,e,label)=>isIndex(k)?evidenceButton(v,k,e,label):`<b>${esc(metricFormat(v,k))}</b>`;
 const extreme=(x,key)=>{const regs=x?.regions||[];return `<span class="extreme-names">${esc(regs.slice(0,2).map(r=>r.name).join(' · ')||'자료 없음')}${regs.length>2?' 외 '+(regs.length-2)+'곳':''}</span>${score(x?.value,key,regs[0]?.index_evidence,regs[0]?.name||'')}<small class="value-basis">${esc(basisText(regs[0]?.basis))}</small>${regs.length>1?`<details class="value-basis"><summary>지역별 근거 (${regs.length}곳)</summary>${regs.map(r=>`<div>${esc(r.name)}${score(x.value,key,r.index_evidence,r.name)}${esc(basisText(r.basis))}</div>`).join('')}</details>`:''}`;};
 const delta=r=>{const c=r.change;if(!c)return '시작월 비교 준비 중';if(c.delta==null)return `<span>비교 불가</span><small>${esc(c.note)}</small>`;const sign=c.delta>0?'+':'';return `<b>${sign}${esc(fmt(c.delta))}${esc(c.unit)}</b>${c.percent!=null?`<small>(${c.percent>0?'+':''}${esc(fmt(c.percent))}%)</small>`:''}${c.note?`<small>${esc(c.note)}</small>`:''}`;};
 $('#summary').innerHTML=rows.length?`<table class="benchmark-table"><thead><tr><th>지표</th><th>선택 지역<br><small>시작월 · 종료월 · 증감</small></th><th>창원 내 최대<small>${esc(endMonth)}</small></th><th>창원 평균<small>${esc(endMonth)}</small></th><th>창원 내 최소<small>${esc(endMonth)}</small></th></tr></thead><tbody>${rows.map(r=>`<tr><th scope="row">${isIndex(r.key)?`<a class="index-link" href="#indices/${r.key}">${esc(r.label)} ↗</a>`:esc(r.label)}<small>종료월 유효 자료 ${r.valid_count}/${r.region_count}곳</small></th><td data-label="선택 지역" class="selected-value"><div class="period-value"><small>시작 ${esc(startMonth)}</small>${score(r.start_value,r.key,r.start_evidence,$('#activeRegion').textContent)}<small class="value-basis">${esc(basisText(r.start_basis))}</small></div><div class="period-value"><small>종료 ${esc(endMonth)}</small>${score(r.selected,r.key,r.end_evidence,$('#activeRegion').textContent)}<small class="value-basis">${esc(basisText(r.selected_basis))}</small></div><div class="period-change"><small>증감</small>${delta(r)}</div></td><td data-label="창원 내 최대 (종료월)">${extreme(r.maximum,r.key)}</td><td data-label="창원 평균 (종료월)"><b>${esc(metricFormat(r.mean,r.key))}</b><small class="value-basis">유효 ${r.valid_count}곳의 단순평균</small></td><td data-label="창원 내 최소 (종료월)">${extreme(r.minimum,r.key)}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">저장된 비교 자료가 없습니다.</p>';
 bindIndexDetails();
}
const TREND_METRICS=new Set(['population_total','young_population_share','single_household_share','households','age_20_39','single_households','age_60_plus','under_20']);
function renderMetricTabs(defs){defs=defs.filter(d=>TREND_METRICS.has(d.key));if(!defs.some(d=>d.key===activeMetric))activeMetric=defs[0]?.key||'population_total';$('#metricTabs').innerHTML=defs.map(d=>`<button type="button" data-metric="${esc(d.key)}" aria-pressed="${activeMetric===d.key}">${esc(d.tab)}</button>`).join('');$('#metricTabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{activeMetric=b.dataset.metric;showMetric()});}
function showMetric(){const spec=TREND_METRICS.has(activeMetric)?dashboardCharts[activeMetric]:null;$('#metricTabs').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.metric===activeMetric)));const sparse=spec?.datasets?.some(s=>s.data.filter(v=>typeof v==='number'&&Number.isFinite(v)).length<2);$('#chartStatus').textContent=(sparse?'일부 지역은 시계열 자료가 부족합니다. ':'')+'양쪽 값은 선택한 시작월·종료월 기준이며 —는 자료 없음, 0은 실제 집계값입니다. 빈 구간은 연결하지 않습니다.';drawCharts(spec?[spec]:[]);}
let personalMetrics=[];
function populateDataRegions(){const select=$('#dataRegion'),selected=select.value;select.innerHTML='<option value="">지역 선택</option>'+regions.filter(r=>r.id.startsWith('4812')).map(r=>`<option value="${esc(r.id)}">${esc(r.full_name||r.name)}</option>`).join('');select.value=selected;}
async function loadPersonalMetrics(){personalMetrics=await api('/api/data/metrics');$('#dataMetric').innerHTML=personalMetrics.map(m=>`<option value="${esc(m.key)}">${esc(m.label)} (${esc(m.unit)})</option>`).join('');updateDataUnit();}
function updateDataUnit(){const m=personalMetrics.find(x=>x.key===$('#dataMetric').value);$('#dataUnit').textContent=m?.unit||'';$('#dataValue').min=m?.key==='sale_price_yoy_pct'?'':0;$('#dataValue').max=m?.unit==='%'&&m?.key!=='sale_price_yoy_pct'||m?.unit==='점'?100:'';$('#dataValue').step=m?.key==='population_total'?1:'any';}
$('#dataMetric').onchange=updateDataUnit;
function selectRecord(r){editingId=r.id;$('#dataDate').value=r.date;$('#dataRegion').value=r.region_id||'';$('#dataMetric').value=r.metric_type||'';$('#dataValue').value=r.value;$('#dataMemo').value=r.memo||'';updateDataUnit();$('#dataUpdate').disabled=false;$('#dataDelete').disabled=false;$('#dataCancel').hidden=false;$('#dataStatus').textContent='선택한 기록을 수정하거나 삭제할 수 있어요. 새 기록 저장은 별도 기록을 추가합니다.';}
async function loadData(){currentRows=await api('/api/data');$('#dataList').innerHTML=currentRows.length?currentRows.map(r=>`<div class="row"><span>${esc(r.date)} · ${esc(r.region_name||'기존 기록')}<br><b>${esc(r.metric_label||'사용자 기록')} ${esc(fmt(r.value))} ${esc(r.unit||'')}</b><br>${esc(r.memo||'')}</span><button data-edit="${esc(r.id)}" class="secondary">선택</button></div>`).join(''):'<p class="muted">본인의 기록이 아직 없어요. 첫 기록을 추가해 보세요.</p>';document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>selectRecord(currentRows.find(x=>x.id===b.dataset.edit)));}
function cancelEdit(){editingId=null;$('#dataForm').reset();$('#dataDate').value=new Date().toLocaleDateString('sv-SE');$('#dataUpdate').disabled=true;$('#dataDelete').disabled=true;$('#dataCancel').hidden=true;updateDataUnit();}
async function saveRecord(update){if(!$('#dataForm').reportValidity())return;if(update&&!editingId)return;const buttons=[$('#dataSave'),$('#dataUpdate'),$('#dataDelete')];buttons.forEach(b=>b.disabled=true);$('#dataStatus').textContent='기록을 저장하고 있어요…';try{await api('/api/data'+(update?'/'+editingId:''),{method:update?'PUT':'POST',body:JSON.stringify({date:$('#dataDate').value,region_id:$('#dataRegion').value,metric_type:$('#dataMetric').value,value:Number($('#dataValue').value),memo:$('#dataMemo').value})});cancelEdit();$('#dataStatus').textContent=update?'수정 내용이 저장됐어요.':'새 개인 기록이 저장됐어요.';await loadData()}catch(e){$('#dataStatus').textContent='저장 오류: '+e.message}finally{$('#dataSave').disabled=false;$('#dataUpdate').disabled=!editingId;$('#dataDelete').disabled=!editingId}}
$('#dataCancel').onclick=cancelEdit;$('#dataForm').onsubmit=e=>{e.preventDefault();saveRecord(false)};$('#dataUpdate').onclick=()=>saveRecord(true);
$('#dataDelete').onclick=async()=>{if(!editingId||!confirm('선택한 본인 기록을 삭제할까요?'))return;try{await api('/api/data/'+editingId,{method:'DELETE'});cancelEdit();$('#dataStatus').textContent='기록이 삭제됐어요.';await loadData()}catch(e){$('#dataStatus').textContent='삭제 오류: '+e.message}};
$('#analyzeRecords').onclick=()=>{$('#analysisTarget').value='personal';$('#chatInput').value='내 기록의 기간, 개수, 평균·최대·최소, 최근 추세를 분석하고 새로운 관찰과 후속 질문을 제안해줘.';$('#chatRegion').textContent='내 기록 분석';$('#chatForm').scrollIntoView({block:'center'});$('#chatInput').focus()};
async function loadConversations(){const rows=await api('/api/conversations');$('#conversationList').innerHTML=rows.length?rows.map(r=>`<div class="row"><span>${esc(r.title)}</span><div class="row-actions"><button class="secondary" data-open="${esc(r.id)}">불러오기</button><button class="danger" data-cdel="${esc(r.id)}">삭제</button></div></div>`).join(''):'<p class="muted">저장된 대화가 없습니다.</p>';document.querySelectorAll('[data-open]').forEach(b=>b.onclick=async()=>{try{const c=await api('/api/conversations/'+b.dataset.open);conversationId=c.id;$('#messages').innerHTML='';(c.messages||[]).filter(m=>['user','assistant'].includes(m.role)).forEach(m=>addMsg(m.role,m.content));$('#analysisTarget').value=c.analysis_target||'region';if(c.analysis_target!=='personal'&&c.region_id&&regions.some(r=>r.id===c.region_id)){chooseRegion(c.region_id,'불러온 대화');comparisonQuestion=c.comparison_question||(c.messages||[]).filter(m=>m.role==='user').at(-1)?.content||'';await loadSummary()}else{clearOverview(c.analysis_target==='personal'?'내 기록 대화예요. 지역을 선택하면 지역 자료를 볼 수 있어요.':'이 대화의 대상 지역을 확인할 수 없어요. 법정읍·면·동을 다시 선택해 주세요.');$('#analysisTarget').value=c.analysis_target||'region'}$('#conversationPreview').textContent='불러온 대화: '+c.title;$('#toolLog').textContent=JSON.stringify(c.last_tools_used||[],null,2);$('#messages').scrollIntoView({block:'start'})}catch(e){$('#conversationPreview').textContent=e.message}});document.querySelectorAll('[data-cdel]').forEach(b=>b.onclick=async()=>{if(!confirm('대화 기록을 삭제할까요?'))return;try{await api('/api/conversations/'+b.dataset.cdel,{method:'DELETE'});if(conversationId===b.dataset.cdel)conversationId=null;await loadConversations()}catch(e){$('#conversationPreview').textContent=e.message}})}
$('#newChat').onclick=()=>{conversationId=null;pendingChat=null;clearOverview();$('#messages').innerHTML='';$('#toolLog').textContent='새 대화를 시작합니다.';$('#chatInput').focus()};
async function loadSummary(keepPeriod=false){if(!activeRegionId)return;const version=++selectionVersion;setStatus('#summaryStatus','지역 자료를 불러오고 있어요…','busy');setStatus('#regionStatus','조회 중 · 잠시만 기다려 주세요.','busy');$('.overview').setAttribute('aria-busy','true');$('#refreshBtn').disabled=true;$('#periodApply').disabled=true;$('#csvBtn').disabled=true;$('#jsonBtn').disabled=true;const timer=waitNotice('#summaryStatus','자료를 비교하고 있어요. 서버 첫 연결은 시간이 걸릴 수 있어요…');try{await fetchSummary(keepPeriod);if(version===selectionVersion){setStatus('#summaryStatus','조회가 완료되었어요. 시작월·종료월·증감과 선택 기간의 그래프를 확인해 주세요.','success');setStatus('#regionStatus',`${$('#activeRegion').textContent} · 조회 완료`,'success')}}catch(e){if(version===selectionVersion){setStatus('#summaryStatus','조회 오류 · '+e.message+' 지역 살펴보기로 다시 시도해 주세요.','error');setStatus('#regionStatus','조회 오류 · '+e.message,'error')}}finally{clearTimeout(timer);if(version===selectionVersion){$('.overview').setAttribute('aria-busy','false');$('#refreshBtn').disabled=false;$('#periodApply').disabled=!activeRegionId}}}
$('#districtSelect').onchange=()=>fillRegions();
$('#regionSelect').onchange=()=>setStatus('#regionStatus','지역 살펴보기를 누르면 선택한 지역을 조회해요.');
$('#refreshBtn').onclick=()=>{const id=$('#regionSelect').value;if(!id){setStatus('#regionStatus','구와 법정읍·면·동을 먼저 선택해 주세요.','error');return}chooseRegion(id);comparisonQuestion='';loadSummary()};
$('#periodApply').onclick=()=>{const start=$('#startMonth').value,end=$('#endMonth').value;setPeriodBounds();if(!start||!end||start>end||start<PERIOD_MIN||end<PERIOD_MIN||start>lastClosedMonth()||end>lastClosedMonth()){setStatus('#summaryStatus',`조회 기간은 ${PERIOD_MIN} ~ ${lastClosedMonth()} 사이로 선택해 주세요. 시작월은 종료월보다 늦을 수 없어요.`,'error');return}loadSummary(true)};
$('#periodReset').onclick=()=>loadSummary(false);
$('#liveBtn').onclick=async()=>{if(!activeRegionId){setStatus('#liveStatus','먼저 채팅하거나 지역 살펴보기로 대상 지역을 선택해 주세요.','error');return}const b=$('#liveBtn'),rid=activeRegionId;b.disabled=true;setStatus('#liveStatus','최신 상태를 확인하고 있어요…','busy');const timer=waitNotice('#liveStatus','서버 응답을 기다리고 있어요…');try{const x=await api(`/api/analytics/regions/${rid}/live`);if(rid===activeRegionId)await loadSummary(true);const failed=(x.refresh_result||[]).some(r=>r.status==='error');setStatus('#liveStatus',failed?'확인은 완료했지만 원 API 갱신에 실패하여 저장 자료를 사용해요.':x.refreshed?'확인 완료 · 원 API 재조회 결과를 반영했어요.':'확인 완료 · 저장된 자료를 확인했어요. 새로운 자료 수집 완료를 의미하지는 않아요.','success')}catch(e){setStatus('#liveStatus','확인 오류 · '+e.message,'error')}finally{clearTimeout(timer);b.disabled=false}};
$('#sourceStatusBtn').onclick=()=>loadSourceStatus();
$('#themeBtn').onclick=()=>{document.body.classList.toggle('dark');localStorage.setItem('changwon-theme',document.body.classList.contains('dark')?'dark':'light');$('#themeBtn').textContent=document.body.classList.contains('dark')?'☀ 라이트 모드':'☾ 다크 모드'};if(localStorage.getItem('changwon-theme')==='dark')$('#themeBtn').click();
['csv','json'].forEach(f=>$('#'+f+'Btn').onclick=()=>{if(!activeRegionId)return;const q=new URLSearchParams({format:f,start_month:appliedStart,end_month:appliedEnd});location.href=`${API}/api/analytics/export/${activeRegionId}?${q}`});
setPeriodBounds();
clearOverview();
Promise.all([loadRegions(),loadPersonalMetrics()]).catch(e=>{setStatus('#regionStatus','초기 연결 오류 · '+e.message+' 새로고침으로 다시 시도해 주세요.','error');addMsg('assistant','초기 연결 오류: '+e.message+' · 잠시 후 새로고침해주세요.')});

window.reloadPrivateRecords=async()=>{await Promise.all([loadData(),loadConversations()])};
window.personalAuth.then(()=>window.reloadPrivateRecords()).catch(e=>{$('#dataStatus').textContent=e.message;$('#conversationList').textContent='인증 연결 후 본인의 대화 목록을 볼 수 있어요.'});
cancelEdit();


