# Google Satellite para Riobamba

Integración con `Google2DImageryProvider` oficial de Cesium. Capa verificada en la cuenta: **3830182, Google Maps 2D Satellite**. Token dedicado creado con autorización expresa el 16 de noviembre de 2026: `Riobamba-Google-Satellite`, solo `assets:read`, solo esa capa y solo la ruta pública del proyecto. No se publica como Google una imagen Esri.

## Mediante Cesium ion

1. Iniciar sesión en https://ion.cesium.com/ y añadir **Google Maps 2D Satellite** desde Asset Depot. Revisar la cuota y las condiciones de la cuenta antes de aceptar compromisos nuevos.
2. Copiar el identificador de esa capa. Crear un token dedicado `assets:read`, limitado a esa capa y a `https://stevanjazziel-ui.github.io/geoportal-catastro/inundaciones-ecuador/`.
3. Configurar las variables `ECUADOR_IMAGERY_PROVIDER=google-ion`, `CESIUM_IMAGERY_ASSET_ID=3830182` y `CESIUM_ION_PUBLIC_TOKEN` en el entorno de generación. Nunca publicar el token predeterminado o una credencial privada. El usuario autorizó distribuir esta credencial dedicada de navegador en el visor público; `dist/imagery-config.js` se distribuye junto al sitio y en su repositorio.

## Mediante Google Maps Platform

Alternativamente habilitar Map Tiles API con una clave de navegador restringida al sitio y a esa API. Requiere facturación de Google configurada. Usar `ECUADOR_IMAGERY_PROVIDER=google-maps` y `GOOGLE_MAPS_PUBLIC_KEY`.

Generar la configuración con `python write_imagery_config.py dist/imagery-config.js`. Las credenciales de navegador serán visibles por diseño y deben estar restringidas. La generación no está conectada automáticamente al workflow actual; la configuración autorizada se copia con los archivos del sitio. Revocar el token en Cesium ion lo invalida también en todas las versiones históricas.

Riobamba usa CesiumJS 1.145 y `baseLayer` para compatibilidad con el proveedor Google. El atlas conserva su versión anterior y muestra Esri hasta su migración independiente. Las simulaciones, el MDT y sus resoluciones permanecen iguales; más zoom satelital no añade detalle hidráulico. Los créditos de Google los gestiona el proveedor oficial.

Referencias: https://cesium.com/learn/cesiumjs/ref-doc/Google2DImageryProvider.html y https://developers.google.com/maps/documentation/tile/get-api-key .
