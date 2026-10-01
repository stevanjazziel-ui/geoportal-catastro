const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const folder = 'data/seguridad-riobamba/revision-metodologica-20261001';
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const load = (file, key) => { const c = {window:{}}; vm.runInNewContext(read(file),c); return c.window[key]; };
const security = load('visor-seguridad-riobamba-data.js','RIOBAMBA_SECURITY_DATA');
const methodology = load('riobamba-metodologia-data.js','RIOBAMBA_METHODOLOGY');
const diagnosis = load('riobamba-seguridad-diagnostico-data.js','RIOBAMBA_SECURITY_DIAGNOSIS');
const police = load('riobamba-accesibilidad-policial-data.js','RIOBAMBA_POLICE_ACCESSIBILITY');
const audit = JSON.parse(read(`${folder}/AUDITORIA_Y_CLASIFICACION.json`));
for (const file of ['riobamba-camaras-data.js','riobamba-censo-data/riobamba_plataformas.geojson','riobamba-censo-data/riobamba_manzanas_stats.json']) {
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),audit.sourceHashes[file],`Original changed: ${file}`);
}
assert.equal(security.events.length,26716);
assert.equal(new Set(security.events.map(e=>e.id)).size,26716);
const totals = Object.fromEntries([1,2,3,4,5].map(i=>[i,security.events.filter(e=>e.analyticalClassId===i).length]));
assert.deepEqual(totals,{'1':2503,'2':1563,'3':6976,'4':14770,'5':904});
assert.equal(methodology.urbanReferencePopulation,177213);
for (const id of [1,2,3]) {
  const events = security.events.filter(e=>e.analyticalClassId===id && e.platform);
  assert.equal(events.length,methodology.urbanCounts[id]);
  assert.equal(events.length / 177213 * 100000,methodology.urbanRates100000[id]);
}
const scenarioReport = [];
for (const radius of [100,150,200]) {
  const scenario = methodology.cameraScenarios[radius];
  assert.ok(scenario.totalCoveredAreaKm2 <= scenario.totalAreaKm2);
  for (const [name,row] of Object.entries(scenario.byPlatformName)) {
    assert.equal(row.population,diagnosis.byPlatformName[name].population);
    assert.equal(row.coveredPopulation + row.uncoveredPopulation,row.population);
    assert.ok(row.coveredAreaKm2 <= row.areaKm2);
    assert.ok(Math.abs(row.coveredPopulation-diagnosis.byPlatformName[name][`cameraCoveredPopulation${radius}`]) <= 1);
    for (const id of [1,2,3]) assert.ok(row.incidentsByClass[id].covered <= row.incidentsByClass[id].total);
    assert.ok(row.exposedUncoveredPopulation250 <= row.uncoveredPopulation + 1);
  }
  const allRows = Object.values(scenario.byPlatformName);
  const population = allRows.reduce((s,r)=>s+r.population,0);
  const coveredPopulation = allRows.reduce((s,r)=>s+r.coveredPopulation,0);
  for (const cell of Object.values(scenario.byCell)) assert.ok(cell.uncoveredPopulation >= 0 && cell.uncoveredPopulation <= cell.population + 1e-8);
  scenarioReport.push({radius,totalAreaKm2:scenario.totalAreaKm2,coveredAreaKm2:scenario.totalCoveredAreaKm2,territoryPct:scenario.totalCoveredAreaKm2/scenario.totalAreaKm2*100,population,coveredPopulation,populationPct:coveredPopulation/population*100,incidentsCovered:Object.fromEntries([1,2,3].map(id=>[id,allRows.reduce((s,r)=>s+r.incidentsByClass[id].covered,0)]))});
}
assert.equal(police.crs,'EPSG:32717 calculo metrico / EPSG:4326 visualizacion');
assert.equal(police.summary.population,171998);
for (const row of police.table) assert.equal(['POB_0_250','POB_250_500','POB_500_1000','POB_1000_2000','POB_MAS_2000'].reduce((s,k)=>s+row[k],0),row.POBLACION);
const html = read('visor-seguridad-riobamba-v2.html');
const extract = (start,end) => {const a=html.indexOf(start),b=html.indexOf(end,a);assert.ok(a>=0&&b>a);return html.slice(a,b);};
const element = () => ({value:'__ALL__'});
const ctx = {cantonalController:null,events:security.events,methodology,platforms:diagnosis.platformMaster,key:'incidence',selectedPlatform:null,
  elements:{search:{value:''},category:element(),subtype:element(),parish:element(),kdePlatform:element(),kdePeriod:element(),incidentDate:{value:''},precision:element(),source:element(),summary:{},graphicAnalysis:{}},
  document:{querySelectorAll:()=>[]},fmt:String,esc:String,categoryPalette:['#111','#222','#333'],metricBars:(title,rows)=>JSON.stringify({title,rows}),clean:s=>String(s).toLowerCase()};
vm.createContext(ctx);
vm.runInContext('const analysisKey=()=>key; const incidentInput=()=>["incidence","kde","giHotspots"].includes(key)?events.filter(e=>[1,2,3].includes(e.analyticalClassId)):events; const filteredPlatforms=()=>platforms;\n'+extract('      const analysisConfig =','      const layerConfig =')+extract('      let eventFilterCache =','      const incidenceRows =')+extract('      const incidenceRows =','      const incidentCoverageHtml =')+'\nthis.api={filteredEvents,incidenceRows,renderIncidence};',ctx);
const filterReport=[];
for (const category of ['__ALL__','DELINCUENCIA','VIOLENCIA','CONVIVENCIA / INCIVILIDADES']) {
  ctx.elements.category.value=category;
  const rows = ctx.api.filteredEvents();
  const expected = security.events.filter(e=>e.platform&&[1,2,3].includes(e.analyticalClassId)&&(category==='__ALL__'||e.category===category));
  assert.equal(rows.length,expected.length);
  ctx.api.renderIncidence();
  assert.ok(ctx.elements.summary.innerHTML.includes(String(rows.length)));
  filterReport.push({category,records:rows.length});
}
ctx.elements.category.value='DELINCUENCIA';ctx.elements.kdePlatform.value='K';ctx.api.renderIncidence();
const k=methodology.byPlatformName['PLATAFORMA K'];
assert.equal(k.counts[1],372);assert.equal(k.population,12255);
assert.equal(ctx.api.incidenceRows()[0].rates[0],372/12255*1000);
assert.ok(ctx.elements.summary.innerHTML.includes('30.35'));
ctx.elements.kdePlatform.value='__ALL__';ctx.elements.subtype.value='Robo a domicilio';
assert.equal(ctx.api.filteredEvents().length,153);
ctx.elements.subtype.value='__ALL__';ctx.elements.category.value='ACTIVIDAD INSTITUCIONAL / POLICIAL';ctx.key='typologies';
assert.equal(ctx.api.filteredEvents().length,13134);
ctx.key='giHotspots';assert.equal(ctx.api.filteredEvents().length,0);
const report={classTotals:totals,urbanScope:methodology.urbanScope,urbanCounts:methodology.urbanCounts,urbanRates100000:methodology.urbanRates100000,manualPlatformK:{population:k.population,delinquency:k.counts[1],formula:'372 / 12255 * 1000',rate:372/12255*1000},scenarios:scenarioReport,filters:filterReport,policePopulation:police.summary.population,originalCameraAndCensusHashesPreserved:true,ambiguousSubtypesExcluded:audit.reviewSubtypes,commitAndPush:false};
fs.writeFileSync(path.join(root,folder,'VALIDACION_METODOLOGICA.json'),JSON.stringify(report,null,2)+'\n');
const table='| Subtipo | Registros | Clasificación anterior | Clasificación aplicada | Estado |\n| --- | ---: | --- | --- | --- |\n'+audit.classification.map(r=>`| ${r.SUBTIPO} | ${r.NUMERO_REGISTROS} | ${r.CLASIFICACION_ANTERIOR} | ${r.CLASIFICACION_NUEVA_PROPUESTA} | ${r.CLASE_PROPUESTA===5?'Fuera del análisis; revisión pendiente':'Clasificación analítica operativa'} |`).join('\n');
fs.writeFileSync(path.join(root,folder,'CLASIFICACION_APLICADA.md'),'# Clasificación analítica aplicada\n\nContinuación autorizada conservando los subtipos ambiguos fuera de los análisis. No es clasificación judicial. La revisión de 39 subtipos (848 registros) sigue pendiente; la clase Otros/revisión contiene además 56 registros no analíticos.\n\n'+table+'\n');
console.log(JSON.stringify(report,null,2));
