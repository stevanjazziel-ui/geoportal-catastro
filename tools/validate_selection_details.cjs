const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'visor-seguridad-riobamba-v2.html'), 'utf8');
const extract = (start, end) => {
  const from = html.indexOf(start), to = html.indexOf(end, from);
  assert.ok(from >= 0 && to > from, start);
  return html.slice(from, to);
};
// Parse every inline script as well as the cantonal adapter before testing handlers.
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
new vm.Script(fs.readFileSync(path.join(root, 'riobamba-cantonal-view.js'), 'utf8'));
const context = {
  mode: 'diagnosis', diagnosisMetric: 'giHotspots',
  selectedId: null, selectedCamera: null, selectedPolice: null,
  selectedPlatform: 'PLATAFORMA M', selectedParish: null, selectedGiCell: null,
  detailMiniMap: null,
  events: [{id: 'event-1', category: 'DELINCUENCIA'}],
  cameras: [{id: 'camera-1'}], policeInfrastructure: [{properties: {code: 'police-1'}}],
  inventoryCameras: [{id: 'camera-1'}],
  isCameraCoverageMode: () => false,
  isInventoryDeficitMode: () => false,
  markers: new Map(), cameraMarkers: new Map(), policeMarkers: new Map(),
  cantonalController: {scope: () => 'URBANO', cameraMatchesScope: () => true}, platformLayer: null,
  filteredEvents: () => context.events,
  platformRecord: (name) => name === 'PLATAFORMA M' ? {platformName: name} : null,
  renderDetail: (event) => { context.detail = event?.id; },
  renderCameraDetail: (id) => { context.detail = id; },
  renderPoliceDetail: (id) => { context.detail = id; },
  renderPlatformDetail: (id) => { context.detail = id; },
  renderList: () => {}, invalidateMapLayout: () => {},
  update: () => { context.updates = (context.updates || 0) + 1; },
  getGiHotspotAnalysis: () => ({cells: [{cellId: 'cell-1'}]}),
  renderConflictModuleDetail: () => { context.detail = context.selectedGiCell; },
  renderHotspots: () => { throw new Error('Do not remove a clicked layer during dispatch'); },
  hotspotLayer: {eachLayer: (callback) => context.giLayers.forEach(callback)},
  giLayers: ['cell-1', 'cell-2'].map((id) => ({giCellId: id, setStyle(style) { this.style = style; }})),
};
vm.createContext(context);
vm.runInContext(
  extract('      function clearDetailMiniMap()', '      let selectedId =') +
  extract('      function renderSelectedEntityDetail(', '      function renderParishDetail(') +
  extract('      function selectCamera(', '      function renderPoliceDetail(') +
  extract('      function selectPolice(', '      function renderPlatformDetail(') +
  extract('      function selectPlatform(', '      function syncModeButtons('), context);
let cases = 0;
for (const mode of ['events', 'police', 'cameras', 'diagnosis']) {
  for (const [handler, id] of [['selectEvent', 'event-1'], ['selectCamera', 'camera-1'], ['selectPolice', 'police-1'], ['selectPlatform', 'PLATAFORMA M']]) {
    context.clearSelection();
    context.mode = mode;
    context.selectedPlatform = 'PLATAFORMA M';
    context[handler](id, false);
    assert.equal(context.mode, mode, 'Selection must not navigate to another module');
    assert.equal(context.diagnosisMetric, 'giHotspots');
    assert.equal(context.selectedPlatform, 'PLATAFORMA M', 'Keep the analysis platform when inspecting resources');
    if (handler !== 'selectPlatform' || mode !== 'diagnosis') assert.equal(context.detail, id);
    cases++;
  }
}
context.selectGiCell('cell-1');
assert.equal(context.detail, 'cell-1');
assert.equal(context.giLayers[0].style.weight, 1.4);
assert.equal(context.giLayers[1].style.weight, .45);
context.selectGiCell('cell-2');
assert.equal(context.selectedGiCell, 'cell-1', 'Ignore unavailable cells');
context.selectEvent('event-1', false);
assert.equal(context.selectedGiCell, null);
assert.equal(context.renderSelectedEntityDetail([]), false, 'Clear a record excluded by subsequent filters');
let removals = 0;
context.detailMiniMap = {remove() { removals++; assert.equal(context.detailMiniMap, null); }};
context.clearDetailMiniMap();
context.clearDetailMiniMap();
assert.equal(removals, 1, 'Dispose each minimap once, before replacing its DOM');
for (const [handler, id] of [['selectEvent', 'missing'], ['selectCamera', 'missing'], ['selectPolice', 'missing'], ['selectPlatform', 'missing']]) {
  context.detail = 'previous';
  context[handler](id, false);
  assert.equal(context.detail, 'previous');
}
const ordering = [];
for (const name of ['hotspotLayer', 'manzanaLayer', 'platformLayer', 'boulevardLayer', 'parishLayer', 'kdePointLayer', 'eventLayer', 'cameraCoverageLayer', 'cameraLayer', 'policeInfrastructureLayer', 'platformLabelLayer']) context[name] = name;
context.bringLayerForward = (layer) => ordering.push(layer);
context.sendLayerBackward = () => {};
vm.runInContext(extract('      function bringVisibleContextToFront()', '      function syncMapLayerVisibility()'), context);
context.bringVisibleContextToFront();
assert.ok(ordering.indexOf('platformLayer') < ordering.indexOf('hotspotLayer'), 'Cell/zone clicks take priority over underlying platforms');
assert.ok(ordering.indexOf('hotspotLayer') < ordering.indexOf('eventLayer'), 'Original points remain selectable above the analysis');
assert.ok(!extract('      function renderDetail(', '      function renderList(').includes('${event.geocode}'), 'Missing geocode must not be interpolated into the module description');
context.elements = {search: {value: ''}, category: {value: 'DELINCUENCIA'}, source: {value: '__ALL__'}, precision: {value: '__ALL__'}};
context.clean = (value) => String(value).toLowerCase();
context.insidePlatformsOnly = () => true;
context.cameras = [{id: 'camera-1', type: 'DOMO'}, {id: 'camera-2', type: 'LA'}];
context.inventoryCameras = context.cameras;
vm.runInContext(extract('      function filteredCameras()', '      function filteredPlatforms()'), context);
context.mode = 'diagnosis';
assert.equal(context.filteredCameras().length, 2, 'Incident categories must not hide contextual cameras');
context.mode = 'cameras';
context.elements.category.value = 'DOMO';
assert.equal(context.filteredCameras().length, 1, 'Camera inventory retains its own type filter');
console.log(JSON.stringify({selectionCases: cases, modulePreserved: true, giLayerLifecycle: true, minimapLifecycle: true, invalidSelectionIgnored: true, clickPriority: true, resourceFiltersIsolated: true}));
