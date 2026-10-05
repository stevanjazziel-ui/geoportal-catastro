/* Reproducible preview: existing metric kernel, original points, no source writes. */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const zlib = require('node:zlib'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'data/seguridad-riobamba/kde-urbano-200m-20261005');
fs.mkdirSync(out, {recursive: true});
const window = {};
for (const f of ['visor-seguridad-riobamba-data.js', 'riobamba-cantonal-data.js', 'riobamba-conflictividad-data.js', 'riobamba-conflictividad.js']) {
  vm.runInNewContext(fs.readFileSync(path.join(root, f), 'utf8'), {window});
}
const api = window.RiobambaConflictivity, correction = window.RIOBAMBA_CONFLICTIVITY_CORRECTION;
const oldWindow = {RIOBAMBA_CONFLICTIVITY_CORRECTION: correction};
vm.runInNewContext(execFileSync('git', ['show', 'a4ebc5a:riobamba-conflictividad.js'], {cwd: root, encoding: 'utf8'}), {window: oldWindow});
const old = oldWindow.RiobambaConflictivity;
const events = api.applyDataset(window.RIOBAMBA_SECURITY_DATA).events;
const assignment = window.RIOBAMBA_CANTONAL_DATA.assignments;
const valid = p => [p.lat, p.lng, p.x, p.y].every(Number.isFinite) && Math.abs(p.lat) <= 90 && Math.abs(p.lng) <= 180 && !(p.lat === 0 && p.lng === 0);
const urban = events.filter(e => assignment[e.id]?.scope === 'URBANO').map(e => ({...e, ...assignment[e.id]}));
const eligible = urban.filter(e => e.hotspotEligible && valid(e));
const grid = correction.urbanGrid;
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
const results = {}, changes = new Set();
for (const category of categories) {
  const candidates = urban.filter(e => category === 'TODOS' || e.category === category);
  const points = eligible.filter(e => category === 'TODOS' || e.category === category);
  const surface = {...api.calculate(points, grid, 200), scope: 'URBANO'};
  surface.visual = api.visualStatistics(surface);
  const originalHash = crypto.createHash('sha256').update(Buffer.from(surface.density.buffer)).digest('hex');
  png(`${category}_200.png`, surface.density, value => api.urbanColor(value, surface.visual));
  assert.equal(crypto.createHash('sha256').update(Buffer.from(surface.density.buffer)).digest('hex'), originalHash);
  const oldH = correction.parameters.URBANO[category === 'TODOS' ? 'DELINCUENCIA' : category].bandwidth;
  const previous = old.calculate(points, grid, oldH);
  png(`${category}_anterior.png`, previous.density, old.color);
  assert.equal(api.urbanColor(surface.visual.p25, surface.visual)[3], 0);
  changes.add(originalHash);
  const peakIndex = surface.density.indexOf(surface.maxDensity);
  const peakX = grid.metricBounds[0][0] + (peakIndex % grid.width + .5) * grid.cellSize;
  const peakY = grid.metricBounds[1][1] - (Math.floor(peakIndex / grid.width) + .5) * grid.cellSize;
  const nearestPeakPoint = points.reduce((best, p) => !best || Math.hypot(p.x-peakX,p.y-peakY) < Math.hypot(best.x-peakX,best.y-peakY) ? p : best, null);
  results[category] = {category, used: points.length, excluded: candidates.length - points.length,
    bandwidth: 200, previousBandwidth: oldH, cellSize: grid.cellSize, crs: 'EPSG:32717', weight: 1,
    ...surface.visual, peakLocation: nearestPeakPoint && [nearestPeakPoint.lat, nearestPeakPoint.lng], densitySha256: originalHash, legend: api.legend(surface)};
  console.log(JSON.stringify(results[category]));
}
assert.equal(eligible.length, 9915); assert.equal(changes.size, 4);
// Preserve rural methods and palettes exactly; no rural raster is generated or written.
for (const c of categories.slice(1)) assert.equal(JSON.stringify(api.parameters('RURAL', c)), JSON.stringify(old.parameters('RURAL', c)));
for (const value of [0, .1, 1, 10, 100, 500, 1000, 10000]) assert.equal(JSON.stringify(api.color(value)), JSON.stringify(old.color(value)));
assert.equal(api.legend(), old.legend());
const sampleGrid = {width: 4, height: 4, cellSize: 20, metricBounds: [[0,0],[80,80]], mask: Array.from({length:16}, (_,i)=>i)};
const sample = [{id: '1', x:30, y:30}, {id:'2', x:30, y:30}];
assert.deepEqual(Array.from(api.calculate(sample, sampleGrid, 200).density), Array.from(old.calculate(sample, sampleGrid, 200).density));
assert(Math.abs(api.calculate(sample, sampleGrid, 200).density[9] - 2e6 / (2 * Math.PI * 200 ** 2 * (1 - Math.exp(-.5)))) < 1e-10);
const excluded = urban.filter(e => !e.hotspotEligible || !valid(e)).map(e => ({id:e.id,category:e.category, reason: !e.hotspotEligible ? 'CATEGORIA_NO_ANALITICA' : 'COORDENADA_INVALIDA'}));
fs.writeFileSync(path.join(out, 'CONTROL_KDE.json'), JSON.stringify({totalBase: events.length, urbanRecords: urban.length,
  outsideUrban: events.length - urban.length, invalidUrbanCoordinates: urban.filter(e=>!valid(e)).length,
  results, excluded, note: 'Los excluidos de TODOS son categorias institucionales/revision dentro del ambito urbano; rural/fuera de urbano se reportan separadamente.'}, null, 2));
const headings = ['category','used','excluded','bandwidth','cellSize','crs','minDensity','maxDensity','p25','p50','p75','p90','p95'];
fs.writeFileSync(path.join(out, 'CONTROL_KDE.csv'), headings.join(',') + '\n' + Object.values(results).map(r => headings.map(k => r[k]).join(',')).join('\n'));
const protectedFiles = execFileSync('git', ['ls-files', '*-data.js', 'riobamba-cantonal-data.js', 'riobamba-conflictividad-data.js', 'data/seguridad-riobamba/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA/*', 'riobamba-censo-data/*'], {cwd:root,encoding:'utf8'}).trim().split(/\r?\n/);
const unchanged = protectedFiles.map(file => {
  const before = execFileSync('git', ['rev-parse', `HEAD:${file}`], {cwd:root,encoding:'utf8'}).trim();
  const after = execFileSync('git', ['hash-object', file], {cwd:root,encoding:'utf8'}).trim();
  assert.equal(after,before, `Fuente protegida modificada: ${file}`); return file;
});
fs.writeFileSync(path.join(out, 'VALIDACION.json'), JSON.stringify({passed:true, ruralParametersAndColorsUnchanged:true,
  unitWeightVerified:true, rasterNotChangedByRendering:true, fourIndependentSurfaces:true, protectedFilesUnchanged:unchanged},null,2));
const payload = {results, bounds: grid.bounds, points: eligible.map(p=>[p.lat,p.lng,p.category]),
  platforms: JSON.parse(fs.readFileSync(path.join(root,'riobamba-censo-data/riobamba_plataformas.geojson'),'utf8'))};
const template = fs.readFileSync(path.join(__dirname,'kde_urban_review.html'),'utf8');
fs.writeFileSync(path.join(out,'index.html'), template.replace('/* REVIEW_DATA */', `const data = ${JSON.stringify(payload)};`));
fs.writeFileSync(path.join(out,'METODOLOGIA_KDE.md'), `# KDE urbano 200 m\n\nPuntos reales originales; universo urbano: union operativa de 18 Plataformas. Peso 1 por registro, preservando multiplicidad XY. Una malla de ${grid.cellSize} m EPSG:32717; kernel gaussiano truncado a 200 m normalizado a volumen 1; suma antes de mascara urbana. No agregacion ni normalizacion por Plataforma.\n\nPercentiles de las celdas positivas, recalculados por subconjunto; P25 transparente solo en imagen. Rampa continua YlOrRd en P25/P50/P75/P90/P95/maximo. Colores relativos al subconjunto: comparar valores numericos, no intensidad cromatica entre categorias. Densidad en eventos/km2, no significancia ni peligrosidad. Repeticion XY y localizacion sin validacion de campo son limitaciones.\n\nA reconstruye la representacion vigente del mismo subconjunto con el radio anterior y escala fija; TODOS es una referencia reconstruida porque antes no existia ese selector. B usa exactamente los mismos puntos, malla y kernel a 200 m. Rural, Gi*, coberturas, brechas y propuestas conservan sus datos. Radio 200 m solicitado no representa un optimo inferido.\n\nCONTROL_KDE.csv contiene los valores reales; CONTROL_KDE.json tambien lista exclusiones y motivos. Sin commit ni push.\n`);
if (process.argv.includes('--publish')) {
  const htmlFile = path.join(out, 'index.html');
  fs.writeFileSync(htmlFile, fs.readFileSync(htmlFile, 'utf8')
    .replace('comparación local', 'comparación y validación')
    .replace('Comparación local:', 'Comparación:').replace('Visor local', 'Visor'));
  const methodFile = path.join(out, 'METODOLOGIA_KDE.md');
  fs.writeFileSync(methodFile, fs.readFileSync(methodFile, 'utf8')
    .replace('Sin commit ni push.', 'Publicacion autorizada por el usuario el 5 de octubre de 2026. Comparacion anterior reconstruida desde a4ebc5a.'));
}
console.log(`Validated ${unchanged.length} protected files. Preview: ${out}/index.html`);
