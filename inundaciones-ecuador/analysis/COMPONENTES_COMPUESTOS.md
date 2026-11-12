# Componentes fluvial, costero y de drenaje

## Estado real de esta ampliación

Se incorporó al motor la recepción de hidrogramas externos en celdas de entrada, niveles variables en bordes y series prescritas de intercambio con nodos de alcantarillado. Se probaron con casos numéricos sintéticos. **No se han activado nuevos escenarios territoriales reales en el visor.** Las 76 ejecuciones publicadas siguen correspondiendo únicamente a lluvia hipotética.

La interfaz de drenaje recibe series firmadas de intercambio, por ejemplo exportadas de un cálculo SWMM. No calcula una red de tuberías ni constituye acoplamiento dinámico bidireccional con SWMM. No debe describirse como alcantarillado ya modelado.

## Datos que impiden cerrar un modelo local

| Componente | Fuente comprobada | Insumos todavía pendientes |
| --- | --- | --- |
| Ríos | GEOGLOWS V2 / INAMHI | Selección y verificación del tramo y su ID; hidrograma completo; geometría del lecho, secciones, márgenes y estructuras; asociación de entradas al dominio |
| Mareas | INOCAR, alturas MLWS | Serie del puerto y evento; vinculación documentada MLWS–referencia vertical del terreno; borde de estuario; batimetría y estado inicial |
| Alcantarillado | Documentación de Interagua y portales municipales | Modelo de red con nodos, cotas de solera, conductos, diámetros, rugosidad, capacidad, descargas, bombas y estructuras; ejecutable SWMM o motor equivalente; validación de los intercambios superficie/red |

No se obtuvo un paquete completo de estos insumos para las 38 localidades. No se deben sustituir por secciones, cotas o capacidades inventadas. El motor rechaza series incompletas, fuentes ausentes, celdas fuera del dominio y niveles con referencia vertical incompatible. La evidencia declarada de datum debe ser revisada por el responsable; un texto en el archivo no verifica por sí mismo una nivelación real.

## Uso de la interfaz

```python
from compound_forcing import CompoundForcing
from hydraulics import simulate
external = CompoundForcing(config, dem.shape, terrain_datum, duration_seconds)
result = simulate(dem, dx, duration_hours=duration_seconds / 3600, external=external)
```

`config.surface_exchange`: lista de objetos con `id`, `kind` (`river_inflow` o `swmm_prescribed_exchange`), `cells` (índices fila/columna), `seconds`, `m3_s`, `source` y opcionalmente `weights`. Los caudales positivos entran en la superficie; los negativos se retiran hasta el agua disponible. Las entradas fluviales no admiten caudales negativos. Los intercambios son entradas/salidas de masa, no aportan momento y necesitan validación física independiente.

`config.stage_boundaries`: objetos con `side` (west/east/north/south), `seconds`, `stage_m`, `source`, `vertical_reference`, `datum_evidence`. La referencia debe coincidir con la del terreno. Se usa una condición de borde de nivel con flujo bidireccional simplificado sobre un lado completo; no se ha contrastado con un modelo estuarino. El nuevo argumento `domain_mask` permite incluir cotas cero y negativas. Para costa deben suministrarse esa máscara, batimetría y estado inicial verificables. La máscara heredada de cotas positivas continúa en los escenarios antiguos de lluvia.

### Ejecución reproducible de un nuevo escenario

`python run_compound.py terreno.npz escenario.json carpeta_nueva`

El NPZ debe contener `dem` (metros), `domain_mask` (booleanos) y opcionalmente `initial_depth` (metros). El JSON contiene `dx_m`, `terrain_datum`, `terrain_source`, `geometry_evidence`, `parameters` y `forcing`. `parameters` usa los argumentos físicos de `simulate`, incluyendo `duration_hours`; `forcing` usa las listas descritas arriba. La evidencia debe identificar levantamientos, secciones, referencias y estructuras utilizadas; el programa exige metadatos, pero no certifica su validez. Los índices fila/columna deben corresponder a la malla entregada.

Se generan `result.npz` con todos los estados y `report.json` con balance, parámetros, volúmenes de intercambio y huellas SHA-256 de entradas y código. Una carpeta existente se rechaza para conservar resultados previos. Las ejecuciones no se insertan automáticamente en el visor; requieren revisión y empaquetado territorial. Los pasos temporales se dividen en los cambios de tramo de las series. Las salidas negativas de drenaje se limitan al agua disponible en cada celda; la diferencia respecto al intercambio solicitado debe revisarse contra el modelo de red.

Verificación: `python -m unittest test_hydraulics test_compound -v` (12 pruebas). Incluye volumen fluvial analítico, cambios de tramo del hidrograma, referencia vertical incompatible, entrada por nivel exterior, lecho bajo cero y extracción limitada. Son comprobaciones numéricas sintéticas, no validación territorial ni evidencia de una red real calculada.

Antes de cada aplicación territorial: revisar geometría, condiciones iniciales, tamaño y extensión del dominio, resolución, compatibilidad temporal/vertical, balance, régimen de flujo, sensibilidad y validación independiente. El solver conserva sus límites de aproximación inercial local y salvaguarda de Froude.

## Referencias consultadas el 12 de noviembre de 2026

- GEOGLOWS: https://training.geoglows.org/rfs/tutorials/data-service/
- Identificación de tramos y advertencias sobre asignación automática: https://training.geoglows.org/rfs/tutorials/find-river-numbers/
- Hidrografía y catálogos: https://training.geoglows.org/rfs/datasets/catalog/
- INOCAR, referencia MLWS: https://www.inocar.mil.ec/mareas/graphs/grafico_diario.php
- Nivelación del río Guayas: https://inocar.mil.ec/web/index.php/noticias/2632-inocar-ejecuto-trabajos-de-nivelacion-para-el-monitoreo-de-mareas-en-el-rio-guayas
- SWMM: https://www.epa.gov/water-research/storm-water-management-model-swmm

Las redes y geometrías de ingeniería faltantes son el siguiente insumo imprescindible. Para un piloto fluvial se prioriza Quevedo; para el componente estuarino, Guayaquil–Durán. Esta priorización no certifica que ya existan todos los datos.
