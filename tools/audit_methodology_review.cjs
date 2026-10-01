const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'data/seguridad-riobamba/revision-metodologica-20261001');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const load = (file, key) => {
  const context = { window: {} };
  vm.runInNewContext(read(file), context);
  return context.window[key];
};
const security = load('visor-seguridad-riobamba-data.js', 'RIOBAMBA_SECURITY_DATA');
const diagnosis = load('riobamba-seguridad-diagnostico-data.js', 'RIOBAMBA_SECURITY_DIAGNOSIS');
const kde = load('riobamba-seguridad-kde-validacion-data.js', 'RIOBAMBA_KDE_VALIDATION');
const spatial = load('riobamba-incidentes-spatial-data.js', 'RIOBAMBA_INCIDENT_SPATIAL');
const cameras = load('riobamba-camaras-data.js', 'RIOBAMBA_CAMERAS_DATA').cameras;
const police = load('policia-06d01-data.js', 'RIOBAMBA_POLICE_SIG_DATA');
const accessibility = load('riobamba-accesibilidad-policial-data.js', 'RIOBAMBA_POLICE_ACCESSIBILITY');
const normalize = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
const classes = ['DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA / INCIVILIDADES', 'ACTIVIDAD INSTITUCIONAL / POLICIAL', 'OTROS / REVISION'];
const rules = new Map();
const assign = (classIndex, subtypes, reason) => {
  for (const subtype of subtypes) {
    const key = normalize(subtype);
    assert.ok(!rules.has(key), `Duplicate classification: ${subtype}`);
    rules.set(key, { classIndex, reason });
  }
};

assign(0, [
  'Abigeato', 'Abuso de confianza', 'Contrabando', 'Daño a propiedad privada',
  'Daño a propiedad pública', 'Daño a propiedad pública o privada', 'Estafa',
  'Extorsión', 'Falsificación de moneda o documentos', 'Falsificación y uso de documento falso',
  'Fraude a persona', 'Hurto', 'Moneda falsa', 'Receptación / cachinería', 'Robo',
  'Robo a carros', 'Robo a domicilio', 'Robo a entidades financieras',
  'Robo a instituciones públicas', 'Robo a unidades económicas', 'Robo a unidades educativas',
  'Robo accesorios de vehículos o autopartes de vehículo', 'Robo de bienes patrimoniales',
  'Robo de motos', 'Robo personas', 'Suplantación de identidad', 'Tentativa de robo',
], 'Hecho patrimonial o económico reportado compatible con clase 1; propuesta analítica, no calificación judicial.');

assign(1, [
  'Abuso sexual', 'Acoso sexual', 'Agresión a la autoridad', 'Agresión física',
  'Agresión verbal', 'Agresiones a personas', 'Asesinato', 'Delitos sexuales',
  'Falta contra la integridad a servidores policiales', 'Falta contra la integridad a servidores públicos',
  'Violación', 'Violencia a niños, niñas y adolescentes',
  'Violencia contra la mujer o miembros del núcleo familiar física',
  'Violencia contra la mujer o miembros del núcleo familiar psicológica',
  'Violencia contra la mujer o miembros del núcleo familiar sexual', 'Violencia intrafamiliar',
], 'Agresión o violencia sexual/familiar reportada; no determina autoría ni sentencia.');
assign(1, [
  'Desaparición forzada', 'Privación arbitraria de la libertad por civiles (Secuestro)',
  'Secuestro', 'Secuestro extorsivo', 'Tentativa de secuestro',
], 'Privación coercitiva de libertad propuesta como violencia; validar esta frontera con delincuencia antes de aplicar.');

assign(2, [
  'Actos inmorales en la vía pública', 'Escándalo', 'Escándalo en espacio privado',
  'Escándalo en espacio público', 'Escándalo por inquilinato', 'Eventos clandestinos',
  'Fiestas clandestinas con consumo de alcohol, drogas con presencia de menores de edad',
  'Fiestas en vivienda', 'Libadores', 'Riña interior de CRS', 'Ruidos molestosos',
  'Venta u ofrecimiento de bebidas alcohólicas o cigarrillos menores de edad',
], 'Convivencia/incivilidades según el subtipo reportado y las reglas solicitadas; riñas en clase 3.');

assign(3, [
  'Agentes municipales', 'Apoyo a instituciones articuladas',
  'Apoyo al control de dispositivos electrónicos de carácter judicial',
  'Boleta / orden de autoridad', 'Boleta de apremio', 'Boleta de auxilio',
  'Boleta de captura', 'Boleta de citación', 'Boleta de comparecencia inmediata',
  'Bomberos', 'Control de espectáculos religiosos', 'Control de manifestaciones',
  'Control de marchas', 'Custodia policial en lugares de riesgo temporal',
  'Encargos domiciliarios', 'Ficha de datos', 'Ficha de datos información', 'Ficha de datos operativo',
  'Orden de incautación/embargo', 'Organismos de salud', 'Organismos de tránsito', 'Otra institución',
  'Patrullaje policial en el sector solicitado', 'Presencia policial',
  'Registro de personas y/o vehículos con actitud sospechosa',
  'Resguardo a personas que traslada valores a nivel local',
  'Resguardo a personas que traslada valores a nivel provincial', 'Resguardo de valores de blindado',
  'Resguardo de víctimas y testigos', 'Resguardo policial', 'Seguridad de autoridades',
  'Seguridad de cárceles', 'Seguridad en espectáculos públicos', 'Traslado de detenidos', 'Traslado de valores',
], 'Actuación, control, resguardo o asistencia institucional; no debe tratarse como hecho delictivo por su sola presencia.');

const knownNonAnalytic = new Set([
  'Muerte accidental', 'Muerte natural', 'Muerte por accidente de tránsito',
  'Recuperación de animales silvestres', 'Rescate y retención de especies silvestres',
].map(normalize));
const reviewReasons = new Map(Object.entries({
  'Muerte indeterminada': 'Causa no determinada; no permite afirmar homicidio ni violencia.',
  'Constatar persona sin vida': 'Constatación sin causa; puede ser actuación institucional o evento no violento.',
  'Osamentas': 'Hallazgo sin determinación de causa ni fecha del hecho.',
  'Persona herida': 'La lesión genérica no distingue accidente de agresión.',
  'Persona herida con arma blanca': 'Lesión con arma; confirmar agresión frente a accidente/autolesión antes de asignar violencia.',
  'Persona herida con arma de fuego': 'Lesión con arma; confirmar agresión frente a accidente/autolesión antes de asignar violencia.',
  'Persona herida con objeto contundente': 'Lesión con objeto; confirmar agresión frente a accidente antes de asignar violencia.',
  'Plantones': 'Una manifestación no constituye automáticamente una incivilidad.',
  'Desalojos': 'No distingue actuación judicial/administrativa de conflicto u otro evento.',
  'Capturado por civiles': 'No identifica el hecho de origen ni prueba un delito.',
  'Sonidos de alarma': 'Alerta sin confirmación del fenómeno ocurrido.',
  'Activación botón de seguridad': 'Alerta sin tipo de hecho confirmado.',
  'C.Plata Paciente Autoreferido': 'Código operativo sin definición aportada.',
  'C.Plata Toma Instalaciones': 'Código operativo sin definición aportada.',
  'Vehículos de perifoneo': 'No distingue servicio institucional de ruido/incivilidad.',
  'Comercialización de sustancias sujetas a fiscalización': 'Definir alcance de delincuencia para drogas; no resolver por inclusión anterior en hotspot.',
  'Consumo de sustancias sujetas a fiscalización': 'Consumo no equivale automáticamente a delito; definir tratamiento en convivencia u otros.',
  'Tenencia ilícita de sustancias sujetas a fiscalización': 'Nombre reporta ilicitud, pero debe acordarse alcance de clase 1 para drogas frente al listado patrimonial solicitado.',
  'Tenencia y porte de arma blanca o cortopunzante': 'No informa autorización, amenaza o agresión; definir alcance analítico antes de clasificar.',
  'Tenencia y porte de armas de fuego': 'No informa autorización, amenaza o agresión; definir alcance analítico antes de clasificar.',
  'Tenencia y porte de explosivos': 'No informa contexto de tenencia ni agresión; definir alcance analítico antes de clasificar.',
  'Tráfico de fauna': 'Hecho ambiental; acordar si delincuencia comprende delitos ambientales o queda fuera de las tres clases analíticas.',
  'Tráfico de flora': 'Hecho ambiental; acordar si delincuencia comprende delitos ambientales o queda fuera de las tres clases analíticas.',
  'Trata de personas': 'Validar asignación a violencia o delincuencia y alcance analítico.',
  'Suicidio': 'Evento autoinfligido; requiere decidir alcance de violencia, no asumir homicidio.',
}).map(([key, value]) => [normalize(key), value]));

const groups = new Map();
const valid = (event) => Number.isFinite(event.lat) && Number.isFinite(event.lng)
  && Math.abs(event.lat) <= 90 && Math.abs(event.lng) <= 180
  && !(event.lat === 0 && event.lng === 0)
  && /^\d{4}-\d{2}-\d{2}$/.test(event.date) && Number.isFinite(Date.parse(event.date));
for (const event of security.events) {
  const subtype = event.subtype || 'SIN SUBTIPO';
  const group = groups.get(subtype) || { subtype, count: 0, validCount: 0, oldCategories: new Set(), oldHotspotCount: 0 };
  group.count += 1;
  group.validCount += Number(valid(event));
  group.oldCategories.add(event.category);
  group.oldHotspotCount += Number(event.hotspotEligible === true);
  groups.set(subtype, group);
}
const existingSubtypes = new Set([...groups.keys()].map(normalize));
for (const key of rules.keys()) assert.ok(existingSubtypes.has(key), `Rule without matching subtype: ${key}`);
const rows = [...groups.values()].sort((a, b) => a.subtype.localeCompare(b.subtype, 'es')).map((group) => {
  const key = normalize(group.subtype);
  const rule = rules.get(key);
  const classIndex = rule?.classIndex ?? 4;
  const reason = rule?.reason || reviewReasons.get(key)
    || (knownNonAnalytic.has(key) ? 'Evento no analítico bajo las tres clases de conflictividad solicitadas.'
      : 'El nombre no determina inequívocamente el fenómeno ni su asignación; solicitar definición/detalle al responsable de la base.');
  return {
    SUBTIPO: group.subtype, NUMERO_REGISTROS: group.count, REGISTROS_VALIDOS: group.validCount,
    CLASIFICACION_ANTERIOR: [...group.oldCategories].join(' / '),
    INCLUIR_HOTSPOT_ANTERIOR_SI: group.oldHotspotCount,
    CLASIFICACION_NUEVA_PROPUESTA: classes[classIndex], CLASE_PROPUESTA: classIndex + 1,
    ESTADO: rule ? 'PROPUESTA_NO_APROBADA' : knownNonAnalytic.has(key) ? 'OTRO_NO_ANALITICO_PROPUESTO' : 'REQUIERE_REVISION',
    MOTIVO: reason,
    CANDIDATO_KDE_GI_TASAS_TRAS_APROBACION: classIndex < 3,
  };
});
const totals = Object.fromEntries(classes.map((label) => [label, rows.filter((row) => row.CLASIFICACION_NUEVA_PROPUESTA === label).reduce((sum, row) => sum + row.REGISTROS_VALIDOS, 0)]));
const validCount = security.events.filter(valid).length;
assert.equal(Object.values(totals).reduce((sum, count) => sum + count, 0), validCount);
assert.equal(rows.length, security.summary.subtypes);
assert.equal(new Set(security.events.map((event) => event.id)).size, security.events.length);
assert.equal(cameras.length, 31);
const review = rows.filter((row) => row.ESTADO === 'REQUIERE_REVISION');
const leakedInstitutional = rows.filter((row) => row.CLASE_PROPUESTA === 4 && row.INCLUIR_HOTSPOT_ANTERIOR_SI > 0);
const hash = (file) => crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex');
const preserved = ['visor-seguridad-riobamba-v2.html', 'visor-seguridad-riobamba-data.js',
  'riobamba-camaras-data.js', 'riobamba-incidentes-spatial-data.js', 'riobamba-seguridad-kde-validacion-data.js',
  'riobamba-seguridad-diagnostico-data.js', 'riobamba-censo-data/riobamba_plataformas.geojson',
  'riobamba-censo-data/riobamba_manzanas_stats.json'];
const report = {
  date: '2026-10-01', status: 'AUDITORIA_Y_PROPUESTA_PARA_REVISION_NO_APLICADA',
  auditedCommit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
  source: security.sourceWorkbook, period: security.period,
  sourceRecords: security.events.length, validRecords: validCount,
  invalidRecords: security.events.length - validCount,
  coordinateCheckScope: 'Rangos geograficos numericos, no prueba independiente de precision ni de limite cantonal.',
  latitudeRange: [Math.min(...security.events.map((event) => event.lat)), Math.max(...security.events.map((event) => event.lat))],
  longitudeRange: [Math.min(...security.events.map((event) => event.lng)), Math.max(...security.events.map((event) => event.lng))],
  spatialWeight: 1, originalEmergencies: security.summary.totalEmergencies,
  totals, subtypes: rows.length, reviewSubtypes: review.length,
  reviewRecords: review.reduce((sum, row) => sum + row.NUMERO_REGISTROS, 0),
  currentInstitutionalSubtypeLeak: leakedInstitutional,
  currentInstitutionalRecordLeak: leakedInstitutional.reduce((sum, row) => sum + row.INCLUIR_HOTSPOT_ANTERIOR_SI, 0),
  currentKde: { records: kde.kdeInputPoints.length, crs: spatial.crs, bandwidth: 700, cellSize: 20, method: kde.metadata.METODO },
  currentGi: { ...Object.fromEntries(['cellSize', 'neighborDistance'].map((key) => [key, spatial.giGrid[key]])), cells: spatial.giGrid.cells.length,
    hotspots: Object.values(spatial.giSummaryByPlatform).reduce((sum, row) => sum + row.hotspots, 0),
    coldspots: Object.values(spatial.giSummaryByPlatform).reduce((sum, row) => sum + row.coldspots, 0),
    significance: 'Nominal; sin correccion de pruebas multiples ni validacion nueva por clase.' },
  population: { currentMaster: diagnosis.summary.populationWithPlatform,
    currentAccessibility: accessibility.summary.population, proposedUrbanDenominator: 177213,
    urbanDenominatorStatus: 'VALOR_SOLICITADO_NO_APLICADO; documentar fuente y geometria urbana antes del numerador.' },
  cameras: { total: cameras.length, uniqueIds: new Set(cameras.map((camera) => camera.id)).size, preserved: true },
  police: { total: police.infrastructure.features.length, assignedPlatforms: diagnosis.summary.policeInfrastructureAssigned, method: accessibility.method,
    generatorInRepository: false },
  sourceHashes: Object.fromEntries(preserved.map((file) => [file, hash(file)])),
  proceedToImplementation: false,
  approvalGate: 'Revisar tabla completa y resolver subtipos ambiguos. No conectar clasificacion, recalcular resultados ni hacer commit/push.',
  classification: rows,
};

const references = [
  ['Fuente y puntos de incidentes', 'visor-seguridad-riobamba-data.js', 'tools/build_riobamba_real_incidents.py: main; visor: events, renderMarkers, filteredEvents'],
  ['Clasificación actual', 'data/seguridad-riobamba/clasificacion-incidentes-2026.json', 'builder: classification; visor: conflictEvents, syncKdeFilterOptions'],
  ['KDE', 'riobamba-seguridad-kde-validacion-data.js; data/kde-validacion/DENSIDAD_INCIDENTES_KDE_700m.png', 'tools/build_kde_validation.py: build_density, main; visor: filteredKdePoints, getFilteredKdeSurface, kdeState, renderHotspots, renderKdeGraphicPanel'],
  ['Gi*', 'riobamba-incidentes-spatial-data.js', 'tools/build_incident_spatial_reference.py: main; visor: getGiHotspotAnalysis, giClass, filteredGiCells'],
  ['Cálculos por Plataforma y tasas', 'riobamba-seguridad-diagnostico-data.js', 'tools/build_security_diagnosis_phase1.py: metrics, platforms; visor: platformRecord, filteredPlatforms, renderPlatformDetail'],
  ['Población y densidad', 'riobamba-censo-data/riobamba_manzanas_stats.json; riobamba_plataformas_stats.json', 'builder diagnóstico: population_allocations; visor: loadCensusLayers, manzanaPopulation, manzanaDensity'],
  ['Evolución temporal', 'visor-seguridad-riobamba-data.js: events.date', 'visor: validDate, temporalRecords, renderGraphicAnalysis (isTemporalMode)'],
  ['Tipos de incidentes y gráficos', 'events.category/subtype y platformMaster', 'visor: categorySummary, metricBars, renderGraphicAnalysis (isTypologiesMode), renderSummary'],
  ['Filtros', 'visor-seguridad-riobamba-v2.html', 'analysisConfig, syncKdeFilterOptions, filteredEvents, kdeFilterMatches, update'],
  ['31 cámaras', 'riobamba-camaras-data.js', 'tools/build_riobamba_cameras_data.py: study_rows; visor: changeCameras, coverageCameraSet, renderCameraMarkers'],
  ['Cobertura territorial', 'manzanas.geojson + cámaras + manToPlatform', 'visor: getCameraCoverageAnalysis, manzanaCoverageFraction, geometryAreaKm2, coverageTerritorialData, renderCameraCoverageGraphics'],
  ['Cobertura poblacional', 'manzanas_stats.json + cámaras + manToPlatform', 'visor: getCameraCoverageAnalysis, coveragePopulationData, renderCameraCoverageGraphics; maestro: cameraCoveredPopulation*'],
  ['UPC e infraestructura policial', 'policia-06d01-data.js', 'tools/build_policia_06d01_data.py: read_layer, transform_point, point_geometry; visor: filteredPoliceInfrastructure, renderPoliceLayers, renderPoliceDetail'],
  ['Proximidad policial', 'riobamba-accesibilidad-policial-data.js', 'visor: policeAccessibility, renderGraphicAnalysis (policeAccessibility), renderPlatformDetail; no generador localizado en repositorio'],
  ['Bulevares', 'data/premio-habitat/premio-habitat-boulevares.geojson; premio-habitat-conexiones.geojson', 'builder diagnóstico: network_union; visor: loadBoulevardNetwork, cameraNearBoulevardNetwork, renderBoulevardGraphics'],
  ['Cobertura institucional', 'maestro + proximidad policial + cobertura calculada en visor', 'builder: classify_institutional_coverage; visor: renderInstitutionalGraphics, renderInstitutionalDetail'],
  ['Brechas B1-B5', 'maestro + getGiHotspotAnalysis + cobertura calculada', 'visor: gapPlatformRows, lowCoverageConcentrationCells, candidateZones, renderGraphicAnalysis; builder: classify_deficit, deficit_score, classify_conflict_exposure'],
];
const findings = [
  'Selección de conflictividad basada únicamente en hotspotEligible/incluir_hotspot. La propuesta detecta ' + report.currentInstitutionalRecordLeak + ' registros de ' + leakedInstitutional.length + ' subtipos institucionales hoy admitidos al KDE/Gi*. No han sido eliminados ni recalculados.',
  'filteredEvents parte de conflictEvents, incluso en Consulta/Tipos/Temporal: la actividad institucional no es explorable allí. La nueva clase 4 necesita una fuente de consulta completa independiente del subconjunto analítico.',
  'El generador asigna precisión A a toda coordenada original y mappable=true sin auditoría externa. Una coordenada presente no prueba precisión de campo; se verificó validez numérica y fecha, no exactitud del lugar ni frontera cantonal.',
  'KDE: puntos originales, peso 1, UTM 17S, celda 20 m, radio 700 m. Kernel exp(-0.5*(d/h)^2), corte d<=h, sin normalización de densidad por unidad de superficie. Explicar qué significa bandwidth en este kernel y no confundir la rampa relativa (percentil 98) con significancia.',
  'Concentraciones KDE: componentes de 4 vecinos sobre 35% del máximo; umbral descriptivo, no prueba estadística ni número validado de sectores. No cambiar radio automáticamente al filtrar.',
  'Gi*: grilla fija 250 m, vecinos binarios 500 m, incluye la propia celda y ceros. Z umbrales 1.65/1.96/2.58, p nominal sin ajuste múltiple. Las celdas de borde se dibujan completas; se asignan a una sola Plataforma por centroide o intersección mayor, no equivalen al recorte exacto por Plataforma.',
  'Población: maestro 171998 por asignación proporcional de intersecciones; cobertura/proximidad 171665 por asignación manToPlatform. Ambas provienen del censo existente, pero no son denominadores intercambiables. 177213 es el denominador urbano solicitado, no una población ya aplicada ni un límite urbano identificado.',
  'Tasas actuales /1000 agregan categorías amplias de conflictividad. No existe el nuevo módulo Incidencia poblacional por tres clases ni tasa urbana /100000. Numerador urbano debe tener el mismo ámbito geográfico del denominador; NO usar automáticamente todo el cantón ni solo parroquia RIOBAMBA.',
  'Cobertura en navegador usa muestreo de puntos de manzana y conversión métrica local aproximada. El maestro usa intersecciones UTM exactas y población areal. Diferencia a 150 m: navegador 14488/171665, maestro 14446/171998. La superficie 20.371896 km2 del gráfico corresponde a manzanas asignadas, NO al área total de los polígonos de las 18 Plataformas.',
  'El maestro crea buffers con cámaras/policía previamente asignadas a Plataformas (29 cámaras, 17 dependencias), omitiendo los dos y nueve puntos externos respectivamente; el navegador de cobertura calcula con los 31 puntos. Los recursos externos pueden aportar cobertura interior: debe revisarse la extensión de cálculo sin eliminar posiciones.',
  'Se conservan las 31 cámaras confirmadas. La institución original no siempre es GADM, aunque ambitoEstudio las rotule MUNICIPAL; distinguir universo acordado de titularidad documental sin modificarlo.',
  'Proximidad policial: distancia euclidiana desde punto representativo de manzana, no red ni velocidades/tiempos. Metadato mezcla EPSG:32717 con aproximación local; no basta para probar una transformación UTM real. Falta generador reproducible de riobamba-accesibilidad-policial-data.js en este repositorio.',
  'Exposición 100/250/500 m y cruces Bulevares dependen del conjunto analítico anterior. Los buffers de exposición son de todos los eventos elegibles, no exclusivamente hotspots estadísticos. Deberán recalcularse por clase tras aprobar la clasificación, manteniendo geometrías originales.',
  'Brechas: persisten deficit_score ponderado 2/1 puntos, cobertura institucional por conteo de recursos presentes, límites discretos de exposición y candidaturas por número de banderas. No es AHP, pero tampoco una coincidencia transparente libre de pesos/umbrales arbitrarios como la solicitada. Hay que sustituir la síntesis y conservar variables observables.',
  'candidateZones reparte población no cubierta de la Plataforma por igual entre sus celdas hotspot; NO calcula la población real de cada zona por intersección censal. lowCoverageConcentrationCells hereda cobertura media de Plataforma, no comprueba cobertura local de cada celda.',
  'Los datos events.date contienen fecha, pero no hora. temporalRecords fija hour=null. No generar hora a partir de T00:00:00 ni inventar franjas. Separar mes y día de semana por clase aprobada.',
  'No se aportaron contenidos de CMI Riobamba-Chambo ni documentos específicos de Ambato/Cuenca. No se atribuye a estas instituciones la metodología o umbrales del código existente; solicitar referencias si se requieren equivalencias documentales.',
];
const table = '| SUBTIPO | NÚMERO DE REGISTROS | CLASIFICACIÓN ANTERIOR | CLASIFICACIÓN NUEVA PROPUESTA | ESTADO | MOTIVO |\n| --- | ---: | --- | --- | --- | --- |\n'
  + rows.map((row) => `| ${row.SUBTIPO} | ${row.NUMERO_REGISTROS} | ${row.CLASIFICACION_ANTERIOR} | ${row.CLASIFICACION_NUEVA_PROPUESTA} | ${row.ESTADO} | ${row.MOTIVO} |`).join('\n');
const totalsTable = '| CLASE PROPUESTA | REGISTROS VÁLIDOS |\n| --- | ---: |\n'
  + Object.entries(totals).map(([label, count]) => `| ${label} | ${count} |`).join('\n')
  + `\n| TOTAL | ${validCount} |`;
const reviewMd = `# Clasificación de subtipos para revisión\n\nFecha: 1 octubre 2026. PROPUESTA NO APLICADA AL VISOR.\n\n`
  + `Fuente: ${security.sourceWorkbook}. Periodo: ${security.period.from} a ${security.period.to}.\n\n`
  + `${rows.length} subtipos; ${security.events.length} registros; ${validCount} válidos (coordenadas numéricas y fecha), ${report.invalidRecords} no válidos. Cada fila pesa 1; Emergencias se conserva sin ponderar.\n\n`
  + totalsTable + `\n\n## Puerta de validación\n\n${review.length} subtipos (${report.reviewRecords} registros) requieren revisión. Los otros también son propuestas no aprobadas, no una clasificación judicial.\n\n`
  + 'Validar especialmente secuestro/desaparición forzada como violencia, lesiones con armas/objetos pendientes de causa y registro de sospechosos como actividad de control. No inferir un delito confirmado de una alerta.\n\n'
  + 'NO continuar con fases 2-19, actualizar derivados o publicar hasta resolver ambigüedades y aprobar esta tabla.\n\n'
  + `## Tabla completa\n\n${table}\n\n## Subtipos pendientes de decisión\n\n`
  + review.map((row) => `- ${row.SUBTIPO}: ${row.NUMERO_REGISTROS}. ${row.MOTIVO}`).join('\n') + '\n';
const auditMd = '# Auditoría metodológica del visor actual\n\nFecha: 1 octubre 2026. FASE 0 completada; sin cambios en aplicación, fuentes o publicación.\n\n'
  + `Versión auditada: ${report.auditedCommit}.\n\n`
  + '## Componentes y dependencias\n\nTodas las funciones de visor indicadas abajo pertenecen a visor-seguridad-riobamba-v2.html.\n\n'
  + '| COMPONENTE | ARCHIVO / FUENTE | FUNCIONES O RUTA DE DATOS |\n| --- | --- | --- |\n'
  + references.map((row) => `| ${row.join(' | ')} |`).join('\n')
  + '\n\n## Hallazgos que condicionan la implementación\n\n'
  + findings.map((finding, index) => `${index + 1}. ${finding}`).join('\n\n')
  + `\n\n## Control de entrada\n\nBase: ${report.sourceRecords}; válidos numéricos/fecha: ${validCount}; originales Emergencias: ${report.originalEmergencies}; peso espacial actual: 1.\n\n`
  + `Latitud: ${report.latitudeRange.join(' a ')}; longitud: ${report.longitudeRange.join(' a ')}. Esto no verifica la precisión de campo ni el límite cantonal.\n\n`
  + `KDE vigente: ${kde.kdeInputPoints.length} puntos. Gi*: ${report.currentGi.cells} celdas, ${report.currentGi.hotspots} hotspots y ${report.currentGi.coldspots} coldspots, significancia nominal.\n\n`
  + `## Clasificación propuesta\n\n${totalsTable}\n\nTabla completa: [CLASIFICACION_PROPUESTA.md](CLASIFICACION_PROPUESTA.md). Datos y huellas de fuentes: [AUDITORIA_Y_CLASIFICACION.json](AUDITORIA_Y_CLASIFICACION.json).\n\n`
  + `## Decisión antes de continuar\n\nSe detectan ${review.length} subtipos ambiguos. Se detiene la implementación según la regla obligatoria. No se recalcularon KDE, Gi*, tasas, cámaras, coberturas ni brechas. La validación completa de fases 17/19 y consola corresponde después de la aprobación, no se presenta como realizada.\n\n`
  + 'Para continuar: aprobar/corregir clasificación por subtipo; decidir el ámbito urbano del denominador 177213; acordar un único criterio censal de asignación y área para las salidas; aportar referencias institucionales si deben citarse. No cambiar fuente censal ni posiciones de las 31 cámaras.\n';

fs.mkdirSync(output, { recursive: true });
fs.writeFileSync(path.join(output, 'AUDITORIA_Y_CLASIFICACION.json'), JSON.stringify(report, null, 2) + '\n');
fs.writeFileSync(path.join(output, 'CLASIFICACION_PROPUESTA.md'), reviewMd);
fs.writeFileSync(path.join(output, 'AUDITORIA_ACTUAL.md'), auditMd);
for (const file of preserved) assert.equal(hash(file), report.sourceHashes[file], `Source changed: ${file}`);
console.log(JSON.stringify({ output, totals, sourceRecords: report.sourceRecords, validRecords: validCount,
  subtypes: rows.length, reviewSubtypes: review.length, reviewRecords: report.reviewRecords,
  currentInstitutionalRecordLeak: report.currentInstitutionalRecordLeak,
  leakedSubtypes: leakedInstitutional.map((row) => [row.SUBTIPO, row.NUMERO_REGISTROS]),
  currentKde: report.currentKde, currentGi: report.currentGi,
  preservedRuntimeFiles: preserved.length, proceedToImplementation: false }, null, 2));
