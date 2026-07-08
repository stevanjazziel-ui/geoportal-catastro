# Publicar el geoportal

El proyecto ya esta preparado como sitio estatico. La entrada principal es `index.html`, que redirige a `geoportal.html`.

## Opcion 1: GitHub Pages

1. Crea un repositorio nuevo en GitHub.
2. Sube todo el contenido de `D:\codex`.
3. En GitHub entra a `Settings > Pages`.
4. En `Build and deployment`, selecciona `Deploy from a branch`.
5. Elige la rama principal y la carpeta `/ (root)`.
6. Guarda y espera la URL publica.

### Asignaciones compartidas con GitHub Pages

Si vas a usar `tramites-iprus.html` y quieres que las asignaciones se vean en cualquier computadora:

1. publica el sitio con GitHub Pages
2. entra al modulo administrador
3. completa `GitHub owner`, `Repositorio` y `Rama`
4. pega un token personal de GitHub con permiso `Contents: Read and write`
5. pulsa `Guardar conexión GitHub`

Desde ese momento, cada asignación puede publicarse al repositorio y GitHub Pages reflejará el cambio cuando termine el redeploy.

## Opcion 2: Netlify

1. Entra a Netlify.
2. Crea un sitio nuevo desde un repositorio o arrastra la carpeta `D:\codex`.
3. El archivo `netlify.toml` ya indica que el sitio se publica desde la raiz.

### Nota para tramites compartidos

Netlify sigue siendo util si quieres un backend compartido inmediato.

El proyecto ya incluye:

- una Function en `netlify/functions/tramites-shared-state.js`
- almacenamiento compartido para asignaciones
- lectura y escritura automatica desde `tramites-iprus.html`

En GitHub Pages tambien puedes compartir asignaciones, pero la publicacion ocurre escribiendo `tramites-iprus-shared-state.js` en el repositorio y el cambio se vera cuando GitHub Pages termine de actualizar el sitio.

## Opcion 3: Vercel

1. Importa el proyecto en Vercel.
2. Publica sin framework.
3. `vercel.json` ya deja la configuracion minima lista.

## Nota importante

El archivo `CATASTRO_2026.geojson` pesa bastante. Si luego quieres mejor rendimiento, conviene simplificarlo, dividirlo por sectores o publicarlo desde GeoServer/PostGIS.
