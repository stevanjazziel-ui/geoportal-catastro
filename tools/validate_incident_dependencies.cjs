const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const parse = (text, name) => {
  const context = { window: {} };
  vm.runInNewContext(text, context);
  return JSON.parse(JSON.stringify(context.window[name]));
};
const load = (file, name) => parse(read(file), name);
const security = load('visor-seguridad-riobamba-data.js', 'RIOBAMBA_SECURITY_DATA');
const diagnosis = load('riobamba-seguridad-diagnostico-data.js', 'RIOBAMBA_SECURITY_DIAGNOSIS');
const kde = load('riobamba-seguridad-kde-validacion-data.js', 'RIOBAMBA_KDE_VALIDATION');
const spatial = load('riobamba-incidentes-spatial-data.js', 'RIOBAMBA_INCIDENT_SPATIAL');
const oldSource = parse(execFileSync('git', ['show', '231fb76:visor-seguridad-riobamba-data.js'], { cwd: root, maxBuffer: 32e6 }).toString(), 'RIOBAMBA_SECURITY_DATA');
const oldDiagnosis = parse(execFileSync('git', ['show', '231fb76:riobamba-seguridad-diagnostico-data.js'], { cwd: root, maxBuffer: 32e6 }).toString(), 'RIOBAMBA_SECURITY_DIAGNOSIS');
assert.deepEqual(security.events, oldSource.events, 'Original observations changed');
const eligible = security.events.filter((event) => event.hotspotEligible);
assert.equal(eligible.length, 12383);
assert.equal(kde.kdeInputPoints.length, eligible.length);
assert.deepEqual(kde.kdeInputPoints.map((point) => point.id).sort(), eligible.map((event) => event.id).sort());
assert.equal(spatial.eligibleRows, eligible.length);
assert.equal(spatial.crs, 'EPSG:32717');
let assigned = 0;
for (const platform of diagnosis.platformMaster) {
  const expected = eligible.filter((event) => event.platform === platform.platform);
  assert.equal(platform.incidents, expected.length, platform.platformName);
  assert.equal(platform.giHotspots, spatial.giSummaryByPlatform[platform.platformName].hotspots);
  assigned += expected.length;
  const old = oldDiagnosis.byPlatformName[platform.platformName];
  for (const key of Object.keys(platform).filter((key) => /^(population$|area|density|cameras|cameraCovered|cameraCoverage|cameraUncovered|policeInfrastructure$|avgPopulationDistancePolice)/i.test(key))) {
    assert.deepEqual(platform[key], old[key], `Unrelated indicator changed: ${platform.platformName}.${key}`);
  }
}
assert.equal(assigned, 11017);
assert.equal(diagnosis.summary.mappedIncidentsAssigned, assigned);
assert.equal(diagnosis.summary.unassigned.events, eligible.length - assigned);
const html = read('visor-seguridad-riobamba-v2.html');
for (const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
const extract = (start, end) => html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start)));
const element = () => ({ value: '__ALL__' });
const context = {
  elements: { category: element(), subtype: element(), parish: element(), kdePlatform: element(), kdePeriod: element(), incidentDate: { value: '' } },
  document: { createElement: () => ({ getContext: () => ({ createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }), putImageData() {} }), toDataURL: () => 'data:image/png;test' }) },
  raster: kde.rasters['700'],
  points: kde.kdeInputPoints,
};
vm.createContext(context);
vm.runInContext('const kdeDefaultRaster = () => raster;\n' +
  extract('      const countKdeConcentrations =', '      const kdeState =') +
  extract('      const kdeColor =', '      const renderFilteredKdeSurface =') +
  '\nthis.compute = getFilteredKdeSurface;', context);
const full = context.compute(context.points);
assert.equal(full.width * 20, context.raster.metricBounds[1][0] - context.raster.metricBounds[0][0]);
assert.equal(full.height * 20, context.raster.metricBounds[1][1] - context.raster.metricBounds[0][1]);
assert.ok(Math.abs(full.maxDensity - context.raster.maxValue) / context.raster.maxValue < 1e-4, 'Filtered and precomputed KDE kernels differ');
assert.equal(full.concentrations, context.raster.observableConcentrations);
context.incidentSpatial = spatial;
context.platformGeojsonCache = true;
context.giPoints = eligible.filter((event) => event.platform);
vm.runInContext('const geoIncidentEvents = () => giPoints; const eventWeight = () => 1;\n' +
  extract('      const giNormalCdf =', '      const giClassRank =') +
  extract('      let giHotspotCache =', '      const categorySummary =') +
  '\nthis.giAnalysis = getGiHotspotAnalysis();', context);
const gi = context.giAnalysis;
assert.equal(gi.cells.reduce((sum, cell) => sum + cell.incCount, 0), assigned);
assert.equal(gi.hotspotCells.length, diagnosis.summary.hotspots);
for (const cell of gi.cells) assert.equal(cell.giStar, cell.zScore);
for (const platform of diagnosis.platformMaster) {
  assert.equal(gi.hotspotCells.filter((cell) => cell.platform === platform.platformName).length, platform.giHotspots);
}
const types = [
  { name: 'Todos los tipos', points: context.points },
  { name: 'Robo a domicilios', points: context.points.filter((p) => /robo.*domicilio/i.test(p.subtype)) },
  { name: 'Violencia interpersonal / familiar', points: context.points.filter((p) => p.category === 'Violencia interpersonal / familiar') },
];
const report = [];
for (const type of types) {
  context.elements.category.value = type.name;
  const surface = context.compute(type.points);
  assert.equal(surface.width, full.width);
  assert.equal(surface.height, full.height);
  assert.ok(type.points.length && surface.maxDensity > 0);
  report.push({ type: type.name, records: type.points.length, concentrations: surface.concentrations, maxDensity: surface.maxDensity });
}
const point = context.points.find((p) => p.platform);
context.elements.category.value = 'single-validation';
const single = context.compute([point]);
context.elements.category.value = 'multiple-validation';
const multiple = context.compute([point, { ...point, id: 'different-event-2' }, { ...point, id: 'different-event-3' }]);
assert.ok(Math.abs(multiple.maxDensity - single.maxDensity * 3) < 1e-5);
context.elements.category.value = 'empty-validation';
assert.equal(context.compute([]).maxDensity, 0);
assert.equal(context.compute([]).concentrations, 0);
console.log(JSON.stringify({ source: security.events.length, eligible: eligible.length, assigned, outsidePlatforms: eligible.length - assigned, giCells: spatial.giGrid.cells.length, bandwidth: context.raster.bandwidth, cellSize: 20, unchangedPopulationAndCameraCoverage: true, filters: report }, null, 2));
