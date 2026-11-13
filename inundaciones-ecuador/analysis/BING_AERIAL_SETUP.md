# Bing Maps Aerial para el visor Cesium

La integración está preparada para Cesium ion, recurso 2 (Bing Maps Aerial). La cuenta del usuario ya contiene esa capa. No se utiliza Google Satellite ni se reutiliza el token predeterminado de la cuenta.

Configuración propuesta, pendiente de autorización para crear la credencial:

- Nombre: `Ecuador-Inundaciones-Bing-Aerial`.
- Único permiso: `assets:read`.
- Único recurso: 2, Bing Maps Aerial.
- Única URL permitida: `https://stevanjazziel-ui.github.io/geoportal-catastro/inundaciones-ecuador/` y sus subrutas.
- Se mantiene activo hasta revocarlo; Cesium ion no ofrece fecha de expiración según su documentación.
- Se guarda en el secreto de GitHub Actions `CESIUM_ION_PUBLIC_TOKEN` del repositorio `stevanjazziel-ui/geoportal-catastro`.
- El despliegue genera `imagery-config.js`. El token es público en el navegador por diseño: por eso debe limitarse al permiso, recurso y URL indicados. No concede escritura, gestión de tokens ni acceso al perfil.
- Las visitas consumen la cuota de imágenes de la cuenta. No se cambia de plan ni se acepta una compra.

El visor conserva una imagen Esri de respaldo mientras carga Bing y muestra cuál proveedor está activo. El respaldo limita las solicitudes al nivel 18; el acercamiento adicional amplía las imágenes existentes. Bing utiliza su proveedor oficial de Cesium y conserva sus créditos y tratamiento de teselas ausentes. Acercar la cámara no crea detalle óptico adicional ni mejora la resolución hidráulica.

La página envía el referente HTTPS completo para que Cesium ion pueda verificar la restricción por ruta. El token no se imprime en el registro de compilación ni se añade al historial Git. Los errores del proveedor no se imprimen porque podrían contener URLs con credenciales.

Referencias: https://cesium.com/learn/ion/cesium-ion-access-tokens/ y https://cesium.com/learn/cesiumjs-learn/cesiumjs-imagery/ .
