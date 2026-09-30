# Correccion de dependencias de incidentes

Fuente: Base de Datos Emergencias_SC_Riobamba (2).xlsx y clasificacion de 139 subtipos.

- Registros originales: 26.716. Se conservan IDs, fechas, coordenadas y el valor original de Emergencias.
- Registros de conflictividad elegibles: 12.383 (incluir_hotspot = SI).
- Registros de conflictividad dentro de las 18 Plataformas: 11.017.
- Registros elegibles fuera de las Plataformas: 1.366. Se mantienen en la entrada del KDE; sus contribuciones dependen de su distancia a la extension urbana del raster.
- Registros institucionales excluidos de conflictividad: 14.333.

## Resultados invalidados y reemplazados

Conteos de incidentes ponderados automaticamente por Emergencias en Gi*, tasas, tipologias, series temporales, diagnostico y cruces de proximidad a camaras, policia y Bulevares. Cada fila participa ahora como una observacion espacial independiente.

El conteo preliminar de un hotspot por Plataforma con dos o mas incidentes fue sustituido por el numero real de celdas hotspot Gi*. No se deben interpretar las celdas como sectores independientes ni confundirlas con componentes KDE.

## Calculo espacial

KDE general y filtrado usan EPSG:32717, celdas de 20 m, bandwidth fijo de 700 m y kernel gaussiano truncado al radio. Se suman contribuciones de los registros originales sin agregacion por Plataforma. La normalizacion visual usa el percentil 98 y no modifica la densidad calculada.

Las concentraciones KDE se cuentan como componentes conexos por cuatro vecinos por encima del 35% de la densidad maxima, usando el mismo criterio en la vista general y filtrada. Es una delimitacion descriptiva, no una prueba de significancia.

Gi* usa una unica grilla fija de 250 m en EPSG:32717 y vecindad binaria de 500 m con la propia celda incluida. Se mantienen celdas sin incidentes y celdas que intersectan los bordes del ambito. Los puntos se asignan a celdas mediante sus coordenadas UTM originales. Las geometrías de las celdas se transforman a WGS84 para la visualizacion. La significancia es nominal, sin correccion por pruebas multiples. Las zonas B2 y B5 dependen de estos resultados y conservan esa limitacion.

## Dependencias actualizadas

Mapa y filtros KDE; KPI, graficos, tabla y leyenda KDE; mapa y resultados Gi*; conteos y tasas por Plataforma; tipos y evolucion temporal; ficha territorial; conteos de incidentes proximos a camaras, policia y Bulevares; diagnostico y brechas B1-B5; exportaciones que consumen la tabla maestra.

Nuevas coordenadas metricas y grilla Gi*: riobamba-incidentes-spatial-data.js. Tabla maestra recalculada: riobamba-seguridad-diagnostico-data.js.

## Validacion

Se verifica automaticamente que la fuente original permanece intacta, que KDE y conflictividad usan los mismos IDs elegibles, que cada Plataforma cuenta sus registros una sola vez y que los indicadores independientes de poblacion, cobertura de camaras y proximidad policial no cambian.

La implementacion filtrada del KDE se compara numericamente con el raster general: maxima densidad y numero de componentes coinciden. Tambien se verifica que tres registros coincidentes producen tres veces la densidad de un registro y que una entrada vacia produce cero. Los resultados Gi* del navegador se contrastan con las celdas y conteos utilizados para construir la tabla maestra.

Tipos probados: todos los tipos (12.383), Robo a domicilio (225), Violencia interpersonal / familiar (1.542). El bandwidth y la celda permanecen constantes.

La tarjeta de Plataforma con mas registros utiliza el conteo de registros asignados, no la maxima densidad raster. Los registros externos se muestran como Fuera de Plataformas y no participan en la eleccion de esa Plataforma.
