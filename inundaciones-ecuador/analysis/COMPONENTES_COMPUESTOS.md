# Componentes fluvial, costero y de drenaje

## Estado real de esta ampliación

Actualización posterior del 12 de noviembre: se descargaron las predicciones horarias INOCAR de 2026 (9 puertos × 8.760 horas), el diccionario oficial de unidades y los metadatos GEOGLOWS V2. Se extrajeron 23.354 salidas fluviales en una ventana regional continental y tres candidatos por localidad cuando existen a menos de 30 km. No equivalen a ríos principales ni a condiciones de entrada verificadas. Hay tres hidrogramas de pronóstico descargados para candidatos próximos a Quevedo, Babahoyo y Guayaquil, emitidos el 12 de noviembre de 2026. Los caudales son modelados, no aforos.

La nueva página `entradas-hidraulicas.html` muestra estas series y los pendientes por localidad. Las mareas originales están en centímetros, convertidas a metros según el diccionario DD-INOCAR-CDA-003-2021-V01. El archivo cubre enero–diciembre de 2026, aunque su nombre de descarga contiene `2025noviembre`. Se conserva la hora original sin asignarle una zona horaria no documentada; requiere verificación antes de sincronizar con UTC de GEOGLOWS. No se convierte MLWS a la referencia del terreno.

Se incorporó al motor la recepción de hidrogramas externos en celdas de entrada, niveles variables en bordes y series prescritas de intercambio con nodos de alcantarillado. Se probaron con casos numéricos sintéticos. **No se han activado nuevos escenarios territoriales reales en el visor.** Las 76 ejecuciones publicadas siguen correspondiendo únicamente a lluvia hipotética.

La interfaz de superficie recibe series firmadas de intercambio. El nuevo ejecutor `run_swmm.py` sí calcula una red INP suministrada con SWMM 5.2.4 (toolkit 0.17.0), exportando niveles, desbordamientos y caudales en SI. Se ejecutó el ejemplo oficial EPA Extran de 10 nodos y 9 enlaces durante 8 horas: error de continuidad de aproximadamente −0,04156 %. Esta comprobación no representa una red de Ecuador. Todavía no hay un acoplamiento dinámico bidireccional ni una red municipal completa integrada.

## Datos que impiden cerrar un modelo local

| Componente | Fuente comprobada | Insumos todavía pendientes |
| --- | --- | --- |
| Ríos | GEOGLOWS V2 / INAMHI | Selección y verificación del tramo y su ID; hidrograma completo; geometría del lecho, secciones, márgenes y estructuras; asociación de entradas al dominio |
| Mareas | INOCAR, alturas MLWS | Serie del puerto y evento; vinculación documentada MLWS–referencia vertical del terreno; borde de estuario; batimetría y estado inicial |
| Alcantarillado | Documentación de Interagua y portales municipales; SWMM instalado y ejecutado | Modelo de red local con nodos, cotas de solera, conductos, diámetros, rugosidad, capacidad, descargas, bombas y estructuras; validación de los intercambios superficie/red |

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

Verificación: `python -m unittest test_hydraulics test_compound test_swmm -v` (14 pruebas). Incluye volumen fluvial analítico, cambios de tramo del hidrograma, referencia vertical incompatible, entrada por nivel exterior, lecho bajo cero, extracción limitada, ejecución del caso oficial EPA y transferencia de su volumen de desbordamiento a una malla sintética. Son comprobaciones numéricas, no validación territorial ni evidencia de una red municipal calculada.

### Datos descargados y redes SWMM

Instalar las dependencias de `requirements-compound.txt` dentro de `.deps`, utilizando el Python autorizado del proyecto. NumPy y pandas proceden del entorno geoespacial existente. No se distribuyen DLL ni paquetes binarios en GitHub.

```text
python -m pip install --target .deps -r requirements-compound.txt
python acquire_compound_data.py
python run_swmm.py raw/compound-acquisition/EPA-Example2.inp swmm-verification/verified-export
python build_compound_inputs.py
python -m unittest test_hydraulics test_compound test_swmm -v
```

La descarga conserva los archivos existentes. Para otro evento/versión usar una carpeta de trabajo nueva; no confundir el pronóstico archivado con una consulta en tiempo real. El catálogo fluvial original ocupa unos 139 MB y queda local; el visor publica únicamente derivados pequeños con procedencia y huellas. No todos los puntos de la ventana regional están dentro de Ecuador.

Para una red real: `python run_swmm.py red.inp carpeta_nueva`. Revisar el informe RPT, inestabilidades, advertencias y balance; el umbral diagnóstico de 1 % no sustituye la validación. Las unidades de entrada pueden ser las seis admitidas por SWMM; la exportación convierte caudal a m³/s y cotas a metros. El paso final se incluye hasta el fin del modelo.

`python swmm_surface_exchange.py carpeta_swmm mapeo.json forzamiento_nuevo.json` convierte los desbordamientos de nodos seleccionados en entradas de superficie. El mapeo exige `source`, `geometry_evidence` y `nodes` (identificador → lista de celdas). Usar ubicaciones verificadas sobre la misma malla. La interpolación `interval_end` conserva el volumen definido por las tasas y duraciones de los pasos exportados; el modo predeterminado continúa siendo lineal. No calcula captación de sumideros ni retorno desde superficie. La exportación de inundación por nodo es una aproximación temporal del flujo interno: revisar convergencia y contrastar su integral con el RPT. Evitar duplicar lluvia y escorrentía ya aportadas a la red. `forcing` del escenario de `run_compound.py` puede recibir el JSON generado después de revisar todos los insumos.

El ejemplo EPA es de dominio público del Gobierno de EE. UU. Fuente: https://github.com/USEPA/swmm-nrtestsuite/blob/dev/public/examples/Example2.inp . Licencia del toolkit instalado: CC0-1.0 y componentes MIT/Apache-2.0; consultar el paquete. Datos GEOGLOWS: https://geoglows.ecmwf.int/license (CC BY 4.0). INOCAR: CC BY, según su catálogo oficial.

Antes de cada aplicación territorial: revisar geometría, condiciones iniciales, tamaño y extensión del dominio, resolución, compatibilidad temporal/vertical, balance, régimen de flujo, sensibilidad y validación independiente. El solver conserva sus límites de aproximación inercial local y salvaguarda de Froude.

## Referencias consultadas el 12 de noviembre de 2026

- GEOGLOWS: https://training.geoglows.org/rfs/tutorials/data-service/
- Identificación de tramos y advertencias sobre asignación automática: https://training.geoglows.org/rfs/tutorials/find-river-numbers/
- Hidrografía y catálogos: https://training.geoglows.org/rfs/datasets/catalog/
- INOCAR, referencia MLWS: https://www.inocar.mil.ec/mareas/graphs/grafico_diario.php
- Nivelación del río Guayas: https://inocar.mil.ec/web/index.php/noticias/2632-inocar-ejecuto-trabajos-de-nivelacion-para-el-monitoreo-de-mareas-en-el-rio-guayas
- SWMM: https://www.epa.gov/water-research/storm-water-management-model-swmm

Las redes y geometrías de ingeniería faltantes son el siguiente insumo imprescindible. Para un piloto fluvial se prioriza Quevedo; para el componente estuarino, Guayaquil–Durán. Esta priorización no certifica que ya existan todos los datos.
