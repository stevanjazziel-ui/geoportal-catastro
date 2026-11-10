# Cobertura visual por brazos de via

Vertices compartidos OSM red consolidada; cada brazo continua por la direccion mas alineada, sin ramificarse en cruces posteriores; se detiene ante giro mayor a 60 grados, fin de via o 250 m. No visibilidad real.

Misma metodologia previa: diferencia del eje especifico aprobado y union disuelta de radios de 200 m, 64 segmentos por cuadrante. Los brazos viales y sus 50 m adicionales son representacion visual y no sustituyen ni amplian esos radios.

Las ubicaciones de camaras no se mueven para asociarlas a una via. Las separaciones y las camaras sin asociacion se conservan en ASOCIACION_CAMARAS.json. Los cruces se forman solo con vertices compartidos; no se conectan cruces geometricos interiores automaticamente. Se complementa OSM con la cartografia vial municipal local cuando no hay una via OSM a 30 m. Las dos redes no se conectan artificialmente entre si. Seis camaras quedan sin brazos por falta de asociacion local; sus radios de 200 m siguen participando en el calculo anterior de brechas.
