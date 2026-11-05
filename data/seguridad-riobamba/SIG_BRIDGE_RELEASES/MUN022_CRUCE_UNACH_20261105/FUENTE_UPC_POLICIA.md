# Ubicaciones de infraestructura policial

La capa publicada `UPC_INFRAESTRUCTURA` se sustituyó con los registros del archivo oficial `UPC.xls` entregado por la Policía. Se incorporaron los 18 registros cuyo código de distrito es `06D01` (Riobamba), con coordenadas transformadas desde longitud/latitud WGS 84 a EPSG:32717.

El GeoPackage conserva también los 33 registros completos en `UPC_POLICIA_FUENTE_33`; los 15 registros de otros distritos no se mezclan en la capa activa de Riobamba. `ATTR_JSON` conserva los atributos de origen. `ID_INFRA` usa un identificador derivado del número de fila `Nro` para mantener cada registro rastreable.

El paquete mantiene sin cambios las capas de cámaras y el resto de las capas existentes. La exportación `UPC_INFRAESTRUCTURA.geojson` contiene los mismos 18 registros en EPSG:4326.

SHA-256 del Excel de origen: `99961955c17a2613b8dbaff9318bee0dbf9c6e0e263c1c0c4b5ed9777302b095`.
