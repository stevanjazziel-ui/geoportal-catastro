# Auditoría metodológica del visor actual

Fecha: 1 octubre 2026. FASE 0 completada; sin cambios en aplicación, fuentes o publicación.

Versión auditada: 22693def36943208c744992a90fad1a5a0bcbffc.

## Componentes y dependencias

Todas las funciones de visor indicadas abajo pertenecen a visor-seguridad-riobamba-v2.html.

| COMPONENTE | ARCHIVO / FUENTE | FUNCIONES O RUTA DE DATOS |
| --- | --- | --- |
| Fuente y puntos de incidentes | visor-seguridad-riobamba-data.js | tools/build_riobamba_real_incidents.py: main; visor: events, renderMarkers, filteredEvents |
| Clasificación actual | data/seguridad-riobamba/clasificacion-incidentes-2026.json | builder: classification; visor: conflictEvents, syncKdeFilterOptions |
| KDE | riobamba-seguridad-kde-validacion-data.js; data/kde-validacion/DENSIDAD_INCIDENTES_KDE_700m.png | tools/build_kde_validation.py: build_density, main; visor: filteredKdePoints, getFilteredKdeSurface, kdeState, renderHotspots, renderKdeGraphicPanel |
| Gi* | riobamba-incidentes-spatial-data.js | tools/build_incident_spatial_reference.py: main; visor: getGiHotspotAnalysis, giClass, filteredGiCells |
| Cálculos por Plataforma y tasas | riobamba-seguridad-diagnostico-data.js | tools/build_security_diagnosis_phase1.py: metrics, platforms; visor: platformRecord, filteredPlatforms, renderPlatformDetail |
| Población y densidad | riobamba-censo-data/riobamba_manzanas_stats.json; riobamba_plataformas_stats.json | builder diagnóstico: population_allocations; visor: loadCensusLayers, manzanaPopulation, manzanaDensity |
| Evolución temporal | visor-seguridad-riobamba-data.js: events.date | visor: validDate, temporalRecords, renderGraphicAnalysis (isTemporalMode) |
| Tipos de incidentes y gráficos | events.category/subtype y platformMaster | visor: categorySummary, metricBars, renderGraphicAnalysis (isTypologiesMode), renderSummary |
| Filtros | visor-seguridad-riobamba-v2.html | analysisConfig, syncKdeFilterOptions, filteredEvents, kdeFilterMatches, update |
| 31 cámaras | riobamba-camaras-data.js | tools/build_riobamba_cameras_data.py: study_rows; visor: changeCameras, coverageCameraSet, renderCameraMarkers |
| Cobertura territorial | manzanas.geojson + cámaras + manToPlatform | visor: getCameraCoverageAnalysis, manzanaCoverageFraction, geometryAreaKm2, coverageTerritorialData, renderCameraCoverageGraphics |
| Cobertura poblacional | manzanas_stats.json + cámaras + manToPlatform | visor: getCameraCoverageAnalysis, coveragePopulationData, renderCameraCoverageGraphics; maestro: cameraCoveredPopulation* |
| UPC e infraestructura policial | policia-06d01-data.js | tools/build_policia_06d01_data.py: read_layer, transform_point, point_geometry; visor: filteredPoliceInfrastructure, renderPoliceLayers, renderPoliceDetail |
| Proximidad policial | riobamba-accesibilidad-policial-data.js | visor: policeAccessibility, renderGraphicAnalysis (policeAccessibility), renderPlatformDetail; no generador localizado en repositorio |
| Bulevares | data/premio-habitat/premio-habitat-boulevares.geojson; premio-habitat-conexiones.geojson | builder diagnóstico: network_union; visor: loadBoulevardNetwork, cameraNearBoulevardNetwork, renderBoulevardGraphics |
| Cobertura institucional | maestro + proximidad policial + cobertura calculada en visor | builder: classify_institutional_coverage; visor: renderInstitutionalGraphics, renderInstitutionalDetail |
| Brechas B1-B5 | maestro + getGiHotspotAnalysis + cobertura calculada | visor: gapPlatformRows, lowCoverageConcentrationCells, candidateZones, renderGraphicAnalysis; builder: classify_deficit, deficit_score, classify_conflict_exposure |

## Hallazgos que condicionan la implementación

1. Selección de conflictividad basada únicamente en hotspotEligible/incluir_hotspot. La propuesta detecta 497 registros de 9 subtipos institucionales hoy admitidos al KDE/Gi*. No han sido eliminados ni recalculados.

2. filteredEvents parte de conflictEvents, incluso en Consulta/Tipos/Temporal: la actividad institucional no es explorable allí. La nueva clase 4 necesita una fuente de consulta completa independiente del subconjunto analítico.

3. El generador asigna precisión A a toda coordenada original y mappable=true sin auditoría externa. Una coordenada presente no prueba precisión de campo; se verificó validez numérica y fecha, no exactitud del lugar ni frontera cantonal.

4. KDE: puntos originales, peso 1, UTM 17S, celda 20 m, radio 700 m. Kernel exp(-0.5*(d/h)^2), corte d<=h, sin normalización de densidad por unidad de superficie. Explicar qué significa bandwidth en este kernel y no confundir la rampa relativa (percentil 98) con significancia.

5. Concentraciones KDE: componentes de 4 vecinos sobre 35% del máximo; umbral descriptivo, no prueba estadística ni número validado de sectores. No cambiar radio automáticamente al filtrar.

6. Gi*: grilla fija 250 m, vecinos binarios 500 m, incluye la propia celda y ceros. Z umbrales 1.65/1.96/2.58, p nominal sin ajuste múltiple. Las celdas de borde se dibujan completas; se asignan a una sola Plataforma por centroide o intersección mayor, no equivalen al recorte exacto por Plataforma.

7. Población: maestro 171998 por asignación proporcional de intersecciones; cobertura/proximidad 171665 por asignación manToPlatform. Ambas provienen del censo existente, pero no son denominadores intercambiables. 177213 es el denominador urbano solicitado, no una población ya aplicada ni un límite urbano identificado.

8. Tasas actuales /1000 agregan categorías amplias de conflictividad. No existe el nuevo módulo Incidencia poblacional por tres clases ni tasa urbana /100000. Numerador urbano debe tener el mismo ámbito geográfico del denominador; NO usar automáticamente todo el cantón ni solo parroquia RIOBAMBA.

9. Cobertura en navegador usa muestreo de puntos de manzana y conversión métrica local aproximada. El maestro usa intersecciones UTM exactas y población areal. Diferencia a 150 m: navegador 14488/171665, maestro 14446/171998. La superficie 20.371896 km2 del gráfico corresponde a manzanas asignadas, NO al área total de los polígonos de las 18 Plataformas.

10. El maestro crea buffers con cámaras/policía previamente asignadas a Plataformas (29 cámaras, 17 dependencias), omitiendo los dos y nueve puntos externos respectivamente; el navegador de cobertura calcula con los 31 puntos. Los recursos externos pueden aportar cobertura interior: debe revisarse la extensión de cálculo sin eliminar posiciones.

11. Se conservan las 31 cámaras confirmadas. La institución original no siempre es GADM, aunque ambitoEstudio las rotule MUNICIPAL; distinguir universo acordado de titularidad documental sin modificarlo.

12. Proximidad policial: distancia euclidiana desde punto representativo de manzana, no red ni velocidades/tiempos. Metadato mezcla EPSG:32717 con aproximación local; no basta para probar una transformación UTM real. Falta generador reproducible de riobamba-accesibilidad-policial-data.js en este repositorio.

13. Exposición 100/250/500 m y cruces Bulevares dependen del conjunto analítico anterior. Los buffers de exposición son de todos los eventos elegibles, no exclusivamente hotspots estadísticos. Deberán recalcularse por clase tras aprobar la clasificación, manteniendo geometrías originales.

14. Brechas: persisten deficit_score ponderado 2/1 puntos, cobertura institucional por conteo de recursos presentes, límites discretos de exposición y candidaturas por número de banderas. No es AHP, pero tampoco una coincidencia transparente libre de pesos/umbrales arbitrarios como la solicitada. Hay que sustituir la síntesis y conservar variables observables.

15. candidateZones reparte población no cubierta de la Plataforma por igual entre sus celdas hotspot; NO calcula la población real de cada zona por intersección censal. lowCoverageConcentrationCells hereda cobertura media de Plataforma, no comprueba cobertura local de cada celda.

16. Los datos events.date contienen fecha, pero no hora. temporalRecords fija hour=null. No generar hora a partir de T00:00:00 ni inventar franjas. Separar mes y día de semana por clase aprobada.

17. No se aportaron contenidos de CMI Riobamba-Chambo ni documentos específicos de Ambato/Cuenca. No se atribuye a estas instituciones la metodología o umbrales del código existente; solicitar referencias si se requieren equivalencias documentales.

## Control de entrada

Base: 26716; válidos numéricos/fecha: 26716; originales Emergencias: 28843; peso espacial actual: 1.

Latitud: -1.878245 a -1.486536; longitud: -78.882122 a -78.444816. Esto no verifica la precisión de campo ni el límite cantonal.

KDE vigente: 12383 puntos. Gi*: 572 celdas, 117 hotspots y 77 coldspots, significancia nominal.

## Clasificación propuesta

| CLASE PROPUESTA | REGISTROS VÁLIDOS |
| --- | ---: |
| DELINCUENCIA | 2503 |
| VIOLENCIA | 1563 |
| CONVIVENCIA / INCIVILIDADES | 6976 |
| ACTIVIDAD INSTITUCIONAL / POLICIAL | 14770 |
| OTROS / REVISION | 904 |
| TOTAL | 26716 |

Tabla completa: [CLASIFICACION_PROPUESTA.md](CLASIFICACION_PROPUESTA.md). Datos y huellas de fuentes: [AUDITORIA_Y_CLASIFICACION.json](AUDITORIA_Y_CLASIFICACION.json).

## Decisión antes de continuar

Se detectan 39 subtipos ambiguos. Se detiene la implementación según la regla obligatoria. No se recalcularon KDE, Gi*, tasas, cámaras, coberturas ni brechas. La validación completa de fases 17/19 y consola corresponde después de la aprobación, no se presenta como realizada.

Para continuar: aprobar/corregir clasificación por subtipo; decidir el ámbito urbano del denominador 177213; acordar un único criterio censal de asignación y área para las salidas; aportar referencias institucionales si deben citarse. No cambiar fuente censal ni posiciones de las 31 cámaras.
