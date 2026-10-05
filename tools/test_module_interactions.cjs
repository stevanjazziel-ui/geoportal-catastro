const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'visor-seguridad-riobamba-v2.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'riobamba-camaras-propuesta.js'), 'utf8');

async function testProposalLifecycle() {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      value: id === 'proposalScenario' ? 'future' : 'urban',
      classList: { add() {}, remove() {} }, style: {},
      querySelectorAll: () => [], addEventListener() {}
    });
    return nodes.get(id);
  };
  const panes = new Map(), attached = new Set(), geometries = [];
  let active = true, miniMaps = 0, graphicsWrites = 0;
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const bounds = { isValid: () => true };
  const layer = () => ({ addTo(map) { map.addLayer(this); return this; }, getBounds: () => bounds });
  const map = {
    getPane: id => panes.get(id), createPane: id => { const p = { style: {} }; panes.set(id, p); return p; },
    hasLayer: l => attached.has(l), removeLayer: l => attached.delete(l), addLayer: l => attached.add(l),
    invalidateSize() {}, fitBounds() {}, setView() {}, remove() {}
  };
  const el = Object.fromEntries(['workspace', 'overlayTitle', 'overlayText', 'summary', 'detail', 'detailTitle', 'legend', 'status', 'graphicAnalysis'].map(id => [id, node(id)]));
  Object.defineProperty(el.graphicAnalysis, 'innerHTML', { set() { graphicsWrites++; } });
  const context = {
    window: { addEventListener() {} }, document: { getElementById: node }, console: { info() {} },
    requestAnimationFrame: fn => fn(),
    fetch: async url => {
      await gate;
      const file = path.join(root, url.split('?')[0]);
      return { ok: true, json: async () => JSON.parse(fs.readFileSync(file, 'utf8')) };
    },
    L: {
      svg: options => ({ svg: true, ...options }),
      geoJSON: (data, options) => { geometries.push(options); return layer(); },
      divIcon() {}, tileLayer: layer,
      map: () => { miniMaps++; return map; }
    }
  };
  vm.runInNewContext(source, context);
  const proposal = context.window.createRiobambaCameraProposal({
    map, elements: el, esc: String, active: () => active, layers: () => [], metricBars: () => ''
  });
  const oldRender = proposal.render();
  active = false; proposal.leave();
  el.detail.textContent = 'Otro modulo';
  active = true;
  const currentRender = proposal.render();
  release(); await Promise.all([oldRender, currentRender]);
  assert.equal(graphicsWrites, 1, 'Only the latest pending render may update the dashboard');
  assert.equal(miniMaps, 1, 'Obsolete renders must not recreate a mini map');
  assert.ok(geometries.filter(o => o?.pane && o.pane !== 'proposal-points').every(o => o.renderer?.svg), 'Custom polygon panes must use SVG to avoid full-canvas hit interception');
  active = false; proposal.leave();
  assert.ok([...panes.values()].every(p => p.style.display === 'none'), 'Inactive proposal panes must not intercept clicks');
  el.detail.textContent = 'Otro modulo';
  await proposal.render();
  assert.equal(el.detail.textContent, 'Otro modulo', 'Inactive rendering must not overwrite another module');
}

function testModuleSelection() {
  const body = html.match(/const analysisKey = \(\) => \{([\s\S]*?)\n      \};/)[1];
  const context = {
    mode: 'police', diagnosisMetric: 'cameraCoverage', incidentMenuView: 'incidents',
    isKdeMode: () => false, isGiHotspotsMode: () => false, isCameraProposalMode: () => false,
    isBoulevardsMode: () => false, isInstitutionalMode: () => false, isGapMode: () => false,
    isTemporalMode: () => false, isTypologiesMode: () => false
  };
  assert.equal(vm.runInNewContext(`(() => {${body}})()`, context), 'police');
  context.mode = 'events'; context.diagnosisMetric = 'populationCoverage';
  assert.equal(vm.runInNewContext(`(() => {${body}})()`, context), 'incidents');
  const lifecycle = html.match(/let renderedModule = null;([\s\S]*?)const urbanGiActive/)[1] + '}';
  let cleared = 0, closed = 0;
  const scope = { mode: 'diagnosis', diagnosisMetric: 'giHotspots', incidentMenuView: 'incidents',
    clearSelection: () => cleared++, map: { closePopup: () => closed++ } };
  vm.createContext(scope);
  vm.runInContext(`let renderedModule = null;${lifecycle}`, scope);
  vm.runInContext('update(); update();', scope);
  assert.equal(cleared, 0, 'Filtering the same module must preserve selection');
  scope.diagnosisMetric = 'hotspots'; vm.runInContext('update();', scope);
  assert.equal(cleared, 1); assert.equal(closed, 3);
  scope.mode = 'police'; vm.runInContext('update();', scope);
  assert.equal(cleared, 2);
  assert.ok(html.includes('!filteredGiCells().some((cell) => cell.cellId === selectedGiCell)'));
  const cantonal = fs.readFileSync(path.join(root, 'riobamba-cantonal-view.js'), 'utf8');
  assert.ok(cantonal.includes('if (map.hasLayer(pointRenderer)) map.removeLayer(pointRenderer)'));
  assert.ok(cantonal.includes('parish = unitControl.value; api.clearSelection()'));
}

(async () => {
  testModuleSelection();
  await testProposalLifecycle();
  console.log('PASS: module routing, selection cleanup, stale async renders, SVG hit testing and inactive pane cleanup.');
})().catch(error => { console.error(error); process.exitCode = 1; });
