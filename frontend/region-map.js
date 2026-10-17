/* Versioned legal-dong reference geometry. Optional OSM tiles are requested only for the visible viewport. */
(() => {
  'use strict';
  const colors = ['#008f9e', '#4778ed', '#ad72ce', '#e59149'];
  const ns = 'http://www.w3.org/2000/svg';
  const codeOf = r => String(r?.bjd_code || r?.id || '');
  function selection(region, comparison = {}) {
    const seen = new Set();
    return [[region, '선택 지역'], ...(comparison.peers || []).slice(0, 2).map((r, i) => [r, `유사 지역 ${i + 1}`]), ...(comparison.seeded_random || []).slice(0, 1).map(r => [r, '무작위 비교'])]
      .filter(([r]) => r && codeOf(r) && !seen.has(codeOf(r)) && seen.add(codeOf(r)))
      .map(([r, role], i) => ({code: codeOf(r), name: r.full_name || r.name || codeOf(r), role, color: colors[i]}));
  }
  // Web Mercator (degree-scaled): identical projection to XYZ background tiles.
  const project = ([lon, lat]) => [lon, -Math.log(Math.tan(Math.PI / 4 + Math.max(-85.05112878, Math.min(85.05112878, lat)) * Math.PI / 360)) * 180 / Math.PI];
  function visibleTiles(b, pixels, maxZoom = 19) {
    const z = Math.max(0, Math.min(maxZoom, Math.floor(Math.log2(360 * Math.max(256, pixels) / (256 * b[2])))));
    const n = 2 ** z, span = 360 / n, tiles = [];
    const left = Math.max(0, Math.floor((b[0] + 180) / span));
    const right = Math.min(n - 1, Math.floor((b[0] + b[2] + 180) / span));
    const top = Math.max(0, Math.floor((b[1] + 180) / span));
    const bottom = Math.min(n - 1, Math.floor((b[1] + b[3] + 180) / span));
    for (let x = left; x <= right; x++) for (let y = top; y <= bottom; y++) tiles.push({z, x, y, left: x * span - 180, top: y * span - 180, span});
    return tiles;
  }
  function rings(g) { return g.type === 'Polygon' ? g.coordinates : g.coordinates.flat(); }
  function bounds(features) {
    const points = features.flatMap(f => rings(f.geometry).flat().map(project));
    return points.length ? [Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1])), Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))] : null;
  }
  function path(g) { return rings(g).map(r => r.map((p, i) => `${i ? 'L' : 'M'}${project(p).join(' ')}`).join(' ') + 'Z').join(' '); }
  // Export pure geometry/selection helpers for contract tests without booting the page.
  if (typeof module !== 'undefined') module.exports = {selection, bounds, path, project, visibleTiles};
  if (typeof document === 'undefined') return;
  const card = document.getElementById('regionMapCard');
  if (!card) return;
  const svg = document.getElementById('regionMapSvg');
  const status = document.getElementById('regionMapStatus');
  const legend = document.getElementById('regionMapLegend');
  const detail = document.getElementById('regionMapDetail');
  const note = document.getElementById('regionMapNote');
  let data, pending, selected = [], generation = 0, box, fullBox, drag, moved = false;
  const shapeNodes = new Map();
  let background = 'none', tileTimer, tileGroup;
  const tileNodes = new Map();
  const backgroundSelect = document.getElementById('mapBackground');
  const tileStatus = document.getElementById('mapBackgroundStatus');
  const attribution = document.getElementById('mapAttribution');
  function queueTiles() { clearTimeout(tileTimer); tileTimer = setTimeout(renderTiles, 160); }
  const setBox = b => { box = b; svg.setAttribute('viewBox', b.join(' ')); queueTiles(); };
  function renderTiles() {
    if (!tileGroup || !box || card.hidden) return;
    if (background === 'none') { tileGroup.replaceChildren(); tileNodes.clear(); return; }
    const pixels = Math.min(svg.clientWidth || 600, (svg.clientHeight || 350) * box[2] / box[3]);
    const tiles = visibleTiles(box, pixels, background === 'terrain' ? 17 : 19);
    const keep = new Set();
    for (const t of tiles) {
      const key = `${t.z}/${t.x}/${t.y}`; keep.add(key);
      if (tileNodes.has(key)) continue;
      const el = document.createElementNS(ns, 'image');
      el.setAttribute('x', t.left); el.setAttribute('y', t.top);
      el.setAttribute('width', t.span); el.setAttribute('height', t.span);
      el.setAttribute('preserveAspectRatio', 'none');
      el.setAttribute('pointer-events', 'none');
      el.addEventListener('error', () => {
        if (background !== 'none' && tileNodes.get(key) === el) tileStatus.textContent = '일부 배경지도를 불러오지 못했어요. 경계만 보기로 전환하거나 잠시 후 다시 선택해 주세요.';
      });
      // Browser default caching and Referer are retained; no proxy, prefetch or offline download.
      el.setAttribute('href', background === 'terrain' ? `https://a.tile.opentopomap.org/${key}.png` : `https://tile.openstreetmap.org/${key}.png`);
      tileNodes.set(key, el); tileGroup.appendChild(el);
    }
    for (const [key, el] of tileNodes) if (!keep.has(key)) { el.remove(); tileNodes.delete(key); }
  }
  backgroundSelect.onchange = () => {
    background = backgroundSelect.value;
    if (tileGroup) tileGroup.replaceChildren(); tileNodes.clear();
    svg.classList.toggle('with-basemap', background !== 'none');
    attribution.hidden = background === 'none';
    attribution.innerHTML = background === 'terrain' ? '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors, SRTM | © <a href="https://opentopomap.org" target="_blank" rel="noopener">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC-BY-SA</a>)' : '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors · <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noopener">지도 오류 제보</a>';
    tileStatus.textContent = background === 'none' ? '' : (background === 'terrain' ? '지형·등고선은 OpenTopoMap 제공 범위에 따라 표시됩니다. ' : '도로·건물은 OpenStreetMap 등록 범위에 따라 표시됩니다. ') + '경계 기준일과 배경지도 갱신시점은 다릅니다.';
    queueTiles();
  };
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(queueTiles).observe(svg);
  function fit(features) {
    const b = bounds(features); if (!b) return;
    const w = Math.max(b[2] - b[0], .002), h = Math.max(b[3] - b[1], .002);
    const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
    const width = Math.max(w, h * 1.35) * 1.16, height = Math.max(h, w / 1.35) * 1.16;
    setBox([cx - width / 2, cy - height / 2, width, height]);
  }
  function zoom(factor) {
    if (!box || !fullBox) return;
    const width = Math.min(fullBox[2] * 1.3, Math.max(fullBox[2] / 500, box[2] * factor));
    const height = width * box[3] / box[2];
    setBox([box[0] + (box[2] - width) / 2, box[1] + (box[3] - height) / 2, width, height]);
  }
  const featureFor = code => data?.features.find(f => f.properties.code === code);
  function describe(code) {
    const f = featureFor(code); if (!f) return;
    const s = selected.find(s => s.code === code);
    detail.textContent = `${f.properties.name}${s ? ' · ' + s.role : ''} · 경계 도형 기준 약 ${f.properties.area_km2.toLocaleString('ko-KR', {maximumFractionDigits: 2})} km²`;
  }
  async function getData() {
    if (data) return data;
    if (!pending) pending = (async () => {
      const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch('data/changwon-legal-boundaries.json', {signal: controller.signal});
        if (!response.ok) throw new Error('경계 파일을 불러오지 못했습니다.');
        const result = await response.json();
        if (result.type !== 'FeatureCollection' || !result.features?.length || !result.metadata?.boundary_date) throw new Error('경계 파일 형식 오류');
        data = result; return data;
      } finally { clearTimeout(timeout); pending = null; }
    })();
    return pending;
  }
  function draw() {
    svg.replaceChildren(); shapeNodes.clear(); tileNodes.clear();
    tileGroup = document.createElementNS(ns, 'g'); svg.appendChild(tileGroup);
    for (const f of data.features) {
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', path(f.geometry)); p.setAttribute('fill-rule', 'evenodd');
      p.setAttribute('vector-effect', 'non-scaling-stroke');
      p.setAttribute('class', 'legal-boundary');
      p.dataset.code = f.properties.code;
      const title = document.createElementNS(ns, 'title');
      title.textContent = `${f.properties.name} · 참고 면적 약 ${f.properties.area_km2} km²`;
      p.appendChild(title); svg.appendChild(p); shapeNodes.set(f.properties.code, p);
      p.addEventListener('pointerenter', () => describe(f.properties.code));
      p.addEventListener('click', () => { if (!moved) describe(f.properties.code); });
    }
    fit(data.features); fullBox = [...box];
  }
  function highlight() {
    for (const p of shapeNodes.values()) { p.style.removeProperty('--region-color'); p.classList.remove('selected-boundary'); }
    legend.replaceChildren();
    let missing = 0;
    for (const s of selected) {
      const f = featureFor(s.code), p = shapeNodes.get(s.code);
      if (p) { p.style.setProperty('--region-color', s.color); p.classList.add('selected-boundary'); svg.appendChild(p); } else missing++;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'map-region secondary';
      button.style.setProperty('--region-color', s.color);
      const name = document.createElement('strong'), value = document.createElement('span');
      name.textContent = `${s.role} · ${s.name.replace(/^경상남도 창원시 /, '')}`;
      value.textContent = f ? `약 ${f.properties.area_km2.toLocaleString('ko-KR', {maximumFractionDigits: 2})} km²` : '경계 자료 없음';
      button.append(name, value); button.disabled = !f;
      button.onclick = () => { fit([f]); describe(s.code); };
      legend.appendChild(button);
    }
    status.textContent = missing ? `${selected.length}개 비교 지역 중 ${missing}곳은 경계 자료가 없습니다. 통계는 그대로 확인할 수 있습니다.` : `${selected.length}개 지역의 위치와 경계 · 지역 이름을 누르면 확대됩니다.`;
    fit(data.features); if (selected[0]) describe(selected[0].code);
  }
  window.RegionMap = {
    clear() { generation++; clearTimeout(tileTimer); selected = []; card.hidden = true; legend.replaceChildren(); detail.textContent = ''; },
    async update(region, comparison, month) {
      const version = ++generation;
      selected = selection(region, comparison);
      if (!selected.length) return this.clear();
      card.hidden = false; status.textContent = '법정읍·면·동 경계를 불러오고 있어요…';
      legend.replaceChildren(); detail.textContent = ''; svg.hidden = true;
      note.textContent = `2023-07-29 경계 참고도 · 통계 종료월 ${month || '—'}. 현재 경계와 다를 수 있습니다. 면적은 단순화된 도형의 계산값이며 공식 면적이 아닙니다.`;
      try {
        await getData(); if (version !== generation) return;
        if (!shapeNodes.size) draw();
        svg.hidden = false; highlight();
        note.textContent = `경계 ${data.metadata.boundary_date} 참고도 · 통계 종료월 ${month || '—'}. 현재 경계와 다를 수 있습니다. 면적은 단순화된 도형의 계산값이며 공식 면적이 아닙니다.`;
      } catch (_) {
        if (version !== generation) return;
        status.textContent = '지도를 불러오지 못했어요. 아래 다시 불러오기를 눌러 주세요. 표와 채팅은 계속 이용할 수 있습니다.';
      }
    }
  };
  document.getElementById('mapAll').onclick = () => { if (data) fit(data.features); };
  document.getElementById('mapSelected').onclick = () => fit(selected.map(s => featureFor(s.code)).filter(Boolean));
  document.getElementById('mapZoomIn').onclick = () => zoom(.7);
  document.getElementById('mapZoomOut').onclick = () => zoom(1 / .7);
  document.getElementById('mapRetry').onclick = async () => {
    const version = generation; status.textContent = '경계를 다시 불러오고 있어요…';
    try { await getData(); if (version !== generation) return; if (!shapeNodes.size) draw(); svg.hidden = false; highlight(); }
    catch (_) { if (version === generation) status.textContent = '지도 연결을 확인해 주세요. 표와 채팅은 계속 이용할 수 있습니다.'; }
  };
  const modal = document.getElementById('regionMapModal'), stage = document.getElementById('regionMapStage'), home = stage.parentNode;
  const anchor = note.nextSibling; stage.appendChild(legend); stage.appendChild(note);
  document.getElementById('mapExpand').onclick = () => { modal.appendChild(stage); modal.showModal(); queueTiles(); };
  document.getElementById('mapClose').onclick = () => modal.close();
  modal.addEventListener('close', () => { home.insertBefore(stage, anchor); document.getElementById('mapExpand').focus(); queueTiles(); });
  svg.addEventListener('pointerdown', e => {
    if (!box) return; moved = false;
    drag = {x: e.clientX, y: e.clientY, box: [...box]}; svg.setPointerCapture(e.pointerId);
  });
  svg.addEventListener('pointermove', e => {
    if (!drag) return;
    const ctm = svg.getScreenCTM(); if (!ctm) return;
    const dx = (e.clientX - drag.x) / ctm.a, dy = (e.clientY - drag.y) / ctm.d;
    if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 4) moved = true;
    setBox([drag.box[0] - dx, drag.box[1] - dy, drag.box[2], drag.box[3]]);
  });
  svg.addEventListener('pointerup', e => { if (!moved) { const target = document.elementFromPoint(e.clientX, e.clientY); if (target?.dataset.code) describe(target.dataset.code); } drag = null; });
  svg.addEventListener('pointercancel', () => { drag = null; });
  svg.addEventListener('keydown', e => {
    if (!box) return;
    if (e.key === '+' || e.key === '=') zoom(.7);
    else if (e.key === '-') zoom(1 / .7);
    else if (e.key.startsWith('Arrow')) {
      const b = [...box], step = .12;
      if (e.key === 'ArrowLeft') b[0] -= b[2] * step;
      if (e.key === 'ArrowRight') b[0] += b[2] * step;
      if (e.key === 'ArrowUp') b[1] -= b[3] * step;
      if (e.key === 'ArrowDown') b[1] += b[3] * step;
      setBox(b);
    } else return;
    e.preventDefault();
  });
})();
