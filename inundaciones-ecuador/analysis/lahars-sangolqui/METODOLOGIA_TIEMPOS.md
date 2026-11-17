# Recorrido 3D con los tiempos publicados por EPN

Esta reproducción responde a la solicitud de usar los tiempos estimados de los estudios. Es una reconstrucción cinemática del avance del frente, separada de las corridas físicas de Kestrel. No calcula nuevos espesores, velocidades locales, caudales, erosión, depósitos, volumen transportado ni límites de inundación.

## Fuente y reloj

Torres Jacobowitz, Cristina Alexandra y Vásquez Falcones, Eduardo Mauricio (2017). *Simulación Numérica Tridimensional del Flujo de Lahares Primarios en el Flanco Norte del Volcán Cotopaxi*, Escuela Politécnica Nacional. [Registro original](https://bibdigital.epn.edu.ec/handle/15000/17595) y [PDF](https://bibdigital.epn.edu.ec/bitstream/15000/17595/1/CD-8076.pdf).

Se transcribieron las columnas de segundos acumulados de la tabla 4.3 (calibración de 1877, página impresa115/PDF140) y tabla4.4 (escenario3, página impresa116/PDF141). Ambas páginas se revisaron visualmente. El escenario3 se denominó más probable por sus autores en2017; esa descripción no es una probabilidad eruptiva actualizada a2026.

El cero del visor corresponde al reloj de las tablas en las entradas superiores del modelo. La reproducción comienza cerca del paralelo UTM norte9934926, no en el cráter ni sobre el glaciar. Aunque observaciones del documento describen valores relativos a la erupción, aquí no se añade un tiempo independiente cráter–entrada que no está resuelto por estas tablas.

Se conserva la distinción entre llegada del frente y momento de caudal máximo: la tabla3 de Toapaxi et al. (2019), doi:10.33333/rp.vol44n1.01, contiene tiempos de caudal máximo y no sustituye estas llegadas.

## Geometría y representación

El Pita, partes del Santa Clara y San Pedro se construyen con vías conectadas de OpenStreetMap, identificadores y respuestas originales conservados en `sources/`. No se inventan conexiones entre componentes inconexas. Los límites se ubican mediante las cotas norte de los tramos del estudio, en EPSG:32717, con conversión final a EPSG:4326.

Los tramos de El Salto y el corredor inicial del Santa Clara se digitalizan de los mapas del anexo9, páginas PDF293–294. Se usan los cruces de la cuadrícula UTM impresa para georreferenciar las imágenes renderizadas a1623×2100 píxeles. Los controles y vértices están en `build_study_timeline.py`; no se obtuvo el GIS original de los autores.

Los 50m indicados en el registro son una tolerancia asumida para la selección de puntos de la figura, **no una precisión total validada del eje del cauce**. El recorrido dentro de un corredor inundado tampoco equivale a recuperar su talweg original. El empalme cartográfico del Santa Clara con el siguiente tramo tiene una discrepancia de191,12m, conservada en la auditoría; no debe utilizarse para decisiones a escala de calles o predios.

Las longitudes cartográficas difieren de las publicadas: por ejemplo, Santa Clara tramo4 tiene unos10,34km frente a8,5km en el estudio, y San Pedro tramo4 unos4,69km frente a6,3km. No se escala la geometría ni se altera el reloj para ocultar esas diferencias. Por ello no se convierte la velocidad visual de un marcador en velocidad del lahar. Las diferencias completas se publican en `delivery-checks.json`.

Las líneas se dibujan sobre un relieve de contexto derivado de Copernicus GLO30. Su grosor es gráfico y no representa ancho inundado. La elevación visual de las líneas facilita su lectura y no es un espesor físico. Las construcciones municipales previas se conservan como referencias visuales, sin actuar como barreras. Su sustitución por Cesium y complemento catastral sigue aplazada según la instrucción del usuario.

## Interpolación temporal

Para cada tramo se conservan sus tiempos publicados de entrada t0 y salida t1. A un tiempo t, la fracción recorrida es `max(0,min(1,(t-t0)/(t1-t0)))`; se ubica el marcador a esa fracción de la longitud cartográfica del tramo. Esa interpolación intermedia es un supuesto de reproducción, no una serie temporal nueva publicada por los autores ni el resultado de resolver conservación de masa y momento.

El Salto presenta una particularidad real en la tabla: su tramo2 comienza antes de que el frente propio termine el tramo1. Los autores lo atribuyen al desbordamiento anticipado del Pita hacia El Salto. Se conservan ambos aportes; no se fuerza una única secuencia temporal.

La animación concluye cuando termina el último tramo temporal del escenario:5985s para el escenario3 y5010s para el ensayo de1877. Que el flujo de una ruta llegue antes al último sector que el de otra a una confluencia intermedia refleja sus relojes independientes; no significa que el peligro termine en ese momento. No se consideran estos tiempos como plazos para evacuar.

## Diferencias e incidencias de la fuente

Hay diferencias entre algunas observaciones narrativas y las columnas acumuladas de las tablas. Se preservan los segundos de esas columnas, sin promedios ni correcciones silenciosas. También hay coordenadas repetidas o intercambiadas en la descripción del Santa Clara; no se copian como extremos de cauce sin control. La correspondencia cartográfica se documenta y su exactitud de campo no está validada.

Los tiempos52min a Sangolquí y60min a San Rafael de Frimberger et al. (RAMMS, doi:10.1002/esp.5056, tabla2, escenario VEI>4) corresponden a otro ensayo. Se enlazan como contexto y no se mezclan con los tramos de EPN2017. Tampoco se modifica la salida de Kestrel para imponer esos tiempos.

## Comprobaciones

`verify_study_timeline.py` contrasta los44 tiempos de los11 tramos con una transcripción independiente de las tablas revisadas visualmente; verifica intervalos, coordenadas, orden de estaciones, separaciones, hashes, tamaños y atributos anónimos de los edificios. Los controles numéricos de entrega no son una validación predictiva del recorrido. Se conserva toda la procedencia y se publica la auditoría.

Datos de cauces: © OpenStreetMap contributors, ODbL. Mapas y tiempos: Torres y Vásquez, EPN2017. No hay entrenamiento de GeoAI: se utiliza geoprocesamiento convencional y reconstrucción temporal explícita.
