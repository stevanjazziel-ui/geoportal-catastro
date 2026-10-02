# Deficit potencial: inventario completo

Vista separada en Brechas; no sustituye al deficit del universo acordado de 31 camaras para cambio.

- Fuente reproducible: los 103 IDs unicos de `riobamba-camaras-inventario-data.js`.
- 99 registros con coordenadas aproximadas; 4 sin ubicacion excluidos de las geometrias, pero conservados en el inventario y las fichas.
- Radios 100, 150 y 200 metros (no diametros), EPSG:32717, buffers de 64 segmentos por cuadrante y union disuelta de las 99 ubicaciones. No sumar coberturas de grupos.
- Area no cubierta: union de las 18 Plataformas menos cobertura disuelta. No se recortan buffers individualmente a las Plataformas.
- Poblacion cubierta: estimacion areal CPV 2022 usando interseccion manzana/cobertura/Plataforma; mismo denominador de los analisis existentes. Fuera = total menos estimacion cubierta. No supone cobertura completa de manzanas parcialmente intersectadas.
- Camaras dentro de cada Plataforma: puntos reales del inventario, sin inventar ubicaciones para pendientes. La cobertura incorpora tambien las camaras externas cuyo buffer intersecta el ambito.
- Incidentes dentro/fuera: puntos originales clasificados para conflictividad, peso 1 por registro; filtros vigentes de tipologia y periodo.
- Las ubicaciones aproximadas, el alcance visual y la operatividad no verificada impiden interpretar cobertura potencial como cobertura efectiva o nivel de seguridad.
- No hay poblacion rural georreferenciada completa: deficit poblacional rural No disponible.

Reproducir: `python tools/build_remaining_camera_coverage.py --inventory`.
Validar: `python tools/validate_inventory_camera_coverage.py` y `node tools/validate_inventory_deficit.cjs`.

Los ocho archivos de insumos y resultados anteriores estan protegidos con SHA-256 en `VALIDACION_COBERTURA_INVENTARIO.json`. KDE, Gi*, poblacion, proximidad policial, 31 camaras y las demas brechas existentes no se recalculan ni se modifican.
