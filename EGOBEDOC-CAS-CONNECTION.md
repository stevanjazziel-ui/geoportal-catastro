# Conexión a eGOB/e-Bedoc con CAS

Este documento resume la manera correcta de conectar el módulo de trámites con el portal:

- Portal protegido: `https://egobedoc.gadmriobamba.gob.ec:8081/my/passig_citizen`
- Autenticación centralizada: `https://egob.gadmriobamba.gob.ec:8443/cas/login`
- Fecha de verificación del flujo: `2026-07-07`

## Hallazgos confirmados

1. La ruta `https://egobedoc.gadmriobamba.gob.ec:8081/my/passig_citizen` no entrega datos públicos.
2. La solicitud redirige al sistema CAS con un parámetro `service` que apunta al callback:
   - `https://egobedoc.gadmriobamba.gob.ec:8081/auth/cas/callback?...`
3. La página de autenticación observada corresponde a:
   - `Apereo CAS 6.6.15`
4. El formulario CAS usa `POST` a:
   - `https://egob.gadmriobamba.gob.ec:8443/cas/login`
5. Los campos relevantes del formulario son:
   - `username`
   - `password`
   - `execution`
   - `_eventId=submit`
   - `geolocation`

## Flujo correcto de conexión

1. El backend solicita la ruta protegida `/my/passig_citizen`.
2. El servidor devuelve redirección a `CAS`.
3. El backend descarga el HTML del login CAS.
4. El backend extrae el token oculto `execution` y conserva la cookie de sesión.
5. El backend envía `POST` con usuario, clave y campos ocultos.
6. CAS redirige al callback de `egobedoc`.
7. `egobedoc` crea la sesión autenticada.
8. El backend ya puede consultar la bandeja y otras rutas autenticadas.

## Arquitectura recomendada

No conectar el frontend estático directamente al portal.

### Recomendado

- Un servicio backend propio:
  - inicia sesión en CAS
  - consulta `/my/passig_citizen`
  - transforma la respuesta a JSON
  - expone endpoints internos para el módulo `tramites-iprus.html`

### Por qué

- El frontend no debe almacenar credenciales.
- CAS usa cookies y tokens dinámicos.
- Desde navegador aparecerán problemas de `CORS`, sesión y seguridad.
- La integración será más mantenible y auditable desde backend.

## Archivo base incluido

Se agregó este cliente de referencia:

- [connect-egobedoc-cas.py](D:\codex\connect-egobedoc-cas.py)

### Modos disponibles

1. `inspect`
   - inspecciona el flujo CAS sin autenticarse
2. `login`
   - intenta iniciar sesión y descargar una ruta protegida

### Ejemplos

```powershell
python connect-egobedoc-cas.py inspect
```

```powershell
python connect-egobedoc-cas.py login --username USUARIO --password CLAVE --save-html outputs\passig_citizen.html
```

## Siguiente paso real

Para completar la conexión faltan credenciales válidas y revisar una sesión autenticada.

Con eso se debe:

1. guardar el HTML de `/my/passig_citizen`
2. identificar si la bandeja se renderiza en HTML directo o con llamadas `XHR/JSON`
3. ubicar los endpoints internos para:
   - listar trámites
   - consultar detalle
   - actualizar estado o asignación

## Riesgos a considerar

- Si el portal depende de vistas HTML y no de API, puede tocar scraping.
- Si el login incluye MFA, CAPTCHA o pasos extra, el backend deberá adaptarse.
- Si el servidor valida IP, `User-Agent` o headers especiales, habrá que reproducirlos.
- Si el entorno local bloquea tráfico saliente para `Python` o `Node`, conviene ejecutar el conector en otro servidor o máquina autorizada.
