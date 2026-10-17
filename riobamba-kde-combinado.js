/* Approved aggregate only. Original CMI points and case identifiers are not published. */
(function (root) {
  "use strict";
  const data = root.RIOBAMBA_KDE_COMBINADO;
  if (!data) throw new Error("Falta el KDE combinado aprobado");
  const url = "./data/seguridad-riobamba/KDE_COMBINADO_200M_20261017/kde-combinado-200m.png";
  let cached;
  const number = value => Number(value).toLocaleString("es-EC", {maximumFractionDigits: 2});
  function surface() {
    if (!cached) {
      const raw = atob(data.densityBase64);
      const bytes = Uint8Array.from(raw, char => char.charCodeAt(0));
      const grid = root.RIOBAMBA_CONFLICTIVITY_CORRECTION.urbanGrid;
      const density = new Float64Array(bytes.buffer);
      if (density.length !== grid.width * grid.height) throw new Error("Raster combinado incompleto");
      cached = {combined: true, scope: "URBANO", density, grid, width: grid.width, height: grid.height,
        bandwidth: data.bandwidth, records: data.records, maxDensity: data.visual.maxDensity,
        visual: data.visual, url};
    }
    return cached;
  }
  function legend() {
    const labels = ["Muy baja", "Baja", "Media", "Alta", "Muy alta"];
    return labels.map((label, i) => `<div class="legend-row"><span class="legend-swatch" style="background:${data.colors[i + 1]}"></span>${label}: ${number(data.colorStops[i])} - ${number(data.colorStops[i + 1])} registros/km&#178;</div>`).reverse().join("")
      + `<p>Hasta ${number(data.colorStops[0])}: transparente. Interpolacion continua; escala fija del estudio comparativo.</p><p>${data.period}. ${data.warning}</p>`;
  }
  function methodologyHtml() {
    return `<h3>KDE combinado provisional: 200 m</h3><p>10.731 registros: 9.915 ECU911 + 816 CMI. ${data.period}.</p><p>EPSG:32717; celda 20 m; peso 1 por registro; kernel gaussiano normalizado y truncado a 200 m; mascara urbana comun, sin correccion de borde. Coordenadas originales conservadas.</p><p>${data.warning} Hay 130 pares candidatos no confirmados; no se eliminaron registros por distancia. Convivencia conserva su volumen original. No es una superficie exclusivamente de robos.</p><p>Publicacion agregada: no incluye puntos ni expedientes CMI. La superficie es fija, sin filtros por fecha o categoria; no representa cobertura visual de camaras. Gi* y el KDE rural permanecen separados.</p>`;
  }
  root.RiobambaCombinedKde = {data, surface, legend, methodologyHtml,
    overlay: () => ({url, bounds: data.bounds, records: data.records, bandwidth: data.bandwidth,
      period: data.period, warning: data.warning}),
    level: value => value <= data.colorStops[0] ? "Sin concentracion visible / muy baja"
      : value < data.colorStops[3] ? "Baja / media" : value < data.colorStops[4] ? "Alta" : "Muy alta"};
})(window);
