"use strict";
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),folder=path.join(root,'data/seguridad-riobamba/COBERTURA_RECTA_20261110');
const json=name=>JSON.parse(fs.readFileSync(path.join(folder,name),'utf8'));
const source=fs.readFileSync(path.join(root,'riobamba-camaras-propuesta.js'),'utf8');new vm.Script(source);
const summary=json('RESUMEN.json'),primary=json('LINEAS_PRINCIPALES_200M.geojson'),extra=json('EXTENSION_VISUAL_50M.geojson'),gaps=json('BRECHA_MACAJI_TRAMO_200M.geojson');
assert.equal(summary.extra50IncludedInGapCalculation,false);assert.equal(summary.radiusForGapM,200);
assert.equal(summary.geometryMode,'STRAIGHT_FROM_CAMERA');assert.equal(summary.exactCameraOrigin,true);
assert.ok(primary.features.every(f=>f.geometry.coordinates.length===2));assert.ok(extra.features.every(f=>f.geometry.coordinates.length===2));
assert.ok(Math.abs(summary.uncoveredMacaji200M-251.99827650681033)<1e-7);
assert.ok(Math.abs(gaps.features.reduce((a,f)=>a+f.properties.LONGITUD_M,0)-summary.uncoveredMacaji200M)<1e-7);
assert.ok(primary.features.every(f=>f.properties.LONGITUD_M<=200.000001));assert.ok(extra.features.every(f=>f.properties.LONGITUD_M<=50.000001&&f.properties.SOLO_VISUAL));
const draw=source.slice(source.indexOf('  function draw() {'),source.indexOf('  function syncLayers() {'));
const styles=source.match(/const streetStyles = (.*);/)[1];
for(const scenarioCode of ['A','B','C']){
 const output={},context={cameraKeys:[],corridorToggles:{},layers:{},data:{platforms:{features:[]},corridors:{features:[]},macajiCorridor:{features:[]},voids:gaps,streetCoverage200:primary,streetExtension50:extra,directionalSummary:summary},scenario:()=>scenarioCode,drawKey:'',L:{geoJSON:(data,options)=>({data,options})},fc:features=>({type:'FeatureCollection',features}),replaceLayer:(key,layer)=>{output[key]=layer},pane:()=>'',renderer:()=>null,syncLayers:()=>{},groupEnabled:group=>group==='existing'||(group==='municipal'&&scenarioCode!=='A')||(group==='police'&&scenarioCode==='C'),originSymbol:(g,f)=>g==='existing'?(f.properties.REQUIERE_CAMBIO?'change':'existing'):g,displayGroup:(g,f)=>g==='existing'&&!f.properties.REQUIERE_CAMBIO?'existing':'interventions',layerVisible:()=>true,platformStyle:{},urbanAxesStyle:{},macajiSegmentStyle:{},platformLabel:()=>'',esc:x=>x,number:x=>String(x),labels:{},selectEntity:()=>{}};
 vm.runInNewContext('const streetStyles = '+styles+';'+draw+';draw();',context);
 assert.equal(output.streetCoverage200.options.style.color,'#15803d');assert.equal(output.streetCoverage200.options.style.dashArray,'8 6');
 assert.equal(output.streetExtension50.options.style.color,'#92cfa2');assert.ok(output.streetExtension50.options.style.opacity<output.streetCoverage200.options.style.opacity);
 assert.deepEqual(output.voids.data,gaps);
 assert.ok(output.streetCoverage200.data.features.every(f=>context.groupEnabled(f.properties.SOURCE_GROUP)));
 context.drawKey='';context.layerVisible=key=>key==='municipal';vm.runInNewContext('draw();',context);
 assert.ok(output.streetCoverage200.data.features.every(f=>f.properties.SOURCE_GROUP==='municipal'));
}
assert.ok(source.includes('Extensión clara de 50 m'));
assert.ok(source.includes('Solo visual; excluida del cálculo'));
console.log('PASS: green dashed 200m arms, lighter 50m visual-only extensions, scenario filtering and unchanged 200m gap calculation.');
