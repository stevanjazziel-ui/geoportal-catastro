# Validacion previa: correccion de conflictividad

Fecha: 2026-10-01. Estado: DETENIDO EN VALIDACION DE INPUT, sin modificar visor, datos productivos, KDE, Gi*, tasas, geometria ni publicacion.

## Resultado

La base contiene 26.716 IDs unicos. Se genero un diccionario explicito para sus 139 subtipos, una version derivada NO APLICADA con CATEGORIA_ANALITICA / RECURRENCIA_XY / FLAG_COORD y un control por seis subconjuntos. No se utilizo Emergencias como peso, no hubo jitter, redondeo, deduplicacion ni desplazamiento de puntos.

La propuesta conservadora incorpora los subtipos nuevos expresamente enumerados, conserva el diccionario previo en los demas y propone Bomberos para OTROS_REVISION por figurar en la lista de revision del documento. Explosivos permanece pendiente porque no se enumera explicitamente junto a armas.

| Categoria | Publicado actualmente | Propuesta conservadora, NO aplicada | Esperado | Diferencia propuesta-esperado |
|---|---:|---:|---:|---:|
| Delincuencia | 2.503 | 2.531 | 2.533 | -2 |
| Violencia | 1.563 | 1.594 | 1.590 | +4 |
| Convivencia | 6.976 | 7.027 | 7.027 | 0 |
| Actividad institucional | 14.770 | 14.749 | 14.778 | -29 |
| Otros/revision | 904 | 815 | 788 | +27 |
| TOTAL | 26.716 | 26.716 | 26.716 | 0 |

Por la instruccion de no continuar cuando los conteos difieran, NO se evaluaron ni seleccionaron bandwidth ni se regeneraron superficies/resultados estadisticos.

## Subtipos responsables de los cambios propuestos

Delincuencia: comercializacion de sustancias (9), tenencia ilicita de sustancias (6), porte de arma blanca (9), porte de armas de fuego (4): +28.

Violencia: heridas con arma blanca (16), arma de fuego (8), objeto contundente (4), Disparos (2), Trata de personas (1): +31.

Convivencia: Consumo de sustancias sujetas a fiscalizacion (51): +51.

Bomberos (21): propuesta de pasar de institucional a Otros/revision, NO aplicada y pendiente de confirmar.

Los otros subtipos se conservan para revision. No se usa coincidencia parcial de palabras ni se ajustan categorias para alcanzar un objetivo numerico.

## Reconciliacion exacta encontrada, no adoptada

Existe una combinacion de cuatro reglas que reproduce EXACTAMENTE las cinco cifras esperadas:

| Subtipo original | N | Categoria que reproduce el objetivo | Motivo para no aplicarla automaticamente |
|---|---:|---|---|
| Bomberos | 21 | ACTIVIDAD_INSTITUCIONAL | El documento tambien lo enumera entre los casos para revision en Otros. |
| Tenencia y porte de explosivos | 2 | DELINCUENCIA | Equivalencia con porte de armas no explicitada; requiere confirmar. |
| Falta contra la integridad a servidores policiales | 4 | ACTIVIDAD_INSTITUCIONAL | El nombre no prueba que sea una actuacion institucional, en lugar de una agresion. |
| Plantones | 4 | ACTIVIDAD_INSTITUCIONAL | El nombre no prueba que se trate de un procedimiento policial/institucional. |

Resultado hipotetico: 2.533 / 1.590 / 7.027 / 14.778 / 788 = 26.716. Coincidir aritmeticamente NO valida semanticamente estas decisiones. La combinacion se guarda como HIPOTESIS, no como clasificacion oficial.

## Diferencia territorial identificada

Los objetivos 24.271 urbanos / 2.445 rurales se reproducen usando PARROQUIA_ORIGEN = RIOBAMBA frente a las otras etiquetas de la base. NO son los resultados del cruce de coordenadas con las geometrías aprobadas.

Con las cuatro reglas hipoteticas y esa etiqueta de origen, tambien se reproducen exactamente todos los conteos por categoria solicitados:

| Categoria | Etiqueta RIOBAMBA | Otras etiquetas |
|---|---:|---:|
| Delincuencia | 2.280 | 253 |
| Violencia | 1.328 | 262 |
| Convivencia | 6.530 | 497 |

El criterio espacial publicado y aprobado sigue dando: 23.732 URBANO, 2.134 RURAL y 850 SIN_ASIGNAR (820 dentro del canton y 30 fuera). La clasificacion tematica no puede cambiar por si sola la ubicacion espacial.

| Etiqueta de origen | En union urbana | En parroquias rurales operativas | Sin asignar espacialmente |
|---|---:|---:|---:|
| RIOBAMBA | 23.375 | 99 | 797 |
| Otras parroquias | 357 | 2.035 | 53 |

Usar las etiquetas de origen para los calculos implicaria otro criterio y podria incluir puntos externos, huecos o puntos dentro de Plataformas con etiqueta rural. No se reasignan para hacer coincidir las cifras. Se requiere confirmar el criterio territorial antes de generar los seis analisis.

## Control de coordenadas exactas

Base completa: 6.420 ubicaciones distintas; recurrencia maxima de una XY = 477 filas. Flags por REGISTROS: NORMAL 4.267; REPETIDA 6.786; ALTA_REPETICION 7.144; MUY_ALTA_REPETICION 8.519. La suma de flags conserva las 26.716 filas. Una coincidencia no prueba duplicacion ni un incidente artificial.

RECURRENCIA_XY / FLAG_COORD se calculan sobre la base completa. La siguiente tabla usa repeticion DENTRO de cada subconjunto espacial y categoria propuestos; porcentaje de filas que comparten XY, no porcentaje de ubicaciones:

| Ambito | Categoria propuesta | N | XY unicas | % registros en XY repetida | Maximo |
|---|---|---:|---:|---:|---:|
| Urbano | Delincuencia | 2.227 | 1.208 | 61,92 | 62 |
| Urbano | Violencia | 1.270 | 875 | 48,03 | 34 |
| Urbano | Convivencia | 6.418 | 2.386 | 76,99 | 117 |
| Rural | Delincuencia | 219 | 131 | 51,60 | 25 |
| Rural | Violencia | 248 | 147 | 50,00 | 21 |
| Rural | Convivencia | 402 | 233 | 51,00 | 38 |

BANDWIDTH_RECOMENDADO queda NO_SELECCIONADO_VALIDACION_ENTRADA_PENDIENTE para los seis subconjuntos, no cero ni una recomendacion inventada.

## Aclaracion sobre el KDE publicado

El codigo publicado ya excluye las clases institucional/revision y usa peso 1. El control de los IDs de entrada confirma cero registros de esas dos clases en el insumo KDE. Por tanto, "Todos los registros +700m" no describe el KDE actual. Podria compararse posteriormente como CONTRAFACTUAL institucional, claramente rotulado, nunca como resultado historico real.

El bandwidth urbano de 700 m no se considera validado para las categorias nuevas. Su evaluacion 200/250/300/400/500/700 m queda pendiente de resolver el input. Lo mismo ocurre con las pruebas rurales 500/750/1.000/1.200/1.500 m, escala compartida de simbologia y menor opacidad. No se heredan ni se optimizan por apariencia.

## Archivos y verificacion

Nuevo script: tools/audit_conflictivity_correction.cjs. Nuevos artefactos en esta carpeta, todos de revision:

- [Diccionario completo, 139 subtipos](SUBTIPO_CATEGORIA_PROPUESTA.csv) y [JSON editable de revision](DICCIONARIO_PROPUESTO.json).
- [Base derivada, no aplicada](REGISTROS_ANALITICOS_PROPUESTA.csv), con coordenadas y SUBTIPO originales intactos.
- [Cambios expresos por subtipo](CAMBIOS_SUBTIPOS.csv).
- [Cuatro reglas pendientes de confirmar](RECONCILIACION_REQUIERE_CONFIRMACION.csv).
- [Comparacion de categorias](COMPARACION_CATEGORIAS.csv) y [categorias por ambito geometrico](COMPARACION_AMBITOS_CATEGORIAS.csv).
- [Cruce etiqueta/geometria](CONTRASTE_AMBITOS_TEXTO_GEOMETRIA.csv).
- [Control de coordenadas](CONTROL_COORDENADAS.csv) y [auditoria completa](AUDITORIA_INPUT.json).

Ejecutado: node tools/audit_conflictivity_correction.cjs. Assertions PASS: N, IDs, total esperado, existencia y unicidad de reglas exactas, reproduccion de la hipotesis, latitud/longitud/SUBTIPO intactos, peso1, cero filtracion institucional del insumo KDE publicado y hashes productivos sin cambios.

Sin cambios en los modulos, menu, layout, camaras, poblacion, proximidad policial ni geometrías. Sin commit ni push. Se detiene para confirmar diccionario y criterio territorial; no se afirma haber completado los KDE/Gi* pendientes.
