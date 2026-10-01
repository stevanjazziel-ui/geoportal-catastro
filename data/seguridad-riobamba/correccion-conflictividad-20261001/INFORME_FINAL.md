# Correccion de incidentes, KDE y Gi* - informe de publicacion

Estado: implementado y probado. Publicacion de los cambios pendientes autorizada por el usuario el 1 de octubre de 2026. Las revisiones previas se conservan como antecedentes de auditoria.

## Autorizaciones y criterios

Se aplicaron las cuatro reglas confirmadas: Bomberos, faltas contra servidores policiales y plantones como ACTIVIDAD_INSTITUCIONAL; tenencia/porte de explosivos como DELINCUENCIA. Son reglas operativas autorizadas, no una certificacion juridica de la tipologia.

Se conserva el cruce geometrico aprobado de la union de las 18 Plataformas y las parroquias reales. La etiqueta parroquial original NO decide el ambito. Por eso no se fuerzan los conteos urbano/rural que figuraban en el documento inicial. Los registros SIN_ASIGNAR no se incorporan artificialmente a ningun universo.

Cada fila participa con peso 1. El campo fuente Emergencias se conserva como dato descriptivo; no multiplica el KDE ni Gi*. No se borraron registros, cambiaron coordenadas/subtipos o dispersaron puntos coincidentes.

## Entregables 1-4: diccionario, conteos y coordenadas

- Diccionario completo: `DICCIONARIO_APROBADO.csv`, 139 subtipos exactos.
- Base derivada: `BASE_ANALITICA_APROBADA.csv`, 26.716 observaciones, categoria, ambito, coordenadas originales, recurrencia y flag.
- Control de seis universos: `CONTROL_COORDENADAS_APROBADO.csv`.

| Categoria | Base completa | Urbano geometrico | Rural geometrico | SIN_ASIGNAR |
| --- | ---: | ---: | ---: | ---: |
| DELINCUENCIA | 2.533 | 2.229 | 219 | 85 |
| VIOLENCIA | 1.590 | 1.268 | 247 | 75 |
| CONVIVENCIA | 7.027 | 6.418 | 402 | 207 |
| ACTIVIDAD_INSTITUCIONAL | 14.778 | 13.140 | 1.178 | 460 |
| OTROS_REVISION | 788 | 677 | 88 | 23 |
| Total | 26.716 | 23.732 | 2.134 | 850 |

Las tres categorias analiticas suman 11.150 registros: 9.915 urbanos, 868 rurales y 367 sin asignacion. Institucional/revision quedan fuera de KDE/Gi*. De los 850 SIN_ASIGNAR, 820 estan dentro del canton y 30 fuera; sus ubicaciones originales se preservan.

Recurrencia global: 6.420 coordenadas unicas, maximo 477 registros coincidentes. Flags por observacion: NORMAL 4.267; REPETIDA 6.786; ALTA_REPETICION 7.144; MUY_ALTA_REPETICION 8.519. No se deduplican eventos diferentes.

El control por categoria/ambito calcula repeticion dentro de ese universo; los flags de la base derivada utilizan la frecuencia global. La repeticion no prueba error, pero exige cautela y verificacion de la precision original; este proceso no certifica que cada localizacion sea un lugar independiente de ocurrencia.

## Entregables 5-12: seis KDE y bandwidth

Los seis mapas y las 33 pruebas estan en `comparacion.html`. Los PNG son mapas cientificos de los datos reales; el visor conserva su mapa base OSM en gris y su interfaz existente.

| Ambito | Categoria | N | Celda m | Radio recomendado m | Componentes descriptivos |
| --- | --- | ---: | ---: | ---: | ---: |
| Urbano | Delincuencia | 2.229 | 20 | 500 | 15 |
| Urbano | Violencia | 1.268 | 20 | 400 | 59 |
| Urbano | Convivencia | 6.418 | 20 | 300 | 13 |
| Rural | Delincuencia | 219 | 100 | 1.500 | 3 |
| Rural | Violencia | 247 | 100 | 1.500 | 2 |
| Rural | Convivencia | 402 | 100 | 1.500 | 3 |

EPSG:32717; kernel gaussiano truncado en h, normalizado a volumen 1, densidad en eventos/km2. Se suman todas las contribuciones antes de enmascarar la superficie. No se calcula desde centroides ni como superficies independientes por Plataforma.

Urbano: 200/250/300/400/500/700 m. Rural: 500/750/1.000/1.200/1.500 m. Dentro de cada universo se mantienen puntos, extension, celda y kernel. La tabla conserva un umbral de componentes fijo por clase durante la comparacion. Los componentes no son sectores peligrosos ni hotspots estadisticos; en los filtros exploratorios el contador describe componentes >=35% del maximo del subconjunto y no debe compararse como una prueba de significancia.

La recomendacion usa log-verosimilitud predictiva media dejando fuera cada grupo XY completo durante la validacion, con piso 1e-12/km2. Evita seleccionar por apariencia o que las coincidencias dominen esa validacion; todos los registros vuelven al raster final. Los radios se mantienen al cambiar subtipo, mes o Plataforma. La seleccion rural coincide con el extremo superior ensayado: no demuestra optimalidad mas alla de 1.500 m y sigue siendo provisional.

Escala de color fija compartida: `log1p(densidad)/log1p(3038.195341858464)`. Sin percentil ni maximo automatico por mapa. Transparencia urbana 0,68 y rural 0,45; densidad cero es transparente. La rampa y la escala permanecen iguales al filtrar. El truncamiento es un soporte finito y forma parte de la metodologia conservada; no equivale a un Gaussian KDE de soporte infinito.

`COMPARACION_BANDWIDTH.csv` incluye fragmentacion, area con contribucion positiva, fusion de componentes, densidad maxima, puntaje predictivo, ubicaciones sin soporte y aporte de coordenadas altamente recurrentes al pico. Area con contribucion positiva NO equivale a area de riesgo.

## Entregables 13-14: Gi* actualizado

Malla/vecindad existentes: urbano 250/500 m, 572 celdas; rural 1.000/2.000 m, 1.132 celdas. Se mantiene el universo con celdas vacias y peso propio. Clasificacion mediante p nominal bilateral (0,01/0,05/0,10), sin forzar hotspots o coldspots. Las probabilidades y clasificaciones coinciden entre el navegador y el calculo independiente en Python.

| Ambito / categoria | H99 | H95 | H90 | No significativo | C90 | C95 | C99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Urbano / delincuencia | 70 | 17 | 11 | 433 | 37 | 4 | 0 |
| Urbano / violencia | 72 | 27 | 7 | 380 | 51 | 35 | 0 |
| Urbano / convivencia | 72 | 30 | 9 | 423 | 36 | 2 | 0 |
| Rural / delincuencia | 46 | 5 | 4 | 1.077 | 0 | 0 | 0 |
| Rural / violencia | 43 | 4 | 5 | 1.080 | 0 | 0 | 0 |
| Rural / convivencia | 49 | 5 | 3 | 1.075 | 0 | 0 | 0 |

Resultados nominales exploratorios, sin FDR ni correccion por las multiples pruebas/categorias. No constituyen un diagnostico definitivo de peligrosidad. La seleccion parroquial rural resume/encuadra el resultado; no redefine el universo de referencia de Gi*. Los CSV y PNG `GI_<AMBITO>_<CATEGORIA>` permiten inspeccionar los seis resultados.

## Entregable 15: comparacion H-I-J-K

El KDE publicado excluia sus clases originales institucional/revision. No se sostiene la premisa de que ese mapa utilizaba los 26.716 registros. Con el diccionario nuevo, cuatro observaciones antes clasificadas como violencia pasan a institucional; dos estan en el ambito urbano operativo. Su aporte al anterior KDE central urbano es 0,0244% de la masa integrada. No fue el motor principal de la superficie central.

Se reconstruyen los antiguos puntos/clases a 700 m con unidades y escala comunes; no son una copia pixel a pixel del renderer anterior, que normalizaba por percentil. `CORREGIDO_*_700` cambia solo clasificacion; `NUEVO_*` cambia solo bandwidth respecto a CORREGIDO. Los escenarios TODOS e INSTITUCIONAL son contrafactuales explicitos, no mapas oficiales ni nuevos selectores.

En el anterior conjunto analitico urbano a 700 m, XY de frecuencia global >=10 aportaban 69,28% de la masa KDE integrada en H-I-J-K. En los nuevos resultados aportan 70,92% para delincuencia, 64,48% para violencia y 69,03% para convivencia. No se eliminaron esas observaciones ni se interpreta esa contribucion como prueba de error.

Manteniendo los puntos corregidos, el maximo central cambia de 293,41 a 376,75 eventos/km2 en delincuencia (700 a 500 m), de 114,27 a 164,13 en violencia (700 a 400 m), y de 704,71 a 1.712,05 en convivencia (700 a 300 m). Separar categorias y radio no implica que desaparezca todo aporte en el centro: alli sigue existiendo distribucion registrada y alta recurrencia. La masa integrada tampoco equivale a un conteo absoluto de incidentes del centro.

## Entregable 16: archivos y dependencias

Modificados: `visor-seguridad-riobamba-v2.html`, `riobamba-cantonal-view.js`, `tools/validate_incident_dependencies.cjs`.

Nuevos: `riobamba-conflictividad.js`, `riobamba-conflictividad-data.js`, `tools/audit_conflictivity_correction.cjs`, `tools/build_conflictivity_correction.py`, `tools/build_conflictivity_dependencies.py`, `tools/build_conflictivity_central_comparison.py`, `tools/build_conflictivity_review.cjs`, `tools/validate_conflictivity_correction.cjs`, y esta carpeta de resultados.

Los agregados dependientes de incidentes se actualizaron: conteos/tasas por Plataforma, tipologias, meses, eventos cerca de policia/red/camaras, exposicion poblacional por proximidad a eventos y componentes de cruce con cobertura existente. El diagnostico general conserva un Gi* descriptivo agregado actualizado, separado de los tres Gi* por categoria del modulo Zonas criticas.

Se retiran las dependencias de la antigua lista KDE y del antiguo indice metrico de 11.042 admisibles: 112 registros ahora admitidos no existian en ese indice. Se reconstruye la entrada desde la version analitica derivada y las coordenadas metricas de todas las observaciones originales. Los nuevos admitidos menos los cuatro reclasificados explican el aumento neto a 11.150, sin duplicar filas. La exposicion poblacional conserva el supuesto previo de distribucion uniforme dentro de las manzanas; no mide posiciones individuales de habitantes.

No se recalcularon poblacion censal, areas/limites, posiciones de camaras, superficies de cobertura, accesibilidad poblacional policial ni longitudes de red. Continuan las 31 camaras acordadas, incluyendo RIO-068-LA; no se introdujeron externas. Las fuentes originales permanecen intactas y sus hashes se comprueban.

## Verificacion y reproduccion

Pruebas: `node tools/validate_incident_dependencies.cjs` (baseline historico inmutable y pipeline derivado nuevo); `node tools/validate_camera_coverage_graphics.cjs` (57 selecciones / 114 renders); `git diff --check`. Las seis entradas KDE y seis Gi* se comprobaron tambien mediante los controles reales del navegador, sin errores de JavaScript.

Filtros adicionales probados en KDE urbano: Robo a domicilio 153; enero 21; enero + Plataforma K 1. Mapa/KPI/graficos/tabla cambiaron conjuntamente, conservando 500 m. Datos de las pruebas: `VALIDACION_CALCULOS.json` y `VALIDACION_NAVEGADOR.json`.

Orden de reproduccion, con NumPy, Shapely, pyproj y Matplotlib ya disponibles:

```text
python tools/build_conflictivity_correction.py
python tools/build_conflictivity_dependencies.py
python tools/build_conflictivity_central_comparison.py
node tools/validate_conflictivity_correction.cjs
node tools/build_conflictivity_review.cjs
```

El primer script requiere el diccionario auditado conservado en esta carpeta. La interfaz usa obligatoriamente los agregados derivados nuevos; no vuelve silenciosamente a los resultados antiguos.

Referencias de contexto metodologico: [validacion de densidades](https://scikit-learn.org/stable/modules/density.html) y [suma/normalizacion de kernels](https://pro.arcgis.com/en/pro-app/3.4/tool-reference/spatial-analyst/how-kernel-density-works.htm). No se afirma equivalencia con el kernel quartico de ArcGIS ni con el kernel gaussiano de soporte infinito de scikit-learn.
