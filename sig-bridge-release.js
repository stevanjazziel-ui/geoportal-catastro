/* Small release pointer; never cache a previous data version as the approved one. */
"use strict";
window.RIOBAMBA_SIG_RELEASE_READY = (async function () {
  const response = await fetch("./sig-bridge-active.json", { cache: "no-store" });
  if (!response.ok) throw new Error("No se pudo verificar la version de datos SIG");
  const release = await response.json();
  if (release.root !== null && !/^\.\/data\/seguridad-riobamba\/SIG_BRIDGE_RELEASES\/[A-Za-z0-9_-]+\/$/.test(release.root)) {
    throw new Error("Version SIG no valida");
  }
  window.RIOBAMBA_SIG_RELEASE_ROOT = release.root;
  if (release.coverageData) {
    if (!release.root || release.coverageData !== "riobamba-brechas-actualizadas-data.js") throw new Error("Dependencias SIG no validas");
    await new Promise(function (resolve, reject) {
      const script = document.createElement("script");
      script.src = release.root + release.coverageData;
      script.onload = function () {
        window.RIOBAMBA_SIG_RELEASE_GAPS = window.RIOBAMBA_UPDATED_GAPS;
        resolve();
      };
      script.onerror = function () { reject(new Error("No se pudieron cargar las coberturas actualizadas")); };
      document.head.appendChild(script);
    });
  }
})().catch(function (error) {
  const report = function () { document.body.textContent = error.message; };
  if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", report);
  else report();
  throw error;
});
