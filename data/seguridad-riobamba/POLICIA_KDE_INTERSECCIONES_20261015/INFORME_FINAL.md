# Policia: KDE urbano e intersecciones principales

Se aplica la alternativa revisada de 30 camaras policiales; 29 reubicaciones y una posicion conservada. Las 103 existentes y las 50 municipales se conservan.

Criterio principal: aporte marginal de KDE urbano Delincuencia + Violencia; kernel gaussiano truncado de 200 m, celda de 20 m y peso 1 por registro. Gi* permanece como referencia sin recalculo. Los nodos son intersecciones reales de grado >=3 sobre vias Expresa, Arterial A/B/P o Colectora de la cartografia municipal.

Se busca continuidad de observacion por ejes, con cumplimiento parcial por cantidad limitada de camaras. La union de radios geometricos no certifica linea de vista. Validar poste, altura, orientacion y obstaculos en campo.

Coberturas y atributos de las nuevas posiciones recalculados en EPSG:32717. Se conserva la asignacion estricta de eventos a manzanas; no se mueven incidentes ni se recalcula brecha territorial.

| Corredor | Cobertura sistema 183 | Sin cobertura (m) |
|---|---:|---:|
| BOULEVARD_MACAJI_BELLAVISTA | 100.000% | 0.000 |
| ANILLO_VIAL | 82.674% | 2274.257 |
| CICLOVIAS | 70.148% | 3276.547 |
| QUEBRADA_LAS_ABRAS | 34.833% | 3398.166 |

Los corredores son efectos secundarios de la ubicacion policial, no objetivos de su seleccion.
