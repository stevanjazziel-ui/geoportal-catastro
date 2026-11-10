const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('riobamba-camaras-propuesta.js', 'utf8');
const cameras = JSON.parse(fs.readFileSync('data/seguridad-riobamba/COBERTURA_RECTA_20261110/CAMARAS_MACAJI_BELLAVISTA.geojson', 'utf8'));
assert.equal(cameras.features.length, 31);
assert.equal(cameras.features.filter(f => f.properties.GRUPO_ORIGEN_VISOR === 'existing').length, 19);
assert.equal(cameras.features.filter(f => f.properties.GRUPO_ORIGEN_VISOR === 'municipal').length, 9);
assert.ok(cameras.features.every(f => f.properties.DISTANCIA_EJE_M <= 200));
assert.equal(cameras.features.filter(f => f.properties.GRUPO_ORIGEN_VISOR === 'police').length, 3);
assert.equal(cameras.features.filter(f => f.properties.DISTANCIA_EJE_M <= 30).length, 14);
const context = {data:{macajiCameras:cameras},fc:features=>({features}),groupEnabled:g=>true,
  toggles:{macajiCameras:true,existing:true,municipal:true,existingRadius:true},cameraKeys:['existing','change','municipal','police','interventions'], individualKeys:['change','municipal','police'],scenario:()=> 'C'};
for (const name of ['macajiCameraFeatures','layerVisible']) {
  const fn = source.slice(source.indexOf('  function '+name+'(')).split('\n  }')[0]+'\n  }';
  vm.runInNewContext(fn, context);
}
assert.equal(context.macajiCameraFeatures().features.length,31);
assert.equal(context.layerVisible('macajiCameras'),true);
for (const key of ['existing','municipal','existingRadius']) assert.equal(context.layerVisible(key),false);
context.toggles.macajiCameras=false;
assert.equal(context.layerVisible('existing'),true);
assert.equal(context.layerVisible('municipal'),true);
context.groupEnabled=g=>g==='existing';
assert.equal(context.macajiCameraFeatures().features.length,19);
const release=JSON.parse(fs.readFileSync('sig-bridge-active.json','utf8')).root;
for(const f of cameras.features){
  const g=f.properties.GRUPO_ORIGEN_VISOR;
  const name={existing:'CAMARAS_EXISTENTES_103_FINAL',municipal:'PROPUESTA_MUNICIPAL_50_FINAL',police:'PROPUESTA_POLICIA_30_FINAL'}[g];
  const id={existing:'ID_CAMARA',municipal:'ID_PROPUESTA',police:'ID_POLICIA'}[g];
  const original=JSON.parse(fs.readFileSync(release+name+'.geojson','utf8')).features.find(o=>o.properties[id]===f.properties[id]);
  assert.deepEqual(f.geometry,original.geometry);
}
console.log('PASS: 31 unchanged camera positions within 200m of approved axis, scenario filtering, exclusive visibility and restoration.');
