# Publicar el geoportal

El proyecto ya esta preparado como sitio estatico. La entrada principal es `index.html`, que redirige a `geoportal.html`.

## Opcion 1: GitHub Pages

1. Crea un repositorio nuevo en GitHub.
2. Sube todo el contenido de `D:\codex`.
3. En GitHub entra a `Settings > Pages`.
4. En `Build and deployment`, selecciona `Deploy from a branch`.
5. Elige la rama principal y la carpeta `/ (root)`.
6. Guarda y espera la URL publica.

## Opcion 2: Netlify

1. Entra a Netlify.
2. Crea un sitio nuevo desde un repositorio o arrastra la carpeta `D:\codex`.
3. El archivo `netlify.toml` ya indica que el sitio se publica desde la raiz.

## Opcion 3: Vercel

1. Importa el proyecto en Vercel.
2. Publica sin framework.
3. `vercel.json` ya deja la configuracion minima lista.

## Nota importante

El archivo `CATASTRO_2026.geojson` pesa bastante. Si luego quieres mejor rendimiento, conviene simplificarlo, dividirlo por sectores o publicarlo desde GeoServer/PostGIS.
