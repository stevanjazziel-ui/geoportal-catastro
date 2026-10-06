# Comparacion puntual de POL-24

La propuesta publicada NO se modifica. CRS EPSG:32717; radio200m. Gi* no recalculado.

Referencia comun:103 existentes +50 municipales finales +lasotras29 policiales finales.
No se suman aportes individuales de alternativas; cada fila sustituye hipoteticamente solo POL-24.

| Opcion | Candidato | Plataforma | D nuevos | V nuevos | D+V | Solape % | Area exclusiva m2 | Desplazamiento m | D/V anteriores conservados | Preferible |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| ACTUAL | CAND-POL-02704 | PLATAFORMA Q | 4 | 3 | 7 | 75.83 | 30371.3 | 0.0 | 7 | NO |
| ALTERNATIVA_1 | CAND-POL-02759 | PLATAFORMA Q | 8 | 7 | 15 | 25.42 | 93712.3 | 194.6 | 6 | SI |
| ALTERNATIVA_2 | CAND-POL-02762 | PLATAFORMA Q | 8 | 6 | 14 | 22.50 | 97376.0 | 207.4 | 5 | SI |
| ALTERNATIVA_3 | CAND-POL-00491 | PLATAFORMA C | 8 | 6 | 14 | 7.53 | 116188.9 | 6965.8 | 0 | SI |
| ALTERNATIVA_4 | CAND-POL-00484 | PLATAFORMA C | 7 | 7 | 14 | 5.94 | 118182.1 | 6988.2 | 0 | SI |
| ALTERNATIVA_5 | CAND-POL-02797 | PLATAFORMA Q | 7 | 7 | 14 | 11.96 | 110619.2 | 277.5 | 4 | SI |

## Interpretacion
Se evaluaron 1883 nodos con remanente significativo D/V; 101 cumplen la comparacion de mejora.
La alternativa mejor situada en la comparacion es CAND-POL-02759; cumple todas las condiciones de mejora.
El ranking prioriza eventos D/V exclusivos; no necesariamente devuelve los nodos de menor solape absoluto ni los mas proximos al punto actual.
Los nodos pueden estar en otra Plataforma. La distancia al punto actual se reporta sin imponer un radio arbitrario de busqueda.
Gi* en el sitio y nivel maximo en el radio son campos distintos; una interseccion con D/V no es una nueva prueba estadistica conjunta.
PERDIDOS_D/V/C y GANADOS_D/V/C muestran cambios de observaciones concretas: no se supone que mantener un conteo conserve exactamente los mismos eventos.
Cada alternativa se compara contra los mismos29 puntos fijos. Consultar PERDIDOS_D/V y GANADOS_D/V para no confundir nuevos conteos con conservar las mismas observaciones.
No se presupone mejora en todas las superficies: consultar AREA_HOTSPOT_D/V_NUEVA_M2 y sus valores actuales en elCSV antes de decidir.
La poblacion asociada es una estimacion areal CPV2022 urbana, no poblacion rural completa.
UPC y corredores son descriptivos, no criterios de seleccion. Ningun nodo se declara instalado ni validado en campo.
Las coordenadas actuales y las otras29, fuentes y visor se verifican sin cambios por hash. Sin commit/push.
La alternativa preferible mas cercana entre todos los nodos evaluados es CAND-POL-02705: 21.1m; 8D/V; solape 73.85%. Conserva 7/7 eventos exclusivos anteriores. No se incorpora automaticamente.

## Control local y mejora mas cercana
Este control admite mantener el mismo numero de D/V si baja el solape; no se confunde con la regla estricta de aumentar D/V utilizada en el ranking principal.
- LOCAL_PLATAFORMA_Q: CAND-POL-02764, PLATAFORMA Q, desplazamiento 158.8m; D/V 5/7, solape 34.55%; conserva 7/7 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
- MEJORA_MAS_CERCANA: CAND-POL-02705, PLATAFORMA Q, desplazamiento 21.1m; D/V 4/4, solape 73.85%; conserva 7/7 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
- CERCANA_CONSERVA_EVENTOS: CAND-POL-02705, PLATAFORMA Q, desplazamiento 21.1m; D/V 4/4, solape 73.85%; conserva 7/7 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
- MENOR_SOLAPE_LOCAL_CONSERVA_EVENTOS: CAND-POL-02768, PLATAFORMA Q, desplazamiento 171.6m; D/V 5/7, solape 32.70%; conserva 7/7 eventos exclusivos actuales. Menor solape sin reducir D/V: SI. No incorporada.
