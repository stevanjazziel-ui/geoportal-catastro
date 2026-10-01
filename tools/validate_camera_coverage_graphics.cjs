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
  operationalMunicipalCameras: [],
  cameraCoverageSet: 'municipal', cameraCoverageScenario: 150,
  cameraCoverageCache: null, cameraCoverageCacheKey: '',
  selectedPlatform: null, populationMode: false,
  platformGeojsonCache: json('riobamba-censo-data/riobamba_plataformas.geojson'),
  manzanaGeojsonCache: json('riobamba-censo-data/riobamba_manzanas.geojson'),
  platformStats: json('riobamba-censo-data/riobamba_plataformas_stats.json'),
  manzanaStats: json('riobamba-censo-data/riobamba_manzanas_stats.json'),
  elements: { graphicAnalysis: {}, detail: {}, detailTitle: {} },
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
  const manzanaPopulation = (feature) => Number(manzanaStats.byMan[feature.properties.man]?.population_total || 0);
` +
  extract('      const pointInRing =', '      const platformMaskRings =') +
  extract('      const coveragePercent =', '      const syncCoverageControls =') +
  extract('      const incidentCoverageHtml =', '      function renderGapMetrics()') +
  extract('      const ringAreaKm2 =', '      const eventPlatformName =') +
  extract('      const ringBounds =', '      const coverageManzanaStyle =') +
  extract('      const getCameraCoverageAnalysis =', '      const platformFilterValue =').replace('const getCameraCoverageAnalysis =', 'const computeCameraCoverageAnalysis =') +
  `
    const scenarioAnalyses = new Map();
    const getCameraCoverageAnalysis = () => {
      const key = cameraCoverageScenario;
      if (!scenarioAnalyses.has(key)) scenarioAnalyses.set(key, computeCameraCoverageAnalysis());
      return scenarioAnalyses.get(key);
    };
  ` +
  extract('      function cameraCoverageRows()', '      function renderBoulevardGraphics()') +
  extract('      function renderCameraCoverageDetail()', '      function renderConflictModuleDetail()') +
  '\nthis.api = { cameraCoverageTotals, coverageTerritorialData, coveragePopulationData, cameraCoverageRows, renderCameraCoverageGraphics, renderCameraCoverageDetail, exportCameraCoverageCsv };', context);

const results = [];
for (const platform of [null, ...context.platforms.map((row) => row.platformName)]) {
  context.selectedPlatform = platform;
  let previousArea = -1;
  let previousPopulation = -1;
  for (const radius of [100, 150, 200]) {
    context.cameraCoverageScenario = radius;
    const totals = context.api.cameraCoverageTotals();
    const territory = context.api.coverageTerritorialData(totals);
    const population = context.api.coveragePopulationData(totals);
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
      const rowCount = (graphic.match(/data-platform-row=/g) || []).length;
      assert.equal(rowCount, platform ? 1 : context.platforms.length);
      context.api.exportCameraCoverageCsv();
      const exportedRows = context.exportedCsv.split('\n');
      assert.equal(exportedRows.length - 1, rowCount);
      assert.ok(exportedRows[0].includes(populationMode ? 'Poblacion_habitantes' : 'Area_total_km2'));
      assert.ok(!exportedRows[0].includes(populationMode ? 'km2' : 'Poblacion'));
      assert.ok(context.exportedFilename.includes(populationMode ? 'poblacional' : 'territorial'));
    }
    results.push({ platform: platform || 'Todas', radius, territory, population });
  }
}
const report = {
  validatedSelections: results.length,
  validatedModuleRenders: results.length * 2,
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
