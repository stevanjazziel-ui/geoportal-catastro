/* Separate full-inventory scenario; the agreed replacement-camera baseline is read-only. */
window.createRiobambaInventoryDeficit = function (api) {
  const {coverage, baseline, inventory, elements, esc, fmt, metricBars} = api;
  const pct = (value, total) => total > 0 ? value / total * 100 : null;
  const percent = (value) => value == null ? "No disponible" : `${value.toFixed(1)}%`;
  const area = (value) => `${value.toFixed(3)} km²`;
  const scenario = () => coverage.scenarios[api.radius()];
  const cameras = () => inventory.filter((camera) => coverage.metadata.locatedIds.includes(camera.id));
  const rows = () => {
    const coveredIds = new Set(scenario().incidentIdsCovered);
    const events = api.events();
    return api.platforms().filter((platform) => !api.selected() || platform.platformName === api.selected()).map((platform) => {
      const row = scenario().byPlatformName[platform.platformName];
      const original = baseline.cameraScenarios[api.radius()].byPlatformName[platform.platformName];
      const records = events.filter((event) => api.eventPlatform(event) === platform.platformName);
      const coveredIncidents = records.filter((event) => coveredIds.has(event.id)).length;
      return {...row, platformRecord: platform, label: platform.platform,
        uncoveredAreaKm2: row.areaKm2 - row.coveredAreaKm2,
        uncoveredPct: 100 - row.coveredPct, originalUncoveredPopulation: original.uncoveredPopulation,
        originalCoveredPopulation: original.coveredPopulation,
        incidents: records.length, coveredIncidents, uncoveredIncidents: records.length - coveredIncidents};
    });
  };
  const totals = () => {
    const selected = rows();
    const result = Object.fromEntries(["population", "coveredPopulation", "uncoveredPopulation", "areaKm2", "coveredAreaKm2", "uncoveredAreaKm2", "cameras", "incidents", "uncoveredIncidents", "originalCoveredPopulation", "originalUncoveredPopulation"].map((key) => [key, selected.reduce((sum, row) => sum + row[key], 0)]));
    return {...result, coveredPct: pct(result.coveredPopulation, result.population), coveredAreaPct: pct(result.coveredAreaKm2, result.areaKm2)};
  };
  const limitations = "Cobertura potencial, no alcance visual ni operatividad verificada. Ubicaciones aproximadas. Población estimada mediante intersección areal de manzanas CPV 2022; no supone que toda una manzana esté cubierta. Ámbito: unión de las 18 Plataformas. No mide peligrosidad ni prioridad de intervención.";
  const narrative = () => {
    const total = totals();
    return `${fmt(total.uncoveredPopulation)} habitantes estimados quedan fuera del escenario del inventario completo (radio ${api.radius()} m). Frente a las 31 para cambio, la unión del inventario cubre potencialmente a ${fmt(total.coveredPopulation - total.originalCoveredPopulation)} habitantes adicionales en el ámbito seleccionado. No se suman coberturas superpuestas.`;
  };
  function renderMetrics() {
    const total = totals();
    const cards = [["Inventario completo", coverage.metadata.totalRecords], ["Cámaras ubicadas · ámbito seleccionado", total.cameras],
      ["Sin coordenadas · inventario", coverage.metadata.pendingRecords.length], ["Población fuera del escenario", total.uncoveredPopulation],
      ["Territorio fuera de cobertura", area(total.uncoveredAreaKm2)], ["Escenario · radio", `${api.radius()} m`]];
    elements.summary.innerHTML = cards.map(([label, value]) => `<div class="card"><span>${esc(label)}</span><strong>${typeof value === "number" ? fmt(value) : esc(value)}</strong></div>`).join("");
  }
  function renderGraphics() {
    const total = totals();
    const selected = rows();
    const table = selected.map((row) => `<tr class="selectable-row" data-inventory-deficit-platform="${esc(row.platformName)}"><td>${esc(row.label)}</td><td>${fmt(row.population)}</td><td>${row.cameras}</td><td>${fmt(row.coveredPopulation)}</td><td>${fmt(row.uncoveredPopulation)}</td><td>${percent(row.uncoveredPct)}</td><td>${area(row.uncoveredAreaKm2)}</td><td>${fmt(row.originalUncoveredPopulation)}</td><td>${row.uncoveredIncidents} / ${row.incidents}</td></tr>`).join("");
    elements.graphicAnalysis.innerHTML = `${metricBars("Población fuera del escenario por Plataforma · inventario completo", selected.map((row) => ({label: row.label, value: row.uncoveredPopulation, color: "#c86670"})), Math.max(...selected.map((row) => row.uncoveredPopulation), 1), "#c86670")}
      <div class="graphic-card"><h3>Población según cobertura · inventario completo</h3><div class="coverage-donut" style="--covered:${total.coveredPct || 0}%;--partial:${total.coveredPct || 0}%"><strong>${percent(total.coveredPct)}<br>cubierta</strong></div><p>Potencialmente cubierta: ${fmt(total.coveredPopulation)} habitantes</p><p>Fuera de cobertura: ${fmt(total.uncoveredPopulation)} habitantes</p></div>
      <div class="graphic-card"><h3>Comparación de universos · radio ${api.radius()} m</h3><table class="mini-table"><thead><tr><th>Universo</th><th>Pob. cubierta</th><th>Pob. fuera</th><th>% cubierta</th></tr></thead><tbody><tr><td>31 para cambio</td><td>${fmt(total.originalCoveredPopulation)}</td><td>${fmt(total.originalUncoveredPopulation)}</td><td>${percent(pct(total.originalCoveredPopulation, total.population))}</td></tr><tr><td>${coverage.metadata.totalRecords} inventariadas · ${coverage.metadata.locatedRecords} ubicadas</td><td>${fmt(total.coveredPopulation)}</td><td>${fmt(total.uncoveredPopulation)}</td><td>${percent(total.coveredPct)}</td></tr></tbody></table></div>
      <div class="graphic-card"><h3>Indicadores por Plataforma · inventario completo</h3><table class="mini-table"><thead><tr><th>Plat.</th><th>Población</th><th>Cám. ubicadas</th><th>Pob. cubierta</th><th>Pob. fuera</th><th>% pob. fuera</th><th>Área fuera</th><th>Pob. fuera con 31</th><th>Incidentes fuera / analizados</th></tr></thead><tbody>${table}</tbody></table><button type="button" id="exportInventoryDeficit">Exportar indicadores CSV</button></div>
      <div class="support-panel"><h3>¿Qué nos dicen los datos?</h3><p>${esc(narrative())}</p><p>${esc(limitations)}</p></div>`;
    document.querySelectorAll("[data-inventory-deficit-platform]").forEach((node) => node.addEventListener("click", () => api.selectPlatform(node.dataset.inventoryDeficitPlatform, true)));
    document.getElementById("exportInventoryDeficit").addEventListener("click", exportCsv);
  }
  function renderDetail(platform) {
    elements.detailTitle.textContent = platform?.platformName || "Déficit · inventario completo";
    const total = totals();
    const metrics = [["Población analizada", fmt(total.population)], ["Población potencialmente cubierta", fmt(total.coveredPopulation)], ["Población fuera del escenario", fmt(total.uncoveredPopulation)], ["% población cubierta", percent(total.coveredPct)], ["Área potencialmente cubierta", area(total.coveredAreaKm2)], ["Área fuera de cobertura", area(total.uncoveredAreaKm2)], ["% territorio cubierto", percent(total.coveredAreaPct)], ["Cámaras ubicadas en el ámbito", total.cameras], ["Radio", `${api.radius()} m`]];
    const pending = coverage.metadata.pendingRecords;
    const locationStatus = pending.length
      ? `<details><summary>Registros pendientes de ubicación (${pending.length})</summary>${pending.map((camera) => `<p>${esc(camera.id)} · ${esc(camera.address)}</p>`).join("")}</details>`
      : `<p>${coverage.metadata.locatedRecords} equipos localizados en ${coverage.metadata.uniqueSites} emplazamientos; originales conservados.</p>`;
    elements.detail.innerHTML = `${platform ? '<div id="inventoryDeficitMiniMap" class="coverage-mini-map"></div>' : "<p>Selecciona una Plataforma para ver su mini mapa e indicadores.</p>"}${metrics.map(([label, value]) => `<div class="mini-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("")}<h3>¿Qué nos dicen los datos?</h3><p>${esc(narrative())}</p>${locationStatus}<p>${esc(limitations)}</p>`;
    if (platform) api.miniMap("inventoryDeficitMiniMap", platform);
  }
  function methodologyHtml() {
    return `<h3>Déficit de videovigilancia · inventario completo</h3><p>Universo: ${coverage.metadata.totalRecords} registros únicos; ${coverage.metadata.locatedRecords} equipos localizados en ${coverage.metadata.uniqueSites} emplazamientos, ${coverage.metadata.pendingRecords.length} pendientes. Geometrías del cierre aceptado sin sobrescribir el inventario original. El análisis de las 31 para cambio se conserva separado.</p><p>Buffers de radio ${api.radius()} m calculados en EPSG:32717 y disueltos antes de intersectar el ámbito y las manzanas. Área fuera = área del ámbito menos cobertura disuelta. Población fuera = población analizada menos estimación areal cubierta. No se suman los resultados de las 31 y las restantes 72.</p><p>Fuente: cierre final de cámaras; población CPV 2022; incidentes originales clasificados para conflictividad (peso 1 por registro, filtros vigentes).</p><p>Procesamiento: ${esc(coverage.metadata.generatedAt)}</p><p>${esc(limitations)}</p>`;
  }
  function exportCsv() {
    const headers = ["Plataforma", "Poblacion", "Camaras_ubicadas", "Poblacion_cubierta", "Poblacion_fuera", "Porcentaje_poblacion_fuera", "Area_fuera_km2", "Poblacion_fuera_31", "Incidentes_fuera", "Incidentes_analizados", "Radio_m"];
    const values = rows().map((row) => [row.platformName, row.population, row.cameras, row.coveredPopulation, row.uncoveredPopulation, row.uncoveredPct, row.uncoveredAreaKm2, row.originalUncoveredPopulation, row.uncoveredIncidents, row.incidents, api.radius()]);
    const csv = [headers, ...values].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = `deficit-inventario-103-${api.radius()}m.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return {scenario, cameras, rows, totals, renderMetrics, renderGraphics, renderDetail, methodologyHtml};
};
