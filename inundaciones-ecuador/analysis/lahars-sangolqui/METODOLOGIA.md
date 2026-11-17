# Lahares del Cotopaxi hacia Sangolquí: adaptación de un escenario publicado

Esta entrega calcula un flujo de agua y sedimentos con Kestrel y lo representa en Cesium. **Es una adaptación exploratoria, no una reproducción exacta del estudio, una predicción de erupción o un modelo validado para decidir evacuaciones.** Las limitaciones del terreno y de las ubicaciones de las fuentes permanecen explícitas. Las pruebas anteriores de inyección de 10, 30 y 60 millones de m³ en el Pita no son los escenarios de erupción de esta entrega; se conservan en el historial del proyecto.

## Referencia principal y entradas

Se toman los hidrogramas y parámetros físicos de [Vasconez, Phillips, Andrade y Woodhouse (2025)](https://doi.org/10.3389/feart.2025.1611579), tablas 1 y 2. El método de generación de las fuentes se describe en [Vasconez et al. (2024), sección 4.1](https://doi.org/10.3389/feart.2024.1426088). Se modela un escenario tipo 1877 con las condiciones del glaciar utilizadas por esos autores, basadas en imágenes de 2020–2022; no se midió de nuevo el glaciar de 2026.

| Fuente norte | Caudal máximo de agua (m³/s) | Agua liberada (m³) |
|---|---:|---:|
| 12 | 2.019 | 908.550 |
| 13 | 577 | 259.650 |
| 14 | 6.058 | 2.726.100 |
| 15 | 3.750 | 1.687.500 |
| 16 | 12.981 | 5.841.450 |
| 17 | 3.462 | 1.557.900 |
| 18 | 16.154 | 7.269.300 |
| 19 | 16.154 | 7.269.300 |
| 20 | 16.154 | 7.269.300 |

Los nueve aportes empiezan simultáneamente. Cada hidrograma es triangular, con máximo a los 150 s y final a los 900 s. Su integral es `Qmáx × 900 / 2`. La suma de los caudales individuales publicados, redondeados a enteros, es 77.309 m³/s y la integral 34.789.050 m³, aproximadamente 34,8 millones de m³. El total de la tabla del artículo figura como 77.308 m³/s; se registra esa diferencia de redondeo y no se redistribuye artificialmente.

**Es volumen de agua de entrada, no volumen de mezcla que llega a Sangolquí.** La concentración inicial de sólidos es cero; la mezcla evoluciona por erosión y depósito. No se impone la trayectoria hacia una calle ni la llegada a los 52 minutos.

## Ubicación de las fuentes y recorrido

Las nueve ubicaciones se digitalizaron de la figura 1B original, de 1.644 × 1.237 píxeles. Se usaron los controles de su rejilla UTM: 780.000 E en x=720, 790.000 E en x=1.394, 9.930.000 N en y=275 y 9.920.000 N en y=948. Se interpretó como UTM 17 Sur, WGS84. El manifiesto conserva las coordenadas de píxel y de terreno y el hash de la figura. La separación entre fuentes se verificó en torno a los 500 m descritos por los autores. No se movieron hacia el cauce más bajo.

Estas **no son las coordenadas GIS originales** de los autores. La tolerancia de digitalización de 80 m es una hipótesis conservadora de trabajo, no una exactitud de campo validada. El radio de cada fuente es de 100 m, conforme al diámetro de 200 m del estudio. El dominio proyectado es EPSG:32717, de 60 × 96 km, `[769800, 9900000, 829800, 9996000]`, y contiene el flanco norte, Salto, Pita, el corredor de Santa Clara y el valle, con margen lateral para trayectorias alternativas. El ráster de entrada incluye una franja de elevaciones reales de 1.200 m fuera de cada borde para la interpolación y celdas auxiliares del motor. Una primera corrida con dominio oriental más estrecho se interrumpió por falta de ese margen y no se aceptó para publicación; la corrida corregida comienza de nuevo desde cero. Agrupar las celdas en bloques de 600 m mejora el cálculo sin cambiar su resolución física de 30 m. La condición exterior detiene la corrida si el flujo alcanza el límite; no se oculta una salida fuera del dominio.

## Terreno: diferencia crucial frente al estudio

Se descargó el [Copernicus DEM GLO-30 público](https://registry.opendata.aws/copernicus-dem/), tesela S01W079, y se reproyectó a una rejilla de 30 m con interpolación bilineal. Se comprobó cobertura numérica completa, incluyendo el VRT interno generado por Kestrel y sus márgenes. La preparación del ráster usa interpolación bilineal y el VRT interno aplica la interpolación cúbica nativa de esta versión del motor; las alturas efectivas permanecen en `base_elevation` de cada NetCDF. Es un **modelo global de superficie**, que puede incluir vegetación y construcciones, no un MDT fino de suelo desnudo. No se sustituyeron huecos por altura cero.

El estudio empleó un MDT fotogramétrico local de 3 m remuestreado, y recomienda 10 m para trabajos futuros. Su sección 6.4 demuestra que un SRTM de 30 m puede detener artificialmente los lahares antes de zonas residenciales. Copernicus tampoco garantiza representar los cañones estrechos o las divisorias de La Caldera. **Cambiar de producto global no resuelve esa limitación ni reproduce el terreno original.**

También se adquirió un terreno numérico oficial del IGM a partir de cartografía 1:50.000, con píxel de 30 m. Un relleno automático completo de sus depresiones habría levantado puntos más de 200 m; no se usó ese terreno alterado en la corrida. El MDT parcial municipal del centro histórico no cubre el recorrido completo y no se integró mezclando referencias altimétricas sin control. La descarga del MDT de SIGTIERRAS conduce a un portal con cuenta de usuario; disponer de su ficha pública no equivale a disponer de sus elevaciones originales.

En Copernicus se aplicó un relleno de mínima cota de salida con ocho vecinos **solo donde la elevación necesaria no superaba 2 m**. Las depresiones más profundas se conservaron; podrían representar relieve real, incluido el cráter. No se levantó un cañón para forzar la llegada del flujo. Este límite de 2 m es una hipótesis explícita de acondicionamiento y difiere del procesamiento del artículo. El manifiesto informa superficie modificada, volumen geométrico de modificación, máxima elevación y número de celdas profundas conservadas. No se realizó todavía un conjunto de corridas para validar la sensibilidad a ese umbral.

Atribución del terreno: Copernicus DEM, producto GLO-30; DLR/Airbus, suministrado bajo COPERNICUS por la Unión Europea y ESA. [Información y licencia del producto](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).

## Motor y parámetros físicos

Se usa el código oficial [Kestrel](https://github.com/jakelangham/kestrel), versión 1.2.1, commit `e0965b438b763d94f0236ca31911bb43e6b82f49`, con licencia GPL-3.0. En Windows se adaptaron dos conversiones de rutas en `RasterData.cpp`, sin cambiar las ecuaciones. La compilación de cálculo usa O3 y LTO, sin fast-math; su hash está en el manifiesto. La prueba independiente de conservación se ejecutó con este binario.

El modelo resuelve ecuaciones de capa somera para agua y sedimentos, incluyendo cambios del lecho. **La representación en 3D no convierte el cálculo en un CFD volumétrico 3D.**

| Parámetro | Valor |
|---|---:|
| Fricción | Variable, Chézy/Pouliquen |
| Coeficiente de Chézy | 0,01 |
| Pouliquen mínimo / máximo | 0,1 / 0,35 |
| Beta de Pouliquen | 0,136 |
| Cambio de fricción: concentración / tasa | 0,4 / 3 |
| Erosión fluida / granular | 0,0001 / 0,1 |
| Profundidad erosionable máxima | 10 m |
| Espesor mínimo para erosión | 0,01 m |
| Porosidad / empaquetamiento máximo | 0,35 / 0,65 |
| Depósito | Spearman–Manning |
| Densidad de agua / sólido | 1.000 / 2.000 kg/m³ |
| Diámetro de sólido | 1,5 mm |
| Viscosidad turbulenta | 0,01 |
| CFL | 0,25 |
| Duración / salida nativa | 9.000 s / cada 15 s |

Los parámetros de la tabla 2 del artículo se conservan; otros ajustes del motor se especifican en el archivo de entrada. No equivalen a una calibración local nueva ni resuelven rocas individuales, taponamientos o fallas de puentes.

## Qué se mide en Sangolquí y San Rafael

Las métricas de área, espesor y velocidad se calculan dentro del rectángulo geográfico `[-78,49; -0,375; -78,395; -0,285]`. **No es un límite administrativo ni coincide con todos los puntos de control de los estudios.** La primera presencia de al menos 5 cm se informa como un intervalo entre dos salidas nativas de 15 s. Que una corrida no alcance ese rectángulo no demuestra seguridad del lugar.

Se añadió una sección de comparación a norte UTM 9.958.500 m, al sur del rectángulo, abarcando los corredores de Pita y Santa Clara. Para cada estado se estima el transporte por unidad de ancho como `H × gamma × v_norte`, donde `gamma = sqrt(1 + bx² + by²)`, consistente con la forma del flujo convectivo de Kestrel. Se interpolan los flujos de las dos filas de celdas adyacentes y se integran en el ancho de la sección. La integral temporal se obtiene por trapecios cada 15 s.

**Es una estimación desde resultados de centros de celda, no el flujo conservativo de caras interno del solver.** Se entregan caudal, transporte positivo, inverso y neto, así como fases de agua y sólidos. El transporte positivo puede contar material que cruza más de una vez. La diferencia al usar salidas cada 30 s examina el muestreo temporal; no acota el error espacial, del terreno o predictivo. Esa integral no equivale a todo el material que entra en la ciudad ni al volumen depositado en las calles.

La velocidad máxima dentro del rectángulo procede de `flow_speed`, en m/s; el visor la muestra en km/h. No se impone una velocidad uniforme ni se divide una distancia aproximada por un tiempo publicado para asignar velocidades a toda la ciudad.

## Comparación con otros estudios

[Frimberger et al. (2021), tabla 2](https://doi.org/10.1002/esp.5056), utilizaron RAMMS, un MDT fotogramétrico diferente y fuentes, erosión y fricción propias. Sus escenarios norte de VEI 2–3, 3–4 y >4 tienen volúmenes iniciales de 7,8; 18,9 y 46 millones de m³, y totales con erosión de 19,4; 34,6 y 70,7 millones de m³. Reportan viajes a San Rafael por Pita de 84, 71 y 60 minutos, y a Sangolquí por Santa Clara de 52 minutos en el escenario mayor.

**Esos números no son entradas ni resultados impuestos a esta adaptación de Kestrel.** El total de un drenaje no se convierte en volumen que atraviesa el centro de Sangolquí. El origen temporal y la ubicación de comparación deben coincidir antes de evaluar una diferencia de llegada. Las velocidades iniciales de RAMMS tampoco equivalen a velocidades locales de llegada. La revisión y tabla de comparación se conservan en `REVISION_ESTUDIOS.md`.

Los servicios municipales publican mapas de espesor, velocidad y llegada en su [visor de lahares](https://geoide.ruminahui.gob.ec/visor_lahar/). Los metadatos consultados no documentan suficientemente escenario y unidades para una comparación cuantitativa automática. Se enlazan como referencia externa: no se colorearon ni interpolaron para simular un movimiento nuevo.

## Comprobaciones de cálculo y entrega

- Prueba plana independiente de 1.000 m³, 40 % de sólidos y sin erosión: volumen y masas se comparan con las integrales conocidas de entrada.
- Pruebas analíticas de integración de los nueve hidrogramas y de unidades, partición por fases y flujo inverso en una sección uniforme.
- Balance del volumen de mezcla y cambio del lecho frente al aporte de agua en todos los cortes; se rechazan diferencias superiores al 0,1 % del aporte.
- Verificación de 601 estados, tiempos, CRS, espesores no negativos, valores finitos y fracción de sólidos.
- El visor exporta cada duodécimo estado nativo: 51 fotogramas cada tres minutos. La llegada y el caudal se calculan con los 601 estados, no con la frecuencia de animación.
- La envolvente combina una copia del agregado de máximos del motor con los 601 estados nativos: las diferencias por orden de actualización se registran, no se ocultan descartando una comprobación.
- Verificación independiente de georreferenciación y de los cinco campos cuantizados de todos los fotogramas. Compresión temporal reversible y hashes de archivos originales.

Estos controles comprueban el cálculo numérico y su transporte al navegador. **No certifican exactitud predictiva en Sangolquí.** La validación sigue pendiente de terreno fino, fuentes GIS originales y contraste en puntos equivalentes con evidencia de campo y resultados de los autores.

## Representación 3D y construcciones

La rejilla del relieve visible se reproyecta y reduce a 1.850 × 820 muestras para el navegador; no es la malla física de 30 m. El relieve visible permanece fijo; se representa el espesor vertical sobre ese terreno para no ocultarlo bajo el lecho erosionado. La cota absoluta modelada permanece en los datos, pero no se debe medir una cota hidráulica sobre la imagen. La envolvente de todo el recorrido reúne instantes diferentes, no una superficie simultánea.

El cambio de construcciones quedó aplazado por indicación del usuario hasta terminar la simulación. Se mantiene la referencia municipal anterior, con alturas estimadas de 3 m por piso, mientras se prepara Cesium como fuente principal y catastro como complemento. No se usan edificios como barreras dentro del solver ni se estiman daños estructurales.

## Reproducir y auditar

Usar el Python existente de GeoAI y las dependencias del proyecto, sin QGIS. No hay entrenamiento de IA: la propagación se calcula mediante ecuaciones físicas.

1. `acquire_public_inputs.py` conserva las fuentes de contexto y edificios sin atributos personales. `acquire_study_inputs.py` recupera la figura y terreno exactos por sus hashes.
2. Compilar el commit indicado de Kestrel, guardar su licencia y adaptación de rutas y verificar la prueba plana. No instalar compiladores globales.
3. `study_reference.py --setup` prepara un directorio independiente `study2025-cop30-v2`, sin sobrescribir las corridas antiguas.
4. `study_reference.py --run` ejecuta la corrida. Los reinicios autorizados por rendimiento usan estados nativos completos, parámetros físicos idénticos y una historia de ejecución explícita; no se reinicia desde archivos gráficos cuantizados.
5. `analyze_study.py` rechaza una corrida incompleta y genera informe y CSV de sección.
6. `pack_study.py` prepara las descargas y ejecuta la verificación independiente contra NetCDF. `node verify_decoder.cjs` comprueba el decodificador real del navegador.
7. Verificar la interfaz y el despliegue de GitHub Pages. Conservar los NetCDF originales localmente y sus hashes en el informe público.

Los paquetes binarios grandes se conservan completos en el mismo repositorio público y se descargan desde GitHub Raw con nombres que contienen su hash. El navegador comprueba SHA-256 antes de descomprimir. GitHub Pages aloja la interfaz, informes y metadatos; excluye estos paquetes de su compilación para respetar su límite de tamaño. La vista local lee los mismos archivos desde el proyecto. Esta separación no reduce la resolución ni los campos exportados.

## Revisión adicional del MDT municipal y recuperación

`audit_municipal_terrain.py` consulta y conserva respuestas públicas Identify/MultiPoint: 14.893 coordenadas, 9.127 cotas válidas. `render_terrain_audit.py` compara cinco perfiles; no modifica el terreno físico. El RMSE de 10,30 m es una diferencia entre productos, no precisión medida en campo. La referencia vertical y resolución nativa del servicio rural no se confirmaron. No se fusionaron productos ni se aplicó un desplazamiento vertical supuesto.

La ejecución se interrumpió durante la sesión del equipo después de guardar el estado 245 (3.675 s). `resume_study.py` verifica hashes, conserva RunInfo, Volume y Maximums anteriores y usa el reinicio oficial de Kestrel, con parámetros físicos idénticos. Los registros de recuperación se incorporan al historial. El análisis final debe comprobar continuidad del balance y los 601 estados antes de publicar.

## Ubicación de los máximos y secciones de estudios

El informe físico conserva la posición y el instante de los máximos muestreados dentro del rectángulo de comparación; incluye cañones y no representa una profundidad uniforme de la ciudad. El espesor de Kestrel es normal a la pendiente; se informa además su componente vertical en la celda del máximo. Los extremos muestreados cada15s no garantizan capturar un pico entre muestras.

Se consultan las secciones con coordenadas de las tablas3.5 y3.7 de Torres y Vásquez (EPN2017), muestreando centros de celdas cercanas a sus líneas y eliminando duplicados. Las velocidades máximas de la tabla4.2 de FLOW-3D se presentan solo como contexto: no son necesariamente la misma magnitud que la velocidad promediada en profundidad y alineada con la pendiente de Kestrel. Entradas y relojes diferentes impiden convertir esa comparación en una calibración directa. La reconstrucción temporal del visor de estudios se conserva separada en `METODOLOGIA_TIEMPOS.md`.
