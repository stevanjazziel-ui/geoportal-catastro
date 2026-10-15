# Propuesta policial: ejes viales y ajustes aprobados

Se aplican las 30 ubicaciones del estudio, con POL-05 en Roma/Viena y POL-17 en Proano/Canonigo Ramos. Autorizacion expresa: "Las 30 del estudio, con los ajustes". No hay nueva optimizacion.

103 existentes (30 para cambio incluidas) y 50 municipales con geometrias fijas. Se mantienen 30 policiales. EPSG:32717, radios potenciales 200 m, quad_segs=64, union disuelta. Se actualizan dependencias de 100/150/200 m.

Cada emplazamiento policial es un vertice vial original compartido, sin inventar coordenadas. POL-05 es el cruce local solicitado Roma/Viena: OSM residencial y jerarquia municipal discrepante, no se certifica como avenida. Los demas nodos corresponden a un eje OSM trunk/primary/secondary/tertiary.

KDE D/V es el criterio principal del estudio; Gi* solo referencia. No se recalculan ni cambian estadisticos, celdas o significancias. Solo se actualizan coberturas. La comparacion conserva perdidas de eventos y grandes desplazamientos.

Los buffers NO son campos visuales. Las camaras solo ven hacia las vias; orientacion, altura y obstaculos requieren comprobacion en campo. No se presupone visibilidad a traves de edificios ni alrededor de esquinas. POL-17/POL-19 conserva un hueco potencial de 12.95 m.

APROBACION_Y_FUENTES.json conserva coordenadas fuente y hashes; TRAZABILIDAD_POLICIA_FINAL.csv enlaza coordenadas publicadas y finales por ID. Los archivos HISTORICO_PREVIO_* son snapshots anteriores, no las coordenadas finales. La geometria final esta en PROPUESTA_POLICIA_30_FINAL y ESCENARIO_FINAL_183.gpkg.
