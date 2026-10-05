# Brechas de cobertura y prioridad territorial

Recalculo con camaras del cierre final, sin reoptimizar 50 municipales ni 30 policiales.
Escenarios A=103, B=153, C=183; REEMPLAZO_31 conserva el objeto de estudio original.
103 equipos existentes en 100 emplazamientos; los equipos coincidentes se conservan y la union evita doble conteo.
EPSG:32717; radios 100/150/200 m, buffer quad_segs=64 y union disuelta antes de intersectar.
COB = porcentaje de area completa de la manzana: baja <33%, parcial 33-66%, buena >66%.
P33 poblacion=43.0; P66=76.0; incidencia P33=0.0; P66=0.0. Valores y problematicas congelados entre escenarios/radios.
Problematica ALTA: Hot Spot D/V95% o99%; MEDIA: D/V90% o tasa D/V superior a P66 sin Hot Spot>=95%. Convivencia>=95% con eventos observados en la manzana puede aportar MEDIA, nunca ALTA por si sola. BAJA: otras situaciones con datos validos.
Brecha ALTA: cobertura baja + poblacion media/alta + problematica alta.
Brecha MEDIA: cobertura baja + poblacion media/alta + problematica media, o cobertura parcial + poblacion media/alta + problematica alta.
Brecha BAJA: otras situaciones evaluadas. SIN EVIDENCIA: falta poblacion, cobertura o problematica. Sin score, AHP ni ponderaciones.
Gi* urbano conservado: celdas100m/distancia200m; Gi* rural intacto. No se mezclan categorias.
INTERSECCION ESTRICTA; 929 asignados, 8986 sin asignar de 9915 urbanos. Sin nearest-neighbor. Los no asignados NO se usan para clasificar manzanas; si conservan su uso original en Gi* y cobertura puntual.
Brechas provisionales: P66 de incidencia0 refleja atribucion incompleta, no ausencia de problematica.
Esta clasificacion constituye una herramienta operativa de priorizacion territorial para el presente estudio. No representa por si sola una medida de peligrosidad, riesgo delictivo ni una metodologia universal de brecha de videovigilancia.
BRECHAS_ACTUALIZADAS.gpkg, capa BRECHAS_POR_MANZANA, y CSV: geometrias originales y campos COB_A/B/C_100/150/200, BRECHA_A/B/C_100/150/200, REGLA y alias COB_100/150/200,BRECHA_100/150/200 del escenario A.
INSUMOS_FIJOS_BRECHAS.json: atributos y percentiles congelados para reproducir con geometrias censales originales. Ejecutar tools/recalculate_current_gaps.py con GeoPandas, Pyogrio, Shapely2 y PyProj.
RESULTADOS.json: fuentes SHA256, coberturas, estadisticas, reglas, clips visuales y datos del visor. VALIDACION.json y COMPARACION_ESCENARIOS.csv: controles y conteos.
