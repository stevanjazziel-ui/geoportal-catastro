# Cierre final del estudio de videovigilancia - Riobamba



**Entrega final. Publicacion autorizada por el usuario; se conservan las limitaciones y advertencias del estudio.**

## Resumen ejecutivo

103 existentes con103geometrias,0nulas;50municipales=22rurales+4LasAbras+24estructurales;30Policia;183equipos. Existentes ocupan100emplazamientos por tres pares documentales co-localizados, sin doble conteo en cobertura.

Las nuevas municipales desplazan 15 puntos. Se modifican 1 policiales tras cerrar las50; las demas conservan su posicion.

| INDICADOR | 103 | 153 | 183 |
| --- | --- | --- | --- |
| Territorio urbano potencialmente cubierto (%) | 25.078 | 34.834 | 41.156 |
| Territorio cantonal potencialmente cubierto (%) | 0.917 | 1.465 | 1.655 |
| Poblacion urbana estimada cubierta (%) | 33.211 | 44.943 | 55.240 |
| DELINCUENCIA eventos cantonales cubiertos (%) | 44.962 | 56.104 | 67.246 |
| DELINCUENCIA Hot Spots CUBIERTO | 159 | 171 | 234 |
| DELINCUENCIA Hot Spots PARCIAL | 110 | 113 | 68 |
| DELINCUENCIA Hot Spots SIN_COBERTURA | 81 | 66 | 48 |
| VIOLENCIA eventos cantonales cubiertos (%) | 32.599 | 45.941 | 57.772 |
| VIOLENCIA Hot Spots CUBIERTO | 147 | 176 | 264 |
| VIOLENCIA Hot Spots PARCIAL | 135 | 154 | 96 |
| VIOLENCIA Hot Spots SIN_COBERTURA | 153 | 105 | 75 |
| CONVIVENCIA eventos cantonales cubiertos (%) | 47.394 | 57.334 | 70.080 |
| CONVIVENCIA Hot Spots CUBIERTO | 161 | 179 | 244 |
| CONVIVENCIA Hot Spots PARCIAL | 126 | 131 | 88 |
| CONVIVENCIA Hot Spots SIN_COBERTURA | 95 | 72 | 50 |
| ANILLO_VIAL (%) | 31.868 | 87.551 | 88.560 |
| CICLOVIAS (%) | 49.390 | 56.436 | 61.622 |
| BOULEVARD_MACAJI_BELLAVISTA (%) | 64.154 | 98.102 | 98.461 |
| QUEBRADA_LAS_ABRAS (%) | 5.974 | 34.833 | 34.833 |

## Restriccion y prioridades municipales

Macaji anterior=91.9369%; FINAL SIN Policia=98.10230%; con183=98.46103%. Longitudtotal=9.541698km; cubierta153=9.360625km; remanente153=181.073m. La condicion>=98% se cumple antes de revisar Policia.

Se mantienen26municipales aceptadas y se seleccionan24 entre nodos/cruces reales. MILP HiGHS: variables binarias por candidato, union de intervalos lineales de cobertura200m, no muestreo raster ni suma de buffers. Macaji>=98% es restriccion; maximizar Anillo y luego maximizar Ciclovias sin sacrificar Anillo (tolerancia numerica0.001m). Sin cuotas individuales ni pesos arbitrarios. Identificadores municipales se emparejan minimizando desplazamiento, no determinan la seleccion.

| CORREDOR | ANTES_PCT | FINAL_153_PCT | DIFERENCIA_PP |
| --- | --- | --- | --- |
| BOULEVARD_MACAJI_BELLAVISTA | 91.937 | 98.102 | 6.165 |
| ANILLO_VIAL | 76.604 | 87.551 | 10.947 |
| CICLOVIAS | 86.678 | 56.436 | -30.242 |

**ADVERTENCIA RELEVANTE: la prioridad estricta de maximizar Anillo produce una perdida importante de Ciclovias. No se oculta ni se presenta esta configuracion como mejora en los tres corredores. Recuperar la cobertura previa de Ciclovias requiere revisar el compromiso entre prioridades; no se cambia automaticamente la orden del usuario ni se transfieren rurales/policiales.**

## Diagnostico de la condicion no cumplida: conservar Ciclovias

Dos comprobaciones auxiliares usan los mismos nodos, radios y26municipales fijas:1)mantener24estructurales,Macaji>=98% y conservar la cobertura anterior deCiclovias;2)minimizar el numero de estructurales necesario para conservar simultaneamente Anillo maximo y Ciclovias anterior. Ninguna modifica las50finales ni crea una propuesta oficial nueva. No son nuevas ponderaciones; sirven para explicar el compromiso y la solucion minima necesaria.

| case | status | message | structuralCameras | municipalTotal | percent | mipGap | dualBound |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 24estructurales,conservarCiclovias,maximizarAnillo | 1 | Time limit reached. (HiGHS Status 13: Time limit reached) | 24 | 50 | {'BOULEVARD_MACAJI_BELLAVISTA': 98.46102817243909, 'ANILLO_VIAL': 69.60112048748472, 'CICLOVIAS': 86.95557083862703} | 0.060 | -5,248.245 |
| Minimoestructurales,conservarAnilloyCiclovias | 0 | Optimization terminated successfully. (HiGHS Status 7: Optimal) | 30 | 56 | {'BOULEVARD_MACAJI_BELLAVISTA': 98.13886125410177, 'ANILLO_VIAL': 88.35873997265384, 'CICLOVIAS': 87.70001430731467} | 0.000 | 30.000 |

Si una corrida termina por limite de tiempo, se reporta incumbente y cota, NO se declara minimo global. Un resultado alternativo con24requiere autorizacion para modificar la prioridad estricta de Anillo. Un resultado conmasde24NO se incorpora porque se mantienen exactamente50municipales.

| phase | objective | status | message | seconds | mipGap | nodes | modelCoveredM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ANILLO_VIAL | 0 | Optimization terminated successfully. (HiGHS Status 7: Optimal) | 77.062 | 0.000 | 2746 | 11,492.517 |
| 2 | CICLOVIAS | 0 | Optimization terminated successfully. (HiGHS Status 7: Optimal) | 89.047 | 0.000 | 1153 | 6,194.397 |

La solucion es optima numericamente dentro del universo de candidatos real disponible, con las tolerancias reportadas. No demuestra optimalidad sobre cualquier poste o emplazamiento no cartografiado. Las fases ordenadas de Anillo y Ciclovias quedan en OPTIMIZACION_ESTRUCTURAL.json.

## Distribucion y movimientos municipales

| ID | GRUPO | DISTANCIA_MOVIMIENTO_M | CAMBIO | MOTIVO |
| --- | --- | --- | --- | --- |
| MUN-001 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-002 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-003 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-004 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-005 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-006 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-007 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-008 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-009 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-010 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-011 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-012 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-013 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-014 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-015 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-016 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-017 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-018 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-019 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-020 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-021 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-022 | CABECERA_RURAL | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-023 | LAS_ABRAS | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-024 | LAS_ABRAS | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-025 | LAS_ABRAS | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-026 | LAS_ABRAS | 0.000 | False | Mantener posicion aceptada; no se demuestra mejora que justifique moverla |
| MUN-027 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-028 | RED_ESTRUCTURAL | 376.063 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-029 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-030 | RED_ESTRUCTURAL | 1,289.059 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-031 | RED_ESTRUCTURAL | 1,073.480 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-032 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-033 | RED_ESTRUCTURAL | 9.813 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-034 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-035 | RED_ESTRUCTURAL | 62.190 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-036 | RED_ESTRUCTURAL | 192.914 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-037 | RED_ESTRUCTURAL | 494.192 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-038 | RED_ESTRUCTURAL | 230.030 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-039 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-040 | RED_ESTRUCTURAL | 3,846.053 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-041 | RED_ESTRUCTURAL | 2,780.331 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-042 | RED_ESTRUCTURAL | 2,446.090 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-043 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-044 | RED_ESTRUCTURAL | 2,845.047 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-045 | RED_ESTRUCTURAL | 62.534 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-046 | RED_ESTRUCTURAL | 135.893 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-047 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-048 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-049 | RED_ESTRUCTURAL | 78.388 | True | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |
| MUN-050 | RED_ESTRUCTURAL | 0.000 | False | Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor |

Se conservan2por cada11cabeceras y4Abras aceptadas. Las posiciones propuestas requieren inspeccion de poste, energia, permisos y campo visual.

## Policia: revision marginal despues de cerrar153

Se inicia con las30 del ultimo paquete consolidado, no con una seleccion nueva. Se recalculan las30 frente a103+50final+otras29. Se revisan las5observadas y otras con perdida de eventos D/V y aumento de solape tras la nueva configuracion municipal. Un reemplazo requiere esa perdida comprobada, alternativa con coincidencia D/V significativa residual, masD+V, sin disminuir D ni V individualmente y menos solape. No se usan cortes de distancia,90%solape ni minimos de eventos. Corredores y UPC se reportan, no optimizan la seleccion policial. La revision es local secuencial, no optimizacion completa de30.

| ID_ANTERIOR | CANDIDATO_ANTERIOR | CANDIDATO_FINAL | DV_NUEVOS_ANTES | DV_NUEVOS_DESPUES | SOLAPE_ANTES | SOLAPE_DESPUES | MOTIVO |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POL-06 | CAND-POL-01923 | CAND-POL-02095 | 4 | 8 | 91.238 | 78.116 | Perdida comprobada con nuevas municipales: 6 a 4 D/V. Alternativa significativa D/V: 4 a 8 exclusivos; solape 91.24% a 78.12%; sin disminuir D ni V individualmente. |

POLICIA_CAMBIOS_FINAL.csv contiene solo reemplazos reales. Los aportes exclusivos no se suman para obtener ganancia global; las comparaciones de escenarios se calculan con la union completa. Tablas detalladas conservan superficie y nivel de significancia, que pueden variar aunque crezca el numero de eventos.

## Georreferenciacion de las cuatro recuperadas

| ID | X | Y | DIRECCION_DOCUMENTAL | DIRECCION_CARTOGRAFICA | METODO_GEO | FUENTE_GEO | CONFIANZA_GEO | OBSERVACION_GEO |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RIO-016-DOMO | 763,618.772 | 9,812,896.385 | Leopoldo Freire y Calle V | LEOPOLDO FREIRE x Y | INTERSECCION_CENSAL_Y_REFERENCIA_TERRITORIAL_ACEPTADA | C:\Users\PC\Downloads\barrios y plataformas\vias\vias_canton_riobamba_utm.shp:nom_eje; FID 1541/1544; GDB Bienestar_social FID18; red OSM local de Riobamba | MEDIA | Usuario acepta el nodo censal Freire x Y con confianza MEDIA despues de revisar la referencia municipal Centro de Rehabilitacion Social, a 98.71 m. Documento conserva Calle V; CSV original dice Calle Y. No se afirma equivalencia V/Y. La GDB rotula Freire a 943.98 m; en el sector la red municipal es sin nombre y la red OSM local rotula Leopoldo Freire. Candidato antes descartado, ahora aceptado expresamente con esta discrepancia. Dos equipos, mismo emplazamiento cartografico; instalacion fisica pendiente de campo. |
| RIO-017-FIJA | 763,618.772 | 9,812,896.385 | Leopoldo Freire y Calle V | LEOPOLDO FREIRE x Y | INTERSECCION_CENSAL_Y_REFERENCIA_TERRITORIAL_ACEPTADA | C:\Users\PC\Downloads\barrios y plataformas\vias\vias_canton_riobamba_utm.shp:nom_eje; FID 1541/1544; GDB Bienestar_social FID18; red OSM local de Riobamba | MEDIA | Usuario acepta el nodo censal Freire x Y con confianza MEDIA despues de revisar la referencia municipal Centro de Rehabilitacion Social, a 98.71 m. Documento conserva Calle V; CSV original dice Calle Y. No se afirma equivalencia V/Y. La GDB rotula Freire a 943.98 m; en el sector la red municipal es sin nombre y la red OSM local rotula Leopoldo Freire. Candidato antes descartado, ahora aceptado expresamente con esta discrepancia. Dos equipos, mismo emplazamiento cartografico; instalacion fisica pendiente de campo. |
| RIO-085-DOMO | 760,270.702 | 9,816,333.109 | José de Orozco y Baltazar Paredes | Jose de Orozco x Baltazar Paredes | INTERSECCION_VIAL_CORROBORADA | C:\Users\PC\Downloads\barrios y plataformas\vias\vias_canton_riobamba_utm.shp:nom_eje; D:\codex\riobamba_matrix_review_20260921\cartografia_base\RIOBAMBA_Cartografia Base.gdb:Vialidad_urbana:TXT | CORROBORADA_CARTOGRAFICAMENTE | Ubicacion aceptada sin desplazamiento; dos fuentes, diferencia 0.41 m. Poste no verificado en campo. |
| RIO-103-DOMO | 758,972.300 | 9,816,675.514 | Luis Urdaneta y Manuel Zambrano | LUIS URDANETA x MANUEL ZAMBRANO | INTERSECCION_VIAL_CENSAL_EXACTA | C:\Users\PC\Downloads\barrios y plataformas\vias\vias_canton_riobamba_utm.shp:nom_eje; FID 7632/7630 | MEDIA | Cruce unico Luis Urdaneta x Manuel Zambrano en red censal; incorporacion cartografica solicitada para consolidacion. Fuente CPV2021, anio 2020, valida=fals. No se encontro corroboracion municipal suficiente ni se certifica posicion fisica del poste. |

Inventario original conservado separado.016/017son dos equipos en un emplazamiento censal aceptado con confianzaMEDIA; discrepanciaV/Y y943.98m municipal documentada; no se certifica la nomenclaturaV/Y ni el poste.085conserva corroboracion0.41m.103cruce censal exacto, corroboracion municipal limitada. Ninguna coordenada cartografica se presenta como levantamiento de campo.

## Las Abras y Cunduana

| LONGITUD_ACTUAL_M | LONGITUD_MAATE_COMPLETA_M | LONGITUD_MAATE_DENTRO_CANTON_M | LONGITUD_COINCIDENTE_EXACTA_M | LONGITUD_SOLO_ACTUAL_M | LONGITUD_SOLO_MAATE_M | LONGITUD_COINCIDENTE_COMPLETA_M | LONGITUD_SOLO_ACTUAL_VS_COMPLETA_M | LONGITUD_SOLO_MAATE_COMPLETA_M | METODO | DECISION |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6,741.994 | 8,977.170 | 5,214.568 | 30.517 | 6,711.477 | 5,184.050 | 18.055 | 6,723.939 | 8,959.114 | Interseccion lineal exacta; no snapping ni tolerancia. No equivale a coincidencia visual entre ejes digitalizados distintos. | Referencia operativa: eje MAATE suministrado, copia recortada al canton. Original completo y eje anterior conservados. Atribucion MAATE del insumo, sin certificacion externa de oficialidad. |

Se adopta operativamente MAATE dentro del canton, conservando MAATE completo, eje anterior y todos los13insumosMAATE y2Cunduana. No se certifica externamente su oficialidad. Coincidencia geometrica exacta es sensible a noding/redondeo; no equivale a coincidencia fisica. Sensibilidades1/5/10/20m se conservan como diagnostico, sin modificar geometria.

| ID | DECISION | EJE_MAATE_DIST_M | MAATE_CUBIERTO_M | MAATE_EXCLUSIVO_M | POBLACION_ASOCIADA | CUNDUANA_PUNTOS_200M | MOTIVO |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MUN-023 | MANTENER | 0.000 | 304.500 | 304.500 | 275.479 | 0 | Cruce vial exacto MAATE aceptado en la corrida anterior; cobertura exclusiva y sectores poblados. Cunduana distante: no se inventa coincidencia. |
| MUN-024 | MANTENER | 0.000 | 362.275 | 362.275 | 76.062 | 0 | Cruce vial exacto MAATE aceptado en la corrida anterior; cobertura exclusiva y sectores poblados. Cunduana distante: no se inventa coincidencia. |
| MUN-025 | MANTENER | 0.000 | 421.332 | 421.332 | 78.319 | 0 | Cruce vial exacto MAATE aceptado en la corrida anterior; cobertura exclusiva y sectores poblados. Cunduana distante: no se inventa coincidencia. |
| MUN-026 | MANTENER | 0.000 | 416.785 | 416.785 | 309.907 | 0 | Cruce vial exacto MAATE aceptado en la corrida anterior; cobertura exclusiva y sectores poblados. Cunduana distante: no se inventa coincidencia. |

| ID | DECISION | MAATE_ACTUAL_M | MAATE_ALTERNATIVA_M | DIMENSIONES_ACTUAL | DIMENSIONES_ALTERNATIVA |
| --- | --- | --- | --- | --- | --- |
| MUN-023 | MANTENER | 304.500 | 304.500 | 5 | 5 |
| MUN-024 | MANTENER | 362.275 | 362.275 | 4 | 4 |
| MUN-025 | MANTENER | 421.332 | 421.332 | 4 | 4 |
| MUN-026 | MANTENER | 416.785 | 416.785 | 5 | 5 |

Se revisaron los37cruces reales MAATE anteriores frente a103+otras49municipales finales. No se encontro mejora de longitud exclusiva sin perder dimensiones de evidencia. LAS_ABRAS_ALTERNATIVAS_FINAL.csv conserva actual+5alternativas y camposCunduana,limpieza,proteccion,JoseMarti,poblacion,D/V/C yGi*complementario.

Cunduana es ambiental, distante de MAATE; no se integra a incidentes, Gi* ni al objetivo policial. Mapas y capas muestran sus posiciones reales, no coincidencias inventadas.

## Cobertura y unidades

Radio200m, no diametro. EPSG:32717, buffer con64segmentos por cuadrante, UNION/DISSOLVE e interseccion; fracciones no sumadas entre camaras. Tres escenariosA103,B153,C183. Cobertura territorial urbana y cantonal se reportan por separado. Cobertura poblacional es estimacion arealCPV2022 dentro de18Plataformas (union29.293km2), con poblacion valida y faltantes explicitos; no equivale a poblacion rural completa ni a visibilidad real.

| ESCENARIO | AREA_TOTAL_URBANA_KM2 | AREA_CUBIERTA_URBANA_KM2 | PCT_URBANO | AREA_TOTAL_CANTON_KM2 | AREA_CUBIERTA_CANTON_KM2 | PCT_CANTON | BUFFER_DISUELTO_KM2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 29.293 | 7.346 | 25.078 | 998.779 | 9.155 | 0.917 | 9.234 |
| B | 29.293 | 10.204 | 34.834 | 998.779 | 14.629 | 1.465 | 14.946 |
| C | 29.293 | 12.056 | 41.156 | 998.779 | 16.529 | 1.655 | 16.846 |
| B_ANTERIOR | 29.293 | 10.113 | 34.522 | 998.779 | 14.731 | 1.475 | 15.048 |
| C_ANTERIOR | 29.293 | 12.046 | 41.121 | 998.779 | 16.712 | 1.673 | 17.029 |

| ESCENARIO | POBLACION_ANALIZADA | POBLACION_CUBIERTA | POBLACION_NO_CUBIERTA | PCT_CUBIERTO | MANZANAS_VALIDAS | MANZANAS_SIN_POBLACION | AMBITO |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 171,998.298 | 57,122.032 | 114,876.266 | 33.211 | 2534 | 291 | 18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible |
| B | 171,998.298 | 77,301.152 | 94,697.146 | 44.943 | 2534 | 291 | 18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible |
| C | 171,998.298 | 95,011.772 | 76,986.526 | 55.240 | 2534 | 291 | 18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible |
| B_ANTERIOR | 171,998.298 | 74,529.959 | 97,468.340 | 43.332 | 2534 | 291 | 18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible |
| C_ANTERIOR | 171,998.298 | 93,337.987 | 78,660.311 | 54.267 | 2534 | 291 | 18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible |

## Hot Spots congelados y remanentes

Las6mallasGi* mantienenWKB,Gi,z-score,p-value,90/95/99,distancias,ambitos,categorias. Solo se agregan campos de relacion con cobertura. Convivencia es complementaria policial. Coincidencia espacialD/V no es una nueva prueba conjunta. No se recalcula KDE ni Gi*.

| ESCENARIO | AMBITO | CATEGORIA | NIVEL | TOTAL | CUBIERTO | PARCIAL | SIN_COBERTURA | CON_ALGUNA_COBERTURA | AREA_TOTAL_M2 | AREA_CUBIERTA_M2 | PCT_AREA_CUBIERTA |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C | URBANO | DELINCUENCIA | 99 | 189 | 158 | 30 | 1 | 188 | 1,856,618.858 | 1,783,035.995 | 96.037 |
| C | URBANO | DELINCUENCIA | 95 | 66 | 45 | 18 | 3 | 63 | 650,157.180 | 570,398.611 | 87.732 |
| C | URBANO | DELINCUENCIA | 90 | 40 | 31 | 6 | 3 | 37 | 399,471.171 | 349,012.050 | 87.369 |
| C | URBANO | VIOLENCIA | 99 | 178 | 136 | 26 | 16 | 162 | 1,732,201.011 | 1,510,506.580 | 87.202 |
| C | URBANO | VIOLENCIA | 95 | 130 | 85 | 35 | 10 | 120 | 1,286,674.485 | 1,047,635.369 | 81.422 |
| C | URBANO | VIOLENCIA | 90 | 75 | 43 | 21 | 11 | 64 | 724,204.180 | 558,281.233 | 77.089 |
| C | URBANO | CONVIVENCIA | 99 | 204 | 153 | 50 | 1 | 203 | 2,039,999.995 | 1,889,264.850 | 92.611 |
| C | URBANO | CONVIVENCIA | 95 | 71 | 57 | 9 | 5 | 66 | 708,199.542 | 634,971.342 | 89.660 |
| C | URBANO | CONVIVENCIA | 90 | 50 | 34 | 14 | 2 | 48 | 490,206.244 | 413,637.149 | 84.380 |
| C | RURAL | DELINCUENCIA | 99 | 46 | 0 | 14 | 32 | 14 | 36,042,108.068 | 1,128,000.744 | 3.130 |
| C | RURAL | DELINCUENCIA | 95 | 5 | 0 | 0 | 5 | 0 | 1,434,609.196 | 0.000 | 0.000 |
| C | RURAL | DELINCUENCIA | 90 | 4 | 0 | 0 | 4 | 0 | 2,870,061.398 | 0.000 | 0.000 |
| C | RURAL | VIOLENCIA | 99 | 43 | 0 | 11 | 32 | 11 | 30,728,040.674 | 800,102.793 | 2.604 |
| C | RURAL | VIOLENCIA | 95 | 4 | 0 | 0 | 4 | 0 | 3,333,417.390 | 0.000 | 0.000 |
| C | RURAL | VIOLENCIA | 90 | 5 | 0 | 3 | 2 | 3 | 4,598,947.177 | 327,897.951 | 7.130 |
| C | RURAL | CONVIVENCIA | 99 | 49 | 0 | 15 | 34 | 15 | 38,397,180.652 | 1,150,450.669 | 2.996 |
| C | RURAL | CONVIVENCIA | 95 | 5 | 0 | 0 | 5 | 0 | 2,415,339.276 | 0.000 | 0.000 |
| C | RURAL | CONVIVENCIA | 90 | 3 | 0 | 0 | 3 | 0 | 2,052,051.100 | 0.000 | 0.000 |

Hot Spot atendido completo:fraccion>=1-1e-8; sin cobertura:<=1e-8; resto:parcial. Tolerancia numerica, no umbral operativo de suficiencia. Los remanentes se reportan separados por nivel y ambito.

## Brechas lineales finales

BRECHA_MACAJI_FINAL,ANILLO,CICLOVIAS,LAS_ABRAS=corredor menos unionC183. IDs,longitud,extremos,camaracercana y distancia. DIST_CAMARA_M es distancia minima entre el segmento completo y el punto de la camara, no desde su centro ni un indicador de separacion maxima. La distancia de un remanente puede ser casi200m por comenzar en el limite delbuffer. Estas brechas lineales no son una clasificacion de brechas por manzana.

| ESCENARIO | CORREDOR | TOTAL_M | CUBIERTO_M | NO_CUBIERTO_M | PCT_CUBIERTO |
| --- | --- | --- | --- | --- | --- |
| A | ANILLO_VIAL | 13,126.599 | 4,183.138 | 8,943.461 | 31.868 |
| A | CICLOVIAS | 10,976.049 | 5,421.096 | 5,554.953 | 49.390 |
| A | BOULEVARD_MACAJI_BELLAVISTA | 9,541.698 | 6,121.335 | 3,420.364 | 64.154 |
| A | QUEBRADA_LAS_ABRAS | 5,214.568 | 311.511 | 4,903.057 | 5.974 |
| B | ANILLO_VIAL | 13,126.599 | 11,492.517 | 1,634.082 | 87.551 |
| B | CICLOVIAS | 10,976.049 | 6,194.397 | 4,781.652 | 56.436 |
| B | BOULEVARD_MACAJI_BELLAVISTA | 9,541.698 | 9,360.625 | 181.073 | 98.102 |
| B | QUEBRADA_LAS_ABRAS | 5,214.568 | 1,816.402 | 3,398.166 | 34.833 |
| C | ANILLO_VIAL | 13,126.599 | 11,624.972 | 1,501.627 | 88.560 |
| C | CICLOVIAS | 10,976.049 | 6,763.636 | 4,212.413 | 61.622 |
| C | BOULEVARD_MACAJI_BELLAVISTA | 9,541.698 | 9,394.854 | 146.844 | 98.461 |
| C | QUEBRADA_LAS_ABRAS | 5,214.568 | 1,816.402 | 3,398.166 | 34.833 |

## Control de calidad

492 controles GIS: 492 aprobados, 0 fallidos.

Se verifican counts,CRS,nulos,invalidas,IDs,0/0,fueraambito,coincidencias,union200m,longitudes,nearest,estadisticasGi*,atributos fuentes,calculos poblacion,incidentes y SHA256. RIO075original fuera del canton se conserva y advierte; no se elimina para aparentar103dentro. Inventarioadministrativooriginal conserva4nulos, pero capaFINAL tiene0.

## Advertencias

- Confianza MEDIA de 016/017 aceptada por usuario; V/Y y 943.98m documentados, no confirmacion del poste.
- RIO-103 geocodificada por cruce censal exacto; corroboracion municipal insuficiente, confianza MEDIA.
- Cunduana es ambiental, distante de MAATE; no entra en incidentes ni Gi* ni seleccion policial.
- Cobertura potencial circular, no visibilidad real; superficies disueltas, sitios coincidentes sin doble conteo.
- Poblacion cubierta es estimacion areal CPV2022 en 18Plataformas; no se extrapola a toda la poblacion rural.
- Nivel D/V residual es coincidencia geometrica de pruebas individuales, no nueva significancia conjunta.
- Reemplazos propuestos pueden reducir area o nivel Gi* atendido aunque aumenten eventos; no optimo global.
- Eje MAATE suministrado adoptado operativamente dentro del canton; atribucion oficial no certificada externamente.
- Nodo vial no certifica poste, energia, permisos ni viabilidad de instalacion. No publicado.
- Coincidencia lineal exacta sensible a digitalizacion, segmentacion y redondeo GEOS al recortar. No representa equivalencia fisica de trazados; revisar tambien las sensibilidades documentadas.
- Ciclovias baja de86.68% a56.44% en153 al aplicar prioridad estricta Anillo. Diagnostico separado conserva Ciclovias pero no sustituye configuracion final sin aprobacion.
- Ciclovias baja de86.68% a56.44% en153 al aplicar prioridad estricta Anillo. Diagnostico separado conserva Ciclovias pero no sustituye configuracion final sin aprobacion.

**La publicacion no elimina la advertencia de perdida de Ciclovias ni certifica viabilidad de instalacion en campo.**
