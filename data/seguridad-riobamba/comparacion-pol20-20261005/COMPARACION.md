# Comparacion puntual de POL-20

La propuesta publicada NO se modifica. CRS EPSG:32717; radio200m. Gi* no recalculado.

Referencia comun:103 existentes +50 municipales finales +lasotras29 policiales finales.
No se suman aportes individuales de alternativas; cada fila sustituye hipoteticamente solo POL-20.

| Opcion | Candidato | Plataforma | D nuevos | V nuevos | D+V | Solape % | Area exclusiva m2 | Desplazamiento m | Preferible |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| ACTUAL | CAND-POL-01220 | PLATAFORMA I | 7 | 3 | 10 | 69.50 | 38323.3 | 0.0 | NO |
| ALTERNATIVA_1 | CAND-POL-00491 | PLATAFORMA C | 8 | 6 | 14 | 7.53 | 116188.9 | 3506.0 | SI |
| ALTERNATIVA_2 | CAND-POL-00484 | PLATAFORMA C | 7 | 7 | 14 | 5.94 | 118182.1 | 3530.1 | SI |
| ALTERNATIVA_3 | CAND-POL-01023 | PLATAFORMA G | 10 | 4 | 14 | 16.18 | 105326.3 | 1349.6 | SI |
| ALTERNATIVA_4 | CAND-POL-01031 | PLATAFORMA G | 10 | 4 | 14 | 7.03 | 116816.3 | 1305.8 | SI |
| ALTERNATIVA_5 | CAND-POL-01020 | PLATAFORMA G | 10 | 3 | 13 | 21.70 | 98380.0 | 1372.5 | SI |

## Interpretacion
Se evaluaron 1826 nodos con remanente significativo D/V; 20 cumplen la comparacion de mejora.
La alternativa mejor situada en la comparacion es CAND-POL-00491; cumple todas las condiciones de mejora.
El ranking prioriza eventos D/V exclusivos; no necesariamente devuelve los nodos de menor solape absoluto ni los mas proximos al punto actual.
Los nodos pueden estar en otra Plataforma. La distancia al punto actual se reporta sin imponer un radio arbitrario de busqueda.
Gi* en el sitio y nivel maximo en el radio son campos distintos; una interseccion con D/V no es una nueva prueba estadistica conjunta.
PERDIDOS_D/V/C y GANADOS_D/V/C muestran cambios de observaciones concretas: no se supone que mantener un conteo conserve exactamente los mismos eventos.
Las cinco alternativas del ranking principal dejan fuera los10 eventos D/V exclusivos actuales en PlataformaI y cubren13-14 en otros sectores. Es una redistribucion, no una mejora local.
No mejoran todas las superficies: las alternativasC pierden el aporte exclusivo de area Hot Spot de Delincuencia del punto actual; las alternativasG pierden el de Violencia. Consultar AREA_HOTSPOT_D/V_NUEVA_M2 en elCSV antes de decidir.
La poblacion asociada es una estimacion areal CPV2022 urbana, no poblacion rural completa.
UPC y corredores son descriptivos, no criterios de seleccion. Ningun nodo se declara instalado ni validado en campo.
Las coordenadas actuales y las otras29, fuentes y visor se verifican sin cambios por hash. Sin commit/push.
La alternativa preferible mas cercana entre todos los nodos evaluados es CAND-POL-01017: 1223.3m; 12D/V; solape 22.61%. No se incorpora automaticamente.

## Control local y mejora mas cercana
Este control admite mantener el mismo numero de D/V si baja el solape; no se confunde con la regla estricta de aumentar D/V utilizada en el ranking principal.
- LOCAL_PLATAFORMA_I: CAND-POL-01204, PLATAFORMA I, desplazamiento 51.9m; D/V 7/3, solape 69.35%; conserva 10/10 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
- MEJORA_MAS_CERCANA: CAND-POL-01214, PLATAFORMA I, desplazamiento 29.2m; D/V 7/3, solape 68.94%; conserva 10/10 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
