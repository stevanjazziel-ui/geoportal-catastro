const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'data/seguridad-riobamba/correccion-conflictividad-20261001');
const load = (file, key) => {
  const context = {window: {}};
  vm.runInNewContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  return context.window[key];
};
const fingerprint = file => crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex');
const protectedFiles = [
  'visor-seguridad-riobamba-data.js', 'visor-seguridad-riobamba-v2.html',
  'riobamba-cantonal-data.js', 'riobamba-cantonal-view.js',
  'riobamba-seguridad-kde-validacion-data.js', 'riobamba-incidentes-spatial-data.js',
  'riobamba-metodologia-data.js', 'riobamba-camaras-data.js',
  'riobamba-censo-data/riobamba_plataformas.geojson',
];
const hashes = Object.fromEntries(protectedFiles.map(file => [file, fingerprint(file)]));
const source = load('visor-seguridad-riobamba-data.js', 'RIOBAMBA_SECURITY_DATA');
const spatial = load('riobamba-cantonal-data.js', 'RIOBAMBA_CANTONAL_DATA');
const events = source.events;
const existingKde = load('riobamba-seguridad-kde-validacion-data.js', 'RIOBAMBA_KDE_VALIDATION');
const sourceById = new Map(events.map(e => [e.id,e]));
const existingKdeClasses = Object.fromEntries([1,2,3,4,5].map(id => [id,0]));
for (const point of existingKde.kdeInputPoints) {
  const event = sourceById.get(point.id);
  assert.ok(event, `Unknown published KDE ID ${point.id}`);
  existingKdeClasses[event.analyticalClassId]++;
}
assert.equal(existingKdeClasses[4]+existingKdeClasses[5],0,'Published KDE has institutional/review leakage');
const names = {1:'DELINCUENCIA', 2:'VIOLENCIA', 3:'CONVIVENCIA', 4:'ACTIVIDAD_INSTITUCIONAL', 5:'OTROS_REVISION'};
const expected = {DELINCUENCIA:2533, VIOLENCIA:1590, CONVIVENCIA:7027, ACTIVIDAD_INSTITUCIONAL:14778, OTROS_REVISION:788};
const expectedScopes = {URBANO:24271, RURAL:2445, SIN_ASIGNAR:0};
const expectedAnalyticalScopes = {URBANO:{DELINCUENCIA:2280,VIOLENCIA:1328,CONVIVENCIA:6530}, RURAL:{DELINCUENCIA:253,VIOLENCIA:262,CONVIVENCIA:497}};

// Exact original subtype keys, never substring matches or inferred target-count fitting.
const changes = new Map([
  ['Comercialización de sustancias sujetas a fiscalización', 1],
  ['Tenencia ilícita de sustancias sujetas a fiscalización', 1],
  ['Tenencia y porte de arma blanca o cortopunzante', 1],
  ['Tenencia y porte de armas de fuego', 1],
  ['Persona herida con arma blanca', 2],
  ['Persona herida con arma de fuego', 2],
  ['Persona herida con objeto contundente', 2],
  ['Disparos', 2],
  ['Trata de personas', 2],
  ['Consumo de sustancias sujetas a fiscalización', 3],
  ['Bomberos', 5],
]);
const counts = items => Object.fromEntries(Object.values(names).map(name => [name, items.filter(e => e.CATEGORIA_ANALITICA === name).length]));
const coordinateKey = e => JSON.stringify([e.lng, e.lat]);
const xyCounts = new Map();
for (const e of events) xyCounts.set(coordinateKey(e), (xyCounts.get(coordinateKey(e)) || 0) + 1);
const flag = n => n >= 30 ? 'MUY_ALTA_REPETICION' : n >= 10 ? 'ALTA_REPETICION' : n >= 2 ? 'REPETIDA' : 'NORMAL';
const subtypes = new Map();
for (const e of events) {
  const current = subtypes.get(e.subtype) || {SUBTIPO:e.subtype, N_REGISTROS:0, CLASE_ACTUAL:e.analyticalClassId};
  assert.equal(current.CLASE_ACTUAL, e.analyticalClassId, `Mixed original class for ${e.subtype}`);
  current.N_REGISTROS++;
  subtypes.set(e.subtype, current);
}
for (const subtype of changes.keys()) assert.ok(subtypes.has(subtype), `Unknown exact subtype: ${subtype}`);
const dictionary = [...subtypes.values()].sort((a,b) => a.SUBTIPO.localeCompare(b.SUBTIPO, 'es')).map(row => {
  const classId = changes.get(row.SUBTIPO) || row.CLASE_ACTUAL;
  return {...row, CATEGORIA_ACTUAL:names[row.CLASE_ACTUAL], CATEGORIA_ANALITICA:names[classId],
    REGLA:changes.has(row.SUBTIPO) ? 'LISTA_EXPLICITA_SOLICITUD_NO_APLICADA' : 'DICCIONARIO_PREVIO_CONSERVADO_PARA_REVISION',
    ESTADO:row.SUBTIPO === 'Bomberos' ? 'PROPUESTA_OTROS_REVISION_REQUIERE_CONFIRMACION' : classId === 5 ? 'PENDIENTE_REVISION' : 'PROPUESTA_NO_APLICADA'};
});
const dictionaryBySubtype = new Map(dictionary.map(row => [row.SUBTIPO, row]));
const derived = events.map(e => {
  const row = dictionaryBySubtype.get(e.subtype), assignment = spatial.assignments[e.id];
  assert.ok(assignment, `Missing assignment ${e.id}`);
  return {ID:e.id, FECHA:e.date, SUBTIPO:e.subtype, LONGITUD:e.lng, LATITUD:e.lat,
    CATEGORIA_ACTUAL:names[e.analyticalClassId], CATEGORIA_ANALITICA:row.CATEGORIA_ANALITICA,
    PARROQUIA_ORIGEN:e.parish, AMBITO:assignment.scope, UNIDAD:assignment.unit, MOTIVO_ASIGNACION:assignment.reason,
    DENTRO_CANTON:assignment.insideCanton, RECURRENCIA_XY:xyCounts.get(coordinateKey(e)),
    FLAG_COORD:flag(xyCounts.get(coordinateKey(e))), PESO_PROPUESTO:1, ESTADO:'PROPUESTA_NO_APLICADA'};
});
assert.equal(events.length, 26716);
assert.equal(new Set(events.map(e => e.id)).size, events.length);
assert.equal(Object.values(expected).reduce((a,b) => a+b,0), events.length);
for (const row of derived) {
  const original = sourceById.get(row.ID);
  assert.equal(row.LONGITUD,original.lng);
  assert.equal(row.LATITUD,original.lat);
  assert.equal(row.SUBTIPO,original.subtype);
  assert.equal(row.PESO_PROPUESTO,1);
}
const currentCounts = counts(events.map(e => ({CATEGORIA_ANALITICA:names[e.analyticalClassId]})));
const proposedCounts = counts(derived);
const scopeCounts = Object.fromEntries(Object.keys(expectedScopes).map(scope => [scope, derived.filter(e => e.AMBITO === scope).length]));
const categoryComparison = Object.keys(expected).map(name => ({CATEGORIA:name, ACTUAL:currentCounts[name], PROPUESTA:proposedCounts[name], ESPERADO:expected[name], DIFERENCIA:proposedCounts[name]-expected[name]}));
const scopeCategoryComparison = Object.entries(expectedAnalyticalScopes).flatMap(([scope, categories]) => Object.entries(categories).map(([category, n]) => ({AMBITO:scope, CATEGORIA:category, PROPUESTA:derived.filter(e => e.AMBITO === scope && e.CATEGORIA_ANALITICA === category).length, ESPERADO:n})));
const quality = scopeCategoryComparison.map(row => {
  const local = derived.filter(e => e.AMBITO === row.AMBITO && e.CATEGORIA_ANALITICA === row.CATEGORIA);
  const groups = new Map();
  for (const e of local) {
    const key = JSON.stringify([e.LONGITUD,e.LATITUD]);
    groups.set(key, (groups.get(key) || 0) + 1);
  }
  // Table recurrence uses the six separate analytical inputs; row flags use the complete base.
  const repeated = [...groups.values()].filter(n => n > 1).reduce((sum,n) => sum+n,0);
  return {CATEGORIA:row.CATEGORIA, AMBITO:row.AMBITO, N_EVENTOS:local.length, N_COORD_UNICAS:groups.size,
    PORCENTAJE_REGISTROS_EN_XY_REPETIDA:local.length ? 100*repeated/local.length : null,
    MAX_REPETICION_XY:groups.size ? Math.max(...groups.values()) : null,
    BANDWIDTH_RECOMENDADO:'NO_SELECCIONADO_VALIDACION_ENTRADA_PENDIENTE'};
});
// Count reconciliation is diagnostic evidence, NOT authorization to adopt ambiguous rules.
const reconciliationRules = new Map([
  ['Bomberos', 'ACTIVIDAD_INSTITUCIONAL'],
  ['Tenencia y porte de explosivos', 'DELINCUENCIA'],
  ['Falta contra la integridad a servidores policiales', 'ACTIVIDAD_INSTITUCIONAL'],
  ['Plantones', 'ACTIVIDAD_INSTITUCIONAL'],
]);
const hypothetical = derived.map(row => ({...row, CATEGORIA_ANALITICA:reconciliationRules.get(row.SUBTIPO) || row.CATEGORIA_ANALITICA}));
const textScope = row => row.PARROQUIA_ORIGEN === 'RIOBAMBA' ? 'URBANO' : 'RURAL';
const scopeCrosswalk = ['URBANO','RURAL'].flatMap(text => ['URBANO','RURAL','SIN_ASIGNAR'].map(geom => ({
  AMBITO_POR_TEXTO:text, AMBITO_GEOMETRICO:geom, N_REGISTROS:derived.filter(row => textScope(row) === text && row.AMBITO === geom).length,
})));
const ruleComparison = [...reconciliationRules].map(([subtype, category]) => ({
  SUBTIPO:subtype, N_REGISTROS:subtypes.get(subtype).N_REGISTROS,
  CATEGORIA_ACTUAL:names[subtypes.get(subtype).CLASE_ACTUAL],
  PROPUESTA_CONSERVADORA:dictionaryBySubtype.get(subtype).CATEGORIA_ANALITICA,
  HIPOTESIS_QUE_RECONCILIA_CONTEOS:category, ESTADO:'REQUIERE_CONFIRMACION_NO_APLICADA',
}));
const hypothesisScopeCounts = Object.fromEntries(['URBANO','RURAL'].map(scope => [scope, counts(hypothetical.filter(row => textScope(row) === scope))]));
assert.deepEqual(counts(hypothetical),expected);
for (const [scope,categories] of Object.entries(expectedAnalyticalScopes)) for (const [category,n] of Object.entries(categories)) assert.equal(hypothesisScopeCounts[scope][category],n);
const audit = {
  date:'2026-10-01', status:'DETENIDO_EN_VALIDACION_DE_INPUT_NO_APLICAR_ANALISIS',
  source:source.sourceWorkbook, records:events.length, uniqueIds:new Set(events.map(e=>e.id)).size,
  currentCounts, proposedCounts, expectedCounts:expected, categoryComparison, scopeCounts, expectedScopes,
  existingPublishedKdeInput:{records:existingKde.kdeInputPoints.length,classes:existingKdeClasses,institutionalLeak:0,reviewLeak:0,weight:1},
  scopeCategoryComparison, changes:dictionary.filter(e => e.CATEGORIA_ACTUAL !== e.CATEGORIA_ANALITICA),
  dictionarySubtypes:dictionary.length, quality, uniqueCoordinates:xyCounts.size,
  coordinateFlags:Object.fromEntries(['NORMAL','REPETIDA','ALTA_REPETICION','MUY_ALTA_REPETICION'].map(label => [label,derived.filter(e => e.FLAG_COORD === label).length])),
  maximumCoordinateRecurrence:Math.max(...xyCounts.values()),
  reconciliationHypothesis:{status:'NO_APLICADA_REQUIERE_CONFIRMACION',rules:ruleComparison,totals:counts(hypothetical),
    bySourceParish:hypothesisScopeCounts,scopeCriterion:'PARROQUIA_ORIGEN = RIOBAMBA; no interseccion geometrica',scopeCrosswalk},
  repetitionDefinition:'RECURRENCIA_XY y FLAG_COORD: base completa, coordenadas originales exactas sin redondeo. Tabla por categoria/ambito: recurrencia dentro del subconjunto; porcentaje de registros, no porcentaje de ubicaciones.',
  unclassifiedScopes:derived.filter(e => e.AMBITO === 'SIN_ASIGNAR').length,
  ambiguityNotes:[
    'Bomberos: la solicitud lo enumera para revision en OTROS; se propone 5, sin aplicarlo. Si se conserva la clase institucional anterior, suma 21 a ACTIVIDAD_INSTITUCIONAL y resta 21 a OTROS_REVISION.',
    'Tenencia y porte de explosivos: 2 registros permanecen OTROS; no se fuerza equivalencia con armas para completar el objetivo de Delincuencia.',
    'Una hipotesis con Bomberos institucional, explosivos delictivo, faltas contra servidores policiales institucional y Plantones institucional reproduce exactamente los cinco conteos. Coincidir no valida semanticamente esas cuatro reglas; requieren confirmacion.',
    'Los conteos objetivo Urbano/Rural se reproducen exactamente con PARROQUIA_ORIGEN = RIOBAMBA, NO con geometria. La geometria aprobada deja 850 SIN_ASIGNAR (820 internos y 30 externos); no se redistribuyen para alcanzar un objetivo.',
    'El KDE publicado NO usa todos los registros: admite solo clases1/2/3 y peso1. Todos los registros a700m seria un contrafactual, no el mapa actual.',
    'No se evaluan bandwidth ni se regeneran Gi*, KDE o tasas mientras no se resuelva este control de entrada.',
  ],
  originalHashes:hashes, productionUnchanged:true, interfaceUnchanged:true, published:false,
};
assert.ok(categoryComparison.some(row => row.DIFERENCIA !== 0), 'Input now reconciles; review the stop gate explicitly before changing stage.');
for (const [file,hash] of Object.entries(hashes)) assert.equal(fingerprint(file),hash,`Original modified: ${file}`);
fs.mkdirSync(out,{recursive:true});
const csv = (file, rows) => {
  const fields=Object.keys(rows[0]);
  const escape=value => `"${String(value ?? '').replaceAll('"','""')}"`;
  fs.writeFileSync(path.join(out,file), '\uFEFF'+[fields,...rows.map(row=>fields.map(field=>row[field]))].map(row=>row.map(escape).join(';')).join('\r\n')+'\r\n','utf8');
};
fs.writeFileSync(path.join(out,'DICCIONARIO_PROPUESTO.json'), JSON.stringify(dictionary,null,2)+'\n');
fs.writeFileSync(path.join(out,'AUDITORIA_INPUT.json'), JSON.stringify(audit,null,2)+'\n');
csv('SUBTIPO_CATEGORIA_PROPUESTA.csv',dictionary);
csv('REGISTROS_ANALITICOS_PROPUESTA.csv',derived);
csv('CAMBIOS_SUBTIPOS.csv',audit.changes);
csv('COMPARACION_CATEGORIAS.csv',categoryComparison);
csv('COMPARACION_AMBITOS_CATEGORIAS.csv',scopeCategoryComparison);
csv('CONTROL_COORDENADAS.csv',quality);
csv('RECONCILIACION_REQUIERE_CONFIRMACION.csv',ruleComparison);
csv('CONTRASTE_AMBITOS_TEXTO_GEOMETRIA.csv',scopeCrosswalk);
console.log(JSON.stringify({status:audit.status,categoryComparison,scopeCounts,expectedScopes,reconciliationHypothesis:audit.reconciliationHypothesis,
  uniqueCoordinates:audit.uniqueCoordinates,maximumCoordinateRecurrence:audit.maximumCoordinateRecurrence,coordinateFlags:audit.coordinateFlags,productionUnchanged:true},null,2));
