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


Actualización visual 14/11/2026: `build_riobamba_context.py` descarga nueve teselas Terrarium Mapzen (zoom 10) para el contexto regional. Se conserva su procedencia y SHA-256 en `regional-context.json.gz`. Su interpolación afecta exclusivamente la visualización fuera del MDT válido, sin ampliar el dominio ni recalcular resultados. Ejecutar este script antes de servir o publicar el visor.

La lámina se dibuja sobre el terreno interpolado de visualización con separación gráfica de 0,15 m para evitar ocultamiento entre mallas. Las profundidades, áreas y balances consultados provienen de los resultados originales; la posición de la malla gráfica no es un levantamiento de cota de lámina. Las áreas del panel usan valores sin cuantización de los informes.


## Escenarios IDF de estación · 14/11/2026

`integrate_riobamba_idf.py` añade lluvias uniformes de diseño desde las tablas históricas de INAMHI (estudio 2015), cuadros 27 (Aeropuerto M0057, p.55) y 72 (ESPOCH M1036, p.100). Se conserva URL, tabla, unidades, valores tabulados y SHA-256 del PDF oficial descargado en `inamhi-idf.json`. No se afirma haber verificado una revisión más reciente.

Nuevos cálculos sin drenaje: ESPOCH 1 h, T10=28,1; T25=34,0; T50=39,2; T100=45,2 mm/h; Aeropuerto 1 h T25=22,9; ESPOCH 2 h T25=18,8 mm/h. Cada evento tiene una hora adicional de recesión. Se vuelve a ejecutar la red y el intercambio de reboses para ESPOCH 1 h T25=34 mm/h, sin escalar salidas hidráulicas antiguas.

La lluvia de estación se aplica uniformemente al dominio sin reducción areal ni distribución temporal observada. El retorno de la lluvia no establece el retorno de la inundación. La comparación de resolución anterior se refiere exclusivamente al caso de 7,10 mm/h; los escenarios IDF no tienen una nueva prueba de convergencia.

Los casos de 7,10 mm/h permanecen como referencias claramente identificadas de origen pendiente. El caso de 24 h previo se conserva localmente y en el historial Git, retirándose su descarga del sitio activo para mantener el límite de GitHub Pages. Ejecutar el integrador después del empaquetador base para reproducir la publicación IDF.


## Ampliación de estrés por preparación ante El Niño · 14/11/2026

El informe ERFEN 012-2026, del 5/11/2026, indica evento activo. La perspectiva mensual de noviembre para el callejón interandino es normal; las estribaciones occidentales y orientales difieren. El informe no determina un factor horario para Riobamba. No se traduce una anomalía oceánica en porcentaje de lluvia local. Se publica el contexto, URL y hash del PDF consultado.

`enlarge_riobamba_stress.py` utiliza la IDF histórica de referencia ESPOCH T100 de 45,2 mm/h en 1h y 24,2 mm/h en 2h. Multiplicadores ELEGIDOS de sensibilidad, sin soporte como pronóstico climático local: +25 %=56,5; +50 %=67,8; +100 %=90,4 mm/h durante 1h. Para 2h, +50 %=36,3 mm/h, acumulado 72,6 mm. Son tormentas uniformes hipotéticas, sin retorno asignado, y no máximos físicamente posibles ni intervalos estadísticos de confianza.

Se añaden dos comparaciones: 67,8 mm/h en 1h con infiltración nula y sin drenaje, como supuesto límite de pérdidas; 90,4 mm/h en 1h con nueva ejecución de SWMM y sus reboses hacia 2D. Infiltración nula no equivale a una medición de suelo saturado ni describe la humedad antecedente real. Todas las simulaciones arrancan con superficie seca y omiten aportes fluviales exteriores. Se recalcula la física completa; no se multiplican profundidades ni áreas de resultados anteriores.

La red mantiene su geometría inferida, salidas y captación supuestas. La comparación con red no es un límite garantizado de seguridad. No hay validación de campo ni nueva prueba de convergencia espacial para estas lluvias ampliadas.

Para mantener el límite de GitHub Pages, la animación se publica cada 30 minutos y con profundidad gráfica en centímetros enteros redondeados hacia abajo; error de representación menor de 1 cm. Los máximos se calculan en TODOS los pasos del solver, no solo en los fotogramas. Las áreas, profundidades máximas y balances del panel proceden de los resultados sin esta cuantización. Los NPZ originales y los paquetes gráficos anteriores se conservan localmente; las revisiones anteriores también están en Git. No se interpreta la animación como una serie de observaciones de 30 min.

Reproducción: preparar los escenarios base/IDF y ejecutar `python enlarge_riobamba_stress.py` como última fase antes de publicar. El manifiesto incluye unidades gráficas explícitas por caso, metadatos separados `stress` e `idf`, fuente base y factor supuesto.


## Lluvia variable de seis horas y recesión · 14/11/2026

`variable_riobamba.py` genera eventos de diseño ESPOCH T25/T50/T100 de seis horas, con bloques de diez minutos y pico central entre 180 y 190 min. Acumulados: 42,6 / 48,6 / 55,2 mm. Picos durante un bloque de diez minutos: 103,4 / 119,6 / 138,4 mm/h; no son intensidades constantes de una o seis horas. `rain_mm_h` en los informes de estos eventos es la MEDIA; el hietograma completo define la lluvia efectiva.

Fuente: cuadro 72, p.100 del estudio INAMHI histórico ya archivado. Se convierten intensidades a profundidades para cada duración; interpolación log-log de profundidad/duración a múltiplos de 10 min; diferencias sucesivas y bloques alternos descendentes alrededor del centro. Referencia metodológica: https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/meteorology/precipitation/frequency-storm . No se ejecuta HEC-HMS ni se presenta el resultado como su salida. El ordenamiento conserva el volumen total. Las ventanas máximas de la tormenta se comprueban frente a las duraciones de referencia: T25/T50 coinciden a precisión numérica; T100 tiene una diferencia máxima aproximada del 0,11 % en duraciones intermedias por el ordenamiento de incrementos tabulados. Se conserva el diagnóstico, sin modificar la tabla original.

Se aplica la lluvia de estación uniformemente, factor areal 1 sin reducción local verificada: es una hipótesis de cobertura espacial, no un período de retorno demostrado para la lluvia media de todo el dominio. Los METAR de SERB permiten documentar secuencias de reportes, no duración continua exacta ni acumulados horarios fiables. Las fechas de esos reportes no se asignan a los eventos sintéticos.

Tres casos sin drenaje y tres con la red inferida. Se recalculan por separado todas las entradas y reboses. Para la red, cada bloque produce exceso de lluvia según las mismas pérdidas por clase que en la superficie. En las transiciones se utiliza una rampa lineal de un segundo y una normalización por nodo que conserva la integral original de aportación; se publica la magnitud de esa corrección. El exportador transfiere reboses por volumen acumulado, no interpola picos instantáneos sin control. Las celdas captadas no reciben lluvia duplicada en 2D. Se conserva la limitación de intercambio en un solo sentido.

Cada cálculo dura doce horas: seis de lluvia y seis de recesión. Se publican el volumen al terminar la lluvia, el volumen final y la fracción restante respecto al máximo almacenado. No se afirma vaciado completo si permanece agua en depresiones. Los máximos se obtienen en todos los pasos, las series numéricas se guardan cada 30 min y la animación publicada cada 60 min para limitar descarga; la gráfica de lluvia conserva sus bloques de 10 min.

Verificación adicional: volumen de los tres hietogramas, posición y duración del pico, coherencia con IDF y conservación temporal de entradas por nodo. Las pruebas del motor, incluido el ejemplo EPA, permanecen activas. Persiste falta de calibración de campo y de convergencia espacial comprobada para estos eventos.

Reproducción: ejecutar `python variable_riobamba.py --return-years 25`, repetir para 50 y 100, luego `python variable_riobamba.py --pack`. Las ejecuciones de cada retorno usan carpetas independientes; SWMM se ejecuta en procesos separados, nunca en hilos que compartan su estado global. Empaquetar después de los escenarios base y de estrés.

Los INP y reportes SWMM completos de doce horas se conservan comprimidos en `model-archives/` del repositorio, con enlaces directos de descarga desde el visor. El preparador de Pages excluye exclusivamente ese directorio propio del artefacto del sitio para mantener el límite de 1 GB; siguen disponibles en GitHub. Los informes JSON y las animaciones permanecen servidos por Pages.

Diagnósticos del mismo evento variable T25: se calcula además sin infiltración y se repite sin red en la malla de 48 m. La comparación incluye la diferencia de máscara válida al agregar el MDT; es una sensibilidad de dos mallas, no una demostración de convergencia. Se publica `variable-grid-sensitivity.json`. Para reproducir esos diagnósticos: `python variable_riobamba.py --diagnostics` antes de empaquetar.

La fracción remanente se refiere al volumen máximo de la serie guardada cada 30 min; se identifica esa frecuencia en el informe. Los máximos de profundidad y huella siguen acumulados en todos los pasos internos.


## Promedio de estaciones y preparación ante El Niño · 15/11/2026

`combined_riobamba.py` lee las tablas 27 (Aeropuerto M0057, página impresa 55) y 72 (ESPOCH M1036, página impresa 100) del PDF INAMHI local preservado. Para cada duración y nivel T de origen calcula `(ESPOCH + Aeropuerto)/2`, con pesos iguales solicitados por el usuario. Conserva valores originales, páginas y SHA-256 en `combined-station-idf.json`. No combina retornos diferentes, no promedia mapas de inundación y no atribuye al promedio un período de retorno: el promedio de cuantiles puntuales no es un cuantil areal ni una probabilidad conjunta.

A seis horas las referencias combinadas suman 36,9 / 41,7 / 46,8 mm; medias 6,15 / 6,95 / 7,8 mm/h. Para la referencia mayor, una hora suma 37,5 mm y dos horas suman 41,2 mm. Se reconstruyen bloques alternos de diez minutos desde profundidades interpoladas log-log, manteniendo el volumen y comprobando ventanas de duración. No se presenta la distribución temporal como una observación.

El boletín ERFEN 012-2026 del 5 de noviembre, comprobado el 15, mantiene El Niño ACTIVO y para noviembre informa precipitación mensual normal en el callejón interandino. No prescribe un multiplicador de lluvia horaria en Riobamba. Por ello las pruebas severas se identifican como hipótesis elegidas, no pronósticos, máximos físicos ni nuevos retornos: (a) doble lluvia de la referencia combinada mayor de una hora: 75 mm en 1 h; (b) doble referencia mayor de seis horas: 93,6 mm en 6 h; (c) repetición de dos perfiles de 46,8 mm: 93,6 mm en 12 h. En (c) los perfiles se siguen inmediatamente, sin pausa seca; no se reinicia el agua superficial ni el estado hidráulico de la red. La absorción del suelo permanece constante: no se calcula humedad antecedente. El cambio de duración se conserva explícito; no se equipara 93,6 mm/6 h con 93,6 mm/12 h.

Cada prueba severa y la referencia combinada mayor se recalculan sin drenaje, con la red inferida y con infiltración nula sin red. Las referencias menores son comparaciones de lluvia sin red. Infiltración nula es un límite hipotético, no humedad medida ni simulación de saturación antecedente. La condición inicial superficial continúa seca; la repetición conserva el estado al iniciar la segunda tormenta. Después de una tormenta de una hora se calcula una hora adicional; tras eventos de seis o doce horas, seis horas adicionales. Se conserva el volumen de aportes a SWMM y de reboses transferidos; no se duplica la lluvia capturada. Error de continuidad de red requerido: valor absoluto <1 %. Los controles de conservación no prueban exactitud frente a eventos observados.

El empaquetado de la tormenta corta conserva salidas cada diez minutos; los demás escenarios se muestran cada hora, preservando máximos por celda del cálculo completo. Las métricas usan resultados originales, mientras las profundidades gráficas se cuantizan hacia abajo en centímetros. Se calcula sensibilidad 24/48 m solo para la referencia mayor combinada de seis horas; no se afirma convergencia espacial ni validación de las demás pruebas. Los escenarios anteriores y sus fuentes se conservan, pero el visor principal deja de mezclar referencias por estación con la nueva base combinada.

Reproducir: `python -m unittest test_combined_rain test_variable_rain test_local_flood_solver test_hydraulics test_compound test_swmm`, después `python run_combined_batch.py`. Máximo dos procesos locales en carpetas independientes, sin aprendizaje automático ni QGIS. Todo escenario falla antes de publicar si no cumple conservación, continuidad o integridad del empaquetado.


Ejecución actual: se adelantaron el cálculo de la red y el caso sin absorción para las dos tormentas de doce horas en dos procesos adicionales (máximo cuatro simultáneos), tras comprobar CPU y memoria disponibles. El lote rutinario sigue limitado a dos procesos. Los CLI usan un bloqueo exclusivo por escenario: si el lote alcanza un cálculo ya activo, espera a que el propietario libere el archivo y reutiliza el resultado terminado. El PID es informativo: su visibilidad puede diferir entre entornos aislados de comandos. No se elimina un bloqueo por una consulta de PID externa. La espera está limitada a una hora; un bloqueo sin liberar exige inspección. Un primer intento de detectar procesos por PID produjo falsos avisos de propietario detenido entre entornos; se corrigió sin interrumpir los cálculos activos ni reemplazar sus resultados. El lote se reanudó con comprobaciones de archivos y control de integridad.


Publicación: por el límite de 1 GB sin comprimir de GitHub Pages, `tools/prepare_pages_site.py` conserva en el sitio los escenarios activos y sirve los 48 archivos históricos de escenarios mediante GitHub raw. No borra archivos del repositorio ni del historial. El índice `previous-scenarios-20261114.json` conserva parámetros y nombres originales, añadiendo `asset_urls` para descargar cada archivo anterior. Grid, relieve, geometría de red, contexto y fuentes siguen en Pages. La comprobación de tamaño parte de los 999.156.034 bytes de la publicación anterior y aplica tamaños exactos de blobs nuevos y archivos históricos excluidos; el tamaño previsto de esta entrega queda por debajo de 1.000.000.000 bytes. El control completo vuelve a ejecutarse en GitHub Actions sobre el checkout íntegro; la copia local es dispersa y no contiene otros proyectos del geoportal.


## Intensidades constantes y duración cada 15 minutos · 15/11/2026

Solicitud posterior expresa: conservar 7,8 / 15,6 / 75 mm/h constantes y permitir duraciones de 15 a 720 minutos, en intervalos de 15. Estos valores eran medias de tormentas variables anteriores: se convierten deliberadamente en nuevas pruebas de intensidad constante, no en IDF oficiales válidas para toda duración ni en pronósticos de El Niño. 75 mm/h durante 12 h acumula 900 mm, sin probabilidad ni máximo físico asignado.

`uniform_riobamba.py` ejecuta nueve trayectorias independientes de 12 horas: tres intensidades por tres condiciones (sin red, red estimada, infiltración cero sin red). Cada selección es un prefijo causal de la misma lluvia constante, hasta el final del tiempo elegido. No se muestra recesión posterior a que pare. Un final más temprano no modifica el agua que ya se calculó durante la lluvia anterior a ese corte. No se escala un mapa, no se extrapolan profundidades y no se usan máximos de horas futuras.

El motor guarda cada quince minutos la profundidad instantánea, el máximo por celda calculado con todos los pasos anteriores y el balance acumulado hasta ese instante. La opción de mayor alcance toma el máximo acumulado del corte elegido; el control de reproducción termina y vuelve a cero en ese corte. Se verificó en dominio inclinado con máscara, infiltración y aportes externos que los prefijos coinciden con simulaciones independientes más cortas. Registrar prefijos no cambia la solución hidráulica.

La red usa aportes constantes desde el inicio hasta las doce horas completas, sin rampa final ni normalización dependiente de la duración. El mismo aporte sirve para todo prefijo. Se controla continuidad de SWMM para las doce horas completas (no se declara ese error como una continuidad medida por separado en cada corte), y se comprueba que cada prefijo de reboses y de lluvia superficial conserva su volumen transferido. La red y la captación continúan inferidas, sin intercambio bidireccional ni calibración de campo.

Hay 48 tiempos por intensidad y condición: 432 selecciones servidas por nueve cálculos completos. La descarga gráfica contiene 49 estados instantáneos y 49 máximos acumulados, ambos en centímetros hacia abajo; las métricas provienen de valores originales. Se sirven los nueve binarios activos desde Pages mediante diferencias temporales y residuos de máximos, con compresión sin pérdida adicional: 3.217.641 bytes en total. La decodificación JavaScript se compara exactamente con los 98 fotogramas originales de cada caso; los paquetes originales se conservan en GitHub. No se eliminan modelos del repositorio. Los anteriores se incorporan al índice histórico con enlaces directos. El informe descargable contiene el cálculo completo y todos los balances por corte; el visor identifica el tiempo seleccionado.

Reproducir: `python -m unittest test_uniform_prefixes test_combined_rain test_variable_rain test_local_flood_solver test_hydraulics test_compound test_swmm`; `python uniform_riobamba.py --batch`; `python verify_uniform_delivery.py`. Máximo cuatro procesos locales, nombres y logs independientes. No reiniciar simultáneamente un lote con carpetas incompletas sin inspección. Los resultados permanecen exploratorios, sin prueba nueva de convergencia específica para estos eventos constantes.
