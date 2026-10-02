const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const context = {window: {}};
vm.createContext(context);
for (const file of ['riobamba-camaras-data.js', 'riobamba-camaras-inventario-data.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
}
const inventory = context.window.RIOBAMBA_CAMERA_INVENTORY;
const study = context.window.RIOBAMBA_CAMERAS_DATA.cameras;
assert.equal(inventory.cameras.length, 103);
assert.equal(new Set(inventory.cameras.map((camera) => camera.id)).size, 103);
assert.equal(new Set(inventory.cameras.map((camera) => camera.sourceId)).size, 103);
assert.equal(study.length, 31);
assert.equal(inventory.cameras.filter((camera) => camera.requiresChange).length, 31);
assert.deepEqual(inventory.cameras.filter((camera) => camera.studyCamera).map((camera) => camera.id).sort(), study.map((camera) => camera.id).sort());
assert.equal(inventory.metadata.studySha256, crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'riobamba-camaras-data.js'))).digest('hex'));
for (const camera of study) {
  const match = inventory.cameras.find((item) => item.id === camera.id);
  for (const key of ['lat', 'lng', 'method', 'confidence']) assert.equal(match[key], camera[key], `${camera.id}: unchanged ${key}`);
}
for (const camera of inventory.cameras) {
  assert.ok(camera.institution && camera.source && camera.locationStatus);
  if (camera.mappable) {
    assert.ok(Number.isFinite(camera.lat) && Number.isFinite(camera.lng));
    assert.ok(camera.lat < -1 && camera.lat > -2.5 && camera.lng < -78 && camera.lng > -79);
    assert.ok(camera.method && !/fallback|spiral|espiral/i.test(camera.method));
  } else {
    assert.equal(camera.lat, null);
    assert.equal(camera.lng, null);
  }
}
const html = fs.readFileSync(path.join(root, 'visor-seguridad-riobamba-v2.html'), 'utf8');
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
new vm.Script(fs.readFileSync(path.join(root, 'riobamba-cantonal-view.js'), 'utf8'));
const extract = (start, end) => {
  const from = html.indexOf(start), to = html.indexOf(end, from);
  assert.ok(from >= 0 && to > from);
  return html.slice(from, to);
};
Object.assign(context, {
  mode: 'cameras', inventoryCameras: inventory.cameras, cameras: study,
  elements: {search: {value: ''}, category: {value: '__ALL__'}, source: {value: '__ALL__'}, precision: {value: '__ALL__'}},
  clean: (value) => String(value).toLowerCase(),
  insidePlatformsOnly: () => true,
  isCameraCoverageMode: () => false,
  isInventoryDeficitMode: () => false,
  cantonalController: {cameraMatchesScope: () => true},
});
vm.runInContext(extract('      function filteredCameras()', '      function filteredPoliceInfrastructure()'), context);
assert.equal(context.filteredCameras().length, 103, 'Full inventory includes unlocated records');
for (const [type, count] of [['DOMO', 85], ['FIJA', 17], ['LA', 1]]) {
  context.elements.category.value = type;
  assert.equal(context.filteredCameras().length, count);
}
context.elements.category.value = '__ALL__';
context.elements.source.value = 'MINEDUC';
assert.equal(context.filteredCameras().length, 6);
context.elements.source.value = '__ALL__';
context.elements.search.value = 'RIO-016-DOMO';
assert.equal(context.filteredCameras().length, 1);
assert.equal(context.filteredCameras()[0].mappable, false);
context.mode = 'diagnosis';
assert.equal(context.filteredCameras().length, 31, 'Analysis remains isolated from inventory filters and extra cameras');
context.mode = 'cameras';
vm.runInContext(extract('      const analysisKey =', '      const analysisConfig ='), context);
for (const metric of ['cameraCoverage', 'populationCoverage', 'hotspots', 'giHotspots']) {
  context.diagnosisMetric = metric;
  assert.equal(vm.runInContext('analysisKey()', context), 'cameras', 'Inventory filters must not inherit a previously selected analysis');
}
console.log(JSON.stringify({records: 103, unique: 103, replacement: 31,
  locatedApproximately: inventory.cameras.filter((camera) => camera.mappable).length,
  pending: inventory.cameras.filter((camera) => !camera.mappable).map((camera) => camera.id),
  filters: {DOMO: 85, FIJA: 17, LA: 1, MINEDUC: 6}, studyUnchanged: true}));
