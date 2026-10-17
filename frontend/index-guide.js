/* Read-only views: keep the existing main DOM, form state and conversations. */
const INDEX_GUIDES={
 vitality_index:{name:'지역활력지수',meaning:'인구·연령 구성·주택 거래·업소 밀도의 여러 신호를 함께 살펴보는 상대지수입니다.',parts:[['인구 전년 대비',35,'(당월 인구 / 전년 동월 인구 − 1) × 100'],['청년 비율',30,'20~39세 인구 / 주민등록 인구 × 100'],['아파트 매매 거래회전율',20,'당월 아파트 매매 건수 / 공동주택 세대수 × 100'],['인구 1천 명당 업소 수',15,'업소 수 / 주민등록 인구 × 1,000']],limits:'청년 비율·거래·업소 밀도가 높다고 삶의 질이 높다는 뜻은 아닙니다. 인구가 적은 법정동에서는 소수의 인원·업소 변화가 비율을 크게 바꿉니다.'},
 housing_pressure_index:{name:'주거시장압력지수',meaning:'가격 변화, 임대 거래 구성, 건축물 노후도와 거래 강도를 함께 비교하는 탐색 지수입니다.',parts:[['아파트 ㎡당 중앙가격 전년 대비',35,'(당월 중앙가격 / 전년 동월 중앙가격 − 1) × 100'],['전월세 거래량 전년 대비',20,'(당월 거래 건수 / 전년 동월 거래 건수 − 1) × 100'],['월세 거래 비율',20,'월세 거래 건수 / 전월세 거래 건수 × 100'],['30년 이상 건축물 비율',15,'30년 이상 건축물 수 / 전체 건축물 수 × 100'],['아파트 매매 거래회전율',10,'당월 아파트 매매 건수 / 공동주택 세대수 × 100']],limits:'가격 상승·월세 비중·노후도는 서로 다른 현상입니다. 높은 점수가 향후 집값 상승이나 가계 주거비 부담을 직접 뜻하지 않습니다. 거래가 적거나 거래 주택 구성이 달라지면 중앙가격도 크게 달라질 수 있습니다.'},
 living_convenience_index:{name:'생활편의지수',meaning:'주민등록 인구 대비 업소와 의료·교육 업종의 공급, 업종 구성, 공동주택 공급 대용지표를 비교합니다.',parts:[['인구 1천 명당 업소 수',30,'업소 수 / 주민등록 인구 × 1,000'],['업종 다양성',25,'−Σ(p × ln p) / ln K × 100 (p: 업종별 비중, K: 업소가 있는 업종 수; K=1이면 0)'],['인구 1천 명당 의료 업소',20,'의료 업소 수 / 주민등록 인구 × 1,000'],['인구 1천 명당 교육 업소',15,'교육 업소 수 / 주민등록 인구 × 1,000'],['공동주택 공급 대용지표',10,'공동주택 세대수 / 주민등록 세대수 × 100']],limits:'실제 이동시간·대중교통·시설 규모·서비스 품질을 측정하지 않습니다. 업종 다양성은 현재 존재하는 업종 간 분포의 균등성에 영향을 받습니다. 공동주택 세대수 비율은 생활편의를 간접적으로 나타내는 대용지표입니다.'},
 commerce_change_index:{name:'상권활력 대리지수',meaning:'현재 업소 구성과 인구 대비 업소 밀도를 이용해 상권의 특성을 간접적으로 비교합니다.',parts:[['인구 1천 명당 업소 수',30,'업소 수 / 주민등록 인구 × 1,000'],['업종 다양성',25,'−Σ(p × ln p) / ln K × 100 (K=1이면 0)'],['인구 1천 명당 음식점',20,'음식점 수 / 주민등록 인구 × 1,000'],['인구 1천 명당 카페',15,'카페 수 / 주민등록 인구 × 1,000'],['인구 1천 명당 편의점',10,'편의점 수 / 주민등록 인구 × 1,000']],limits:'매출·유동인구·개폐업을 직접 측정하지 않습니다. 주거 인구가 적은 상업지역은 밀도가 높게 나타날 수 있습니다. 과거 업소 스냅샷이 없는 달에는 지수나 증감을 제공할 수 없습니다.'}
};
let mainScroll=0,returnFocus=null;
function renderGuide(key='vitality_index'){
 const g=INDEX_GUIDES[key]||INDEX_GUIDES.vitality_index;
 $('#guideTabs').innerHTML=Object.entries(INDEX_GUIDES).map(([k,v])=>`<a class="guide-tab ${v===g?'active':''}" href="#indices/${k}" ${v===g?'aria-current="true"':''}>${v.name}</a>`).join('');
 $('#guideContent').innerHTML=`<h2 tabindex="-1" id="guideHeading">${g.name}</h2><p>${g.meaning}</p><h3>구성산식과 기본 가중치</h3><div class="guide-table-wrap"><table class="guide-table"><thead><tr><th>구성지표</th><th>가중치</th><th>원자료 계산</th></tr></thead><tbody>${g.parts.map(p=>`<tr><th>${p[0]}</th><td>${p[1]}%</td><td>${p[2]}</td></tr>`).join('')}</tbody></table></div><p class="guide-formula">원자료 → 같은 월 창원 내 백분위 점수 → 가중평균</p><p>백분위 = 100 × (해당 값보다 작은 지역 수 + 같은 값의 지역 수 × 0.5) / 유효 지역 수</p><p>지수 = Σ(유효 구성지표의 백분위 × 기본 가중치) / 유효 구성지표의 기본 가중치 합계. 구성지표별 백분위와 최종 지수는 소수 둘째 자리로 반올림합니다.</p><p>예: 지역활력에서 거래회전율이 빠지면 나머지 기본 가중치 합계는 80%이며, 실제 적용 비중은 43.75%·37.5%·18.75%가 됩니다. 원자료 자체에 가중치를 곱하는 방식이 아닙니다.</p><div class="guide-warning"><h3>의미와 해석의 한계</h3><p>${g.limits}</p></div><h3>공통 해석 원칙</h3><ul><li>공식 통계가 아닌 프로젝트 정의 지수입니다. 높은 점수는 해당 구성지표의 상대적 위치가 높다는 뜻이며, 살기 좋은 순위나 투자 전망이 아닙니다.</li><li>결측 구성항목은 제외하고 가중치를 재조정합니다. 유효 구성항목이 2개 미만이면 미산출합니다. 0과 자료 없음(—)을 구분합니다.</li><li>월별 비교군과 구성항목이 달라질 수 있어 점수 증감을 절대적인 개선 정도로 해석하면 안 됩니다.</li><li>법정동은 행정동·생활권과 다를 수 있습니다. 작은 분모·적은 거래 건수·자료별 기준시점을 함께 확인하세요.</li><li>상권·건축물·공동주택은 스냅샷 자료를 포함합니다. 최신 자료를 과거 값으로 복제하지 않습니다.</li></ul><p class="muted">방법 버전 3.2 · 현재 계산식 기준. 표의 수치를 누르면 해당 지역·월의 구성자료와 재현 확인 상태를 볼 수 있습니다.</p>`;
}
function showSection(){
 const isGuide=location.hash.startsWith('#indices');
 if(isGuide&&!$('#mainView').hidden){mainScroll=window.scrollY;returnFocus=document.activeElement;}
 $('#mainView').hidden=isGuide;$('#indexGuide').hidden=!isGuide;
 $('#navMain').setAttribute('aria-current',isGuide?'false':'page');$('#navGuide').setAttribute('aria-current',isGuide?'page':'false');
 if(isGuide){renderGuide(location.hash.split('/')[1]);window.scrollTo(0,0);$('#guideHeading').focus({preventScroll:true});}
 else {window.scrollTo(0,mainScroll);if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});}
 window.closeIndexDetail?.();
}
window.addEventListener('hashchange',showSection);
renderGuide();showSection();
let evidenceItems=[],detailAnchor=null,pinned=false,closeTimer;
function evidenceButton(v,key,detail,label){
 if(v==null||!detail)return `<b>${esc(metricFormat(v,key))}</b>`;
 const id=evidenceItems.push({...detail,region_label:label})-1;
 return `<button type="button" class="index-value" data-evidence="${id}" aria-haspopup="dialog" aria-expanded="false" aria-controls="indexDetail" aria-label="${esc(label)} ${esc(INDEX_GUIDES[key]?.name||key)} ${esc(detail.month)} ${esc(metricFormat(v,key))}점 계산 근거">${esc(metricFormat(v,key))} <span aria-hidden="true">ⓘ</span></button>`;
}
function closeIndexDetail(){clearTimeout(closeTimer);$('#indexDetail').hidden=true;detailAnchor?.setAttribute('aria-expanded','false');pinned=false;detailAnchor=null;}
window.closeIndexDetail=closeIndexDetail;
function openIndexDetail(button,lock=false){
 clearTimeout(closeTimer);if(pinned&&detailAnchor!==button&&!lock)return;
 const x=evidenceItems[Number(button.dataset.evidence)];if(!x)return;
 detailAnchor?.setAttribute('aria-expanded','false');detailAnchor=button;pinned=lock;button.setAttribute('aria-expanded','true');
 const num=v=>v==null?'—':fmt(v),pop=x.raw?.find(r=>r.key==='population_total')?.value;
 $('#indexDetailBody').innerHTML=`<h3 id="detailHeading">${esc(INDEX_GUIDES[x.key]?.name||x.key)}</h3><p>${esc(x.region_label)} · ${esc(x.month)} · ${num(x.stored_score)}점</p><p class="detail-badge">구성 ${x.available_count}/${x.total_count}개 · 방법 ${esc(x.method_version||'미확인')}</p><dl class="detail-raw">${(x.raw||[]).map(r=>`<div><dt>${esc(r.label)}</dt><dd>${num(r.value)}</dd></div>`).join('')}</dl>${pop>0&&pop<1000?`<p class="guide-warning">주민등록 인구 ${num(pop)}명. 분모 고정 시 청년 1명 차이는 약 ${num(100/pop)}%p입니다.</p>`:''}<p class="muted">${esc(x.notice)}</p>${x.components.map(c=>`<section class="detail-component"><strong>${esc(c.label)}: ${num(c.value)}${esc(c.unit)}</strong>${c.numerator_label?`<small>${esc(c.numerator_label)} ${num(c.numerator)}${c.denominator_label?' / '+esc(c.denominator_label)+' '+num(c.denominator):''}</small>`:''}<small>기본 ${num(c.base_weight*100)}% · ${x.verified?'적용':'현재 구성 기준'} ${c.effective_weight==null?'제외':num(c.effective_weight*100)+'%'} · 유효 ${c.valid_regions}곳</small><small>백분위 ${num(c.percentile)} · 기여 ${num(c.contribution)}점</small><small>자료 기준 ${esc(c.source_as_of||'미기록')} · 수집 ${esc(c.fetched_at||'미기록')}${c.source_status?' · '+esc(c.source_status):''}</small></section>`).join('')}<a href="#indices/${esc(x.key)}">산식·의의·한계 자세히 보기 →</a>`;
 const panel=$('#indexDetail');panel.hidden=false;const r=button.getBoundingClientRect(),width=Math.min(440,window.innerWidth-24);panel.style.width=width+'px';panel.style.left=Math.max(12,Math.min(r.left,window.innerWidth-width-12))+'px';panel.style.top=Math.max(12,Math.min(r.bottom+6,window.innerHeight-panel.offsetHeight-12))+'px';
}
function bindIndexDetails(){
 document.querySelectorAll('[data-evidence]').forEach(b=>{b.onmouseenter=()=>openIndexDetail(b);b.onfocus=()=>openIndexDetail(b);b.onmouseleave=()=>{if(!pinned)closeTimer=setTimeout(closeIndexDetail,220)};b.onclick=()=>{openIndexDetail(b,true);$('#closeIndexDetail').focus();};});
}
$('#indexDetail').onmouseenter=()=>clearTimeout(closeTimer);
$('#indexDetail').onmouseleave=()=>{if(!pinned)closeTimer=setTimeout(closeIndexDetail,220)};
$('#indexDetail').onfocusin=()=>{pinned=true;clearTimeout(closeTimer)};
$('#closeIndexDetail').onclick=()=>{const b=detailAnchor;closeIndexDetail();b?.focus();closeIndexDetail();};
$('#indexDetail').onfocusout=()=>setTimeout(()=>{if(!$('#indexDetail').contains(document.activeElement)&&document.activeElement!==detailAnchor)closeIndexDetail()},0);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#indexDetail').hidden){const b=detailAnchor;closeIndexDetail();b?.focus();closeIndexDetail();}});
 document.addEventListener('click',e=>{if(!e.target.closest('#indexDetail,[data-evidence]'))closeIndexDetail()});
 window.addEventListener('resize',closeIndexDetail);

document.addEventListener('focusin',e=>{if(detailAnchor&&!e.target.closest('#indexDetail,[data-evidence]'))closeIndexDetail()});
