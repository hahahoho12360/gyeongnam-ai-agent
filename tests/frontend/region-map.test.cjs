const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {selection, bounds, path} = require('../../frontend/region-map.js');
const geometry = JSON.parse(fs.readFileSync('frontend/data/changwon-legal-boundaries.json'));
assert.equal(geometry.features.length, 204);
assert.equal(new Set(geometry.features.map(f => f.properties.code)).size, 204);
for (const f of geometry.features) {
  assert.match(f.properties.code, /^481(21|23|25|27|29)\d{3}00$/);
  assert(f.properties.area_km2 > 0);
  assert(['Polygon', 'MultiPolygon'].includes(f.geometry.type));
  assert(!/NaN|undefined/.test(path(f.geometry)));
}
assert(bounds(geometry.features).every(Number.isFinite));
const r = i => ({id: geometry.features[i].properties.code, name: `지역${i}`});
assert.deepEqual(selection(r(0), {peers:[r(1),r(2)],seeded_random:[r(3)]}).map(x => x.code), [0,1,2,3].map(i => r(i).id));
assert.equal(selection(r(0), {peers:[r(0),r(1)],seeded_random:[r(1)]}).length, 2);
assert.equal(selection(null).length, 0);
assert.equal((path({type:'Polygon',coordinates:[[[0,0],[2,0],[2,2],[0,0]],[[.5,.5],[1,.5],[1,1],[.5,.5]]]}).match(/Z/g)||[]).length,2);

class Node {
  constructor(){this.children=[];this.style={setProperty(){},removeProperty(){}};this.dataset={};this.classList={add(){},remove(){}};this.parentNode=this;}
  appendChild(n){this.children.push(n);return n;}
  append(...n){this.children.push(...n);}
  replaceChildren(){this.children=[];}
  setAttribute(){} addEventListener(){} insertBefore(){}
}
async function run(){
  const nodes = new Map();const node = id => {if(!nodes.has(id)) nodes.set(id,new Node());return nodes.get(id);};
  let finish;
  const box={window:{},document:{getElementById:node,createElement:()=>new Node(),createElementNS:()=>new Node()},setTimeout,clearTimeout,AbortController,fetch:()=>new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>geometry});})};
  vm.createContext(box);vm.runInContext(fs.readFileSync('frontend/region-map.js','utf8'),box);
  const first=box.window.RegionMap.update(r(0),{peers:[r(1),r(2)],seeded_random:[r(3)]},'2026-09');
  box.window.RegionMap.clear();finish();await first;
  assert.equal(node('regionMapCard').hidden,true,'late fetch must not revive a cleared map');
  await box.window.RegionMap.update(r(4),{peers:[r(5),r(6)],seeded_random:[r(7)]},'2026-08');
  assert.equal(node('regionMapCard').hidden,false);
  assert.equal(node('regionMapLegend').children.length,4);
  assert(node('regionMapNote').textContent.includes('2026-08'));
  assert(node('regionMapNote').textContent.includes('2023-07-29'));
  await box.window.RegionMap.update({id:'9999999999',name:'없는 경계'}, {}, '2026-09');
  assert(node('regionMapStatus').textContent.includes('1곳은 경계 자료가 없습니다'));
  assert.equal(node('regionMapLegend').children[0].disabled,true);
  console.log('204 legal boundaries, holes, comparison identity, stale response and missing geometry checks passed');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
