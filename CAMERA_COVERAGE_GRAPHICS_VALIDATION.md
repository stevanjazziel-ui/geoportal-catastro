# Validacion de graficos de cobertura

Fecha: 2026-09-30. Validacion previa a la publicacion autorizada.

## Separacion de resultados

- `coverageTerritorialData`: area cubierta/no cubierta en km2 y porcentaje territorial.
- `coveragePopulationData`: habitantes cubiertos/no cubiertos y porcentaje poblacional.
- Dona binaria: el segmento parcial anterior duplicaba parte de la poblacion.
- KPI, escenarios, tablas, ficha y CSV utilizan la unidad de su modulo.
- La ficha seleccionada usa el mismo denominador del calculo por manzanas que
  los graficos y la tabla; no mezcla el area del poligono completo con el area
  de las manzanas analizadas.
- No se modificaron CSS, menu, mapa, plataformas, inventario ni otros analisis.
- Se conserva el estimador espacial existente basado en muestreo de manzanas.
  Estos valores no constituyen una nueva interseccion geometrica exacta.

## Resultados actuales: todas las plataformas

Area analizada: 20.3718960873 km2. Poblacion analizada: 171665 habitantes.

| Radio | Area cubierta km2 | Area no cubierta km2 | Cobertura territorial | Habitantes cubiertos | Habitantes no cubiertos | Cobertura poblacional |
| --- | --- | --- | --- | --- | --- | --- |
| 100 m | 0.592731 | 19.779165 | 2.9% | 6675 | 164990 | 3.9% |
| 150 m | 1.257960 | 19.113936 | 6.2% | 14488 | 157177 | 8.4% |
| 200 m | 2.151721 | 18.220175 | 10.6% | 24689 | 146976 | 14.4% |

Plataforma I, 150 m: area cubierta 0.220061 km2 de 0.736790 km2 (29.9%);
poblacion cubierta 3036 de 9060 habitantes (33.5%).

## Auditoria del inventario: 31 registros confirmados

- Total de registros: 31.
- IDs unicos: 31. Coordenadas unicas: 31. Duplicados: 0.
- Marcados para cambio: 31; tipos DOMO: 30; tipo LA: 1.
- Registro distinto de DOMO: RIO-068-LA, Centro Operativo Local Riobamba,
  institucion ECU911. El informe PDF, pagina 3, tambien lo marca SI.
- El usuario confirmo mantener las 31 camaras existentes y autorizo publicar.
  Se conserva RIO-068-LA; NO se ha eliminado ni excluido ningun registro.
- El listado historico anterior al commit a249022 contiene RIO-001 a RIO-030;
  solo seis estan marcados para cambio. No equivale al conjunto actual menos uno.
- Instituciones en el inventario actual: GADM RIOBAMBA 18, MINEDUC 5,
  ECU 911 Riobamba 7, ECU911 1. La etiqueta interna MUNICIPAL no demuestra
  por si sola propiedad municipal; no se ha alterado su interpretacion aqui.
- Los resultados utilizan el universo confirmado de 31 registros actuales,
  no un subconjunto de 30.

## Comprobaciones

`node tools/validate_camera_coverage_graphics.cjs`: 57 selecciones
(todas + 18 plataformas, tres radios), 114 renderizados de modulos y CSV.
Se comprueban unidades independientes, sumas cubierta/no cubierta, porcentajes,
crecimiento entre escenarios y conservacion del escenario seleccionado.

Prueba en navegador: ambos modulos, radios 100/150/200 y Plataforma I.
Regresion de incidentes: `node tools/validate_incident_dependencies.cjs`.
