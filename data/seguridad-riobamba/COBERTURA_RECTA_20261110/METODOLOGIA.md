# Cobertura visual por brazos de via

Rayos rectos desde la coordenada exacta de la camara, orientados por los brazos iniciales del cruce o segmento asociado. Cada rayo tiene 200 m y una extension colineal de 50 m. Sin recorridos, giros, ramificaciones ni origen desplazado al nodo vial. No certifica visibilidad real ni ausencia de obstaculos.

Misma metodologia previa: diferencia del eje especifico aprobado y union disuelta de radios de 200 m, 64 segmentos por cuadrante. Los brazos viales y sus 50 m adicionales son representacion visual y no sustituyen ni amplian esos radios.

Las ubicaciones de camaras no se mueven para asociarlas a una via. Las separaciones y las camaras sin asociacion se conservan en ASOCIACION_CAMARAS.json. Los cruces se forman solo con vertices compartidos; no se conectan cruces geometricos interiores automaticamente. Se complementa OSM con la cartografia vial municipal local cuando no hay una via OSM a 30 m. Las dos redes no se conectan artificialmente entre si. Seis camaras quedan sin brazos por falta de asociacion local; sus radios de 200 m siguen participando en el calculo anterior de brechas.
