# Revision local de la ampliacion cantonal

Fecha: 2026-10-01. Revision local completada antes de commit/push. El usuario autorizo publicar posteriormente mediante el mensaje "publica".

Visor local: http://127.0.0.1:8767/visor-seguridad-riobamba-v2.html?check=cantonal-review-20261001

## Alcance implementado

- Selector funcional Cantonal / Urbano / Rural sin sustituir el layout ni la URL.
- Plataformas originales para el ambito urbano operativo; once parroquias rurales reales, seleccion por mapa o lista, etiquetas, zoom y minimapa.
- Asignacion espacial separada de los registros originales. No se trasladaron incidentes a centroides ni se alteraron coordenadas originales.
- Filtros de clase, subtipo, mes y fecha exacta sincronizados con puntos, KDE, KPI, tablas y graficos. KDE inicia en DELINCUENCIA.
- KDE metrico con una malla por ambito, suma de contribuciones, mascara posterior y reproyeccion del raster mediante indices UTM/WGS84. Paleta verde/turquesa secuencial y puntos originales activables.
- Gi* urbano conservado y Gi* rural exploratorio. La seleccion de parroquia NO recalcula una prueba independiente para esa parroquia: explora la malla rural global del subconjunto temporal/tipologico.
- Tasas separadas para Delincuencia, Violencia y Convivencia; comparacion urbano/rural sin ranking compuesto.
- Evolucion mensual y por dia de semana utilizando fechas reales. No se invento una hora de ocurrencia.
- Proximidad policial euclidiana de puntos de eventos a dependencias inventariadas; no tiempos de respuesta ni cobertura de toda la poblacion.
- Escenarios originales 100/150/200 m, 31 camaras y resultados urbanos de superficie, poblacion e incidentes conservados. El contexto cantonal muestra el escenario urbano identificado como tal.
- Exportacion CSV contextual y tablas reproducibles por parroquia; limitaciones visibles para resultados rurales no calculables.
- Correccion acotada de un fallo CSS previo que comprimia el contenido movil en la columna del menu. Misma navegacion lateral, sin nueva navegacion superior.

## Control de entrada y ambitos

| Concepto | Registros |
|---|---:|
| Base original, IDs unicos | 26.716 |
| URBANO, union operativa de las 18 Plataformas | 23.732 |
| RURAL, parroquias rurales menos union urbana | 2.134 |
| SIN_ASIGNAR | 850 |
| SIN_ASIGNAR dentro del canton | 820 |
| Fuera del canton | 30 |
| Dentro del canton, todas las clases | 26.686 |
| Elegibles originales, clases 1/2/3 | 11.042 |
| Analiticos urbanos | 9.810 |
| Analiticos rurales | 867 |
| Analiticos cantonales | 11.034 |

El analisis cantonal incluye puntos internos sin unidad asignada; no asigna parroquias por semejanza de texto. La superposicion Gi* urbana/rural deja fuera 357 eventos analiticos internos sin unidad, y lo advierte expresamente. KDE cantonal y tasas cantonales si incluyen esos 357.

Clases originales: Delincuencia 2.503; Violencia 1.563; Convivencia 6.976; servicios institucionales 14.770; Otros/revision 904. Los servicios institucionales y Otros/revision se consultan, pero no entran en KDE, Gi* ni tasas de conflictividad. Los 39 subtipos ambiguos no se reclasificaron arbitrariamente.

## Parametros y resultados

Todos los calculos de distancia usan EPSG:32717; representacion cartografica WGS84. Peso = 1 por observacion, sin multiplicar por Emergencias. Coincidencias de coordenadas entre observaciones diferentes se conservan.

| Metodo | Urbano | Rural | Cantonal |
|---|---|---|---|
| KDE, celda / bandwidth | 20 / 700 m | 100 / 1.500 m | 100 / 1.500 m |
| Gi*, celda / vecindad | 250 / 500 m | 1.000 / 2.000 m | Superposicion, no prueba unica |
| Gi*, celdas | 572 | 1.132 | Mantiene las dos mallas |
| Gi*, eventos analiticos | 9.810 | 867 | 10.677; 357 sin malla |

KDE conserva el kernel relativo existente: exp(-0.5*d^2/h^2), truncado en h. Suma antes de mascara; no es una intensidad normalizada de incidentes/km2. Concentraciones descriptivas = componentes conectados sobre el 35% del maximo; no significancia estadistica.

Gi* usa pesos binarios incluyendo la propia celda y p nominal bilateral de aproximacion normal, sin FDR. Se evaluaron nueve configuraciones rurales: celdas 500/750/1.000 m y vecindades 1,5/2/3 veces la celda. Se selecciono el soporte mayor para reducir fragmentacion y la vecindad menor evaluada sin aislados y con media de al menos ocho vecinos; NO se selecciono segun cuantos hotspots producia.

Resultado rural general: 119 celdas ocupadas y 1.013 vacias; media 0,766 eventos/celda; maximo 133; vecinos medios 10,65, minimo 3, maximo 12, sin aislados. Siete clases: H99 = 47; H95 = 8; H90 = 5; no significativo = 1.072; C90/C95/C99 = 0. No se forzaron coldspots. Totales hotspots por clase: Delincuencia 55, Violencia 53, Convivencia 57. Los recuentos por parroquia pueden incluir una misma celda que cruza limites; las areas usan intersecciones geometricas reales.

La escasez, exceso de ceros y minimo de tres vecinos limitan la inferencia normal rural. Estos resultados son EXPLORATORIOS, nominales y pendientes de revision metodologica; no equivalen a peligrosidad ni a validacion formal de significancia corregida. Referencia primaria: [documentacion Gi*](https://pro.arcgis.com/en/pro-app/3.4/tool-reference/spatial-statistics/h-how-hot-spot-analysis-getis-ord-gi-spatial-stati.htm).

Sensibilidad KDE rural, mismos 867 puntos / celda 100 m: bandwidth 1.000/1.500/2.000 m produce 3/3/2 componentes descriptivos. Mediana de vecino mas cercano = 0 por coordenadas coincidentes reales; p90 = 254,45 m. Los 1.500 m son un escenario fijo exploratorio de escala rural, NO un parametro optimizado ni certificado.

## Poblacion y tasas

| Referencia | Poblacion | Delincuencia | Violencia | Convivencia | Tasas por 100.000, mismo orden |
|---|---:|---:|---:|---:|---|
| Cantonal | 260.882 | 2.501 | 1.562 | 6.971 | 958,67 / 598,74 / 2.672,09 |
| Urbana | 177.213 | 2.199 | 1.244 | 6.367 | 1.240,88 / 701,98 / 3.592,85 |
| Rural | 83.669 | 219 | 246 | 402 | 261,75 / 294,02 / 480,46 |

Las once parroquias rurales suman 71.991 habitantes CPV, NO 83.669. La referencia rural incluye otros 11.678 de PARROQ 060150. La geometria operativa no coincide con la delimitacion censal/legal urbana, por lo que estas tasas son referencias operativas, no denominadores espacialmente concordantes certificados. Por unidad se conserva su poblacion CPV y tasa /1.000; no se redistribuyeron habitantes artificialmente. La ficha indica que los numeradores responden a filtros activos.

La union original de Plataformas ocupa 29,293119 km2; no sustituye un limite urbano oficial. Existen 32,760976 km2 internos fuera de los ambitos definidos. Hay 585,12 m2 de Plataformas fuera del canton y 0,098614 km2 de superposicion urbana/rural; se documentan sin redibujar las Plataformas. La prioridad urbana evita doble conteo de 68 puntos presentes tambien en parroquias rurales.

## Cobertura conservada y datos no disponibles

31 registros de camaras, 31 unicos, cero duplicados. Se conserva RIO-068-LA por autorizacion del usuario. No se incorporaron las 103 camaras externas al universo de estudio.

| Radio | Area cubierta km2 | % territorio | Habitantes cubiertos | % poblacion |
|---|---:|---:|---:|---:|
| 100 m | 0,877181 | 2,9945 | 6.354 | 3,6942 |
| 150 m | 1,900881 | 6,4892 | 14.581 | 8,4774 |
| 200 m | 3,187249 | 10,8805 | 24.464 | 14,2234 |

Estos escenarios usan el area operativa original y 171.998 habitantes georreferenciados del calculo de cobertura, no la referencia urbana 177.213. Los donuts territoriales usan km2; los poblacionales, habitantes. A 150 m, observaciones cubiertas: Delincuencia 221, Violencia 115, Convivencia 636.

No disponible: inventario rural validado de camaras, poblacion georreferenciada rural completa, exposicion/cobertura poblacional rural, deficit de videovigilancia rural, brechas derivadas y zonas candidatas rurales. No se extrapolan inventarios urbanos, no se representan estos faltantes mediante cero, ni se inventan AHP o indices.

26 dependencias policiales originales: 17 urbanas, ocho rurales y una externa (Chambo). Los ceros en tablas significan cero entradas del INVENTARIO suministrado, no inexistencia real de dependencias. Proximidad rural media de los 2.134 puntos de eventos: aproximadamente 1.783 m; no representa toda la poblacion. Red de Bulevares urbana conservada como contexto cantonal, sin inventar red rural ni rutas/velocidades.

## Fuentes, archivos y pruebas

Fuentes: Base de Datos Emergencias_SC_Riobamba (2).xlsx y clasificacion original; shapefiles limite_canton_riobamba_wgs84 / division_parroquial_riobamba_wgs84; 18 Plataformas originales; CPV 2022 (cruce espacial auditado, no union directa CODPAR); inventarios originales de camaras, policia y Bulevares. La clase A de la fuente no certifica independientemente la exactitud de las coordenadas.

Modificados: visor-seguridad-riobamba-v2.html; tools/validate_methodology_update.cjs (contexto de aislamiento de pruebas). Ninguno de los trece datasets productivos originales fue alterado: hashes conservados.

Nuevos de esta ampliacion: riobamba-cantonal-data.js; riobamba-cantonal-view.js; tools/build_cantonal_analysis.py; tools/validate_cantonal_analysis.cjs; esta carpeta de resultados. Se reutilizo la auditoria local previa de tools/audit_cantonal_expansion.py y auditoria-cantonal-20261001, sin repetir innecesariamente la lectura del censo nacional completo. PUBLICACION_EE782CC.png es una evidencia previa ajena a esta ampliacion.

Salidas: [metadatos](METODOLOGIA.json), [asignacion espacial](ASIGNACION_ESPACIAL.csv), [evaluacion de mallas](EVALUACION_GI_RURAL.json), GI_RURAL_GENERAL/DELINCUENCIA/VIOLENCIA/CONVIVENCIA.csv (COUNT, GI_ZSCORE, GI_PVALUE, GI_CLASS, PARROQUIA), [validacion parroquial](TABLA_VALIDACION_PARROQUIAS.csv), [validacion numerica](VALIDACION.json), [validacion navegador](VALIDACION_NAVEGADOR.json).

Pruebas ejecutadas, todas PASS:

- node tools/validate_cantonal_analysis.cjs: cada celda Gi* frontend contra Python; simetria/vecinos; KDE sumatorio, coincidencias, cero eventos, mascara y sensibilidad; datos originales y 31 camaras preservados.
- node tools/validate_methodology_update.cjs: tasas por clase, scope operativo, tres radios, separacion area/poblacion y filtros.
- node tools/validate_camera_coverage_graphics.cjs: 57 selecciones, 114 renders de ambos modulos y auditoria de las 31 camaras.
- node tools/validate_incident_dependencies.cjs: kernel original, filtros y dependencias urbanas. Esta prueba historica ejercita los 11.042 elegibles originales; la nueva UI urbana usa solo los 9.810 asignados, contrastados por la prueba metodologica y el navegador.
- git diff --check: sin errores de whitespace; solo advertencias normales LF/CRLF.

## Evidencia visual de los veinte puntos solicitados

| Punto | Evidencia / verificacion |
|---|---|
| 1. Cantonal | [KDE cantonal](KDE_CANTONAL.png), [Gi* cantonal](GI_CANTONAL.png) |
| 2. Urbano | [KDE urbano](KDE_URBANO_DELINCUENCIA.png) |
| 3. Rural | [KDE rural](KDE_RURAL.png) |
| 4. Selector Plataformas | [Plataforma I y cobertura](COBERTURA_PLATAFORMA_I.png); K tambien probado con KDE |
| 5. Selector parroquias | [San Luis](PARROQUIA_SAN_LUIS.png), [Cacha por click](CACHA_PUNTOS_Y_KDE.png) |
| 6. Limites rurales | [Limites reales](KDE_RURAL.png) |
| 7. KDE Delincuencia urbano | [2.199 registros](KDE_URBANO_DELINCUENCIA.png) |
| 8. KDE Violencia urbano | [1.244 registros](KDE_URBANO_VIOLENCIA.png) |
| 9. KDE Convivencia urbano | [6.367 registros](KDE_URBANO_CONVIVENCIA.png) |
| 10. KDE rural | [219 Delincuencia](KDE_RURAL.png), [zoom 75 San Luis](PARROQUIA_SAN_LUIS.png) |
| 11. Hot Spot urbano | [Gi* urbano](GI_URBANO.png) |
| 12. Hot Spot rural | [Gi* rural](GI_RURAL.png), [filtro 99%](GI_RURAL_99.png) |
| 13. Incidencia poblacional | [Cantonal](INCIDENCIA_CANTONAL.png), [rural](INCIDENCIA_RURAL.png) |
| 14. Comparacion urbano/rural | [Tasas independientes](COMPARACION_URBANO_RURAL.png) |
| 15. Cobertura territorial | [Superficie](COBERTURA_TERRITORIAL.png) |
| 16. Cobertura poblacional | [Habitantes](COBERTURA_POBLACIONAL.png) |
| 17. Cobertura de incidentes | [Tres clases](COBERTURA_INCIDENTES.png) |
| 18. Validacion por Plataforma | [CSV original preservado](../revision-metodologica-20261001/VALIDACION_PLATAFORMAS.csv); validado numericamente |
| 19. Validacion por parroquia | [CSV nuevo](TABLA_VALIDACION_PARROQUIAS.csv), tasas y siete clases Gi* |
| 20. Consola sin errores | [Registro navegador](VALIDACION_NAVEGADOR.json): consoleErrors = [] |

Complementarias: [temporal Calpi](EVOLUCION_TEMPORAL_CALPI.png), [proximidad rural](PROXIMIDAD_RURAL.png), [limitaciones rurales](BRECHAS_RURALES_LIMITACIONES.png), [movil 390 px](RESPONSIVE_390.png).

Aprobacion de publicacion recibida despues de presentar esta revision. No se presenta el Gi* rural ni los denominadores operativos como una certificacion metodologica definitiva. Los JSON de validacion documentan la etapa previa a la publicacion.
