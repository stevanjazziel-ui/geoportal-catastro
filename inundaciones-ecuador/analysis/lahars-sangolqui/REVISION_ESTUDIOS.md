# Revisión de los escenarios de erupción para Sangolquí

Revisión: 17 de noviembre de 2026. Esta referencia no reemplaza las entradas del solver ni convierte las pruebas anteriores en escenarios calibrados.

## Fuente que debe guiar la comparación

Frimberger, Andrade, Weber y Krautblatter (2021), [Modelling future lahars...](https://onlinelibrary.wiley.com/doi/full/10.1002/esp.5056), tabla 2 y sección 4.3. Modelo RAMMS calibrado retrospectivamente con el evento de 1877; escenarios futuros hipotéticos y condicionados a sus supuestos sobre erupción y glaciar.

| Escenario del artículo | Volumen inicial, millones m³ | Incorporación por erosión, millones m³ | Total en drenaje norte, millones m³ | Pico en entrada, m³/s | Sangolquí, minutos de viaje | San Rafael por Pita, minutos de viaje |
|---|---:|---:|---:|---:|---:|---:|
| VEI 2–3 | 7,8 | 11,6 | 19,4 | 32.000 | — | 84 |
| VEI 3–4 | 18,9 | 15,7 | 34,6 | 64.000 | — | 71 |
| VEI >4 | 46 | 24,7 | 70,7 | 128.000 | 52 | 60 |

El guion reproduce la ausencia de llegada reportada en esa tabla y ruta de simulación; no establece seguridad del lugar. Los 70,7 millones de m³ corresponden al volumen total del flujo en el drenaje norte del escenario, no a una medición o integral de volumen que atraviesa el centro de Sangolquí. Los tiempos son de viaje del escenario publicado, no plazos para evacuar ni predicción de una próxima erupción.

## Velocidades: mantener el lugar y la definición

El artículo compara velocidades locales con evidencias en Jatabamba, Proaño y Hacienda San Rafael (figuras 3 y 6). La figura 6 muestra las velocidades locales reconstruidas para calibrar el evento de 1877: Jatabamba, 18 m/s (64,8 km/h); Proaño, 20 m/s (72 km/h); Hacienda San Rafael, 20 m/s (72 km/h). Son objetivos históricos en esos sitios, no velocidades uniformes futuras en Sangolquí. Sin las ubicaciones GIS originales no se compara el máximo de un rectángulo urbano como si fuera una medición en esos puntos. El valor de velocidad inicial de 10 m/s de la sección 4.2 es una condición de entrada del modelo RAMMS; no es la velocidad con la que llega a la ciudad. No debe usarse una velocidad uniforme para todo el recorrido.

[Vasconez et al. (2024), tabla 1](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2024.1426088/full) recoge estimaciones históricas de aproximadamente 50 km/h hacia Chillos (unos 40 km en menos de una hora). Son estimaciones históricas de propagación y no una velocidad local de diseño para cada calle. El mismo trabajo distingue los depósitos históricos del drenaje norte (60–75 millones m³, estimación atribuida a Mothes et al., 2004) de sus propias entradas de agua y mezcla.

## Diferencia con nuestras pruebas

Las pruebas de 10, 30 y 60 millones de m³ introducen mezcla en un solo punto del Pita, aguas abajo del volcán. No son los tres escenarios de Frimberger. Los resultados locales publicados no deben presentarse como reproducción de su tabla ni como un pronóstico de lahares. La fuente inicial de 40 % de sólidos difiere también del aporte de agua desde nueve fuentes glaciares usado por [Vasconez et al. (2025), tabla 1](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2025.1611579/full): 34,8 millones de m³ de agua al drenaje norte no equivalen directamente a volumen de mezcla que llega a la ciudad.

## Trabajo requerido para un escenario respaldado

1. Elegir y mantener un escenario documentado, su estado del glaciar, geometría de fuentes, cronología e hidrogramas. No mezclar entradas de RAMMS con resultados de Kestrel como si fueran el mismo ensayo.
2. Cubrir el recorrido desde esas fuentes y los desbordamientos del Pita al Santa Clara. Las pruebas iniciales de inyección local no cubrían ese tramo; la nueva adaptación de nueve fuentes sí cubre el recorrido desde el volcán, en un dominio de 60 × 96 km.
3. Resolver mejor los cañones y las divisorias de La Caldera; el DEM público de 30 m no caracteriza completamente ese paso.
4. Comparar las salidas con tiempos, velocidades, alturas y huellas del estudio en los mismos sitios y usando el mismo origen temporal. No ajustar una animación visual para imponer llegadas.
5. Para responder cuánto material entra en la ciudad, definir secciones en Pita y Santa Clara y obtener Q(t), velocidad local e integral temporal del flujo de mezcla. El nuevo análisis integra el transporte estimado por una sección transversal de comparación cada 15 segundos. No equivale a todo lo que entra a la ciudad ni a sus depósitos, y no sustituye secciones por cauce con geometría local validada.

## Revisión del terreno municipal

El servicio MDT GADMUR 2024 permite consultar valores numéricos mediante Identify/MultiPoint. Se consultaron 14.893 puntos: malla regional de 120 m y cinco perfiles de 5 m cerca del corredor crítico. Hubo 9.127 valores numéricos válidos. Frente al Copernicus reproyectado, la diferencia municipal menos Copernicus tiene mediana −2,17 m, percentiles 5–95 de −19,79 a +2,49 m y RMSE de 10,30 m; diferencia absoluta máxima 123,12 m. El espaciado de consulta no demuestra resolución nativa de 5 m. No se fusionaron esos valores: faltan metadatos que confirmen la referencia vertical y la precisión original. No debe aplicarse un desplazamiento constante para corregir diferencias espaciales variables. Informe y muestras reproducibles: `sources/municipal-terrain-audit/`.
