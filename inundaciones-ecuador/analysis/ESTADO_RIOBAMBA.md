# Riobamba: insumos recibidos y preparación hidráulica

Revisión del 12 de noviembre de 2026. Los originales se conservan en `riobamba-inputs`. No se modificaron archivos en Drive ni las hojas de cálculo.

## Trabajo terminado

- Descargados y leídos el ZIP de anegamientos, MDT y sus dos XML, caudales H0789, CSV retrospectivo, cuencas, máximos anuales de precipitación y cartografía de alcantarillas.
- Extraída la red del portal público conservando sus atributos originales, sin adoptar los 800 mm que el código usa como respaldo gráfico.
- Preparado `riobamba-preparacion.gpkg` con seis capas: red, nodos sin cotas asignadas, anotaciones de cotas, anotaciones hidráulicas, cuencas y estructuras de cruce/evacuación.
- Exportadas las series a CSV manteniendo los originales y las marcas de procedencia. Preparada una tabla de candidatos de asociación entre cotas CAD y nodos.
- Registradas las características y huellas de los insumos en `audit.json`.

## Resultados de la revisión

| Componente | Resultado | Consecuencia para el modelo |
| --- | --- | --- |
| Red del portal | 6.359 tramos y 4.933 nodos; 3.903 combinados, 1.803 pluviales y 653 colectores | Existe una base geométrica concreta para Riobamba |
| Diámetros | 417 tramos sin valor | Conservar NULL; no asumir 800 mm |
| Sentidos | 724 tramos marcados como dudosos por la fuente | Revisar contra cotas de fondo y planos |
| Topología | 86 identificadores de nodo con posiciones de sus extremos separadas más de 0,2 m | Revisar identidad y conexión antes de generar INP |
| Anotaciones CAD | 1.620 cotas y 483 anotaciones hidráulicas | El texto no permite asumir automáticamente cota de fondo, tapa o referencia vertical |
| Asociación preliminar | 358 nodos con una cota candidata a menos de 5 m; 15 tienen dos candidatas en ese radio | Candidatos para revisión, sin asignación hidráulica automática |
| MDT | 3.840 × 3.750 píxeles de aproximadamente 3 m; EPSG:31977 | Relieve local disponible; el XML no identifica el datum vertical |
| Cobertura MDT | 46,143 % del rectángulo tiene dato; 4.622 de los 4.933 nodos caen sobre dato válido | Delimitar el dominio válido; no convertir NoData en elevación cero |
| Anegamiento | 725.658 polígonos clasificados, EPSG:31977 | Su método, fecha de evento y profundidades no quedan establecidos por los campos inspeccionados; no es automáticamente una huella observada para calibración |
| Cartografía «Alcantarillado» | 264 estructuras AQ065 de cruce/evacuación | Es una capa diferente de la red de tuberías |
| H0789 Chibunga | 11.322 registros diarios, 1985–2015; 568 faltantes; marcas H y PDM | Preservar faltantes y procedencia. Confirmar unidades y significado de las marcas antes de calibrar |
| Precipitación | 77 máximos anuales, 1950–2026, acumulados de 1 h y 24 h | No es un hietograma. Verificar fuente, estación y completitud de 2026 |

## Lo que falta para ejecutar una red local verificable

Clasificar y vincular cotas de fondo y tapa a los nodos; revisar las conexiones y sentidos; definir descargas, materiales/rugosidades, captación de sumideros y estructuras; confirmar referencias verticales y el origen de las series. El dato diario no resuelve directamente picos subhorarios de inundación urbana. Para el Chibunga hacen falta geometría del lecho y condiciones de entrada/salida adecuadas al evento.

No se generó un INP usando cotas o diámetros supuestos. No se ha ejecutado una nueva simulación hidráulica local de Riobamba con estos insumos. El siguiente producto es la conciliación de las cotas y estructuras con su documentación de ingeniería; la tabla `cotas_candidatas_revision.csv` adelanta esa revisión.

Fuentes proporcionadas: [portal de red](https://alva-piva-ayuda.vercel.app/alcantarillado/), [anegamientos](https://drive.google.com/drive/folders/1f5qi1zbSJl6g9J0IG5x0AOOkJef4ZPcO), [Proyecto PIVA](https://drive.google.com/drive/folders/1GCHBInV71GKNds_kdjOS1FIEFK30fXuT). Los metadatos de creación de archivos no prueban la fecha del levantamiento.
