const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8');
const window = {};
for (const name of ['visor-seguridad-riobamba-data.js','riobamba-cantonal-data.js','riobamba-conflictividad-data.js','riobamba-incidentes-spatial-data.js','riobamba-conflictividad.js']) vm.runInNewContext(read(name), {window});
const source = window.RIOBAMBA_SECURITY_DATA, correction = window.RIOBAMBA_CONFLICTIVITY_CORRECTION;
const engine = window.RiobambaConflictivity, territory = window.RIOBAMBA_CANTONAL_DATA;
const before = JSON.stringify(source), events = engine.applyDataset(source).events;
const totals = Object.fromEntries(engine.classes.map((name) => [name,events.filter((e) => e.category === name).length]));
assert.equal(JSON.stringify(source),before);
assert.deepEqual(totals, {DELINCUENCIA:2533,VIOLENCIA:1590,CONVIVENCIA:7027,ACTIVIDAD_INSTITUCIONAL:14778,OTROS_REVISION:788});
for (let i = 0; i < events.length; i++) {
  for (const key of ['id','subtype','date','parish','lat','lng','platform','weight','source']) assert.equal(events[i][key],source.events[i][key]);
  assert.ok(events[i].RECURRENCIA_XY >= 1);
}
for (const [name,hash] of Object.entries(correction.metadata.sourceHashes)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,name))).digest('hex'),hash,name);
const html = read('visor-seguridad-riobamba-v2.html');
for (const script of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(script[1]);
const extract = (text,start,end) => text.slice(text.indexOf(start),text.indexOf(end,text.indexOf(start)));
const element = () => ({value:'__ALL__'});
const context = {window, incidentSpatial:window.RIOBAMBA_INCIDENT_SPATIAL, platformGeojsonCache:true,
  elements:{category:element(),subtype:element(),parish:element(),kdePlatform:element(),kdePeriod:element(),incidentDate:{value:''}},
  api:{}, data:territory, items:[]};
vm.createContext(context);
vm.runInContext('const geoIncidentEvents = () => items; const eventWeight = () => 1; const assignment = (id) => data.assignments[id];\n'+
  extract(html,'      const giNormalCdf =','      const giClassRank =')+
  extract(html,'      let giHotspotCache =','      const categorySummary =')+
  extract(read('riobamba-cantonal-view.js'),'  function giResult(','  function ruralGi()')+
  '\nthis.urbanGi = getGiHotspotAnalysis; this.ruralResult = giResult; this.api.giNormalCdf = giNormalCdf;',context);
const report = [];
for (const scope of ['URBANO','RURAL']) for (const category of engine.classes.slice(0,3)) {
  const items = events.filter((e) => e.category === category && territory.assignments[e.id].scope === scope);
  const parameter = engine.parameters(scope,category), grid = scope === 'URBANO' ? correction.urbanGrid : territory.kdeGrids.RURAL;
  assert.equal(items.length,parameter.records);
  const points = items.map((e) => ({id:e.id,x:territory.assignments[e.id].x,y:territory.assignments[e.id].y}));
  const surface = engine.calculate(points,grid,parameter.bandwidth);
  const expected = correction.evaluations.find((r) => r.scope === scope && r.category === category && r.recommended);
  assert.ok(Math.abs(surface.maxDensity-expected.maxDensityEventsKm2)/expected.maxDensityEventsKm2 < 1e-5,`${scope}/${category} KDE disagrees with Python`);
  const candidates = correction.evaluations.filter((r) => r.scope === scope && r.category === category);
  assert.equal(candidates.length,scope === 'URBANO' ? 6 : 5);
  assert.equal(parameter.bandwidth,[...candidates].sort((a,b) => b.cvMeanLogLikelihood-a.cvMeanLogLikelihood || a.bandwidth-b.bandwidth)[0].bandwidth);
  context.items = items; context.elements.category.value = category;
  const cells = scope === 'URBANO' ? context.urbanGi().cells : context.ruralResult(territory.ruralGrid,items);
  const reference = correction.gi[scope][category];
  assert.equal(cells.reduce((sum,c) => sum+c.incCount,0),items.length);
  cells.forEach((cell,i) => {
    const r = reference.results[i];
    assert.equal(cell.incCount,r.COUNT);
    assert.ok(Math.abs(cell.zScore-r.GI_ZSCORE) <= .00051);
    assert.ok(Math.abs(cell.pValue-r.GI_PVALUE) <= .000051);
    assert.equal(cell.giClass.replace(' %','%'),r.GI_CLASS);
  });
  report.push({scope,category,records:items.length,bandwidth:parameter.bandwidth,maxDensity:surface.maxDensity,giLevels:reference.levels});
}
const grid = correction.urbanGrid, p = events.find((e) => e.hotspotEligible && territory.assignments[e.id].scope === 'URBANO');
const xy = territory.assignments[p.id];
const single = engine.calculate([xy],grid,300), repeated = engine.calculate([xy,xy,xy],grid,300);
assert.ok(Math.abs(repeated.maxDensity-single.maxDensity*3) < 1e-9);
assert.equal(engine.calculate([],grid,300).maxDensity,0);
assert.equal(engine.color(0)[3],0);
assert.equal(correction.derivedDiagnosis.summary.mappedIncidentsAssigned,9915);
assert.equal(correction.derivedDiagnosis.summary.incidentSpatialQuality.conflictRows,11150);
assert.equal(correction.derivedDiagnosis.summary.incidentSpatialQuality.notUsedForSpatialAnalysis,15566);
assert.equal(correction.derivedDiagnosis.platformMaster.reduce((s,p) => s+p.incidents,0),9915);
assert.equal(correction.derivedMethodology.urbanCounts['1'],2229);
assert.equal(correction.centralAudit.publishedRecordsReclassifiedInstitutionalGlobal,4);
assert.equal(correction.centralAudit.publishedUrbanRecordsReclassifiedInstitutional,2);
const originals = {};
for (const name of ['riobamba-seguridad-diagnostico-data.js','riobamba-metodologia-data.js']) vm.runInNewContext(read(name),{window:originals});
for (const platform of correction.derivedDiagnosis.platformMaster) {
  const original = originals.RIOBAMBA_SECURITY_DIAGNOSIS.byPlatformName[platform.platformName];
  for (const key of Object.keys(original).filter((k) => /^(population$|area|density|cameras|cameraTotal$|policeInfrastructure$|avgPopulationDistancePoliceM$)/i.test(k))) assert.equal(JSON.stringify(platform[key]),JSON.stringify(original[key]),`${platform.platformName}.${key}`);
}
for (const radius of ['100','150','200']) {
  const original = originals.RIOBAMBA_METHODOLOGY.cameraScenarios[radius];
  const updated = correction.derivedMethodology.cameraScenarios[radius];
  for (const key of ['totalAreaKm2','totalCoveredAreaKm2','totalManzanas','coveredManzanas','byMan','byCell']) assert.equal(JSON.stringify(updated[key]),JSON.stringify(original[key]),`Camera geometry changed: ${radius}/${key}`);
}
const output = {sourceImmutable:true,originalCoordinatesPreserved:true,weight:1,totals,cases:report,emptyAndCoincidentChecks:true,sharedColorReference:correction.colorReference};
fs.writeFileSync(path.join(root,'data/seguridad-riobamba/correccion-conflictividad-20261001/VALIDACION_CALCULOS.json'),JSON.stringify(output,null,2));
console.log(JSON.stringify(output,null,2));
