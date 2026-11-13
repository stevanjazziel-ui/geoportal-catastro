# Riobamba: aproximación local exploratoria · 12/11/2026

Visor: [riobamba.html](../riobamba.html). El atlas nacional conserva sus escenarios anteriores. Este piloto local añade tres simulaciones distintas y no está calibrado. **La extensión inundada no ha demostrado convergencia con la malla. No utilizar por calle/predio ni como alerta o diseño.**

## Datos utilizados y papel dentro del modelo

| Fuente suministrada | Uso implementado | Limitación |
|---|---|---|
| MDT.TIF, ~3 m, EPSG:31977 | Promedio a celdas de cálculo de 24 m; 59,17 km² con ≥95 % de terreno válido por celda | Datum vertical y fecha de levantamiento no documentados; no resuelve bordillos ni sumideros |
| Cobertura: 2.550 polígonos, 2018 | Rugosidad e infiltración espacialmente variables por clase | Parámetros estimados, no ensayos locales; cobertura antigua |
| Geomorfología, CAUCE ACTUAL | Identifica el cauce en la cobertura y sus parámetros superficiales | No modifica el fondo ni inventa batimetría |
| PrecipitacionMax.xlsx, 1950–2025 | Máximos suministrados: 7,100825 mm/1 h y 56,882992 mm/24 h; tormentas uniformes sintéticas | Procedencia de estación/producto sin confirmar; 2026 incompleto excluido; no período de retorno |
| Portal: 6.359 tramos | Escenario separado SWMM: 6.047 tramos y 4.767 nodos dentro del terreno válido | Cotas enterradas, captación y salidas estimadas; se excluyen 305 tramos fuera del terreno y 7 menores de 2 m |
| 417 diámetros faltantes en la fuente | 354 de los tramos retenidos usan la mediana por sistema: 0,30/0,30/0,80 m | Se conserva que fueron estimados; no se adopta el valor visual de respaldo del portal como medición |
| 1.620 cotas CAD y 483 anotaciones hidráulicas | Conservadas en la revisión y capa contextual descargable | Papel tapa/fondo sin verificar; no se asignan automáticamente |
| 264 alcantarillas cartográficas | Capa contextual, distinta de la red del portal | Sin capacidades/cotas verificadas; no añade conductos hidráulicos ficticios |
| ANEGAMIENTO2: 725.658 polígonos | Rasterización contextual de BAJO/MEDIO/ALTO/MUY ALTO y cálculo de solapamiento | Clasificación de origen metodológico no confirmado; no es una inundación observada ni valida el modelo |
| Cinco cuencas y series diarias de caudal | Contexto hidrológico y series preservadas descargables | No se usa un caudal diario como pico instantáneo; faltan entrada de evento y secciones de río |

Los originales completos permanecen en el proyecto local. Se publican derivados compactos, metadatos con SHA-256, series preservadas y el INP/informe de la red estimada, comprimidos. No se entrenó ningún modelo de aprendizaje automático.

## Superficie

`prepare_riobamba_model.py` transforma las capas al CRS del MDT, agrega el terreno y excluye NoData. Los ceros de almacenamiento fuera de la máscara **nunca son cotas de fondo**. Los parámetros por clase se publican íntegros en el manifiesto; por ejemplo, urbano n=0,08 e infiltración constante 0,5 mm/h, agricultura n=0,05 y 5 mm/h. Estos valores son supuestos del proyecto, no parámetros calibrados ni resultados de ensayos de suelo.

`local_flood_solver.py` resuelve una aproximación inercial local bidimensional: continuidad conservativa, presión por gradiente de lámina, fricción Manning, paso adaptativo CFL 0,45, limitación de Froude y limitación de flujo por el volumen disponible. Cada celda recibe lluvia y pierde agua por infiltración hasta el volumen disponible. Inicialmente seco. Los bordes del dominio y huecos NoData tienen salida crítica libre; no reciben aportes externos. Esa frontera es un supuesto importante, especialmente junto al borde. No se imponen mareas a Riobamba.

## Red estimada y transferencia de reboses

`approximate_riobamba_network.py` utiliza SWMM 5.2.4, onda dinámica, CMS. Reconciliación geométrica de extremos por coordenada a 0,1 m, sin fusionar nodos alejados que reutilizan identificadores del portal. Las cotas de fondo son terreno de la malla menos 1 m de cobertura menos el mayor diámetro incidente; n de tubería=0,013, sección circular. No son cotas levantadas.

Se supone una salida libre junto al nodo más bajo de cada uno de los 82 componentes, mediante un conducto auxiliar de 10 m y desnivel 0,1 m. Captación instantánea del exceso de lluvia en celdas situadas a ≤75 m del nodo más cercano, excluyendo cauces cartografiados; área captada: 23,426496 km². Se resta la infiltración estimada antes de inyectar el caudal, y se declara una rampa lineal de un minuto al terminar la lluvia. No hay retardo hidrológico de subcuencas ni capacidad de sumideros medida.

Los volúmenes acumulados de rebose de SWMM se diferencian por intervalos de 60 s y se exportan como tasas medias conservativas (CMS/m³). La integral exportada coincide con el volumen acumulado: 115.092,95 m³. Las celdas captadas no reciben además lluvia/infiltración en 2D: se evita el doble conteo. El rebose se incorpora como fuente superficial. **No existe retorno de agua a la red ni retroalimentación de la lámina superficial.** La comparación tampoco representa un límite matemático inferior/superior: la red puede concentrar agua y aumentar profundidades locales.

Continuidad de la red: 0,4333 %. Superar este control no valida la geometría ni los supuestos. El informe SWMM completo incluye advertencias y diagnóstico de oscilaciones; debe revisarse antes de cualquier uso de ingeniería. La transferencia de superficie conserva agua numéricamente, pero la combinación todavía necesita validación con un evento real.

## Resultados y controles

| Escenario sintético | Duración lluvia / cálculo | Huella máxima ≥5 cm | Máximo puntual de profundidad |
|---|---|---:|---:|
| 1 h, sin drenaje | 1 h / 2 h | 1,176 km² | 0,990 m |
| 1 h, red estimada | 1 h / 2 h | 0,890 km² | 2,440 m |
| 24 h, sin drenaje | 24 h / 26 h | 3,362 km² | 6,466 m |

La huella máxima reúne celdas mojadas en diferentes momentos; no es una lámina simultánea. Las profundidades son resultados condicionados por pérdidas, depresiones y fronteras asumidas; no pronósticos. El escenario de 24 h no incorpora drenaje y puede retener agua en depresiones del MDT sin estructuras representadas.

Error relativo del balance superficial ≤4,5×10⁻¹³ en los tres casos. Pruebas: lluvia/infiltración analítica, lago en reposo, máscara/borde y transferencia temporal conservativa, además de las verificaciones previas del motor y del ejemplo EPA: **18 pruebas aprobadas**. Se conservan las salidas originales sin cuantizar; el visor usa milímetros enteros solo para reducir la descarga.

Sensibilidad: el mismo caso de 1 h a 48 m produce 0,751 km², **−36,1 %** frente a 24 m. También varía ligeramente la máscara válida por agregación. Esta prueba evidencia falta de convergencia espacial. Quedan pendientes refinamiento de malla, sensibilidad a pérdidas/captación, geometría verificada y validación con eventos, antes de afirmar una aproximación de precisión conocida.

## Reproducción

Ejecutar con Python del entorno GeoAI y dependencias de `requirements-riobamba.txt`, manteniendo la disposición de `riobamba-inputs/` local. Los originales de Drive no se incluyen completos en GitHub por tamaño.

1. `python prepare_riobamba_model.py --dx 24`
2. `python run_riobamba_cases.py --case hour` y `--case day`
3. `python approximate_riobamba_network.py`
4. Invocar `run()` de `run_riobamba_cases.py` con `network=Path('riobamba-runs/grid-24m/network-inferred-1h-v2')`, mismo caso de 1 h.
5. Preparar 48 m y ejecutar el caso de 1 h para la sensibilidad.
6. `python pack_riobamba.py`; servir `dist/` mediante HTTP. Los escenarios reservan sus nombres y rechazan sobrescribir resultados.

Referencias metodológicas: [EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm), [HEC-RAS: capas de cobertura y rugosidad](https://www.hec.usace.army.mil/confluence/rasdocs/rmum/6.1/land-classification-layers). Estas referencias no sustituyen las mediciones locales ni acreditan los valores de infiltración supuestos.
