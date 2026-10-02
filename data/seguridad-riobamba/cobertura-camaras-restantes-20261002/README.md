# Cobertura de camaras restantes

Universo reproducible: IDs del inventario de 103 camaras menos los IDs de las
31 camaras acordadas para cambio. Resultado: 72 registros, 68 ubicados de forma
aproximada y 4 pendientes. No se considera que los 72 sean municipales ni se
afirma que esten operativos.

## Metodo

- Proyeccion WGS 84 / UTM 17S, EPSG:32717, orden longitud/latitud.
- Radios de 100, 150 y 200 metros; no diametros.
- Buffers con 64 segmentos por cuadrante y union disuelta: una superposicion
  no cuenta dos veces para area o poblacion.
- Geometria visual continua sin recorte por Plataforma; estadisticas por
  interseccion con las 18 Plataformas, el canton o el ambito rural operativo.
- Poblacion potencialmente cubierta: proporcion del area de cada manzana
  censal cubierta, manteniendo la metodologia y denominadores existentes.
  Se asume distribucion uniforme dentro de cada manzana. No estima personas
  observables, seguridad efectiva ni poblacion rural/cantonal completa.
- Las manzanas conservan su contorno, sin relleno de la unidad completa.
  El amarillo representa exclusivamente la geometria disuelta de los buffers
  metricos del escenario; una interseccion pequena no pinta toda la manzana.

## Resultados

| Radio | Union completa km2 | Cubierta en Plataformas km2 | Poblacion cubierta en Plataformas | Porcentaje poblacional |
|---|---:|---:|---:|---:|
| 100 m | 1.931989 | 1.545179 | 11.383 | 6,6% |
| 150 m | 4.107973 | 3.235132 | 25.464 | 14,8% |
| 200 m | 6.615516 | 5.095826 | 41.039 | 23,9% |

Poblacion analizada disponible en las Plataformas: 171.998 habitantes.
La union completa incluye sectores externos a las Plataformas; no se utiliza
su superficie como si toda correspondiera al area urbana operativa.

## Exclusiones

RIO-016-DOMO, RIO-017-FIJA, RIO-085-DOMO y RIO-103-DOMO: sin coordenadas.
Se conservan en el inventario y se reportan como pendientes, sin inventar
ubicaciones, asignar centroides ni generar cobertura para esos registros.

## Integracion Y Validacion

En Cobertura potencial de camaras y Cobertura poblacional se puede elegir
Para cambio (31) o Restantes (72). El radio y la Plataforma actualizan mapa,
KPI, dona territorial/poblacional independiente, comparacion, tabla, minimapa
y exportacion CSV. Las fichas de camara distinguen ambos universos.

Los ambitos cantonal y rural de las restantes tienen resultados de superficie;
la cobertura de poblacion completa se indica como No disponible.

Validacion: 114 combinaciones de universo/Plataforma/radio y 228 renders de
modulos. Comprobacion independiente de la geometria contra los buffers UTM,
la union, las intersecciones y el crecimiento monotono de los escenarios.
Pruebas de navegador: tres radios, Plataforma I, poblacion urbana, canton,
ambito rural, San Juan, clic de camara y retorno a las 31 para cambio.

Se verificaron los SHA-256 de las ocho fuentes protegidas: inventarios,
incidentes, KDE/Gi*, metodologia, diagnostico y accesibilidad policial.
No se recalculan ni sustituyen las brechas, cobertura institucional o
relaciones con Bulevares del universo de reemplazo por las restantes.

Reproducir desde la raiz del repositorio:

```powershell
python tools/build_remaining_camera_coverage.py
python tools/validate_remaining_camera_coverage.py
node tools/validate_camera_coverage_graphics.cjs
node tools/validate_camera_inventory.cjs
node tools/validate_selection_details.cjs
```

`VALIDACION_COBERTURA_RESTANTES.json` contiene los hashes, exclusiones y totales.
Las tres capas GeoJSON y las tres tablas CSV se guardan en esta carpeta.
