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

Si vas a usar `tramites-iprus.html` solo con GitHub Pages y quieres que las asignaciones se vean en cualquier computadora:

1. publica el sitio con GitHub Pages
2. entra al modulo administrador
3. completa `GitHub owner`, `Repositorio` y `Rama`
4. pega un token personal de GitHub con permiso `Contents: Read and write`
5. pulsa `Guardar conexión GitHub`

Desde ese momento, el estado compartido puede publicarse al repositorio y GitHub Pages reflejará el cambio cuando termine el redeploy.

## Opcion 2: Netlify

1. Entra a Netlify.
2. Crea un sitio nuevo desde un repositorio o arrastra la carpeta `D:\codex`.
3. El archivo `netlify.toml` ya indica que el sitio se publica desde la raiz.

### Backend automatico para tramites compartidos

Si quieres cero configuracion en las computadoras de trabajo, esta es la opcion correcta.

El proyecto ya incluye:

- una Function en `netlify/functions/tramites-shared-state.js`
- almacenamiento compartido para asignaciones, revisiones, evidencia grafica, borradores, cola de tareas y bitacora de cambios
- lectura y escritura automatica desde `tramites-iprus.html`
- refresco automatico del estado compartido entre computadoras
- un archivo `tramites-iprus-config.js` para apuntar a un backend remoto si mantienes el frontend en GitHub Pages

Tienes dos formas de usarlo:

1. publica todo el sitio en Netlify:
   el frontend y el backend quedan en el mismo dominio y no necesitas token en ninguna computadora
2. deja el frontend en GitHub Pages y publica solo el backend en Netlify:
   en `tramites-iprus-config.js` coloca `backendBaseUrl` con la URL publica de Netlify y el portal usara ese backend automaticamente

Con esta opcion ya no hace falta pegar tokens en las computadoras para asignar, revisar o subir evidencia.

## Opcion 3: Vercel

1. Importa el proyecto en Vercel.
2. Publica sin framework.
3. `vercel.json` ya deja la configuracion minima lista.

## Nota importante

El archivo `CATASTRO_2026.geojson` pesa bastante. Si luego quieres mejor rendimiento, conviene simplificarlo, dividirlo por sectores o publicarlo desde GeoServer/PostGIS.
