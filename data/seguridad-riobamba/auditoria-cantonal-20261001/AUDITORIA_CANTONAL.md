# Ampliacion cantonal: auditoria previa para revision

Fecha: 2026-10-01. Etapa: SOLO AUDITORIA. No se modifica la interfaz, los calculos activos, las Plataformas, las 31 camaras ni la URL. SIN commit y SIN push.

## 1. Disponibilidad comprobada

| Insumo | Estado | Evidencia / limitacion |
|---|---|---|
| Limite cantonal | DISPONIBLE | limite_canton_riobamba_wgs84.shp, 1 poligono; 998,779047 km2. Fuente local; confirmar vigencia/autoridad antes de declararlo limite legal oficial. |
| Limite urbano | NO DISPONIBLE como limite censal/legal urbano validado | Existen 5 parroquias administrativas URBANA y la union de Plataformas como ambito operativo. NO son necesariamente el limite urbano CPV/AUR. |
| Plataformas | DISPONIBLE | 18 geometrías originales; union 29,293119 km2, sin modificaciones. |
| Parroquias rurales | DISPONIBLE | 11 poligonos RURAL en division_parroquial_riobamba_wgs84.shp; validos. |
| Poblacion urbana | DISPONIBLE | Referencia 177.213, corroborada por el conteo CPV AUR=1. |
| Poblacion rural | DISPONIBLE | Referencia 83.669, corroborada por el conteo CPV AUR=2; incluye parte del codigo Riobamba. |
| Poblacion por parroquia | DISPONIBLE, enlace espacial preliminar documentado | CPV tiene 12 codigos: Riobamba agregado y 11 parroquias rurales. No se une directamente al CODPAR distinto del shapefile. |
| Poblacion por Plataforma | DISPONIBLE | Estimador areal CPV existente; 171.998 habitantes asignados. No se sustituye por 177.213 ni se escala. |
| Incidentes urbanos | DISPONIBLE | 23.732 registros por interseccion con las Plataformas; 9.810 de clases analiticas 1-3. |
| Incidentes rurales | DISPONIBLE | 2.134 registros por interseccion rural, excluyendo los ya urbanos; 867 de clases 1-3. |
| UPC / infraestructura | PARCIAL | 26 posiciones originales: 17 urbanas, 8 rurales, 1 exterior (Chambo). Inventario del distrito, no certificacion de exhaustividad cantonal. |
| Red vial | PARCIAL para accesibilidad | 10.791 ejes locales y geometrías disponibles; sin velocidades, restricciones ni topologia de enrutamiento validada. |
| Camaras urbanas | DISPONIBLE | Las 31 del estudio se conservan; 29 dentro de Plataformas y 2 fuera. No se descartan por estar fuera. |
| Camaras rurales | NO DISPONIBLE como inventario validado | No se interpreta falta de inventario como ausencia real de camaras. No se extrapolan las 31 al canton. |
| Bulevares | DISPONIBLE | Capa actual de Bulevares/conexiones intacta; no se asume red rural completa. |

Rutas territoriales locales: C:/Users/PC/Downloads/barrios y plataformas/dar poder a la gente/. Red vial: C:/Users/PC/Downloads/barrios y plataformas/vias/. Archivos de produccion conservados se identifican por SHA-256 en AUDITORIA_CANTONAL.json.

Se inspecciono tambien dpa_parroquial.zip: contiene 428 unidades pero ninguna del canton 0601/Riobamba. NO se utiliza como sustituto de la division parroquial local. El Distrito policial Riobamba-Chambo NO se usa como limite cantonal.

## 2. Validacion de limites

Los .prj locales declaran WGS84 geografico. El cruce se efectua tras transformar coordenadas y geometrías a WGS84 / UTM 17S, EPSG:32717, siempre longitud/latitud en ese orden.

- 16 parroquias administrativas: 11 rurales y 5 urbanas; geometrías validas, sin reparacion silenciosa.
- La union parroquial y el canton difieren solo 0,016 m2, compatible con redondeo numerico de la exportacion; solape parroquial practicamente cero.
- La union de las 5 parroquias URBANA tiene 61,954896 km2, distinta de los 29,293119 km2 de Plataformas.
- Las Plataformas intersectan 0,098614 km2 de parroquias RURAL y presentan 585,12 m2 exteriores al limite cantonal local. No se corrigen ni recortan sus geometrías originales.
- Hay 32,760976 km2 del canton fuera de la union de Plataformas y de las parroquias RURAL: el esquema operativo actual NO particiona completamente el canton.

## 3. Asignacion preliminar de incidentes

Regla propuesta, no aplicada a produccion: verificar canton; si intersecta una Plataforma, URBANO; en otro caso, si intersecta una parroquia RURAL unica, RURAL; si no, SIN_ASIGNAR. La Plataforma se conserva como unidad urbana, la parroquia como unidad rural. No se asigna ambito por texto.

| Ambito | Todos los registros | Solo delincuencia, violencia y convivencia |
|---|---:|---:|
| Urbano | 23.732 | 9.810 |
| Rural | 2.134 | 867 |
| Sin asignar | 850 | 365 |
| Total | 26.716 | 11.042 |

Comprobacion: 23.732 + 2.134 + 850 = 26.716. La columna de todos los registros incluye actividad institucional y otros; NO significa numero de delitos.

Desglose SIN_ASIGNAR: 820 dentro del canton pero fuera de Plataformas/parroquias RURAL; 30 fuera del canton. Los 26.686 registros geometricamente dentro del canton no equivalen solo a urbano+rural, porque quedan los 820 pendientes.

Hay 68 eventos que intersectan simultaneamente una Plataforma y una parroquia RURAL (63 San Luis, 5 Lican). Se cuentan una vez, como urbanos, por la precedencia operativa propuesta; esta decision debe revisarse junto con los denominadores poblacionales. Ningun punto intersecta multiples Plataformas en esta corrida. No se borran coincidentes: cada registro real conserva su ID.

Se detectaron 105 discrepancias entre el texto de parroquia original y la parroquia rural intersectada. El campo original se conserva; el resultado espacial se guarda aparte para revision.

Detalle de los 26.716 registros: ASIGNACION_PRELIMINAR.csv. Los 850 pendientes, con ID, coordenadas, fecha, clase, subtipo y motivo: SIN_ASIGNAR.csv. No se alteran coordenadas ni se generan centroides artificiales de incidentes.

## 4. Poblacion y concordancia de ambitos

Se leyeron las 16.938.986 filas del archivo CPV_2022_Poblacion_Manloc.csv sin modificarlo. Se contaron personas con I01=06, I02=01 y CANTON=0601, una fila por persona. Resultado: 260.882.

Los valores originales AUR=1 y AUR=2 producen respectivamente 177.213 y 83.669, coincidentes con las referencias del usuario. La aritmetica se valida: 177.213 + 83.669 = 260.882. La geometria que materializa exactamente esa division censal sigue pendiente; no se infiere de un nombre administrativo.

Los 11 codigos rurales suman 71.991. El codigo 060150 (Riobamba) contiene 188.891 personas: 177.213 en AUR=1 y otras 11.678 en AUR=2. Por tanto, 71.991 + 11.678 = 83.669. NO repartir estos 11.678 arbitrariamente entre las parroquias.

El enlace de codigos CPV con nombres rurales se verifico mediante interseccion areal de las manzanas codificadas con los poligonos parroquiales: concordancia 100 % para 10 parroquias y 99,9774 % para San Juan, cuyo pequeno cruce con Calpi se conserva como discrepancia. Es un enlace espacial preliminar, no un cambio de codigo oficial. 060150 cruza las 5 parroquias urbanas; no se atribuyen sus 188.891 habitantes solo a Lizarzaburu por ser el mayor cruce.

| Parroquia rural | Codigo CPV propuesto | Poblacion CPV | Registros rurales | Delincuencia | Violencia | Convivencia |
|---|---|---:|---:|---:|---:|---:|
| Cacha | 060151 | 2.362 | 36 | 3 | 2 | 5 |
| Calpi | 060152 | 6.223 | 236 | 26 | 18 | 54 |
| Cubijies | 060153 | 3.264 | 85 | 10 | 9 | 21 |
| Flores | 060154 | 2.733 | 17 | 2 | 1 | 2 |
| Lican | 060155 | 11.726 | 519 | 63 | 65 | 101 |
| Licto | 060156 | 6.778 | 122 | 13 | 12 | 21 |
| Pungala | 060157 | 3.925 | 33 | 1 | 3 | 5 |
| Punin | 060158 | 4.682 | 66 | 9 | 3 | 13 |
| Quimiag | 060159 | 4.479 | 62 | 7 | 7 | 11 |
| San Juan | 060160 | 6.309 | 139 | 10 | 19 | 22 |
| San Luis | 060161 | 19.510 | 819 | 75 | 107 | 147 |
| Total 11 parroquias | | 71.991 | 2.134 | 219 | 246 | 402 |

No se calculan tasas nuevas con denominadores de distinto ambito. En particular, 867 eventos de estas unidades rurales NO se dividen directamente por 83.669 sin resolver el componente rural de 060150 y los solapes urbanos. El total parroquial completo de Lican/San Luis tampoco se usa silenciosamente para un numerador que excluye sectores incluidos en Plataformas.

El archivo censal geoespacial actual del visor representa 199.971 personas en 3.301 manzanas con estadisticas, frente a 260.882 del canton: faltan 60.911 personas en ese emparejamiento. Disponer de los totales rurales NO basta para producir cobertura poblacional rural espacialmente completa. Se necesitan localidades/sectores censales rurales y su enlace poblacional.

## 5. Clasificacion propuesta

Se propone mantener, para la ampliacion, las cinco clases analiticas de la version local auditada, sin reasignaciones arbitrarias:

| Clase | Base completa | Urbano | Rural | Sin asignar |
|---|---:|---:|---:|---:|
| Delincuencia | 2.503 | 2.199 | 219 | 85 |
| Violencia | 1.563 | 1.244 | 246 | 73 |
| Convivencia / incivilidades | 6.976 | 6.367 | 402 | 207 |
| Actividad institucional / policial | 14.770 | 13.134 | 1.177 | 459 |
| Otros / revision | 904 | 788 | 90 | 26 |
| Total | 26.716 | 23.732 | 2.134 | 850 |

CLASIFICACION_SUBTIPOS.md contiene TODOS los 139 subtipos, numero de registros, clasificacion actual local y propuesta cantonal. Se mantienen pendientes los 39 subtipos ambiguos; clases 4 y 5 no participan en KDE, Gi* ni tasas de conflictividad. No se declara validacion judicial de delitos.

Nota de control: el informe narrativo anterior consignaba por error 672 registros urbanos de Otros/revision y total 23.616. Los conteos auditados correctos son 788 y 23.732; no cambia el numerador analitico urbano de 9.810 ni sus tres tasas.

## 6. Datos faltantes y decisiones previas a implementar

1. Resolver los 820 puntos interiores sin unidad y los 68 puntos en solapes urbano/rural. Aprobar una particion territorial coherente, sin cambiar las Plataformas ni asumir que todo exterior a ellas es rural.
2. Delimitar espacialmente el componente rural de 060150 (11.678 habitantes) y el area urbana censal, o documentar otra particion operativa con denominadores compatibles.
3. Confirmar fuente, fecha y autoridad de los limites locales. El CRS y la validez geometrica fueron comprobados; no se certifica por ello su vigencia legal.
4. Completar la geometria poblacional rural dispersa; no convertir totales parroquiales en puntos de residentes.
5. Obtener inventario validado de videovigilancia rural. Mantener Informacion de videovigilancia rural pendiente/no disponible; no mostrar cero como ausencia real.
6. Validar cobertura del inventario policial cantonal, red vial conectada, restricciones y velocidades si se requiere accesibilidad. Hoy solo hay proximidad euclidiana; no tiempo de respuesta.
7. Evaluar KDE rural/cantonal a partir de dispersion y cantidad de puntos; no copiar automaticamente bandwidth 700 m/celda 20 m urbanos. Evaluar malla y vecindad Gi* por escala y suficiencia; no forzar significancia con pocos datos.
8. Revisar subtipos ambiguos; no introducirlos automaticamente en analisis espaciales.

## 7. Archivos que se propondria modificar tras revision

- visor-seguridad-riobamba-v2.html: selector Cantonal/Urbano/Rural, unidades y filtros sincronizados, comparaciones y textos de disponibilidad, conservando layout/URL.
- tools/build_riobamba_real_incidents.py y visor-seguridad-riobamba-data.js: agregar ambito y unidad por interseccion, conservando campos originales.
- Nuevo generador/dataset territorial: importar limites y enlace poblacional rural con trazabilidad; no cambiar Plataformas.
- tools/build_kde_validation.py y tools/build_incident_spatial_reference.py: parametros y superficies/mallas por escala tras evaluacion; no reciclar la malla urbana ruralmente.
- tools/build_methodology_update.py y riobamba-metodologia-data.js: denominadores por ambito/unidad y comparacion urbano-rural, una vez resuelta la concordancia.
- Generadores/datasets de diagnostico y proximidad policial: extender unidades y mantener No disponible donde falten insumos rurales.
- Pruebas de dependencias: verificar sumas urbano+rural+sin asignar, filtros, exclusiones institucionales, tasas independientes y propagacion de datos faltantes.

NO se modificaria riobamba-camaras-data.js ni las geometrías originales de Plataformas/Bulevares. NO se implementaria AHP, puntaje de peligrosidad ni ranking final.

## 8. Salidas y control de no modificacion

Generados SOLO para auditoria: AUDITORIA_CANTONAL.json, POBLACION_CPV_AUDITADA.json, ASIGNACION_PRELIMINAR.csv, SIN_ASIGNAR.csv, PARROQUIAS_PRELIMINAR.csv, CLASIFICACION_SUBTIPOS.md y este informe. Nuevo script reproducible: tools/audit_cantonal_expansion.py.

La auditoria compara hashes antes/despues de 13 archivos productivos, incluidos interfaz, incidentes, camaras, censo/Plataformas, Bulevares y resultados activos; todos identicos. Las modificaciones locales preexistentes de la etapa anterior se conservan, no se revierten ni se publican.

Comprobaciones: 18 Plataformas; 31 camaras unicas; 139 subtipos; 11.042 eventos analiticos; reconciliacion de 26.716 registros; reconciliacion de 260.882 habitantes; coherencia de geometrías; archivos fuente abiertos solo para lectura.

Se detiene el trabajo en este punto para revision, conforme al orden solicitado. No se activa aun el selector territorial ni se recalculan/publican analisis cantonales.
