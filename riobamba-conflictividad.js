/* Derived classification and metric KDE. The original source remains immutable. */
(function (root) {
  "use strict";
  const data = root.RIOBAMBA_CONFLICTIVITY_CORRECTION;
  const classes = ["DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA", "ACTIVIDAD_INSTITUCIONAL", "OTROS_REVISION"];
  const colors = [[255,255,178], [254,204,92], [253,141,60], [240,59,32], [189,0,38]];
  function applyDataset(source) {
    return {...source, events: source.events.map((event) => {
      const category = data.dictionary[event.subtype];
      if (!category) throw new Error(`Subtipo sin clasificar: ${event.subtype}`);
      const analyticalClassId = classes.indexOf(category) + 1;
      const recurrence = data.recurrenceById[event.id];
      return {...event, category, CATEGORIA_ANALITICA: category, analyticalClassId,
        originalClassificationStatus: event.classificationStatus,
        classificationStatus: analyticalClassId === 5 ? "EXCLUIDO_PENDIENTE_REVISION" : "APROBADO_OPERATIVO",
        hotspotEligible: analyticalClassId <= 3, analyticalWeight: 1,
        RECURRENCIA_XY: recurrence,
        FLAG_COORD: recurrence === 1 ? "NORMAL" : recurrence < 10 ? "REPETIDA" : recurrence < 30 ? "ALTA_REPETICION" : "MUY_ALTA_REPETICION"};
    })};
  }
  function parameters(scope, category) {
    if (scope === "URBANO") {
      const records = ["TODOS", "__ALL__"].includes(category)
        ? classes.slice(0, 3).reduce((n, name) => n + data.parameters.URBANO[name].records, 0)
        : data.parameters.URBANO[category]?.records;
      if (records == null) throw new Error(`Universo KDE no definido: ${scope}/${category}`);
      return {bandwidth: 200, cellSize: data.urbanGrid.cellSize, records, selection: "Radio urbano fijo solicitado; no altera el KDE rural."};
    }
    const result = data.parameters[scope]?.[category];
    if (!result) throw new Error(`Universo KDE no definido: ${scope}/${category}`);
    return result;
  }
  function calculate(points, grid, bandwidth) {
    const width = grid.width, height = grid.height, size = grid.cellSize;
    const west = grid.metricBounds[0][0], north = grid.metricBounds[1][1];
    const density = new Float64Array(width * height), grouped = new Map();
    points.forEach((p) => {
      if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) throw new Error(`Coordenada metrica invalida: ${p.id}`);
      const key = `${p.x}:${p.y}`;
      if (!grouped.has(key)) grouped.set(key, {x: p.x, y: p.y, count: 0});
      grouped.get(key).count++;
    });
    const radius = Math.ceil(bandwidth / size), h2 = bandwidth * bandwidth;
    const normalization = 1e6 / (2 * Math.PI * h2 * (1 - Math.exp(-.5)));
    grouped.forEach((p) => {
      const cx = Math.floor((p.x - west) / size), cy = Math.floor((north - p.y) / size);
      for (let y = Math.max(0, cy - radius - 1); y <= Math.min(height - 1, cy + radius + 1); y++) {
        const dy = north - (y + .5) * size - p.y;
        for (let x = Math.max(0, cx - radius - 1); x <= Math.min(width - 1, cx + radius + 1); x++) {
          const dx = west + (x + .5) * size - p.x, d2 = dx * dx + dy * dy;
          if (d2 <= h2) density[y * width + x] += p.count * normalization * Math.exp(-.5 * d2 / h2);
        }
      }
    });
    const mask = new Set(grid.mask);
    let maxDensity = 0;
    for (let i = 0; i < density.length; i++) {
      if (!mask.has(i)) density[i] = 0;
      maxDensity = Math.max(maxDensity, density[i]);
    }
    return {density, width, height, maxDensity, grid, bandwidth, records: points.length};
  }
  function color(value) {
    const t = Math.min(1, Math.log1p(value) / Math.log1p(data.colorReference));
    const position = t * 4, index = Math.min(3, Math.floor(position)), fraction = position - index;
    return [...colors[index].map((c, channel) => Math.round(c + (colors[index + 1][channel] - c) * fraction)), value > 0 ? Math.round(255 * Math.pow(t, .65)) : 0];
  }
  function renderRaster(surface) {
    const grid = surface.grid, canvas = document.createElement("canvas");
    canvas.width = grid.width; canvas.height = grid.height;
    const context = canvas.getContext("2d"), image = context.createImageData(grid.width, grid.height);
    const visual = surface.scope === "URBANO" ? (surface.visual || visualStatistics(surface)) : null;
    grid.warpIndex.forEach((source, index) => {
      if (source >= 0) image.data.set(visual ? urbanColor(surface.density[source], visual) : color(surface.density[source]), index * 4);
    });
    context.putImageData(image, 0, 0);
    return canvas.toDataURL("image/png");
  }
  const urbanColors = [[255,255,178], [254,217,118], [254,178,76], [253,141,60], [240,59,32], [189,0,38]];
  function visualStatistics(surface) {
    const positive = Array.from(surface.density).filter(v => v > 0).sort((a, b) => a - b);
    const percentile = (p) => {
      if (!positive.length) return 0;
      const position = (positive.length - 1) * p, index = Math.floor(position);
      return positive[index] + (positive[Math.min(index + 1, positive.length - 1)] - positive[index]) * (position - index);
    };
    const minDensity = surface.grid.mask.length ? surface.grid.mask.reduce((n, i) => Math.min(n, surface.density[i]), Infinity) : 0;
    return {minDensity, maxDensity: surface.maxDensity, positiveCells: positive.length,
      p25: percentile(.25), p30: percentile(.30), p50: percentile(.50), p75: percentile(.75), p90: percentile(.90), p95: percentile(.95)};
  }
  const urbanTransparentPercentile = 30;
  function urbanColor(value, stats, thresholdPercentile = urbanTransparentPercentile) {
    const threshold = thresholdPercentile === 30 ? stats.p30 : stats.p25;
    if (!(value > threshold)) return [255,255,178,0];
    const stops = [threshold, stats.p50, stats.p75, stats.p90, stats.p95, stats.maxDensity];
    const alpha = [0, 65, 115, 165, 200, 215];
    let i = 0;
    while (i < 4 && value > stops[i + 1]) i++;
    const fraction = stops[i + 1] > stops[i] ? Math.min(1, (value - stops[i]) / (stops[i + 1] - stops[i])) : 1;
    return [...urbanColors[i].map((c, channel) => Math.round(c + (urbanColors[i + 1][channel] - c) * fraction)),
      Math.round(alpha[i] + (alpha[i + 1] - alpha[i]) * fraction)];
  }
  function concentrationLevel(value, stats) {
    if (!(value > stats.p30)) return "Sin concentracion visible / muy baja";
    return value <= stats.p50 ? "Muy baja" : value <= stats.p75 ? "Baja" : value <= stats.p90 ? "Media" : value <= stats.p95 ? "Alta" : "Muy alta";
  }
  function sampleDensity(surface, lat, lng) {
    const {grid} = surface, [[south, west], [north, east]] = grid.bounds;
    const x = Math.floor((lng - west) / (east - west) * grid.width);
    const y = Math.floor((north - lat) / (north - south) * grid.height);
    if (x < 0 || y < 0 || x >= grid.width || y >= grid.height) return null;
    const index = grid.warpIndex[y * grid.width + x];
    return index >= 0 ? surface.density[index] : null;
  }
  const number = (value) => Number(value).toLocaleString("es-EC", {maximumFractionDigits: 2});
  function urbanLegend(surface) {
    const s = surface.visual || visualStatistics(surface);
    const limits = [s.p30, s.p50, s.p75, s.p90, s.p95, s.maxDensity];
    const labels = ["Muy baja", "Baja", "Media", "Alta", "Muy alta"];
    return labels.map((label, i) => {
      const rgba = urbanColor((limits[i] + limits[i + 1]) / 2, s);
      return `<div class="legend-row"><span class="legend-swatch" style="background:rgba(${rgba.slice(0,3).join(',')},${rgba[3]/255})"></span>${label}: ${number(limits[i])} - ${number(limits[i + 1])} eventos/km&#178;</div>`;
    }).reverse().join("")
      + `<p>0 - P30 positivo (${number(s.p30)}): transparente. Transici&#243;n continua y opacidad variable. Escala propia del subconjunto, no comparable directamente por color entre categor&#237;as. Densidad descriptiva, no significancia estad&#237;stica.</p>`;
  }
  const legend = (surface) => surface?.scope === "URBANO" ? urbanLegend(surface) : colors.map((rgb, i) => {
    const limits = [0, .125, .375, .625, .875, 1];
    const lower = Math.expm1(Math.log1p(data.colorReference) * limits[i]);
    const upper = Math.expm1(Math.log1p(data.colorReference) * limits[i + 1]);
    return `<div class="legend-row"><span class="legend-swatch" style="background:rgb(${rgb.join(',')})"></span>${lower.toFixed(1)} - ${upper.toFixed(1)} eventos/km&#178;</div>`;
  }).join("") + "<p>Escala logar&#237;tmica fija compartida. Concentraci&#243;n de eventos registrados; no implica por s&#237; sola peligrosidad.</p>";
  function methodologyHtml(scope, category, surface) {
    if (scope === "URBANO") {
      const stats = surface && (surface.visual || visualStatistics(surface));
      return `<h3>KDE urbano - ${["TODOS", "__ALL__"].includes(category) ? "Todos los eventos anal&#237;ticos" : category}</h3><p>EPSG:32717; celda 20 m; bandwidth urbano fijo 200 m; peso 1 por registro. Kernel gaussiano truncado a 200 m, normalizado a volumen 1. Suma de contribuciones en una malla urbana com&#250;n, seguida de m&#225;scara del &#225;mbito operativo de 18 Plataformas. Sin promedios ni normalizaci&#243;n por Plataforma. Coordenadas y eventos coincidentes conservados.</p>
        <p>Solo DELINCUENCIA, VIOLENCIA y CONVIVENCIA con coordenadas v&#225;lidas y asignaci&#243;n espacial urbana. Los percentiles se calculan sobre las celdas positivas del subconjunto filtrado. Valores hasta P30 transparentes solo en la imagen: no se eliminan del raster num&#233;rico. Interpolaci&#243;n suave YlOrRd entre P30/P50/P75/P90/P95/m&#225;ximo; opacidad de 0 a 84 %. Sin suavizado adicional. El KDE rural conserva sus par&#225;metros.</p>
        ${stats ? `<table class="mini-table"><tbody>${[...["minDensity", "maxDensity"].map(k => [k === "minDensity" ? "Densidad m&#237;nima" : "Densidad m&#225;xima", stats[k]]), ...["p25", "p30", "p50", "p75", "p90", "p95"].map(k => [k.toUpperCase(), stats[k]])].map(([label, value]) => `<tr><th>${label}</th><td>${number(value)} eventos/km&#178;</td></tr>`).join("")}</tbody></table>` : ""}
        <p>Las concentraciones son componentes descriptivos con umbral 35 % del m&#225;ximo; no pruebas Gi*. La repetici&#243;n de coordenadas no acredita error ni peligrosidad. Menor bandwidth reduce suavizado; 200 m es una configuraci&#243;n solicitada, no un &#243;ptimo estad&#237;stico demostrado.</p><a href="./data/seguridad-riobamba/kde-visual-abc-20261005/index.html" target="_blank" rel="noopener">Comparaci&#243;n visual A/B/C y control num&#233;rico</a>`;
    }
    const rows = data.evaluations.filter((e) => e.scope === scope && e.category === category);
    const parameter = parameters(scope, category);
    const quality = data.quality.find((q) => q.AMBITO === scope && q.CATEGORIA === category);
    return `<h3>KDE ${scope} - ${category}</h3><p>EPSG:32717; celda ${parameter.cellSize} m; radio ${parameter.bandwidth} m; peso 1 por registro; kernel gaussiano truncado y normalizado a volumen 1. Densidad en eventos/km&#178;. Se suma antes de aplicar la m&#225;scara; no se fragmenta por Plataforma.</p>
      <p>Recomendaci&#243;n provisional por log-verosimilitud predictiva: se retiene fuera cada grupo XY completo durante la validaci&#243;n; todos sus registros se conservan en el resultado final. ${parameter.atCandidateBoundary ? "El valor elegido est&#225; en el extremo del intervalo ensayado; no acredita un &#243;ptimo fuera de esos candidatos." : ""}</p>
      <p>Universo completo utilizado para comparar radios, antes de los filtros exploratorios: ${quality.N_EVENTOS} eventos; ${quality.N_COORD_UNICAS} coordenadas &#250;nicas; repetici&#243;n m&#225;xima ${quality.MAX_REPETICION_XY}. Coordenadas repetidas no significan necesariamente error ni deben eliminarse autom&#225;ticamente.</p>
      <table class="mini-table"><thead><tr><th>Radio m</th><th>Validaci&#243;n</th><th>Concentraciones</th><th>&#193;rea influencia km&#178;</th><th>M&#225;ximo eventos/km&#178;</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${r.bandwidth}${r.recommended ? " *" : ""}</td><td>${r.cvMeanLogLikelihood.toFixed(3)}</td><td>${r.concentrations}</td><td>${r.influenceAreaKm2.toFixed(2)}</td><td>${r.maxDensityEventsKm2.toFixed(1)}</td></tr>`).join("")}</tbody></table>
      <p>Los componentes de esta comparaci&#243;n utilizan el mismo umbral dentro de cada clase. No son hotspots estad&#237;sticos. Escala cartogr&#225;fica logar&#237;tmica fija, compartida incluso al filtrar.</p>
      <a href="./data/seguridad-riobamba/correccion-conflictividad-20261001/comparacion.html" target="_blank" rel="noopener">Comparaci&#243;n completa, controles y resultados</a>`;
  }
  root.RiobambaConflictivity = {applyDataset, parameters, calculate, renderRaster, color, legend, methodologyHtml, classes, visualStatistics, urbanColor, urbanColors, concentrationLevel, sampleDensity, urbanTransparentPercentile};
})(window);
