# Ecuador · Agua y territorio

Visor de terreno 2D/3D, susceptibilidad exploratoria y simulaciones hidráulicas de lluvia para 38 localidades seleccionadas de Ecuador. Desarrollo: 11 de noviembre de 2026.

## Qué está calculado

- Terreno real de Mapzen / Terrain Tiles a zoom 11 (~76 m) en 38 ventanas de 128 × 128 celdas, con margen de cálculo de 32 celdas.
- Drenaje derivado por priority-flood y D8, acumulación contribuyente y altura relativa al drenaje (HAND). La máscara de cotas positivas no es una delimitación oficial de mar/tierra.
- Dos simulaciones por localidad: lluvia uniforme **hipotética** de 50 y 100 mm/h durante 2 horas; seguimiento total 4 horas. Son 76 ejecuciones precomputadas, con 17 estados cada 15 minutos.
- Modelo hidráulico 2D de aproximación inercial local, fricción Manning, continuidad conservativa y flujos entre celdas. Su resultado se representa en 3D; no es un solver de fluidos tridimensional.
- Inventario de 16 fuentes/componentes para completar un modelo local: INAMHI, INOCAR, IGM, SNGR, JRC, HydroSHEDS, Copernicus, NASA, FONAG y datos municipales.
- Consultas puntuales del servicio institucional de susceptibilidad de SNGR, con estados y atributos originales. `NO APLICABLE`, ausencia de coincidencia o error no equivalen a amenaza baja.

## Límites de uso

**Sin calibración ni validación con inundaciones reales. No es pronóstico, alerta oficial, cartografía de evacuación ni estudio de diseño.** La conservación numérica de volumen no demuestra exactitud territorial.

El terreno de simulación es un promedio 2 × 2 de las celdas originales (~153 m). No resuelve calles, bordillos, colectores, alcantarillas, edificios individuales o defensas. No se incorporaron batimetría, caudales externos de toda la cuenca, niveles medidos aguas abajo ni mareas. Los bordes son de salida libre y las cotas no positivas se excluyen. Manning 0,05 y pérdida constante 5 mm/h son supuestos sin calibrar. No se asigna un periodo de retorno a las lluvias hipotéticas.

La aproximación inercial local omite aceleración convectiva y no es adecuada para interpretar flujos rápidos supercríticos. Una salvaguarda limita Froude a 1; se registra su frecuencia en cada ejecución. El dominio recortado y sus salidas afectan el resultado; no representan condiciones de borde medidas.

Se conservan depresiones del terreno. Algunas localidades presentan acumulaciones profundas en celdas aisladas; requieren revisar drenajes no representados, errores del relieve y conectividad. Esos máximos no son cotas esperadas. El visor muestra el percentil 95 de profundidad entre celdas con al menos 5 cm y avisa sobre acumulaciones profundas.

La proporción de terreno favorable se calcula sobre una **ventana alrededor de un punto GeoNames**, no sobre el polígono urbano o cantonal. La población de GeoNames sirve para selección, con fechas heterogéneas; no equivale a población censal INEC ni población expuesta. La Libertad se corrige a Santa Elena conservando el atributo original de GeoNames; se muestra Durán como Durán (Eloy Alfaro).

## Reproducir

Usar el Python del entorno geoespacial indicado por el proyecto. Dependencias de procesamiento: Python, NumPy, Pillow; únicamente biblioteca estándar para descarga y archivos.

En la versión de GitHub, los scripts están en `analysis/`: ejecutar desde esa carpeta para regenerar una nueva entrega en `analysis/dist/`. En el proyecto de trabajo original están en su raíz. Los archivos publicados del visor están un nivel arriba de `analysis/`.

```text
cd analysis
python build_data.py
python gather_hydraulic_sources.py
python -m unittest test_hydraulics -v
python run_simulations.py
python pack_simulations.py
python validate_delivery.py
python -m http.server 8000 --directory dist
```

`build_data.py` descarga GeoNames y teselas reales. Las fallas no se convierten en elevación cero. `run_simulations.py` reutiliza archivos existentes; para parámetros o versiones distintas usar una nueva carpeta de ejecución o retirar explícitamente sólo los resultados que se vayan a regenerar. No reutilizar resultados anteriores tras cambiar el solver sin versionar y recalcular.

El despliegue estático no ejecuta cálculos en el servidor ni llama APIs con secretos. La vista 3D utiliza CesiumJS 1.105.2 desde jsDelivr, con imagen satelital Esri y una malla georreferenciada de las cotas locales y de la lámina calculada. El globo de contexto usa el elipsoide; el relieve detallado está en la ventana descargada. La vista 2D conserva Leaflet. Cesium y los mapas base requieren conexión; los resultados se incluyen localmente. El código y las salidas de esta entrega se publican en la carpeta `inundaciones-ecuador` del repositorio.

## Comprobaciones

Se probaron lluvia uniforme con solución analítica en recinto cerrado, lago en reposo, drenaje con conservación de masa y positividad, rechazo de terreno incompleto, HAND desconocido sin canales y cota HAND cero en canales derivados. `validate_delivery.py` verifica integridad y balance de las 76 ejecuciones. Estas comprobaciones no sustituyen benchmarks hidráulicos independientes ni validación de campo. Revisar `validation.json`.

## Metodología y atribución

Implementación original; no se copió código de los artículos ni de otros solvers.

- Bates, Horritt y Fewtrell (2010), aproximación inercial local: https://doi.org/10.1016/j.jhydrol.2010.03.027
- Nobre et al. (2011), HAND: https://doi.org/10.1016/j.jhydrol.2011.03.051
- Barnes, Lehman y Mulla (2014), priority-flood: https://doi.org/10.1016/j.cageo.2013.04.024
- GeoNames: https://download.geonames.org/export/dump/ · CC BY 4.0.
- Mapzen / Tilezen Terrain Tiles: https://registry.opendata.aws/terrain-tiles/ · atribución por fuentes: https://github.com/tilezen/joerd/blob/master/docs/attribution.md
- SNGR: https://sgrportal.gestionderiesgos.gob.ec/server/rest/services/Susceptibilidad_de_Inundaciones/MapServer/0 · no se redistribuyen los polígonos completos; se conservan respuestas puntuales con fuente.
- Leaflet 1.x: BSD-2-Clause (cabecera de la librería). CesiumJS: Apache-2.0. Plotly ya no se carga ni se utiliza en el visor.
- Bases cartográficas: OpenStreetMap / CARTO, Esri y proveedores, OpenTopoMap / SRTM según la base seleccionada.

## Siguiente fase hidráulica

Riobamba: disponible el [modelo local 3D](riobamba.html), separado de los escenarios nacionales. Integra MDT suministrado de 3 m en cálculo de 24 m, cobertura 2018, máximos de lluvia y comparación con SWMM sobre geometría del portal. Incluye escenarios IDF, pruebas de estrés y capas de contexto. Las cotas enterradas, salidas, captación y diámetros faltantes de la red son estimados y se declaran. Los caudales diarios permanecen como contexto; faltan batimetría e hidrogramas para simular una crecida fluvial. **No está calibrado y la huella aún no converge al cambiar de malla (−36,1 % a 48 m frente a 24 m).** Consultar [método, resultados y limitaciones](analysis/RIOBAMBA_MODELO_LOCAL.md) y [auditoría original](analysis/ESTADO_RIOBAMBA.md).

Ampliación del 12 de noviembre: el motor acepta hidrogramas fluviales, niveles exteriores variables e intercambios prescritos de alcantarillado. `run_compound.py` ejecuta nuevos escenarios con dominio explícito y registra su procedencia. `run_swmm.py` calcula redes INP suministradas y exporta sus resultados; se verificó con el caso oficial EPA Extran, no con una red de Ecuador. `swmm_surface_exchange.py` transfiere desbordamientos prescritos hacia la superficie. Se descargaron mareas INOCAR de 9 puertos (8.760 horas cada uno), tres hidrogramas candidatos GEOGLOWS y se preparó la revisión de insumos de 38 localidades, disponibles en `entradas-hidraulicas.html`. **Todavía faltan geometrías locales, referencias compatibles y acoplamiento dinámico bidireccional; las 76 salidas publicadas siguen siendo de lluvia.** Consultar [estado, requisitos y uso](analysis/COMPONENTES_COMPUESTOS.md). Se verificaron 14 pruebas numéricas; no hay calibración de campo.

Preparar un piloto por cuenca o tramo con terreno de precisión adecuada y referencia vertical conocida, secciones de cauces y estructuras, hidrogramas o lluvia de evento y pérdidas justificadas, niveles aguas abajo, mareas cuando proceda y observaciones para calibración/validación. Comparar mallas, rugosidades y condiciones de borde; revisar balance y estabilidad. Consultar el inventario publicado en `datos-hidraulicos.html`.

JRC ofrece profundidades modeladas regionales LISFLOOD/LISFLOOD-FP; el catálogo se verificó, pero el servidor de descarga no respondió durante esta sesión. No se presentan como datos integrados ni como simulación propia. INAMHI, INOCAR y las fuentes municipales deben verificarse por estación, producto y tramo antes de alimentar un modelo local.


Verificación local ampliada: 18 pruebas aprobadas; balances superficiales conservativos y continuidad de SWMM 0,4333 %. La integración de Bing Aerial está preparada, pero crear y guardar el token limitado de Cesium ion sigue pendiente de autorización; mientras tanto se utiliza Esri con solicitudes limitadas al nivel 18.


Actualización IDF: el visor local incluye ESPOCH T25/1h (34 mm/h), desde los cuadros 27 y 72 del estudio histórico INAMHI 2015. Incluye comparación de estaciones, duración y retorno de lluvia, y recalcula SWMM para ese evento. No son tormentas observadas ni retornos de inundación. Los escenarios previos de 7,10 mm/h quedan como referencias; el de 24h se conserva en el archivo local y el historial. Detalle y reproducción en analysis/RIOBAMBA_MODELO_LOCAL.md.


Ampliación de preparación ante El Niño: escenarios hipotéticos de estrés de 56,5 / 67,8 / 90,4 mm/h (1h), 36,3 mm/h (2h), una prueba sin infiltración y una nueva comparación SWMM de 90,4 mm/h. Los aumentos son supuestos de sensibilidad sobre la IDF histórica T100; NO constituyen predicción de El Niño, máximos físicos ni tienen retorno asignado. Consultar stress-context.json y analysis/RIOBAMBA_MODELO_LOCAL.md.
