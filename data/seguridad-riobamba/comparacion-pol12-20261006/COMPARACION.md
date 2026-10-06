# Comparacion puntual de POL-12

La propuesta publicada NO se modifica. CRS EPSG:32717; radio200m. Gi* no recalculado.

Referencia comun:103 existentes +50 municipales finales +lasotras29 policiales finales.
No se suman aportes individuales de alternativas; cada fila sustituye hipoteticamente solo POL-12.

| Opcion | Candidato | Plataforma | D nuevos | V nuevos | D+V | Solape % | Area exclusiva m2 | Desplazamiento m | D/V anteriores conservados | Preferible |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ACTUAL | CAND-POL-01014 | PLATAFORMA H | 10 | 1 | 11 | 60.58 | 49536.1 | 0.0 | 11 | NO |
| ALTERNATIVA_1 | CAND-POL-00419 | PLATAFORMA D | 10 | 3 | 13 | 4.62 | 119846.6 | 2811.5 | 0 | SI |
| ALTERNATIVA_2 | CAND-POL-00588 | PLATAFORMA D | 24 | 10 | 34 | 0.00 | 125651.1 | 1887.3 | 0 | NO |
| ALTERNATIVA_3 | CAND-POL-00575 | PLATAFORMA D | 23 | 10 | 33 | 0.00 | 125651.1 | 1916.3 | 0 | NO |
| ALTERNATIVA_4 | CAND-POL-00573 | PLATAFORMA D | 23 | 9 | 32 | 0.00 | 125651.1 | 1920.3 | 0 | NO |
| ALTERNATIVA_5 | CAND-POL-00591 | PLATAFORMA D | 22 | 10 | 32 | 0.00 | 125651.1 | 1849.3 | 0 | NO |

## Interpretacion
Se evaluaron 1826 nodos con remanente significativo D/V; 1 cumplen la comparacion de mejora.
La alternativa mejor situada en la comparacion es CAND-POL-00419; cumple todas las condiciones de mejora.
El ranking prioriza eventos D/V exclusivos; no necesariamente devuelve los nodos de menor solape absoluto ni los mas proximos al punto actual.
Los nodos pueden estar en otra Plataforma. La distancia al punto actual se reporta sin imponer un radio arbitrario de busqueda.
Gi* en el sitio y nivel maximo en el radio son campos distintos; una interseccion con D/V no es una nueva prueba estadistica conjunta.
PERDIDOS_D/V/C y GANADOS_D/V/C muestran cambios de observaciones concretas: no se supone que mantener un conteo conserve exactamente los mismos eventos.
Cada alternativa se compara contra los mismos29 puntos fijos. Consultar PERDIDOS_D/V y GANADOS_D/V para no confundir nuevos conteos con conservar las mismas observaciones.
No se presupone mejora en todas las superficies: consultar AREA_HOTSPOT_D/V_NUEVA_M2 y sus valores actuales en elCSV antes de decidir.
La poblacion asociada es una estimacion areal CPV2022 urbana, no poblacion rural completa.
UPC y corredores son descriptivos, no criterios de seleccion. Ningun nodo se declara instalado ni validado en campo.
Las coordenadas actuales y las otras29, fuentes y visor se verifican sin cambios por hash. Sin commit/push.
La alternativa preferible mas cercana entre todos los nodos evaluados es CAND-POL-00419: 2811.5m; 13D/V; solape 4.62%. Conserva 0/11 eventos exclusivos anteriores. No se incorpora automaticamente.

## Control local y mejora mas cercana
Este control admite mantener el mismo numero de D/V si baja el solape; no se confunde con la regla estricta de aumentar D/V utilizada en el ranking principal.
- LOCAL_PLATAFORMA_H: CAND-POL-01024, PLATAFORMA H, desplazamiento 79.2m; D/V 10/1, solape 48.10%; conserva 9/11 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
- MEJORA_MAS_CERCANA: CAND-POL-01024, PLATAFORMA H, desplazamiento 79.2m; D/V 10/1, solape 48.10%; conserva 9/11 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
