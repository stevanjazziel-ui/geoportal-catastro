const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const pointer = JSON.parse(fs.readFileSync(path.join(root, 'sig-bridge-active.json'), 'utf8'));
assert.match(pointer.releaseId, /^[A-Za-z0-9_-]+$/);
assert.equal(pointer.coverageData, 'riobamba-brechas-actualizadas-data.js');
const directory = path.resolve(root, pointer.root);
assert.ok(directory.startsWith(root + path.sep));
const context = {window: {}};
vm.runInNewContext(fs.readFileSync(path.join(directory, pointer.coverageData), 'utf8'), context);
const gaps = context.window.RIOBAMBA_UPDATED_GAPS;
assert.equal(gaps.inventoryCameraOverlay.length, 103);
assert.equal(gaps.inventoryCameraOverlay.filter(c => c.requiresChange).length, 30);
assert.equal(gaps.inventoryCameraOverlay.filter(c => c.requiresChange && c.ambitoEstudio === 'MUNICIPAL').length, 30);
assert.equal(gaps.metadata.uniqueSites, 103);
const results = JSON.parse(fs.readFileSync(path.join(directory, 'RESULTADOS.json'), 'utf8'));
assert.deepEqual(results.counts, {existing:103,changeIncluded:30,municipal:50,police:30});
const inventory = JSON.parse(fs.readFileSync(path.join(directory, 'CAMARAS_EXISTENTES_103_FINAL.geojson'), 'utf8'));
const ids = new Set(gaps.inventoryCameraOverlay.filter(c => c.requiresChange).map(c => c.id));
assert.equal(ids.size, 30);
for (const feature of inventory.features) assert.equal(feature.properties.REQUIERE_CAMBIO, ids.has(feature.properties.ID_CAMARA));
const rings = JSON.parse(fs.readFileSync(path.join(directory, 'RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson'), 'utf8'));
assert.equal(rings.features.length, 103);
for (const ring of rings.features) assert.equal(ring.properties.REQUIERE_CAMBIO, ids.has(ring.properties.ID_CAMARA));
for (const radius of [100,150,200]) {
  const scenarios = gaps.scenarios[radius];
  for (const [key,count] of Object.entries({A:103,B:153,C:183,REEMPLAZO_30:30})) assert.equal(scenarios[key].cameraRecords,count);
  assert.equal(gaps.replacementScenarios[radius].coverage.properties.cameras_total,30);
  assert.equal(gaps.inventoryCoverage.scenarios[radius].coverage.properties.cameras_total,103);
}
const validation = JSON.parse(fs.readFileSync(path.join(directory,'VALIDACION.json'),'utf8'));
assert.equal(validation.publishBlocks.length,0);
assert.ok(validation.approvedException.authorization);
assert.equal(validation.giRecalculated,false);
assert.equal(validation.kdeRecalculated,false);
for (const file of ['sig-bridge-release.js','riobamba-camaras-propuesta.js','riobamba-cobertura-corredores.js','riobamba-deficit-inventario.js']) {
  new vm.Script(fs.readFileSync(path.join(root,file),'utf8'),{filename:file});
}
const html = fs.readFileSync(path.join(root,'visor-seguridad-riobamba-v2.html'),'utf8');
for (const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) new vm.Script(script[1]);
assert.ok(html.includes('window.RIOBAMBA_SIG_RELEASE_GAPS || window.RIOBAMBA_UPDATED_GAPS'));
assert.ok(html.includes('let diagnosisMetric = "cameraProposal"'));
console.log('PASS: active release, 103/30/73 IDs, symbols and radii, 12 scenarios, approved exception and JS syntax.');
