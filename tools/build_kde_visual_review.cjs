/* A/B/C render audit: one immutable density raster, three color/alpha mappings. */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const zlib = require('node:zlib'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'data/seguridad-riobamba/kde-visual-abc-20261005');
fs.mkdirSync(out, {recursive: true});
const window = {};
for (const file of ['visor-seguridad-riobamba-data.js', 'riobamba-cantonal-data.js', 'riobamba-conflictividad-data.js', 'riobamba-conflictividad.js']) {
  vm.runInNewContext(fs.readFileSync(path.join(root, file), 'utf8'), {window});
}
const api = window.RiobambaConflictivity, correction = window.RIOBAMBA_CONFLICTIVITY_CORRECTION;
const oldWindow = {RIOBAMBA_CONFLICTIVITY_CORRECTION: correction};
const baseline = execFileSync('git', ['show', 'ddfdccd:riobamba-conflictividad.js'], {cwd: root, encoding: 'utf8'});
vm.runInNewContext(baseline, {window: oldWindow});
const old = oldWindow.RiobambaConflictivity;
const current = fs.readFileSync(path.join(root, 'riobamba-conflictividad.js'), 'utf8');
const kernel = text => text.slice(text.indexOf('  function calculate('), text.indexOf('  function color(')).replaceAll('\r\n', '\n');
assert.equal(kernel(current), kernel(baseline), 'Numerical KDE kernel must remain unchanged');
const events = api.applyDataset(window.RIOBAMBA_SECURITY_DATA).events;
const assignments = window.RIOBAMBA_CANTONAL_DATA.assignments;
const urban = events.filter(e => assignments[e.id]?.scope === 'URBANO').map(e => ({...e, ...assignments[e.id]}));
const valid = p => [p.lat, p.lng, p.x, p.y].every(Number.isFinite) && Math.abs(p.lat) <= 90 && Math.abs(p.lng) <= 180;
const eligible = urban.filter(e => e.hotspotEligible && valid(e));
const grid = correction.urbanGrid;
const hashDensity = s => crypto.createHash('sha256').update(Buffer.from(s.density.buffer)).digest('hex');
const crc = bytes => {
  let c = 0xffffffff;
  for (const b of bytes) { c ^= b; for (let n = 0; n < 8; n++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0); }
  return (c ^ 0xffffffff) >>> 0;
};
function png(file, density, color) {
  const raw = Buffer.alloc((grid.width * 4 + 1) * grid.height);
  grid.warpIndex.forEach((source, i) => {
    if (source >= 0) raw.set(color(density[source]), Math.floor(i / grid.width) * (grid.width * 4 + 1) + 1 + (i % grid.width) * 4);
  });
  const chunk = (name, payload) => {
    const result = Buffer.alloc(payload.length + 12);
    result.writeUInt32BE(payload.length); result.write(name, 4); payload.copy(result, 8);
    result.writeUInt32BE(crc(result.subarray(4, -4)), result.length - 4); return result;
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(grid.width); header.writeUInt32BE(grid.height, 4); header[8] = 8; header[9] = 6;
  fs.writeFileSync(path.join(out, file), Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]));
}
const categories = ['TODOS', 'DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA'];
const results = {}, hashes = new Set();
for (const category of categories) {
  const candidates = urban.filter(e => category === 'TODOS' || e.category === category);
  const points = eligible.filter(e => category === 'TODOS' || e.category === category);
  const surface = {...api.calculate(points, grid, 200), scope: 'URBANO'};
  surface.visual = api.visualStatistics(surface);
  const stats = surface.visual, before = hashDensity(surface);
  assert.equal(hashDensity(old.calculate(points, grid, 200)), before);
  png(`${category}_A.png`, surface.density, value => {
    const rgba = old.urbanColor(value, stats); rgba[3] = Math.round(rgba[3] * .68); return rgba;
  });
  png(`${category}_B.png`, surface.density, value => api.urbanColor(value, stats, 25));
  png(`${category}_C.png`, surface.density, value => api.urbanColor(value, stats, 30));
  assert.equal(hashDensity(surface), before);
  assert.equal(api.urbanColor(stats.p25, stats, 25)[3], 0);
  assert.equal(api.urbanColor(stats.p30, stats, 30)[3], 0);
  let veilB = 0, veilC = 0, secondaryPeaks = 0, retainedB = 0, retainedC = 0;
  for (const i of grid.mask) {
    const value = surface.density[i];
    if (value > 0 && value <= stats.p50) {
      veilB += api.urbanColor(value, stats, 25)[3] / 255;
      veilC += api.urbanColor(value, stats, 30)[3] / 255;
    }
    if (value < stats.p50 || value <= 0) continue;
    const x = i % grid.width, y = Math.floor(i / grid.width);
    let maximum = true, strict = false;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (!dx && !dy || x + dx < 0 || x + dx >= grid.width || y + dy < 0 || y + dy >= grid.height) continue;
      const other = surface.density[(y + dy) * grid.width + x + dx];
      if (other > value) maximum = false;
      if (other < value) strict = true;
    }
    if (maximum && strict) {
      secondaryPeaks++;
      retainedB += api.urbanColor(value, stats, 25)[3] > 0;
      retainedC += api.urbanColor(value, stats, 30)[3] > 0;
    }
  }
  const selected = veilC < veilB && retainedC === secondaryPeaks ? 'C' : 'B';
  assert.equal(selected, 'C', 'Review P30 visually if it fails to preserve secondary peaks');
  hashes.add(before);
  results[category] = {category, used: points.length, excluded: candidates.length - points.length,
    bandwidth: 200, cellSize: grid.cellSize, crs: 'EPSG:32717', weight: 1, ...stats,
    selected, veilB, veilC, veilReductionPct: (1 - veilC / veilB) * 100,
    secondaryPeaks, retainedB, retainedC, densitySha256: before, legend: api.legend(surface)};
  console.log(JSON.stringify({...results[category], legend: undefined}));
}
assert.equal(eligible.length, 9915); assert.equal(hashes.size, 4);
for (const c of categories.slice(1)) assert.equal(JSON.stringify(api.parameters('RURAL', c)), JSON.stringify(old.parameters('RURAL', c)));
for (const v of [0, .1, 1, 10, 100, 500, 1000, 10000]) assert.equal(JSON.stringify(api.color(v)), JSON.stringify(old.color(v)));
assert.equal(api.legend(), old.legend());
const protectedFiles = execFileSync('git', ['ls-files', '*-data.js', 'data/seguridad-riobamba/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA/*', 'riobamba-censo-data/*'], {cwd:root,encoding:'utf8'}).trim().split(/\r?\n/);
for (const file of protectedFiles) {
  assert.equal(execFileSync('git', ['hash-object', file], {cwd:root,encoding:'utf8'}).trim(), execFileSync('git', ['rev-parse', `HEAD:${file}`], {cwd:root,encoding:'utf8'}).trim(), file);
}
const html = fs.readFileSync(path.join(root, 'visor-seguridad-riobamba-v2.html'), 'utf8');
const oldHtml = execFileSync('git', ['show', 'HEAD:visor-seguridad-riobamba-v2.html'], {cwd:root,encoding:'utf8',maxBuffer:5000000});
const gi = text => text.slice(text.indexOf('      const giClass ='), text.indexOf('      const categorySummary')).replaceAll('\r\n', '\n');
assert.equal(gi(html), gi(oldHtml), 'Gi* classification and calculations unchanged');
assert.equal(fs.readFileSync(path.join(root, 'riobamba-cantonal-view.js'), 'utf8').replaceAll('\r\n','\n'), execFileSync('git', ['show', 'HEAD:riobamba-cantonal-view.js'], {cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n'));
const payload = {results, bounds: grid.bounds, points: eligible.map(p=>[p.lat,p.lng,p.category]),
  platforms: JSON.parse(fs.readFileSync(path.join(root,'riobamba-censo-data/riobamba_plataformas.geojson'),'utf8'))};
fs.writeFileSync(path.join(out, 'CONTROL_KDE.json'), JSON.stringify({totalBase:events.length, urbanRecords:urban.length, outsideUrban:events.length-urban.length, results}, null, 2));
const headings = ['category','used','excluded','crs','bandwidth','cellSize','minDensity','maxDensity','p25','p30','p50','p75','p90','p95','selected','veilReductionPct','secondaryPeaks','retainedC'];
fs.writeFileSync(path.join(out, 'CONTROL_KDE.csv'), headings.join(',') + '\n' + Object.values(results).map(r=>headings.map(k=>r[k]).join(',')).join('\n'));
fs.writeFileSync(path.join(out, 'VALIDACION.json'), JSON.stringify({passed:true,kernelUnchanged:true,GiUnchanged:true,ruralUnchanged:true,protectedFiles:protectedFiles.length,fourDistinctRasters:true,allDensityHashesIdenticalBeforeAfter:true},null,2));
fs.writeFileSync(path.join(out, 'METODOLOGIA_VISUAL.md'), '# Representacion KDE A/B/C\n\nA: version publicada ddfdccd, mismo bandwidth 200 m y raster numerico, con la opacidad global anterior 0.68. B: P25 transparente; C: P30 transparente. Cada categoria usa su propio raster y sus percentiles de valores positivos. C reduce la suma de opacidad de las celdas positivas <=P50 respecto de B, conservando todos los maximos locales >=P50 (vecindad inmediata de ocho celdas). Es un control visual descriptivo, no una prueba estadistica ni un criterio de peligrosidad.\n\nRampa continua YlOrRd con alpha 0/65/115/165/200/215 en P30/P50/P75/P90/P95/max. Opacidad maxima 84.3%; no se aplica otra opacidad global ni suavizado. Densidades en eventos/km2; EPSG:32717, celda 20 m, kernel y peso 1 originales. No cambia ningun valor ni dato original. Los colores relativos no comparan magnitudes absolutas entre categorias.\n\nTODOS: excluye categorias institucionales/revision urbanas; fuera del ambito urbano se reporta separadamente. Gi*, rural, camaras, corredores, brechas y geometrías quedan intactos. Sin commit ni push.\n');
fs.writeFileSync(path.join(out, 'index.html'), fs.readFileSync(path.join(__dirname, 'kde_visual_review.html'), 'utf8').replace('/* REVIEW_DATA */', `const data = ${JSON.stringify(payload)};`));
if (process.argv.includes('--publish')) {
  const file = path.join(out, 'METODOLOGIA_VISUAL.md');
  fs.writeFileSync(file, fs.readFileSync(file, 'utf8').replace('Sin commit ni push.', 'Publicacion autorizada por el usuario el 5 de octubre de 2026, despues de revisar A/B/C.'));
}
console.log(`PASS: ${protectedFiles.length} protected files, 4 independent unchanged densities. Preview: ${out}/index.html`);
