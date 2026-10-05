# Representacion KDE A/B/C

A: version publicada ddfdccd, mismo bandwidth 200 m y raster numerico, con la opacidad global anterior 0.68. B: P25 transparente; C: P30 transparente. Cada categoria usa su propio raster y sus percentiles de valores positivos. C reduce la suma de opacidad de las celdas positivas <=P50 respecto de B, conservando todos los maximos locales >=P50 (vecindad inmediata de ocho celdas). Es un control visual descriptivo, no una prueba estadistica ni un criterio de peligrosidad.

Rampa continua YlOrRd con alpha 0/65/115/165/200/215 en P30/P50/P75/P90/P95/max. Opacidad maxima 84.3%; no se aplica otra opacidad global ni suavizado. Densidades en eventos/km2; EPSG:32717, celda 20 m, kernel y peso 1 originales. No cambia ningun valor ni dato original. Los colores relativos no comparan magnitudes absolutas entre categorias.

TODOS: excluye categorias institucionales/revision urbanas; fuera del ambito urbano se reporta separadamente. Gi*, rural, camaras, corredores, brechas y geometrías quedan intactos. Publicacion autorizada por el usuario el 5 de octubre de 2026, despues de revisar A/B/C.
