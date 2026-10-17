const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const read=f=>fs.readFileSync(path.join(root,f),'utf8');
const window={};
for(const file of ['riobamba-conflictividad-data.js','riobamba-kde-combinado-data.js','riobamba-kde-combinado.js'])
  vm.runInNewContext(read(file),{window,atob});
const api=window.RiobambaCombinedKde,data=api.data,surface=api.surface();
assert.equal(data.records,10731);
assert.equal(data.ecu911+data.cmi,data.records);
assert.equal(data.bandwidth,200);
assert.equal(data.cellSize,20);
assert.equal(surface.records,10731);
assert.equal(surface.density.length,554*542);
assert.equal(crypto.createHash('sha256').update(Buffer.from(surface.density.buffer)).digest('hex'),data.densitySha256);
assert.equal(data.densitySha256,'166262fc878f2fe42c716bfa9f5754e3e9efce33eed0233f7c9237a0424720d8');
const mask=new Set(surface.grid.mask);
let max=0;
for(let i=0;i<surface.density.length;i++) {
  assert(Number.isFinite(surface.density[i])&&surface.density[i]>=0);
  if(!mask.has(i))assert.equal(surface.density[i],0);
  max=Math.max(max,surface.density[i]);
}
assert.equal(max,data.visual.maxDensity);
const png=fs.readFileSync(path.join(root,'data/seguridad-riobamba/KDE_COMBINADO_200M_20261017/kde-combinado-200m.png'));
assert.equal(crypto.createHash('sha256').update(png).digest('hex'),data.pngSha256);
assert(!('events' in data)&&!('points' in data)&&!('features' in data));
assert.equal(data.deduplicated,false);
assert.match(api.legend(),/doble conteo/);
assert.match(api.methodologyHtml(),/enero-agosto/);
assert.match(api.methodologyHtml(),/enero-9 octubre/);
assert.equal(api.level(data.colorStops[3]+1),'Alta');
assert.equal(api.level(data.colorStops[4]+1),'Muy alta');
assert.equal(api.overlay().bandwidth,200);
for(const file of ['riobamba-kde-combinado.js','riobamba-kde-combinado-data.js','riobamba-camaras-propuesta.js']) new vm.Script(read(file),{filename:file});
const html=read('visor-seguridad-riobamba-v2.html');
for(const [,attrs,script] of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) if(!attrs.includes('src='))new vm.Script(script);
for(const file of ['riobamba-conflictividad.js','riobamba-conflictividad-data.js','riobamba-hotspot-urbano-200m-data.js','riobamba-cantonal-data.js','sig-bridge-active.json']) {
  const previous=execFileSync('git',['show','HEAD:'+file],{cwd:root,maxBuffer:128*1024*1024});
  assert.equal(read(file).replace(/\r\n/g,'\n'),previous.toString().replace(/\r\n/g,'\n'),file+' must remain unchanged');
}
assert.match(html,/if \(window.RiobambaCombinedKde\) return window.RiobambaCombinedKde.overlay\(\)/);
console.log(JSON.stringify({passed:true,records:surface.records,bandwidth:surface.bandwidth,numericHash:data.densitySha256,privateRecordsPublished:false,giAndRuralAndCameraReleaseUnchanged:true}));
