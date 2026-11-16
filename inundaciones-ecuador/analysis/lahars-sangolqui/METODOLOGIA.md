# Lahares en Sangolquí: cálculo exploratorio y edificios 3D

El visor representa un **modelo de capa somera de mezcla agua–sedimentos calculado con Kestrel**, sobre terreno real. Se visualiza en 3D mediante Cesium y Google Satellite. No es un modelo volumétrico 3D, un pronóstico de erupción, un mapa oficial de amenaza ni una evaluación de daños estructurales. **No está calibrado para Sangolquí.**

## Escenarios y punto de entrada

Se comparan entradas hipotéticas de **10, 30 y 60 millones de m³ de mezcla**, con fracción volumétrica inicial de sólidos de 0,4. Cada liberación tiene hidrograma triangular, pico a 150 s y fin a 900 s. El caudal pico es `2 × volumen / 900`. La simulación continúa hasta 9.000 s, con salidas cada 180 s.

Estos volúmenes y su concentración son **supuestos de comparación**, no una estimación validada de la próxima erupción ni una reproducción de 1877. No se asignan probabilidades ni periodos de retorno. Tampoco se confunden con los 34,8 millones de m³ de **agua** que el estudio de 2025 distribuye entre nueve fuentes sobre el glaciar.

El punto geográfico de referencia proviene de la tabla 1, punto 4, del [estudio de muestreo del río Pita de 2019](https://doi.org/10.26807/ia.v7i2.104): aporte de la quebrada Chorro al Pita, 78°25′57,86″ O; 0°29′9,73″ S. Solo se reutiliza su ubicación del cauce, **no datos de caudales de lahares**. Para la entrada numérica se eligió la menor cota del DEM dentro de 120 m; el desplazamiento fue de unos 27 m. El radio de la fuente numérica es 100 m. La mezcla se libera en ese punto aguas arriba de la ciudad; no se modela el deshielo ni la generación de lahar en el glaciar, ni se impone una trayectoria dibujada hacia Sangolquí.

El tiempo del visor comienza en la entrada de mezcla al Pita, **no en el inicio de una erupción**. No sirve como tiempo de evacuación.

## Motor y parámetros

Se utilizó [Kestrel](https://github.com/jakelangham/kestrel), University of Bristol, versión v1.2.1, commit `e0965b438b763d94f0236ca31911bb43e6b82f49`. Resuelve conservación y cantidad de movimiento de una mezcla, con fricción y cambios del lecho por erosión y depósito. Se compiló localmente con GCC/GFortran, GDAL, PROJ, NetCDF y OpenMP mediante MSYS2. El parche de Windows solo adapta dos conversiones de rutas de archivos en C++; no modifica ecuaciones ni esquema numérico. Se conserva su GPL-3.0 y se enlaza el código original.

Las leyes y valores de referencia se revisaron en la [documentación oficial](https://kestrel-unibristol.readthedocs.io/en/latest/) y el [estudio de resolución del Cotopaxi](https://doi.org/10.3389/feart.2025.1611579). Reutilizar valores de ese estudio **no equivale a calibrar este modelo**.

| Parámetro | Valor utilizado |
|---|---:|
| Fricción | Variable entre Chézy y granular |
| Chézy, coeficiente adimensional | 0,01 |
| Pouliquen mínimo / máximo / beta | 0,1 / 0,35 / 0,136 |
| Cambio de régimen: concentración / tasa | 0,4 / 3 |
| Erosión | Mixta |
| Tasa de erosión fluida / granular | 0,0001 / 0,1 |
| Profundidad erosionable máxima | 10 m |
| Espesor mínimo para erosión | 0,01 m |
| Porosidad / empaquetamiento máximo | 0,35 / 0,65 |
| Depósito | Spearman–Manning |
| Densidad de agua / sólido | 1.000 / 2.000 kg/m³ |
| Diámetro de sólido | 1,5 mm |
| Viscosidad turbulenta | 0,01 |
| CFL | 0,25 |
| Condición de borde | Detener si el flujo alcanza el límite |

La geometría, el tamaño de grano representativo y la reología no caracterizan rocas individuales, puentes, taponamientos ni derrumbes discretos.

## Terreno y resolución

El terreno completo deriva del [HGT público S01W079, Mapzen/Skadi](https://s3.amazonaws.com/elevation-tiles-prod/skadi/S01/S01W079.hgt.gz), con una muestra por segundo de arco, aproximadamente 30 m. Se reproyectó a EPSG:32717. El dominio ampliado al norte es de 24,6 × 55,5 km. La malla de publicación es 30 m. La cobertura se verifica sin sustituir huecos por alturas cero. La rejilla del visor se reproyecta para mostrar el terreno; no alimenta el solver. El relieve radar puede incluir vegetación y construcciones; no equivale a un levantamiento LiDAR del suelo desnudo. Falta verificar época y compatibilidad del datum vertical para usos de ingeniería.

**Los cauces estrechos y La Caldera pueden estar mal representados a esta resolución.** No se puede interpretar cada edificio o parcela como afectado/no afectado a partir de esta malla. Remuestrear a píxeles menores no agregaría topografía real. Se requiere terreno fino del corredor, inspección de cauces y contraste con evidencias para mejorar el cálculo.

También se localizó un ImageServer municipal del centro histórico con píxel de origen de 0,5 m, datum vertical declarado EGM96. Se descargó una copia F32 a unos 5 m y se verificaron cotas numéricas; tiene cobertura parcial y huecos. **No se incorporó a la hidráulica de esta entrega**, pues no cubre el corredor y su integración requiere controlar compatibilidad altimétrica. El MDT cantonal de 5 m anunciado en el catálogo mantiene una descarga pendiente.

## Construcciones

Se descargaron 20.463 huellas de bloques constructivos del [servicio público municipal](https://geoide.ruminahui.gob.ec/server/rest/services/BDD_CATASTRO/catastro/MapServer/1), consultando únicamente geometría, identificador técnico y número de pisos. El visor descarta ese identificador y publica solo huellas, pisos, altura estimada y cota de apoyo. No contiene claves catastrales, propietarios, valores ni domicilios personales.

Se estima la altura como **3 m por piso**. Cuando no hay pisos válidos se asume un piso y se marca esa limitación. No son alturas medidas. Se simplifica la geometría para visualización conservando su topología; geometrías vacías/no válidas o fuera del dominio se omiten y el manifiesto informa el número efectivamente incluido.

Los edificios se dibujan en Cesium como extrusiones del catastro, **no con Cesium OSM Buildings**. Actúan como referencia visual y no como obstáculos dentro del cálculo. No se estima resistencia, colapso, daño, población expuesta ni seguridad de rutas.

## Resultados y representación

Solo se empaquetan corridas terminadas en 9.000 s con los 51 fotogramas. Los NetCDF originales quedan en el proyecto local. Los informes públicos contienen los parámetros, métricas por fotograma, controles y hashes de esos originales. La descarga gráfica conserva profundidades, velocidades, concentración y altura de superficie por celda; no se obtiene interpolando mapas municipales.

El espesor se toma de `flow_depth` [m], la velocidad de `flow_speed` [m/s] y la concentración de `solids_fraction`. La descarga conserva el desplazamiento de superficie calculado como cambio del lecho más `H / sqrt(1 + bx² + by²)`, coherente con los factores geométricos del modelo. No se utilizan los vértices internos de reinicio como si fueran coordenadas geográficas.

El relieve visible permanece fijo. Para evitar ocultar debajo de ese relieve un cauce erosionado durante el cálculo, el visor dibuja el espesor vertical `H / sqrt(1 + bx² + by²)` sobre su terreno de referencia. Es una representación visual del espesor, **no la cota absoluta de la superficie del modelo**. Los máximos se muestran como una cobertura sobre el terreno. Las cotas modeladas y los cambios de lecho siguen conservados en las descargas; no se debe medir una cota hidráulica sobre la imagen 3D.

La profundidad y velocidad gráficas se cuantizan hacia abajo a centésimas de sus unidades; concentración a 0,0001 y alturas al centímetro más próximo. Las métricas proceden de los números originales. La compresión por diferencias temporales es reversible y su decodificación se comprueba. La envolvente combina el archivo agregado de Kestrel con todos sus estados exportados: en la primera corrida se detectaron diferencias finales de hasta 0,0171 m de espesor y 0,074 m/s entre ambos; sus magnitudes y celdas se registran en el informe. No se ocultan descartando la comprobación. Los instantes de primera humectación proceden del archivo agregado; los ausentes se conservan desconocidos y no equivalen a llegada de un frente de 5 cm. «Todo el recorrido» muestra un alcance acumulado, no una superficie simultánea.

Las métricas urbanas corresponden a un rectángulo de comparación Sangolquí–San Rafael (`[-78,49; -0,375; -78,395; -0,285]`), **no a un límite administrativo ni a todo el cantón**. El máximo en el dominio puede ser mucho mayor cerca de la entrada; no se presenta como profundidad de la ciudad.

## Comprobaciones y límites de validación

- Prueba independiente sobre dominio plano: liberación triangular de 1.000 m³, 40 % de sólidos, sin erosión ni salida; se verifica volumen, masa de sólidos y masa de mezcla contra sus integrales de entrada.
- Balance de volumen de mezcla y cambio del lecho en cada corte de los escenarios, contra la integral del hidrograma. El empaquetador rechaza discrepancias superiores al 0,1 % del volumen de entrada.
- Verificación de terminación, tiempos, CRS, no negatividad del espesor, fracción de sólidos y consistencia entre máximos de todos los pasos y fotogramas.
- Comparación exacta de los enteros gráficos antes y después de comprimir; el decodificador real del navegador tiene controles de orden, valores con signo y descargas truncadas.

Estas pruebas comprueban el cálculo y la entrega; **no prueban precisión predictiva en Sangolquí**. Falta contraste local con espesores, velocidades, tiempos y depósitos observados de escenarios definidos.

El municipio publica mapas de espesor máximo, velocidad máxima y llegada en su [visor de lahares](https://geoide.ruminahui.gob.ec/visor_lahar/). Sus metadatos consultados no detallan unidades ni escenario; se enlazan como referencia externa y no se presentan como una validación cuantitativa del cálculo nuevo. Los anexos del estudio científico incluyen perfiles de cauces, pero no se han tratado como un MDT georreferenciado completo.

## Reproducir

Los scripts usan el Python GeoAI existente y dependencias locales del proyecto (`numpy`, `rasterio`, `pyproj`, `shapely`, `scipy`, `netCDF4`, `cftime`). En la copia de GitHub, los scripts están en `analysis/lahars-sangolqui`; debe conservarse la estructura indicada en cada script o ajustar el directorio de salida al regenerar un sitio separado.

1. `acquire_public_inputs.py`: descarga pública y auditoría de hashes; edificios sin atributos personales.
2. `prepare_inputs.py`: contexto de terreno y referencias del estudio, sin ejecutar un lahar.
3. Compilar el commit de Kestrel indicado, con la adaptación de Windows si corresponde. Conservar el binario y bibliotecas en `tools/`; la instalación de compiladores no se publica como parte del sitio.
4. `run_kestrel.py --setup`, seguido por `--run menor-30m`, `--run grande-30m`, `--run mayor-30m`. La variable `LAHAR_THREADS` permite de 1 a 4 hilos.
5. Ejecutar `--run benchmark` y después `pack_viewer.py`; este último verifica terminación y balances antes de crear las descargas del visor.
6. `node verify_decoder.cjs` y comprobación de la interfaz publicada. No usar los paquetes gráficos cuantizados para reiniciar una simulación.

El cálculo preliminar de 60 m iniciado antes de ampliar el dominio es una prueba interna: no se presenta como comparación controlada de resolución con las corridas ampliadas de 30 m.
