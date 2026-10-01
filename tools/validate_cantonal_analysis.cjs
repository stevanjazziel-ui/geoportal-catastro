const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root,file),'utf8');
const load = (file,key) => { const c={window:{}}; vm.runInNewContext(read(file),c); return c.window[key]; };
const data=load('riobamba-cantonal-data.js','RIOBAMBA_CANTONAL_DATA');
const source=load('visor-seguridad-riobamba-data.js','RIOBAMBA_SECURITY_DATA');
const original=JSON.parse(read('data/seguridad-riobamba/auditoria-cantonal-20261001/AUDITORIA_CANTONAL.json'));
for (const [file,hash] of Object.entries(original.protectedProductionHashesBefore)) {
  if(file==='visor-seguridad-riobamba-v2.html') continue;
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),hash,`Immutable input changed: ${file}`);
}
const events=source.events;
assert.equal(events.length,Object.keys(data.assignments).length);
const scopes=Object.fromEntries(['URBANO','RURAL','SIN_ASIGNAR'].map(s=>[s,events.filter(e=>data.assignments[e.id].scope===s).length]));
assert.deepEqual(scopes,{URBANO:23732,RURAL:2134,SIN_ASIGNAR:850});
assert.equal(Object.values(scopes).reduce((a,b)=>a+b),26716);
assert.equal(data.population.URBANO+data.population.RURAL,data.population.CANTONAL);
assert.equal(data.parishes.features.length,11);
assert.equal(data.parishes.features.reduce((s,f)=>s+f.properties.population,0),71991);
const rural=events.filter(e=>e.hotspotEligible&&data.assignments[e.id].scope==='RURAL');
assert.equal(rural.length,867);
assert.equal(data.ruralGrid.generalResults.reduce((s,c)=>s+c.COUNT,0),867);
for (const [i,neighbors] of data.ruralGrid.neighbors.entries()) {
  assert.ok(neighbors.includes(i));
  assert.ok(neighbors.length>1);
  for(const j of neighbors) assert.ok(data.ruralGrid.neighbors[j].includes(i));
}
const html=read('visor-seguridad-riobamba-v2.html');
const script=read('riobamba-cantonal-view.js');
new vm.Script(script);
for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
const extract=(text,start,end)=>text.slice(text.indexOf(start),text.indexOf(end,text.indexOf(start)));
const ctx={data,scope:'RURAL',assignment:id=>data.assignments[id],api:{},surfaceCache:null,
  document:{createElement:()=>({getContext:()=>({createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}}),toDataURL:()=> 'test'})}};
vm.createContext(ctx);
const code = [extract(html,'      const giNormalCdf =','      const giClass ='),extract(html,'      const giClass =','      const giClassRank ='),extract(html,'      const countKdeConcentrations =','      const kdeState ='),extract(html,'      const kdeColor =','      const percentile ='),'this.api={giNormalCdf,giClass,kdeColor,countKdeConcentrations};',extract(script,'  function giResult(','  function ruralGi('),extract(script,'  function kdeSurface(','  function renderLegend('),'this.computeGi=giResult;this.computeKde=kdeSurface;'].join('\n');
vm.runInContext(code,ctx);
const scenarios=[];
for(const id of [null,1,2,3]) {
  const items=rural.filter(e=>id===null||e.analyticalClassId===id);
  const actual=ctx.computeGi(data.ruralGrid,items);
  const expected=id===null?data.ruralGrid.generalResults:data.ruralGrid.byClass[id];
  actual.forEach((cell,i)=>{
    assert.equal(cell.incCount,expected[i].COUNT);
    assert.ok(Math.abs(cell.zScore-expected[i].GI_ZSCORE)<1e-10);
    assert.ok(Math.abs(cell.pValue-expected[i].GI_PVALUE)<2e-7);
    assert.equal(cell.giClass.replaceAll(' ',''),expected[i].GI_CLASS.replaceAll(' ',''));
  });
  scenarios.push({class:id??'general',records:items.length,hotspots:actual.filter(c=>c.giClass.startsWith('HOT')).length,coldspots:actual.filter(c=>c.giClass.startsWith('COLD')).length});
}
const sensitivity=[];
for(const bandwidth of [1000,1500,2000]) {
  data.kdeGrids.RURAL.bandwidth=bandwidth;
  const surface=ctx.computeKde(rural);
  assert.ok(surface.maxDensity>0);
  const mask=new Set(surface.grid.mask);
  for(let i=0;i<surface.density.length;i++) if(!mask.has(i)) assert.equal(surface.density[i],0);
  sensitivity.push({bandwidth,cellSize:100,records:rural.length,maxDensity:surface.maxDensity,concentrations:surface.concentrations});
}
data.kdeGrids.RURAL.bandwidth=1500;
assert.equal(ctx.computeKde([]).maxDensity,0);
const one=ctx.computeKde([rural[0]]).maxDensity;
const multiple=ctx.computeKde([rural[0],{...rural[0]}]).maxDensity;
assert.ok(Math.abs(multiple-2*one)<1e-5,'Coincident real observations retain multiplicity');
const grid=data.gridAssessment.find(r=>r.cellSize===1000&&r.distance===2000);
const cantonClasses=Object.fromEntries([1,2,3].map(id=>[id,events.filter(e=>e.analyticalClassId===id&&data.assignments[e.id].insideCanton).length]));
const report={scopes,total:events.length,cantonalInside:events.filter(e=>data.assignments[e.id].insideCanton).length,cantonClasses,ruralGi:scenarios,ruralGrid:grid,kdeSensitivity:sensitivity,originalDataHashesPreserved:true,all31CamerasPreserved:true,urbanBoundary:'Operative, not certified census/legal boundary',ruralInventory:'Not available',commitAndPush:false};
fs.writeFileSync(path.join(root,'data/seguridad-riobamba/expansion-cantonal-20261001/VALIDACION.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
