# Guia rapida para nuevas isocronas categorizadas

Este flujo ya quedo preparado para reutilizar la misma metodologia con nuevas capas como educacion, salud u otra similar.

## 1. Colocar el ZIP fuente

Pon el archivo ZIP con el shapefile en `D:\codex` o deja anotada su ruta completa.

## 2. Registrar la nueva capa

Edita [riobamba_categorized_isocronas_config.py](D:\codex\riobamba_categorized_isocronas_config.py) y agrega una nueva entrada dentro de `CATEGORIZED_ISOCHRONE_CONFIGS`.

Debes definir:

- `key`: nombre corto, por ejemplo `seguridad`
- `display_name`: nombre visible
- `output_suffix`: sufijo para los archivos de salida
- `source_zip_candidates`: una o varias rutas posibles del ZIP

El script ya busca estos campos de forma flexible dentro del shapefile:

- categoria: `CATEGORIA`, `categoria`, `Categoria`
- nombre: `Nombre_Equ`, `nombre`, `NOMBRE`
- tipo: `Equipamien`, `equipamiento`, `EQUIPAMIEN`
- codigo: `codigo`, `CODIGO`, `Codigo`

Las categorias activas siguen esta regla:

- `BARRIAL` = 400 m
- `ZONAL` = 1000 m
- `CANTONAL` = no genera isocrona

## 3. Ver las capas registradas

```powershell
python build-riobamba-categorized-isocronas.py --list
```

## 4. Generar una capa puntual

```powershell
python build-riobamba-categorized-isocronas.py salud --exports
```

Eso hace dos cosas:

- genera GeoJSON y estadisticas
- actualiza los ZIP de descarga en `D:\codex\riobamba-censo-data\shp`

## 5. Generar todas las capas categorizadas

```powershell
python build-riobamba-categorized-isocronas.py --all --exports
```

## 6. Scripts rapidos ya listos

Si quieres seguir usando comandos cortos, estos wrappers siguen funcionando:

```powershell
python build-riobamba-educacion-categorizada-isocronas.py
python build-riobamba-salud-categorizada-isocronas.py
python build-riobamba-isochrone-shapefile.py
```

## 7. Archivos que se actualizan

Resultados principales:

- `D:\codex\riobamba-censo-data\riobamba_<capa>.geojson`
- `D:\codex\riobamba-censo-data\riobamba_<capa>_stats.json`
- `D:\codex\riobamba-censo-data\riobamba_isocronas_<capa>.geojson`
- `D:\codex\riobamba-censo-data\riobamba_isocronas_<capa>_stats.json`

Descargas:

- ZIP por cada isocrona separada
- ZIP con puntos de inicio
- `manifest.json` actualizado para el portal
