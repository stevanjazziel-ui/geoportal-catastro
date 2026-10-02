const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const json = (file) => JSON.parse(read(file).replace(/^\uFEFF/, ''));
const load = (file, key) => {
  const context = { window: {} };
  vm.runInNewContext(read(file), context);
  return context.window[key];
};
const html = read('visor-seguridad-riobamba-v2.html');
assert.ok(!html.includes('data-camera-set'), 'Remove the camera group selector and its obsolete listeners');
assert.ok(html.includes('let cameraCoverageSet = "inventory";'), 'Coverage opens with the complete inventory');
const extract = (start, end) => {
  const offset = html.indexOf(start);
  assert.ok(offset >= 0, start);
  const stop = html.indexOf(end, offset);
  assert.ok(stop > offset, end);
  return html.slice(offset, stop);
};
const diagnosis = load('riobamba-seguridad-diagnostico-data.js', 'RIOBAMBA_SECURITY_DIAGNOSIS');
const cameras = load('riobamba-camaras-data.js', 'RIOBAMBA_CAMERAS_DATA').cameras;
assert.equal(cameras.length, 31, 'Preserve the confirmed 31-camera inventory');
assert.ok(cameras.some((camera) => camera.id === 'RIO-068-LA'), 'Preserve RIO-068-LA');
const context = {
  methodology: load('riobamba-metodologia-data.js', 'RIOBAMBA_METHODOLOGY'),
  diagnosis,
  conflictEvents: load('visor-seguridad-riobamba-data.js', 'RIOBAMBA_SECURITY_DATA').events.filter((e) => e.hotspotEligible),
  platforms: diagnosis.platformMaster,
  changeCameras: cameras.filter((camera) => camera.requiresChange),
  municipalCameras: cameras,
  externalCameras: [],
  inventoryCoverage: load('riobamba-camaras-inventario-cobertura-data.js', 'RIOBAMBA_INVENTORY_CAMERA_COVERAGE'),
  inventoryCameras: load('riobamba-camaras-inventario-data.js', 'RIOBAMBA_CAMERA_INVENTORY').cameras,
  coverageGeometries: load('riobamba-camaras-cobertura-geometrias.js', 'RIOBAMBA_CAMERA_COVERAGE_GEOMETRIES'),
  remainingCameras: load('riobamba-camaras-inventario-data.js', 'RIOBAMBA_CAMERA_INVENTORY').cameras.filter((camera) => !camera.studyCamera),
  operationalMunicipalCameras: [],
  cameraCoverageSet: 'municipal', cameraCoverageScenario: 150,
  cameraCoverageCache: null, cameraCoverageCacheKey: '',
  selectedPlatform: null, populationMode: false, coverageMode: true,
  platformGeojsonCache: json('riobamba-censo-data/riobamba_plataformas.geojson'),
  manzanaGeojsonCache: json('riobamba-censo-data/riobamba_manzanas.geojson'),
  platformStats: json('riobamba-censo-data/riobamba_plataformas_stats.json'),
  manzanaStats: json('riobamba-censo-data/riobamba_manzanas_stats.json'),
  elements: { graphicAnalysis: {}, detail: {}, detailTitle: {} },
  cameraCoverageLayer: {clearLayers() { context.mapShapes = []; }},
  L: {geoJSON(geometry, options) { return {addTo() { context.mapShapes.push({geometry, options}); }}; }},
  document: { getElementById: () => null, querySelectorAll: () => [] },
  Blob: class { constructor(parts) { context.exportedCsv = parts.join(''); } },
  URL: { createObjectURL: () => 'blob:test', revokeObjectURL: () => {} },
  fmt: (value) => Number(value).toLocaleString('es-EC'),
  esc: (value) => String(value),
  metricBars: (title, rows) => JSON.stringify({ title, rows }),
  cameraCoverageColor: () => '#2f6f5f',
  renderCameraCoverageMiniMap: () => {},
};
context.document.createElement = () => ({ click() { context.exportedFilename = this.download; } });
vm.createContext(context);
vm.runInContext(`
  const filteredPlatforms = () => platforms;
  const platformRecord = (name) => platforms.find((row) => row.platformName === name);
  const isPopulationCoverageMode = () => populationMode;
  const isCameraCoverageMode = () => coverageMode;
  const isGapMode = () => false;
  const isInventoryDeficitMode = () => false;
  const manzanaPopulation = (feature) => Number(manzanaStats.byMan[feature.properties.man]?.population_total || 0);
` +
  extract('      const pointInRing =', '      const platformMaskRings =') +
  extract('      const cameraCoverageRowAtScenario =', '      const coveragePercent =') +
  extract('      const coveragePercent =', '      const syncCoverageControls =') +
  extract('      const incidentCoverageHtml =', '      function renderGapMetrics()') +
  extract('      const ringAreaKm2 =', '      const eventPlatformName =') +
  extract('      const ringBounds =', '      const coverageManzanaStyle =') +
  extract('      const coverageManzanaStyle =', '      const getCameraCoverageAnalysis =') +
  extract('      const getCameraCoverageAnalysis =', '      const platformFilterValue =').replace('const getCameraCoverageAnalysis =', 'const computeCameraCoverageAnalysis =') +
  `
    const scenarioAnalyses = new Map();
    const getCameraCoverageAnalysis = () => {
      const key = cameraCoverageScenario + '-' + (coverageMode ? cameraCoverageSet : 'municipal');
      if (!scenarioAnalyses.has(key)) scenarioAnalyses.set(key, computeCameraCoverageAnalysis());
      return scenarioAnalyses.get(key);
    };
  ` +
  extract('      function cameraCoverageRows()', '      function renderBoulevardGraphics()') +
  extract('      function renderCameraCoverageDetail()', '      function renderConflictModuleDetail()') +
  extract('      function renderCameraCoverageLayer()', '      function renderPoliceLayers()') +
  '\nthis.api = { cameraCoverageTotals, coverageTerritorialData, coveragePopulationData, cameraCoverageRows, renderCameraCoverageGraphics, renderCameraCoverageDetail, exportCameraCoverageCsv, coverageManzanaStyle, renderCameraCoverageLayer, coverageCameraSet, coveragePendingCameras, cameraCoverageRowAtScenario, cameraCoverageTotalsAtScenario };', context);

const results = [];
for (const cameraSet of ['municipal', 'inventory']) {
context.cameraCoverageSet = cameraSet;
assert.equal(context.api.coverageCameraSet(null).length, cameraSet === 'inventory' ? 99 : 31);
assert.equal(context.api.coverageCameraSet(null).filter((camera) => camera.requiresChange).length, 31);
assert.equal(context.api.coveragePendingCameras().length, cameraSet === 'inventory' ? 4 : 0);
for (const platform of [null, ...context.platforms.map((row) => row.platformName)]) {
  context.selectedPlatform = platform;
  let previousArea = -1;
  let previousPopulation = -1;
  for (const radius of [100, 150, 200]) {
    context.cameraCoverageScenario = radius;
    const totals = context.api.cameraCoverageTotals();
    const territory = context.api.coverageTerritorialData(totals);
    const population = context.api.coveragePopulationData(totals);
    if (cameraSet === 'inventory') {
      const baseline = context.methodology.cameraScenarios[radius];
      assert.equal(context.api.cameraCoverageRowAtScenario('PLATAFORMA I', radius).coveredPopulation,
        baseline.byPlatformName['PLATAFORMA I'].coveredPopulation, 'Institutional and gap helpers must retain the 31-camera baseline');
      const baselineTotals = context.api.cameraCoverageTotalsAtScenario(radius);
      const expectedArea = platform ? baseline.byPlatformName[platform].coveredAreaKm2 : baseline.totalCoveredAreaKm2;
      assert.equal(baselineTotals.coveredArea, expectedArea, 'Do not leak complete inventory coverage into original gap results');
      assert.equal(context.cameraCoverageSet, 'inventory', 'Baseline helpers must restore the combined dashboard universe');
    }
    context.api.renderCameraCoverageLayer();
    assert.equal(context.mapShapes.length, 2, 'Display dissolved outlines and metric census intersections');
    const displayed = context.mapShapes[0];
    const expectedGeometry = (cameraSet === 'inventory' ? context.inventoryCoverage : context.coverageGeometries).scenarios[radius].coverage;
    assert.equal(displayed.geometry, expectedGeometry);
    assert.equal(displayed.options.style.fillColor, '#e6b24f');
    assert.equal(displayed.options.style.fillOpacity, .5, 'Preserve the requested yellow radius fill');
    const clipped = context.mapShapes[1];
    assert.equal(clipped.geometry, context.coverageGeometries.censusClips[cameraSet][radius]);
    assert.equal(clipped.options.style.fillColor, '#e6b24f');
    assert.equal(clipped.options.style.fillOpacity, .16, 'Census intersections must have a subtler fill than the radius');
    assert.equal(clipped.options.style.weight, 1.8, 'Emphasize clipped census outlines');
    for (const populationMode of [false, true]) {
      context.populationMode = populationMode;
      const official = cameraSet === 'inventory' ? context.inventoryCoverage.scenarios[radius] : context.methodology.cameraScenarios[radius];
      for (const selected of [false, true]) {
        for (const feature of context.manzanaGeojsonCache.features) {
          const fraction = official.byMan[feature.properties.man] ?? 0;
          const style = context.api.coverageManzanaStyle(feature, selected);
          assert.equal(style.fillOpacity, 0, 'Neither coverage module may fill whole original census blocks');
          if (fraction > 0) {
            assert.equal(style.fillColor, '#e6b24f', 'Preserve the original golden census color');
            assert.equal(style.weight, selected ? 2 : 1.5, 'Emphasize intersected census outlines without filling whole blocks');
          }
        }
      }
    }
    for (const data of [territory, population]) {
      assert.ok(Math.abs(data.covered + data.uncovered - data.total) < 1e-8);
      assert.ok(Math.abs(data.coveredPct + data.uncoveredPct - 100) < 1e-8);
    }
    assert.ok(territory.covered >= previousArea);
    assert.ok(population.covered >= previousPopulation);
    previousArea = territory.covered;
    previousPopulation = population.covered;
    for (const populationMode of [false, true]) {
      context.populationMode = populationMode;
      context.api.renderCameraCoverageGraphics();
      context.api.renderCameraCoverageDetail();
      const graphic = context.elements.graphicAnalysis.innerHTML;
      const detail = context.elements.detail.innerHTML;
      assert.ok(graphic.includes(populationMode ? 'Población según cobertura' : 'Superficie según cobertura'));
      const firstCard = graphic.split('Incidentes dentro de cobertura potencial')[0];
      assert.ok(!firstCard.includes(populationMode ? 'km²' : 'Población'));
      assert.ok(!graphic.includes('Parcialmente cubierta'));
      assert.ok(detail.includes(populationMode ? 'habitantes' : 'km²'));
      const percentages = graphic.match(/--covered:([\d.]+)%;--partial:([\d.]+)%/);
      assert.equal(percentages[1], percentages[2], 'Donut must have only two non-overlapping parts');
      assert.equal(context.cameraCoverageScenario, radius, 'Scenario comparison changed selected radius');
      assert.equal(context.cameraCoverageSet, cameraSet, 'Scenario comparison changed selected camera universe');
      const rowCount = (graphic.match(/data-platform-row=/g) || []).length;
      assert.equal(rowCount, platform ? 1 : context.platforms.length);
      context.api.exportCameraCoverageCsv();
      const exportedRows = context.exportedCsv.split('\n');
      assert.equal(exportedRows.length - 1, rowCount);
      assert.ok(exportedRows[0].includes(populationMode ? 'Poblacion_habitantes' : 'Area_total_km2'));
      assert.ok(!exportedRows[0].includes(populationMode ? 'km2' : 'Poblacion'));
      assert.ok(context.exportedFilename.includes(populationMode ? 'poblacional' : 'territorial'));
      assert.ok(context.exportedFilename.includes(cameraSet === 'inventory' ? 'inventario-completo' : 'para-cambio'));
    }
    results.push({ cameraSet, platform: platform || 'Todas', radius, territory, population });
  }
}
}
for (const radius of [100, 150, 200]) {
  const study = results.find((r) => r.cameraSet === 'municipal' && r.platform === 'Todas' && r.radius === radius);
  const official = context.methodology.cameraScenarios[radius];
  assert.equal(study.territory.covered, official.totalCoveredAreaKm2, 'Original replacement coverage must be preserved');
  const inventory = results.find((r) => r.cameraSet === 'inventory' && r.platform === 'Todas' && r.radius === radius);
  assert.equal(inventory.territory.covered, context.inventoryCoverage.scenarios[radius].totalCoveredAreaKm2);
  assert.notEqual(inventory.population.covered, study.population.covered);
}
context.selectedPlatform = null;
context.cameraCoverageSet = 'inventory';
context.coverageMode = false;
const isolated = context.api.cameraCoverageTotals();
assert.equal(isolated.coveredArea, context.methodology.cameraScenarios[context.cameraCoverageScenario].totalCoveredAreaKm2, 'Non-coverage modules must retain the replacement universe');
const report = {
  validatedSelections: results.length,
  validatedModuleRenders: results.length * 2,
  unifiedInventory: {records: context.inventoryCameras.length, located: 99, replacement: 31, remainingLocated: 68, pending: 4},
  cameraAudit: {
    totalRecords: cameras.length,
    uniqueRecords: new Set(cameras.map((camera) => camera.id)).size,
    duplicates: cameras.length - new Set(cameras.map((camera) => camera.id)).size,
    domoRecords: cameras.filter((camera) => camera.type === 'DOMO').length,
    otherRecords: cameras.filter((camera) => camera.type !== 'DOMO').map((camera) => ({ id: camera.id, type: camera.type, institution: camera.institution, requiresChange: camera.requiresChange })),
    confirmedStudyRecords: 31,
    inventoryPreserved: true,
  },
  results: results.filter((row) => row.platform === 'Todas' || row.platform === 'PLATAFORMA I'),
};
console.log(JSON.stringify(report, null, 2));
