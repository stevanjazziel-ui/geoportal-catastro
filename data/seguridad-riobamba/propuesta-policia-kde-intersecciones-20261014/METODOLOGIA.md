# Alternativa policial por KDE e intersecciones

Corrida separada: no sustituye la propuesta publicada. Se conservan las 103 cámaras inventariadas y las 50 propuestas municipales.

La selección prioriza la integral de KDE urbano de Delincuencia + Violencia que aporta cada radio de 200 m fuera de la cobertura acumulada. La malla y el kernel replican los parámetros del visor: EPSG:32717, celda 20 m, kernel gaussiano truncado y normalizado, peso 1 por registro. Los candidatos deben ser nodos de grado ≥3 coincidentes con vías Expresa, Arterial A/B/P o Colectora, dentro de las 18 Plataformas. Cada buffer nuevo debe intersectar la cobertura base o una propuesta previamente elegida. Gi* queda como referencia; no se recalcula.

La unión de buffers solo indica continuidad geométrica de proximidad. No equivale a línea de vista real: para certificarla se requieren altura y orientación de cámaras, edificios/obstáculos y óptica. Las coordenadas son propuestas para revisión de campo.

Consultar RESULTADOS.json, MOVIMIENTOS_POLICIA_30.csv y PROPUESTA_POLICIA_30_KDE_INTERSECCIONES.geojson.
