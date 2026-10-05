# Revision final de redundancia espacial - 30 camaras policiales

## Alcance y metodo
- Solo auditoria y escenario de prueba. Los 103 puntos existentes, 50 municipales y 30 policiales oficiales permanecen intactos.
- EPSG:32717; radio 200 m; buffer con 64 segmentos por cuadrante, igual que la corrida final.
- Cada aporte exclusivo se mide contra 103 + 50 + las OTRAS 29 policiales. No se suman aportes individuales.
- Redundancia: BAJA <50%; MEDIA [50,70]%; ALTA (70,85]%; MUY ALTA >85%. Los extremos compartidos se resuelven explicitamente.
- Se revisan todos los solapes >70%, incluso cuando su aporte D/V no es bajo. Prioridad maxima: >85% y D/V <=2. No se invento otro umbral de bajo aporte.
- Alternativas: banco congelado de nodos viales del proyecto, mismo ambito; no se seleccionan puntos oficiales ni duplicados exactos de existentes/municipales.
- Preferible: mas D+V nuevos, sin disminuir D o V por separado, menor solape, evidencia residual significativa de D O V y sin reducir el maximo nivel significativo del entorno de 200 m. No se exige coincidencia simultanea de ambas categorias.
- Orden lexicografico entre alternativas: preferible; D/V nuevos; nivel y area de coincidencia D/V residual; area D+V nueva; menor solape; Convivencia; grado vial. Sin ponderaciones ni distancia minima.
- En cada iteracion la alternativa y el punto actual se comparan contra exactamente las mismas otras29. Una recomendacion modifica solo el escenario de prueba antes de revisar la siguiente.
- Gi* del SITIO se obtiene de la celda que contiene el punto; NIVEL_DEL/VIOL representa el maximo Hot Spot dentro del buffer. No son equivalentes.
- En limites de celdas se conservan todas las clases/IDs; z/p escalar queda No disponible si hay mas de una. No se inventa un nivel conjunto D/V.
- Hot Spots CON_APORTE: celdas con area adicional positiva; PRIMERA_ATENCION: antes sin cobertura y ahora con alguna; COMPLETADOS: antes parciales y ahora cubiertas. Atendido no significa eliminado.
- Poblacion adicional: estimacion proporcional de area exclusiva intersectada con manzanas CPV2022 dentro de las 18 Plataformas. Sin poblacion valida: No disponible; faltantes: estimacion parcial.
- Distancias entre puntos son euclidianas, no recorridos ni tiempos. Banderas <200/<300/<400 m son descriptivas, nunca reglas de reubicacion.
- Corredores, UPC y via cercana son contexto. No se optimiza Anillo, Ciclovias, Macaji-Bellavista, Las Abras ni Cunduana.
- Nodo vial documental no acredita por si solo factibilidad de instalacion; requiere inspeccion de campo. No se inventa infraestructura critica ni justificacion operativa.

## Tabla de las 30 - escenario oficial actual
| ID | Plataforma | Solape % | Exclusiva m2 | D | V | D+V | Redundancia | Recomendacion |
|---|---|---:|---:|---:|---:|---:|---|---|
| POL-17 | PLATAFORMA M | 96.68 | 4176.4 | 0 | 0 | 0 | MUY ALTA | REUBICAR |
| POL-19 | PLATAFORMA K | 95.95 | 5086.2 | 0 | 0 | 0 | MUY ALTA | REUBICAR |
| POL-18 | PLATAFORMA M | 86.30 | 17220.2 | 1 | 1 | 2 | MUY ALTA | REUBICAR |
| POL-07 | PLATAFORMA J | 90.55 | 11879.1 | 2 | 2 | 4 | MUY ALTA | REUBICAR |
| POL-15 | PLATAFORMA J | 75.44 | 30865.3 | 2 | 0 | 2 | ALTA | REUBICAR |
| POL-16 | PLATAFORMA H | 77.23 | 28608.1 | 2 | 3 | 5 | ALTA | REUBICAR |
| POL-14 | PLATAFORMA J | 80.68 | 24278.1 | 3 | 3 | 6 | ALTA | REUBICAR |
| POL-06 | PLATAFORMA O | 78.12 | 27497.4 | 5 | 3 | 8 | ALTA | REUBICAR |
| POL-26 | PLATAFORMA K | 82.20 | 22362.4 | 7 | 4 | 11 | ALTA | MANTENER |
| POL-05 | PLATAFORMA P | 75.70 | 30530.2 | 27 | 3 | 30 | ALTA | MANTENER |
| POL-22 | PLATAFORMA F | 59.71 | 50626.9 | 1 | 1 | 2 | MEDIA | MANTENER |
| POL-28 | PLATAFORMA K | 65.97 | 42756.6 | 1 | 2 | 3 | MEDIA | MANTENER |
| POL-11 | PLATAFORMA K | 52.25 | 59995.8 | 4 | 2 | 6 | MEDIA | MANTENER |
| POL-10 | PLATAFORMA O | 60.51 | 49617.6 | 4 | 3 | 7 | MEDIA | MANTENER |
| POL-12 | PLATAFORMA H | 66.03 | 42682.5 | 9 | 0 | 9 | MEDIA | MANTENER |
| POL-13 | PLATAFORMA O | 61.40 | 48504.9 | 4 | 5 | 9 | MEDIA | MANTENER |
| POL-20 | PLATAFORMA I | 69.50 | 38323.3 | 7 | 3 | 10 | MEDIA | MANTENER |
| POL-27 | PLATAFORMA O | 53.59 | 58317.0 | 9 | 4 | 13 | MEDIA | MANTENER |
| POL-24 | PLATAFORMA Q | 51.32 | 61169.0 | 8 | 9 | 17 | MEDIA | MANTENER |
| POL-02 | PLATAFORMA O | 59.64 | 50713.5 | 13 | 5 | 18 | MEDIA | MANTENER |
| POL-04 | PLATAFORMA P | 66.13 | 42560.7 | 18 | 41 | 59 | MEDIA | MANTENER |
| POL-29 | PLATAFORMA H | 29.35 | 88766.6 | 4 | 5 | 9 | BAJA | MANTENER |
| POL-21 | PLATAFORMA B | 24.67 | 94649.3 | 5 | 4 | 9 | BAJA | MANTENER |
| POL-08 | PLATAFORMA C | 38.19 | 77662.8 | 7 | 5 | 12 | BAJA | MANTENER |
| POL-30 | PLATAFORMA Q | 37.85 | 78093.5 | 8 | 4 | 12 | BAJA | MANTENER |
| POL-25 | PLATAFORMA M | 47.85 | 65522.8 | 7 | 7 | 14 | BAJA | MANTENER |
| POL-09 | PLATAFORMA J | 39.82 | 75621.6 | 7 | 7 | 14 | BAJA | MANTENER |
| POL-23 | PLATAFORMA H | 24.07 | 95403.8 | 17 | 5 | 22 | BAJA | MANTENER |
| POL-03 | PLATAFORMA J | 42.16 | 72680.9 | 17 | 10 | 27 | BAJA | MANTENER |
| POL-01 | FUERA DE PLATAFORMAS | 0.00 | 125651.1 | 33 | 18 | 51 | BAJA | MANTENER |

## Balance conjunto oficial vs prueba
| Categoria | Eventos cubiertos oficial | Eventos cubiertos prueba | Diferencia |
|---|---:|---:|---:|
| DELINCUENCIA | 1702 | 1783 | +81 |
| VIOLENCIA | 918 | 989 | +71 |
| CONVIVENCIA | 4921 | 4999 | +78 |

| Hot Spot urbano | Completos oficial/prueba | Parciales oficial/prueba | Sin cobertura oficial/prueba | Area cubierta oficial/prueba (m2) |
|---|---:|---:|---:|---:|
| DELINCUENCIA | 234/227 | 54/61 | 7/7 | 2702446.7/2693364.7 |
| VIOLENCIA | 264/263 | 82/107 | 37/13 | 3116423.2/3300668.7 |
| CONVIVENCIA | 244/232 | 73/85 | 8/8 | 2937873.3/2900282.5 |

La mejora de eventos no implica mejora de todas las superficies: el area cubierta de Hot Spots urbanos D cambia -9082.0 m2; las celdas D completas pasan de 234 a 227. Los niveles Gi* no cambian. Convivencia es complementaria y tambien presenta cambios de superficie. Estas contrapartidas requieren revision antes de aplicar las recomendaciones.

## Recomendaciones iterativas
### POL-17 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 0 a 43, sin perder D o V individualmente; solape 96.68% a 0.00%. Nodo vial de grado 3, Hot Spot residual D/V 0%/99%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-19 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 0 a 24, sin perder D o V individualmente; solape 95.95% a 7.73%. Nodo vial de grado 3, Hot Spot residual D/V 0%/99%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-18 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 2 a 24, sin perder D o V individualmente; solape 85.71% a 17.87%. Nodo vial de grado 3, Hot Spot residual D/V 99%/0%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-15 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 2 a 22, sin perder D o V individualmente; solape 75.44% a 0.00%. Nodo vial de grado 3, Hot Spot residual D/V 0%/99%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-07 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 4 a 21, sin perder D o V individualmente; solape 90.55% a 0.00%. Nodo vial de grado 4, Hot Spot residual D/V 0%/99%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-16 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 5 a 19, sin perder D o V individualmente; solape 77.23% a 19.49%. Nodo vial de grado 3, Hot Spot residual D/V 99%/0%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-14 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 9 a 15, sin perder D o V individualmente; solape 65.71% a 16.02%. Nodo vial de grado 4, Hot Spot residual D/V 99%/0%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-06 - REUBICAR
Reubicar en escenario de prueba: D/V adicionales 8 a 14, sin perder D o V individualmente; solape 78.12% a 54.46%. Nodo vial de grado 3, Hot Spot residual D/V 0%/99%. No se exige que ambas categorias sean significativas en la misma celda. Las superficies/niveles pueden variar: consultar alternativas. Pendiente validacion operativa de campo.
### POL-26 - MANTENER
Mantener: entre 1817 nodos residuales del mismo ambito, ninguno mejora simultaneamente eventos D/V y solape sin perder D o V, conservando evidencia D o V residual y el nivel maximo significativo en el entorno. La proximidad no obliga a reubicar.
### POL-05 - MANTENER
Mantener: entre 1806 nodos residuales del mismo ambito, ninguno mejora simultaneamente eventos D/V y solape sin perder D o V, conservando evidencia D o V residual y el nivel maximo significativo en el entorno. La proximidad no obliga a reubicar.
### POL-22 - MANTENER
Solape 59.71% y 2 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 90%/99%. Mantener ubicacion.
### POL-28 - MANTENER
Solape 65.97% y 3 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 95%/99%. Mantener ubicacion.
### POL-11 - MANTENER
Solape 52.25% y 6 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-10 - MANTENER
Solape 60.51% y 7 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-12 - MANTENER
Solape 66.03% y 9 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-13 - MANTENER
Solape 61.40% y 9 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-20 - MANTENER
Solape 69.50% y 10 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-27 - MANTENER
Solape 53.59% y 13 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/95%. Mantener ubicacion.
### POL-24 - MANTENER
Solape 51.32% y 17 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-02 - MANTENER
Solape 59.64% y 18 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-04 - MANTENER
Solape 66.13% y 59 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-29 - MANTENER
Solape 29.35% y 9 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/95%. Mantener ubicacion.
### POL-21 - MANTENER
Solape 24.67% y 9 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 90%/95%. Mantener ubicacion.
### POL-08 - MANTENER
Solape 38.19% y 12 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 90%/95%. Mantener ubicacion.
### POL-30 - MANTENER
Solape 37.85% y 12 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-25 - MANTENER
Solape 47.85% y 14 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-09 - MANTENER
Solape 39.82% y 14 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-23 - MANTENER
Solape 24.07% y 22 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/95%. Mantener ubicacion.
### POL-03 - MANTENER
Solape 42.16% y 27 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.
### POL-01 - MANTENER
Solape 0.00% y 51 eventos D/V exclusivos; no combina solape >70% con aporte bajo. Entorno Hot Spot D/V 99%/99%. Mantener ubicacion.

## Plataforma J
La referencia visual no identifica un ID unico. Se auditaron todas las policiales cuyo punto cae en Plataforma J; las cinco mas cercanas a cada una figuran en PLATAFORMA_J_5_CERCANAS.csv.
- POL-07: solape 90.55%; exclusiva 11879.1 m2; D/V 2/2; entorno Hot Spot D/V 99%/99%; REUBICAR.
- POL-15: solape 75.44%; exclusiva 30865.3 m2; D/V 2/0; entorno Hot Spot D/V 99%/99%; REUBICAR.
- POL-14: solape 80.68%; exclusiva 24278.1 m2; D/V 3/3; entorno Hot Spot D/V 99%/99%; REUBICAR.
- POL-09: solape 39.82%; exclusiva 75621.6 m2; D/V 7/7; entorno Hot Spot D/V 99%/99%; MANTENER.
- POL-03: solape 42.16%; exclusiva 72680.9 m2; D/V 17/10; entorno Hot Spot D/V 99%/99%; MANTENER.

## Archivos
- AUDITORIA_30_POLICIA.csv: detalle completo actual, distancias, niveles, areas, beneficios y recomendaciones.
- ALTERNATIVAS_ITERATIVAS.csv: actual + hasta5 alternativas por cada caso revisado, mismo contexto de iteracion.
- DECISIONES.csv: recomendaciones; ESCENARIO_PRUEBA_30.csv: reevaluacion final conjunta del escenario de prueba.
- REDUNDANCIA_POLICIA_30.gpkg: puntos, buffers, exclusivas, superposiciones actuales/prueba y alternativas, EPSG:32717.
- RESULTADOS.json: resultados completos, escenarios y hashes de fuentes.
- index.html: mapa interactivo con tabla completa y comparador actual/prueba.

## Validacion
30 policiales en ambos escenarios; areas cuadran; eventos exclusivos cotejados independientemente; reproduce la corrida final; fuentes protegidas conservan sus hashes. Sin commit ni push.
