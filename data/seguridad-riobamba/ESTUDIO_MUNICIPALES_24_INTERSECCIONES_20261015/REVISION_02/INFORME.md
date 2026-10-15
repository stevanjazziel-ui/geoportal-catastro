# Estudio de 24 municipales: intersecciones y trazabilidad

ESTUDIO NO APLICADO AL VISOR. Publicar el estudio no implica aprobar ni aplicar ubicaciones.

24 municipales estructurales urbanas; 103 existentes, 22 rurales, 4 Las Abras y 30 policiales fijas

Cruces actuales verificados en la red municipal: 3 de24.

## Comparacion

| Escenario | Macaji % | Macaji sin cubrir m | Anillo % | Ciclovias % | Principales | Movidas >1m | Total movido m | Mediana m | Maximo m | Cumple metas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ACTUAL | 100.000 | 0.000 | 80.039 | 64.595 | - | 0 | 0 | 0 | 0 | Referencia |
| A_CRUCES_PRINCIPALES_CERCANOS | 95.276 | 450.729 | 75.367 | 62.671 | 24 | 22 | 1306.6 | 49.6 | 163.5 | False |
| C_PRIORIDAD_PRINCIPALES | 100.000 | 0.000 | 80.022 | 57.725 | 23 | 24 | 5079.3 | 83.5 | 1162.4 | True |
| D_PRIORIDAD_CICLOVIAS | 100.000 | 0.000 | 80.000 | 58.682 | 20 | 24 | 5076.1 | 83.5 | 1162.4 | True |

Los porcentajes de la tabla usan103existentes+50municipales. Las30policiales permanecen fijas y solo se reportan aparte en RESULTADOS.json.

## Trazabilidad

AUDITORIA_24_ACTUALES.csv identifica la situacion actual; ALTERNATIVAS_5_POR_CAMARA.csv contiene cinco cruces principales cercanos por camara y su efecto individual, no sumable.
Cada escenario conserva ID_PROPUESTA, coordenadas anteriores y estudiadas, distancia, azimut, ID del nodo, grado, vias, tipologias, fuente y conexion teorica por red.
La asignacion de24IDs a24posiciones seleccionadas minimiza el desplazamiento para esa seleccion; no implica que el desplazamiento sea optimo global entre todas las selecciones factibles.

## Catalogos y solucionador

```json
[
  {
    "label": "B_PRINCIPALES_CON_COBERTURA",
    "phase": "PRIORIDAD_VIAS_PRINCIPALES",
    "catalogCount": 610,
    "status": 2,
    "message": "The problem is infeasible. (HiGHS Status 8: model_status is Infeasible; primal_status is None)",
    "objective": null,
    "gap": null
  },
  {
    "label": "C_PRIORIDAD_PRINCIPALES",
    "phase": "PRIORIDAD_VIAS_PRINCIPALES",
    "catalogCount": 1092,
    "status": 0,
    "message": "Optimization terminated successfully. (HiGHS Status 7: Optimal)",
    "objective": -23.0,
    "gap": 0.0
  },
  {
    "label": "C_PRIORIDAD_PRINCIPALES",
    "phase": "MAX_CICLOVIAS",
    "catalogCount": 1092,
    "status": 0,
    "message": "Optimization terminated successfully. (HiGHS Status 7: Optimal)",
    "objective": -914.7894301139987,
    "gap": 0.0
  },
  {
    "label": "C_PRIORIDAD_PRINCIPALES",
    "phase": "MIN_DESPLAZAMIENTO_CON_OBJETIVOS_FIJOS",
    "status": 0,
    "objective": 5079.30473301634,
    "gap": 0.0
  },
  {
    "label": "D_PRIORIDAD_CICLOVIAS",
    "phase": "MAX_CICLOVIAS",
    "catalogCount": 1092,
    "status": 0,
    "message": "Optimization terminated successfully. (HiGHS Status 7: Optimal)",
    "objective": -1019.8604862824432,
    "gap": 0.0
  },
  {
    "label": "D_PRIORIDAD_CICLOVIAS",
    "phase": "PRIORIDAD_VIAS_PRINCIPALES",
    "catalogCount": 1092,
    "status": 0,
    "message": "Optimization terminated successfully. (HiGHS Status 7: Optimal)",
    "objective": -19.999999999999982,
    "gap": 0.0
  },
  {
    "label": "D_PRIORIDAD_CICLOVIAS",
    "phase": "MIN_DESPLAZAMIENTO_CON_OBJETIVOS_FIJOS",
    "status": 0,
    "objective": 5076.090654509761,
    "gap": 0.0
  }
]
```

## Limitaciones

- Cruces topologicos de ejes GIS en 2D: validar pasos a desnivel, poste y esquina operativa en campo.
- Los 400m por red ilustran dos alcances de200m; no son certificacion de visibilidad ni condicion dura para todos los puntos.
- Continuidad parcial por cantidad limitada de camaras. No se agrandan radios ni se cuentan otras30policiales para cumplir metas municipales.
- No se cambia KDE ni Gi*. KDE y eventos son contexto, no sustituyen los objetivos territoriales municipales.
- La factibilidad y optimalidad son relativas al catalogo GIS, no al conjunto de todas las esquinas fisicas existentes.
- Desplazamiento calculado entre coordenadas propuestas, no obra ejecutada. No hay autorizacion de implantacion.

No se modifica ninguna fuente ni archivo del visor. Revisar resultados antes de decidir una implementacion.

## Control de interpretacion

Los 3 cruces exactos actuales se comprueban con tolerancia geometrica de0.05m en Vialidad_urbana. Otras2posiciones provienen de nodos de otra red y difieren0.94/2.21m; esa diferencia no prueba por si sola un error de campo. No confundir no coincidencia exacta entre fuentes con ubicacion fisica incorrecta.

La alternativaC prioriza el numero de cruces en vias principales, despues Ciclovias y finalmente el desplazamiento. La alternativaD prioriza Ciclovias, despues vias principales y finalmente el desplazamiento. Ambas exigen Macaji100 y Anillo80. El solucionador demuestra sus objetivos dentro del catalogo, no visibilidad real.

Los nombres de calles proceden deTXT. NOMBRE corresponde a parroquia y se conserva separadamente comoPARROQUIA_RED. Los cruces sin dos nombres confirmados se senalan como pendientes; no se sustituyen por nombres parroquiales ni etiquetas inventadas.

ID_TRAMOS_TARGET_FID identifica los segmentos deVialidad_urbana incidentes en cada nodo; permite auditar tambien los cruces sin nombre o con caracteres ilegibles en la fuente.

Los enlaces azules y los pares por red comparan exclusivamente estas24municipales; no representan la conectividad de todo el sistema183. Se entregan los276pares por escenario, incluidos desconectados y mayores de400m.

Ninguna seleccion solo en cruces conserva la actual cobertura de Ciclovias64.5948% al exigir Macaji100/Anillo80 en este catalogo; el maximo obtenido y demostrado es58.6819%. Esto no autoriza reducir la cobertura ni implementar la alternativa.

## Desplazamientos de la alternativaC

| ID | Distancia m | Nodo | Via principal |
|---|---:|---|---|
| MUN-027 | 156.38 | Nodo en Villa Orellana (otra via sin nombre confirmado) | True |
| MUN-028 | 92.96 | Av. 9 de Octubre x Calle Dècima | True |
| MUN-029 | 139.09 | Nodo en Av. Unidad Nacional (otra via sin nombre confirmado) | True |
| MUN-030 | 130.31 | Av. Edelberto Bonilla Oleas x Mendoza | True |
| MUN-031 | 47.86 | Nodo en Av. 9 de Octubre (otra via sin nombre confirmado) | True |
| MUN-032 | 1142.98 | Cristobal Colon x España | True |
| MUN-033 | 40.20 | Nodo en Av. Unidad Nacional (otra via sin nombre confirmado) | True |
| MUN-034 | 133.79 | Av. Edelberto Bonilla Oleas x Jose Maria Velasco Ibarra | True |
| MUN-035 | 76.15 | Colombia x Esmeraldas | True |
| MUN-036 | 58.49 | Nodo en Av. 9 de Octubre (otra via sin nombre confirmado) | True |
| MUN-037 | 201.28 | Nodo en Junin (otra via sin nombre confirmado) | True |
| MUN-038 | 96.13 | Bernardo Darquea x Josè Veloz x Primera Constituyente x Puruha | True |
| MUN-039 | 12.07 | Nodo en Santa Martha (otra via sin nombre confirmado) | True |
| MUN-040 | 218.67 | Nodo en Baron de Carondelet (otra via sin nombre confirmado) | True |
| MUN-041 | 85.50 | Nodo en Av. Daniel Leon Borja (otra via sin nombre confirmado) | True |
| MUN-042 | 925.75 | Av. Juan Bernardo de León x Puruha | False |
| MUN-043 | 59.98 | Av. 9 de Octubre x La Valetta x Paris | True |
| MUN-044 | 50.67 | Cruce sin nombres viales confirmados | True |
| MUN-045 | 20.52 | Nodo en Albania (otra via sin nombre confirmado) | True |
| MUN-046 | 65.26 | Av. Edelberto Bonilla Oleas x Av. Simon Bolivar x Bolivar Bonilla | True |
| MUN-047 | 81.47 | Cruce sin nombres viales confirmados | True |
| MUN-048 | 1162.44 | Cruce sin nombres viales confirmados | True |
| MUN-049 | 41.08 | 2 de Agosto x Almagro x Av. 9 de Octubre | True |
| MUN-050 | 40.28 | Av. 9 de Octubre x Av. Celso augusto Rodriguez x Cartagena | True |
