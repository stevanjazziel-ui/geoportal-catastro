# Actualizacion metodologica: resultados para revision

Fecha: 2026-10-01. Estado: implementacion local, SIN commit ni push.
Base de comparacion: version publicada 22693de. Auditoria previa conservada en AUDITORIA_ACTUAL.md y AUDITORIA_Y_CLASIFICACION.json.

## Alcance autorizado

Se conserva el visor actual, la URL publica, las geometrías originales de 18 Plataformas, la fuente censal, las posiciones de infraestructura y las 31 camaras acordadas. El usuario autorizo usar la union de las 18 Plataformas como ambito urbano operativo para las tasas sobre 177.213 habitantes; NO se presenta como limite urbano legal.

No se implementa AHP, peligrosidad, ponderacion arbitraria ni ranking final. Los subtipos ambiguos permanecen fuera del analisis de conflictividad y disponibles para consulta.

## Clasificacion aplicada

Fuente: Base de Datos Emergencias_SC_Riobamba (2).xlsx, hoja Export. Se conservan los identificadores, coordenadas originales, fechas, subtipos, parroquias, campo Emergencias y clasificacion anterior para trazabilidad.

| Clase | Base completa | Dentro de las Plataformas |
|---|---:|---:|
| Delincuencia | 2.503 | 2.199 |
| Violencia | 1.563 | 1.244 |
| Convivencia / Incivilidades | 6.976 | 6.367 |
| Actividad institucional / policial | 14.770 | 13.134 |
| Otros / revision | 904 | 788 |
| Total | 26.716 | 23.732 |

Los 139 subtipos, frecuencias, clase anterior, clase nueva y justificacion estan en CLASIFICACION_APLICADA.md. De la clase 5, 39 subtipos / 848 registros requieren revision; otros 56 registros se mantienen como otros no analiticos. Esta clasificacion de registros no acredita delitos judicialmente confirmados.

Solo clases 1, 2 y 3 participan en KDE, Gi*, incidencia y brechas. Las clases 4 y 5 permanecen consultables en Incidentes, Consulta, Tipos y Evolucion temporal.

## Incidencia poblacional

Nuevo acceso en Conflictividad, siguiendo el menu existente. Categoria, subtipo, parroquia, Plataforma, mes y fecha afectan los registros, mapa, KPI, graficos y tabla.

| Clase | Numerador dentro del ambito | Tasa / 100.000 hab. |
|---|---:|---:|
| Delincuencia | 2.199 | 1.240,88 |
| Violencia | 1.244 | 701,98 |
| Convivencia | 6.367 | 3.592,85 |

Denominador general: 177.213, referencia urbana indicada por el proyecto. Denominadores por Plataforma: poblacion censal asignada mediante el estimador areal existente. Su suma es 171.998; no se modifica ni escala artificialmente para igualarla a la referencia urbana.

Comprobacion manual K: 372 / 12.255 * 1.000 = 30,354957 registros de delincuencia por cada 1.000 habitantes. El visor muestra 30,35. Violencia K: 152 / 12.255 * 1.000 = 12,40. Convivencia K: 639 / 12.255 * 1.000 = 52,14.

El mapa general muestra registros analiticos filtrados / 1.000 habitantes; no llama a su suma tasa de delincuencia. Las tasas de las tres clases se presentan por separado. Con una clase seleccionada, el contexto identifica el subconjunto; los ceros de clases filtradas no significan ausencia en la base completa.

## KDE y Gi*

Coordenadas originales; peso 1 por registro. Emergencias conserva su valor fuente, pero NO pondera KDE, Gi* ni tasas. Distancias en WGS 84 / UTM 17S, EPSG:32717; visualizacion geografica en Leaflet.

KDE: kernel gaussiano truncado al bandwidth, celda 20 m y bandwidth operativo existente 700 m, fijo al filtrar. Se regeneraron tambien rasters de validacion 200/300/500 m. Superficie continua sobre una cuadrícula comun, recortada visualmente por el ambito, no por Plataforma. Intensidad relativa, NO probabilidad, peligrosidad ni significancia estadistica.

KDE general utiliza 11.042 registros de clases 1-3; excluye 15.674 institucionales/otros. Incluye 1.232 puntos analiticos externos como aportes al borde de la superficie continua. NO entran al numerador de tasas urbanas ni al Gi* del ambito. Este universo ampliado queda visible en la tabla KDE como Fuera de Plataformas; no equivale al universo urbano de 9.810 registros.

Gi*: 572 celdas regulares de 250 m, vecindad 500 m y 9.810 registros dentro del ambito. Se recorta la geometria de celdas al limite real, conservando la cuadrícula de calculo. Inferencia normal nominal, sin correccion de pruebas multiples.

| Filtro | Registros KDE | Registros Gi* | Celdas hotspot | Celdas coldspot |
|---|---:|---:|---:|---:|
| Todas las clases analiticas | 11.042 | 9.810 | 127 | 77 |
| Delincuencia | 2.503 | 2.199 | 98 | 38 |
| Violencia | 1.563 | 1.244 | 106 | 87 |
| Convivencia | 6.976 | 6.367 | 111 | 41 |
| Robo a domicilio | 225 | 153 | 50 | 21 |

La prueba de kernel confirma: tres registros coincidentes producen tres veces la contribucion de uno; una zona sin aportes produce cero. Los filtros alteran realmente el raster calculado y Gi*. La capa de puntos originales conserva control de encendido/apagado.

## Camaras y cobertura

31 registros unicos, cero duplicados: 30 DOMO y RIO-068-LA, conservado por instruccion expresa del usuario. Todas las 31 posiciones originales participan; 29 estan dentro de las Plataformas y 2 fuera, cuyos buffers pueden contribuir al ambito. No se eliminan camaras por estar fuera.

Buffers calculados en EPSG:32717, disueltos antes de intersecar; radios, NO diametros. Sin doble conteo de area por superposicion. Cobertura territorial y poblacional tienen datasets y graficos independientes.

| Radio | Area cubierta km2 | % territorio | Poblacion cubierta | % poblacion |
|---|---:|---:|---:|---:|
| 100 m | 0,877181 | 3,0 % | 6.354 | 3,7 % |
| 150 m | 1,900881 | 6,5 % | 14.581 | 8,5 % |
| 200 m | 3,187249 | 10,9 % | 24.464 | 14,2 % |

Area total: 29,293119 km2 de la union real de Plataformas, NO los 20,371896 km2 de superficie neta de manzanas utilizados por el frontend anterior. Poblacion analizada: 171.998, asignacion censal areal existente, NO 171.665 del antiguo frontend aproximado. Estos cambios corrigen denominadores; no alteran las geometrías ni la fuente censal. Conteo global: 2.825 manzanas unicas, evitando sumar dos veces las que cruzan Plataformas.

Cobertura de incidentes se separa por clase. En 150 m: 221 / 2.199 delincuencia (10,05 %); 115 / 1.244 violencia (9,24 %); 636 / 6.367 convivencia (9,99 %). El indicador usa la coordenada original dentro de la union de buffers; no presupone vigilancia efectiva.

La poblacion cubierta es una estimacion uniforme areal dentro de cada manzana, no ubicaciones observadas de residentes. Grafico territorial en km2; grafico poblacional en habitantes; seleccion de Plataforma y escenario actualiza cada uno por separado.

## Policia, Bulevares y brechas

Proximidad a infraestructura policial: distancia euclidiana metrica desde el punto representativo de manzana a la mas cercana de las 26 dependencias originales. Se conserva el inventario; 17 dependencias / 13 UPC estan dentro del ambito. Las 9 dependencias exteriores NO se descartan del calculo de cercania. No es tiempo de respuesta ni accesibilidad por red vial. Misma poblacion censal de 171.998, bandas poblacionales reconciliadas.

Bulevares: geometrías intactas. Se separan delincuencia/violencia/convivencia a 100 m de la red. Cercania no implica causalidad ni garantiza seguridad.

Brechas: variables transparentes de problematica, poblacion y cobertura. Se invalidan puntuaciones arbitrarias anteriores y prioridades automaticas. B2 usa celdas Gi* hotspot nominal con registros y menos del 50 % de superficie de la celda cubierta localmente; NO el promedio de la Plataforma. B5 exige ademas poblacion estimada fuera de cobertura en esa misma celda. El 50 % es un criterio exploratorio visible, no un umbral formal validado. B3 usa estimacion poblacional a 250 m de incidentes y fuera de los buffers; B1/B4 presentan porcentajes/variables sin indice compuesto. En el escenario general de 150 m se identifican 109 celdas B2 y 109 B5, sin ranking final.

## Archivos y componentes

Codigo actualizado:
- visor-seguridad-riobamba-v2.html: FilterBar contextual, filtros sincronizados, incidencia, graficos por modulo, cobertura oficial, tabla de Bulevares, brechas y metadatos.
- tools/build_riobamba_real_incidents.py: clasificacion reproducible y trazabilidad de campos originales.
- tools/build_kde_validation.py: exclusiones por clase; rasters recalculados.
- tools/build_incident_spatial_reference.py: geometria Gi* recortada al ambito.
- tools/build_security_diagnosis_phase1.py: dependencias recalculadas y eliminacion de puntuaciones arbitrarias activas.
- tools/build_methodology_update.py: nuevo generador de tasas, cobertura metrica, proximidad y tabla de validacion.
- tools/audit_methodology_review.cjs: auditoria inicial y propuesta; su snapshot original NO se sobrescribe tras la implementacion.
- tools/validate_incident_dependencies.cjs, tools/validate_camera_coverage_graphics.cjs y tools/validate_methodology_update.cjs: pruebas reproducibles.

Datos regenerados/nuevos: visor-seguridad-riobamba-data.js; riobamba-seguridad-diagnostico-data.js; riobamba-seguridad-kde-validacion-data.js; riobamba-incidentes-spatial-data.js; riobamba-accesibilidad-policial-data.js; nuevo riobamba-metodologia-data.js; rasters DENSIDAD_INCIDENTES_KDE_200/300/500/700m.png. Reportes nuevos en esta carpeta. Inventarios originales de camaras, Plataformas y censo conservan hashes originales.

## Validacion realizada

- node tools/validate_methodology_update.cjs: PASS; clasificacion, sumas, tasas, filtros, hashes originales, cobertura y proximidad.
- node tools/validate_incident_dependencies.cjs: PASS; origen, dependencias, raster filtrado/general, kernel y Gi* por clases/subtipo.
- node tools/validate_camera_coverage_graphics.cjs: PASS; 57 selecciones, 114 representaciones de modulo, area/poblacion independientes y exportacion de cobertura.
- Navegacion y render local: Diagnostico, poblacion, densidad, exposicion, Incidentes, Consulta, KDE, Gi*, Incidencia, Tipos, Temporal, Policia/proximidad, inventario de camaras, ambas coberturas, Bulevares, institucional y B1-B5 comprobados durante la implementacion.
- Pruebas visibles finales: incidencia general/K; KDE delincuencia/violencia; Gi* violencia; actividad institucional disponible en Tipos; meses/dias reales y hora No disponible en Temporal; tres escenarios de area; poblacion 200 m; detalle y minimapa de I con geometria y teselas cargadas. Consola de errores del navegador: vacia.
- VALIDACION_PLATAFORMAS.csv contiene las 18 filas, tasas independientes, celdas Gi*, cobertura territorial, poblacional y de delincuencia. VALIDACION_METODOLOGICA.json conserva los resultados numericos.
- Evidencia visual: VALIDACION_VISUAL_INCIDENCIA.png.

## Pendientes y limitaciones: NO ocultar

1. Revisar los 39 subtipos ambiguos antes de incorporarlos a analisis; por ahora excluidos.
2. Gi* sin correccion de pruebas multiples; significancia nominal. Resumen Gi* por Plataforma asigna cada celda a una Plataforma, no reparte la significancia por area de cruce.
3. Coordenadas originales disponibles no significan precision de campo verificada independientemente; se retira la etiqueta publica Precision alta.
4. Las Plataformas originales tienen un pequeño solape de 74,166 m2. La union evita duplicacion del area global; la poblacion preserva el estimador censal existente. Las tasas de poblaciones pequeñas, como E (129 habitantes asignados), requieren especial cautela.
5. No se recibieron los documentos formales del CMI Riobamba-Chambo ni las metodologías de Ambato/Cuenca. No se afirma haber validado equivalencia con esos marcos.
6. La navegacion general de Descargas / Ficha de Plataforma / Diagnostico integrado permanece deshabilitada como en el visor previo; no se declara implementada. El panel de detalle y las exportaciones existentes de cobertura si fueron comprobados.
7. En el viewport normal 1280x720 existe un problema previo de acceso a grupos inferiores cuando el sidebar esta colapsado. Las pruebas de navegacion completa requirieron viewport temporal 1440x1100; no se certifica responsive integral ni se modifica el layout en esta actualizacion metodologica.

El resultado es un diagnostico exploratorio de registros, no un mapa de peligrosidad. La revision metodologica y autorizacion de publicacion siguen pendientes.
