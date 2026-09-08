# Publicar el geoportal

El proyecto se publica por GitHub Pages. La entrada principal es `index.html`, que redirige a `geoportal.html`.

## GitHub Pages

1. Sube el contenido del repositorio a GitHub.
2. En GitHub entra a `Settings > Pages`.
3. En `Build and deployment`, selecciona `Deploy from a branch`.
4. Elige la rama principal y la carpeta `/ (root)`.
5. Guarda y espera la URL pública.

## Asignaciones compartidas con GitHub Pages

Si vas a usar `tramites-iprus.html` con estado compartido entre computadoras:

1. Entra al módulo administrador.
2. Completa `GitHub owner`, `Repositorio` y `Rama`.
3. Pega un token personal de GitHub con permiso `Contents: Read and write`.
4. Pulsa `Guardar conexión GitHub`.

Desde ese momento, el estado compartido se publica al repositorio y GitHub Pages refleja el cambio cuando termina el redeploy.

## Nota importante

El archivo `CATASTRO_2026.geojson` pesa bastante. Si luego quieres mejor rendimiento, conviene simplificarlo, dividirlo por sectores o publicarlo desde GeoServer/PostGIS.
