const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
for(const hash of ['','#indices/vitality_index']){
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:id!=='#mainView',setAttribute(){},focus(){},contains(){return false}});return nodes.get(id)};
 const sandbox={location:{hash},document:{activeElement:null,addEventListener(){},querySelectorAll(){return []}},window:{scrollY:0,scrollTo(){},addEventListener(){}},$:node,clearTimeout,setTimeout,esc:String,fmt:String,metricFormat:v=>v??'—'};
 vm.createContext(sandbox);vm.runInContext(fs.readFileSync('frontend/index-guide.js','utf8'),sandbox);
 assert.equal(node('#mainView').hidden,hash.startsWith('#indices'));
 assert.match(node('#guideContent').innerHTML,/구성산식과 기본 가중치/);
 assert.equal(vm.runInContext('evidenceItems.length',sandbox),0);
 assert.equal(vm.runInContext("evidenceButton(null,'vitality_index',{},'지역')",sandbox),'<b>—</b>');
}
console.log('Main/guide initialization and missing score checks passed');
