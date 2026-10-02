const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'visor-seguridad-riobamba-v2.html'), 'utf8');
const graphics = html.slice(html.indexOf('      function renderGraphicAnalysis()'));
assert.ok(graphics.indexOf('if (isInventoryDeficitMode())') < graphics.indexOf('if (isGapMode())'), 'Dispatch inventory graphics before the legacy gap renderer');
const context = {window: {}, document: {querySelectorAll: () => [], getElementById: () => ({addEventListener() {}})}};
vm.createContext(context);
for (const file of ['riobamba-camaras-inventario-data.js', 'riobamba-camaras-inventario-cobertura-data.js', 'riobamba-conflictividad-data.js', 'riobamba-deficit-inventario.js']) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
const coverage = context.window.RIOBAMBA_INVENTORY_CAMERA_COVERAGE;
const baseline = context.window.RIOBAMBA_CONFLICTIVITY_CORRECTION.derivedMethodology;
const names = Object.keys(coverage.scenarios[100].byPlatformName);
let radius = 150, selected = null, subset = null, filteredEvents = [];
const elements = {summary: {}, graphicAnalysis: {}, detail: {}, detailTitle: {}};
let miniMap = null;
const api = context.window.createRiobambaInventoryDeficit({coverage, baseline,
  inventory: context.window.RIOBAMBA_CAMERA_INVENTORY.cameras, elements,
  esc: String, fmt: (value) => Number(value).toLocaleString('es-EC'),
  metricBars: (title, rows) => JSON.stringify({title, rows}), radius: () => radius,
  selected: () => selected, events: () => filteredEvents, eventPlatform: (event) => event.platform,
  platforms: () => names.filter((name) => !subset || name === subset).map((name) => ({platformName: name, platform: name.replace('PLATAFORMA ', '')})),
  selectPlatform() {}, miniMap: (id, platform) => {miniMap = [id, platform.platformName];},
});
assert.equal(api.cameras().length, 99);
let cases = 0;
for (selected of [null, ...names]) {
  let previousPopulation = -1, previousArea = -1;
  for (radius of [100, 150, 200]) {
    const total = api.totals();
    assert.equal(total.population, total.coveredPopulation + total.uncoveredPopulation);
    assert.ok(total.coveredPopulation >= total.originalCoveredPopulation);
    assert.ok(total.coveredPopulation >= previousPopulation && total.coveredAreaKm2 >= previousArea);
    assert.ok(Math.abs(total.areaKm2 - total.coveredAreaKm2 - total.uncoveredAreaKm2) < 1e-9);
    assert.equal(api.rows().length, selected ? 1 : 18);
    api.renderMetrics(); api.renderGraphics(); api.renderDetail(selected ? {platformName: selected} : null);
    assert.ok(elements.graphicAnalysis.innerHTML.includes('103 inventariadas · 99 ubicadas'));
    assert.ok(!elements.graphicAnalysis.innerHTML.includes('Gi*'));
    if (selected) assert.equal(miniMap[1], selected);
    assert.ok(elements.detail.innerHTML.includes('sin coordenadas') || elements.detail.innerHTML.includes('pendientes de ubicación'));
    previousPopulation = total.coveredPopulation; previousArea = total.coveredAreaKm2;
    cases++;
  }
}
selected = null; radius = 150; subset = names[0];
assert.equal(api.rows().length, 1, 'Platform filter controls the whole dashboard');
const inside = coverage.scenarios[150].incidentIdsCovered[0];
filteredEvents = [{id: inside, platform: subset}, {id: 'outside-test', platform: subset}];
assert.equal(api.totals().incidents, 2);
assert.equal(api.totals().uncoveredIncidents, 1);
filteredEvents = filteredEvents.slice(0, 1);
assert.equal(api.totals().incidents, 1);
assert.equal(api.totals().uncoveredIncidents, 0);
console.log(JSON.stringify({dashboardCases: cases, locatedCameras: 99, independentBaseline: true, filteredIncidents: true, miniMaps: true, noGiReuse: true}));
