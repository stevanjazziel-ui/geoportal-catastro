const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const context = {window: {}};
vm.runInNewContext(fs.readFileSync(path.join(root, 'riobamba-brechas-actualizadas-data.js'), 'utf8'), context);
const data = context.window.RIOBAMBA_UPDATED_GAPS;
assert.equal(data.metadata.located, 103);
assert.equal(data.metadata.uniqueSites, 100);
assert.equal(data.inventoryCameraOverlay.length, 103);
assert.equal(data.inventoryCameraOverlay.filter(c => c.requiresChange).length, 31);
const classify = (coverage, population, problem) => {
  if (coverage == null || !population || !problem) return 'SIN EVIDENCIA';
  const supported = ['MEDIA', 'ALTA'].includes(population);
  const low = coverage < data.metadata.method.coverageLow;
  const partial = !low && coverage <= data.metadata.method.coverageHigh;
  if (low && supported && problem === 'ALTA') return 'ALTA';
  if (supported && ((low && problem === 'MEDIA') || (partial && problem === 'ALTA'))) return 'MEDIA';
  return 'BAJA';
};
for (const radius of [100, 150, 200]) {
  for (const scenario of ['A', 'B', 'C', 'REEMPLAZO_31']) {
    const result = data.scenarios[radius][scenario];
    const counts = Object.fromEntries(Object.keys(result.gapCounts).map(k => [k, 0]));
    for (const row of Object.values(result.byMan)) {
      assert.equal(row.level, classify(row.urban ? row.coveragePct : null, row.populationLevel, row.problem));
      assert.ok(row.coveragePct >= 0 && row.coveragePct <= 100);
      if (row.urban) counts[row.level]++;
    }
    assert.deepEqual(JSON.parse(JSON.stringify(result.gapCounts)), counts);
    assert.equal(Object.values(counts).reduce((a, b) => a + b, 0), 2825);
  }
  for (const coverage of [data.replacementScenarios[radius], data.inventoryCoverage.scenarios[radius]]) {
    assert.equal(Object.keys(coverage.byCell).length, Object.keys(data.inventoryCoverage.scenarios[200].byCell).length);
    assert.ok(coverage.totalCoveredAreaKm2 <= coverage.totalAreaKm2);
    for (const row of Object.values(coverage.byPlatformName)) {
      assert.equal(row.coveredPopulation + row.uncoveredPopulation, row.population);
      assert.ok(row.coveredAreaKm2 <= row.areaKm2 + 1e-8);
    }
  }
}
for (const [file, hash] of Object.entries(data.metadata.sourceHashes)) {
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'), hash, file);
}
for (const file of ['riobamba-deficit-inventario.js', 'riobamba-camaras-propuesta.js']) new vm.Script(fs.readFileSync(path.join(root, file), 'utf8'), {filename: file});
const html = fs.readFileSync(path.join(root, 'visor-seguridad-riobamba-v2.html'), 'utf8');
for (const script of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) new vm.Script(script[1]);
assert.ok(html.includes('let diagnosisMetric = "cameraProposal"'));
assert.ok(html.includes('activateDiagnosisMetric("cameraProposal");'));
assert.ok(html.includes('id="cameraProposalMode"'));
const sidebar = html.match(/<nav\b[\s\S]*?<\/nav>/)[0];
assert.ok(!/<summary>(Detalle territorial|Descargas)<\/summary>/.test(sidebar));
assert.ok(sidebar.includes('id="cameraProposalMode"'));
assert.ok(!html.includes('99 ubicaciones aproximadas · 4 sin coordenadas'));
console.log('PASS: 12 scenarios, all block rules, coverage totals, source hashes, JS syntax and proposal startup.');
console.log(JSON.stringify(data.scenarios[200].A.gapCounts));
console.log(JSON.stringify(data.scenarios[200].B.gapCounts));
console.log(JSON.stringify(data.scenarios[200].C.gapCounts));
