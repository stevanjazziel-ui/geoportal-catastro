# PROPUESTA FINAL POLICIA NACIONAL - 30 CAMARAS

**Estado: FINAL DEL ESTUDIO. Propuestas no instaladas; requieren validacion operativa de campo.**

## Cierre aprobado
- 8 reubicadas: POL-06, POL-07, POL-14, POL-15, POL-16, POL-17, POL-18, POL-19. Las otras 22 mantienen exactamente sus coordenadas.
- 103 existentes + 50 municipales finales + 30 policiales = 183 equipos; 31 para cambio son parte de las 103.
- Candidatos aprobados de la revision iterativa; no se regeneraron las 30 ni se cambiaron Gi*, KDE, fuentes o ejes.
- Las ocho recomendaciones proceden de la seleccion iterativa aprobada. El conjunto final de 30 se verifico contra 103 + 50 + las otras 29.
- CRS metrico EPSG:32717; radio 200 m; buffers de 64 segmentos por cuadrante y cobertura disuelta.
- Gi* D/V es el criterio principal; Convivencia y corredores son complementarios. No se impone400m ni otro minimo de separacion.
- Gi* del sitio y nivel maximo en el radio200m son campos diferentes. No se fabrica una significancia conjunta D/V.
- Aportes exclusivos individuales no se suman; el balance anterior/final se obtiene de la union completa.

## Comparacion anterior/final
| Indicador | Anterior | Final |
|---|---:|---:|
| DELINCUENCIA cubiertos | 1702.00 | 1783.00 |
| VIOLENCIA cubiertos | 918.00 | 989.00 |
| CONVIVENCIA cubiertos | 4921.00 | 4999.00 |
| D+V cubiertos | 2620.00 | 2772.00 |
| Hot Spots urbanos DELINCUENCIA completas | 234.00 | 227.00 |
| Hot Spots urbanos DELINCUENCIA parciales | 54.00 | 61.00 |
| Hot Spots urbanos DELINCUENCIA sin cobertura | 7.00 | 7.00 |
| Hot Spots urbanos DELINCUENCIA area cubierta m2 | 2702446.66 | 2693364.70 |
| Hot Spots urbanos VIOLENCIA completas | 264.00 | 263.00 |
| Hot Spots urbanos VIOLENCIA parciales | 82.00 | 107.00 |
| Hot Spots urbanos VIOLENCIA sin cobertura | 37.00 | 13.00 |
| Hot Spots urbanos VIOLENCIA area cubierta m2 | 3116423.18 | 3300668.73 |
| Solape medio % | 59.63 | 36.94 |
| Solape maximo % | 96.68 | 75.83 |
| Area exclusiva agregada policial m2 | 1900265.07 | 2591100.77 |

## Redundancia final
BAJA <50%: 19; MEDIA [50,70]%: 9; ALTA (70,85]%: 2; MUY ALTA >85%: 0.
No hay excepciones >85%. Los solapes70-85% se justifican individualmente enPOLICIA_BENEFICIO_FINAL.csv.

## Pares policiales proximos
- <100 m: 0 pares.
- 100-200 m: 1 pares.
- 200-300 m: 4 pares.
- 300-400 m: 7 pares.
- POL-02 / POL-13: 156.04m. Ambas necesarias por aportes independientes: POL-02 suma 13 D/5 V y POL-13 4 D/5 V contra el resto del escenario183. Entornos Gi* D/V 99%/99% y 99%/99%; nodos viales distintos de grados 4/3. Solapes globales 59.64%/61.40%, no extremos. No se inventa un equipamiento critico ni se impone distancia minima.

## Hot Spots prioritarios
- Ningun nucleoD/V99 previamente con alguna cobertura pasa aSIN COBERTURA. Los valoresGi*, categorias, celdas y parametrizacion permanecen intactos.
- Transiciones completas a parciales: 11 celdas de Delincuencia y 19 de Violencia. No confundir estas transiciones con el balance neto: otras celdas pasan a completas. Ninguna de estas transiciones produce ausencia total.
- El area cubierta de Hot Spots urbanos de Delincuencia disminuye ligeramente; la de Violencia aumenta. Los eventos D/V cubiertos aumentan en 152.
- El control por celda y nivel99 figura enCONTROL_NUCLEOS_GI_99.csv; transiciones enCELDAS_COMPLETAS_A_PARCIALES.csv.
- La cobertura por categoria, nivel y ambito se reporta enHOTSPOTS_ATENDIDOS_FINAL.csv. Los resultadosruralesGi* no se recalculan.

## Fuentes oficiales y derivados
- ESCENARIO_FINAL_183.gpkg contienePROPUESTA_POLICIA_30_FINAL(30), ESCENARIO_FINAL_183(183), CONTROL_SOLAPES_POLICIA_FINAL, AUDITORIA_REUBICACIONES_POLICIA y la matriz de distancias.
- La unica fuente policial activa esPROPUESTA_POLICIA_30_FINAL en este paquete. HISTORICO_POLICIA_ANTERIOR y la revision previa no son propuestas oficiales activas.
- Los atributos de coberturaC de incidentes/manzanas/Hot Spots se actualizan para el nuevo escenario; sus geometria y valores estadisticos originales no cambian.
- Las capas GI_URBANO_* y GI_RURAL_* son copias integras del resultado estadistico congelado. Sus atributos historicos COB_C no deben utilizarse como cobertura final: para ese fin utilizar HOTSPOT_* y HOTSPOTS_ATENDIDOS_FINAL.
- Las coberturasA/B y los ejes deMacaji, Anillo, Ciclovias, LasAbras y Cunduana se conservan; solo se evalua su interseccion con el nuevo escenarioC. No fueron objetivos de optimizacion policial.
- Las brechas por manzanaC anteriores quedan invalidadas para esta configuracion; no se reutilizan ni se declaran recalculadas en este cierre. A/B permanecen intactos.
- La poblacion adicional/cubierta es una estimacion areal urbanaCPV2022 en18Plataformas. Rural completa:No disponible; faltantes no se representan por cero.
- MAPA_FINAL_POLICIA_NACIONAL y CONTROL_FINAL_SOLAPES son dos vistas del mismo conjunto final, no versiones alternativas.

## Validacion
103/50 conservadas;22coordenadas policiales conservadas;8movimientos aprobados;30policiales exactas;183equipos;0solapes>85%;0nucleos99abandonados;0nuevospares<200m. Fuentes originales verificadas porhash. Sin commit ni push.
