/* Current metric camera coverage, isolated from historical deficit calculations. */
window.createRiobambaCurrentCoverage = function (api) {
  "use strict";
  const el = api.elements;
  const labels = { current: "73 actuales", interventions: "110 intervenciones", combined: "183 en conjunto" };
  const colors = { current: "#1f5c99", interventions: "#cc3b78", combined: "#16876c" };
  const number = (value, digits = 0) => Number(value).toLocaleString("es-EC", { maximumFractionDigits: digits });
  const esc = api.esc;
  const rowHtml = rows => rows.map(([key, value]) => `<div class="mini-row"><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`).join("");
  const controls = document.getElementById("currentCoverageControls");
  const layerControls = document.getElementById("currentCoverageLayerControls");
  let data, loading, active = false, version = 0, group = "combined", extent = "city", fitNeeded = true;
  let selected = null;
  const clipCache = new Map();
  let activeClipKey = "";
  const layers = {};
  const toggles = { points: true, buffers: true, cantonBoundary: true, blocks: true, blockCoverage: true, platforms: true };
  const current = () => data.coverage.scenarios[String(api.radius())];
  const metrics = () => current().groups[group];
  function clear() { Object.values(layers).forEach(layer => api.map.removeLayer(layer)); }
  function clearLegacyLayers() { (api.layers() || []).forEach(layer => api.map.removeLayer(layer)); }
  function reset() { group = "combined"; extent = "city"; selected = null; fitNeeded = true; }
  function leave() {
    version++;
    if (!active) return;
    active = false; clear();
    el.workspace.classList.remove("current-coverage-active");
    layerControls.hidden = true;
  }
  async function load() {
    if (data) return;
    if (!loading) loading = (async () => {
      const root = window.RIOBAMBA_SIG_RELEASE_ROOT;
      if (!root) throw new Error("Falta el paquete SIG activo");
      const names = { coverage: "COBERTURA_73_110_183.json", existing: "CAMARAS_EXISTENTES_103_FINAL.geojson",
        municipal: "PROPUESTA_MUNICIPAL_50_FINAL.geojson", police: "PROPUESTA_POLICIA_30_FINAL.geojson", platforms: "PLATAFORMAS_TERRITORIALES.geojson", blocks: "MANZANAS_BASE_COBERTURA.geojson" };
      const entries = await Promise.all(Object.entries(names).map(async ([key, file]) => {
        const response = await fetch(root + file, { cache: "no-store" });
        if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
        return [key, await response.json()];
      }));
      const next = Object.fromEntries(entries);
      if (next.coverage.schemaVersion !== 3) throw new Error("Falta el cálculo actualizado con límite cantonal");
      const current = next.existing.features.filter(f => f.properties.REQUIERE_CAMBIO !== true);
      const interventions = [...next.existing.features.filter(f => f.properties.REQUIERE_CAMBIO === true), ...next.municipal.features, ...next.police.features];
      next.groups = { current, interventions, combined: [...current, ...interventions] };
      for (const [key, expected] of Object.entries({ current: 73, interventions: 110, combined: 183 })) {
        if (next.groups[key].length !== expected) throw new Error("Partición de cámaras incorrecta");
        for (const radius of [100, 150, 200]) if (next.coverage.scenarios[radius].groups[key].cameraCount !== expected) throw new Error("Cobertura desactualizada");
      }
      const ids = next.groups.combined.map(f => f.properties.ID_CAMARA || f.properties.ID_PROPUESTA || f.properties.ID_POLICIA);
      if (new Set(ids).size !== 183) throw new Error("Cámaras duplicadas");
      data = next;
    })().catch(error => { loading = null; throw error; });
    return loading;
  }
  async function loadClips(file) {
    if (!clipCache.has(file)) clipCache.set(file, (async () => {
      const response = await fetch(window.RIOBAMBA_SIG_RELEASE_ROOT + file, { cache: "no-store" });
      if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
      return response.json();
    })().catch(error => { clipCache.delete(file); throw error; }));
    return clipCache.get(file);
  }
  function renderLegend() {
    el.legend.innerHTML = `<span><i class="proposal-key existing"></i>73 actuales</span><span><i class="proposal-key interventions"></i>110 intervenciones</span><span><i class="current-block-key full"></i>Manzana completa</span><span><i class="current-block-key partial"></i>Porción cubierta de manzana parcial</span><span>Unión disuelta · ${api.radius()} m</span>`;
  }
  function detail() {
    el.detailTitle.textContent = selected ? selected.title : "Cobertura del escenario";
    const m = metrics();
    const rows = selected?.rows || [["Grupo", labels[group]], ["Radio", `${api.radius()} m`],
      ["Área cubierta en plataformas", `${number(m.coveredPlatformAreaKm2, 2)} km² (${number(m.coveredPlatformAreaPct, 2)} %)`],
      ["Población urbana cubierta", `${number(m.censusUrbanCoveredPopulation)} (${number(m.censusUrbanCoveredPct, 2)} % de 177.213)`],
      ["Población cubierta total", number(m.coveredPopulation)], ["Dentro de plataformas", number(m.insidePlatformPopulation)],
      ["Fuera de plataformas", number(m.outsidePlatformPopulation)],
      ["Área cubierta en Riobamba", `${number(m.coveredCantonAreaKm2, 2)} km²`],
      ["Área fuera del cantón · excluida", `${number(m.outsideCantonAreaKm2, 2)} km²`],
      ["Radios unidos · sin recorte cantonal", `${number(m.dissolvedAreaKm2, 2)} km²`],
      ["Área de manzanas cubierta en Riobamba", `${number(m.blockStats.coveredCantonAreaKm2, 2)} km²`],
      ["Manzanas totalmente cubiertas", number(m.blockStats.full)],
      ["Manzanas parcialmente cubiertas", number(m.blockStats.partial)],
      ["Manzanas sin cobertura", number(m.blockStats.uncovered)], ["Total manzanas", number(m.blockStats.total)]];
    el.detail.innerHTML = rowHtml(rows) + `<p class="current-coverage-note">110 intervenciones: 30 para cambio + 50 municipales + 30 policiales. Las 30 para cambio están incluidas en el inventario original, no son equipos adicionales. Cobertura potencial por proximidad, no visibilidad comprobada.</p>`;
  }
  function draw() {
    clearLegacyLayers(); clear();
    const m = metrics();
    layers.buffers = L.geoJSON(m.coverage, { interactive: false, style: { color: colors[group], weight: 1.3, fillColor: colors[group], fillOpacity: toggles.blockCoverage ? .06 : .22 } });
    layers.cantonBoundary = L.geoJSON(data.coverage.cantonBoundary, { interactive: false, style: { color: "#343a40", weight: 1.5, dashArray: "6 4", fill: false } });
    const covered = new Map(data.activeClips.features.map(f => [f.properties.ID_MANZANA, f.properties]));
    const selectBlock = feature => {
      const p = feature.properties;
      const coverage = covered.get(p.ID_MANZANA);
      const state = coverage?.ESTADO || "uncovered";
      selected = { title: `Manzana ${p.ID_MANZANA}`, rows: [
        ["Estado", ({ full: "Totalmente cubierta", partial: "Parcialmente cubierta", uncovered: "Sin cobertura" })[state]],
        ["Área de manzana", `${number(p.AREA_M2, 1)} m²`], ["Área cubierta", `${number(coverage?.AREA_CUBIERTA_M2 || 0, 1)} m²`],
        ["Cobertura superficial", `${number(coverage?.COBERTURA_PCT || 0, 2)} %`],
        ["Población censal", p.POBLACION == null ? "No disponible" : number(p.POBLACION)],
        ["Población cubierta estimada", p.POBLACION == null ? "No disponible" : number(coverage?.POBLACION_CUBIERTA || 0)],
        ["Grupo y radio", `${labels[group]} · ${api.radius()} m`]] }; detail();
    };
    const blockEvents = (feature, layer) => {
      const p = feature.properties;
      const coverage = covered.get(p.ID_MANZANA);
      layer.bindTooltip(`Manzana ${esc(p.ID_MANZANA)} · ${number(coverage?.COBERTURA_PCT || 0, 1)} %`);
      layer.on("click", () => selectBlock(feature));
    };
    layers.blocks = L.geoJSON(data.blocks, { style: { color: "#71828a", weight: .65, opacity: .7, fill: false }, onEachFeature: blockEvents });
    layers.blockCoverage = L.geoJSON(data.activeClips, { style: feature => ({
      color: feature.properties.ESTADO === "full" ? "#16876c" : "#a47108", weight: .65,
      fillColor: feature.properties.ESTADO === "full" ? "#16876c" : "#e4bb43", fillOpacity: .58 }), onEachFeature: blockEvents });
    layers.platforms = L.geoJSON(data.platforms, { style: { color: "#385a52", weight: 1, fill: false }, onEachFeature(feature, layer) {
      const name = feature.properties.platform_name;
      layer.bindTooltip(esc(name.replace(/^PLATAFORMA\s+/i, "")), { permanent: true, direction: "center", className: "proposal-platform-label" });
      layer.on("click", () => {
        selected = { title: name, rows: Object.entries(current().groups).flatMap(([key, value]) => {
          const row = value.platforms.find(p => p.name === name);
          return [[labels[key], `${number(row.coveredAreaKm2, 2)} km² · ${number(row.coveredPct, 2)} %`]];
        }) }; detail();
      });
    } });
    layers.points = L.geoJSON({ type: "FeatureCollection", features: data.groups[group] }, { pointToLayer(feature, latlng) {
      const symbol = feature.properties.ID_CAMARA && feature.properties.REQUIERE_CAMBIO !== true ? "existing" : "interventions";
      const id = feature.properties.ID_CAMARA || feature.properties.ID_PROPUESTA || feature.properties.ID_POLICIA;
      return L.marker(latlng, { title: id, alt: id, icon: L.divIcon({ className: `proposal-camera-icon proposal-camera-${symbol} current-coverage-camera`, html: "<span></span>", iconSize: [20, 20], iconAnchor: [10, 10] }) });
    }, onEachFeature(feature, layer) {
      const p = feature.properties, id = p.ID_CAMARA || p.ID_PROPUESTA || p.ID_POLICIA;
      layer.bindTooltip(esc(id));
      layer.on("click", () => { selected = { title: id, rows: [["Ubicación", p.DIRECCION || p.INTERSECCION_O_NODO || "Sin dirección documentada"], ["Radio potencial", `${api.radius()} m`]] }; detail(); });
    } });
    for (const key of ["buffers", "cantonBoundary", "platforms", "blocks", "blockCoverage", "points"]) if (toggles[key]) layers[key].addTo(api.map);
    api.map.invalidateSize();
    if (fitNeeded) {
      const bounds = (extent === "city" ? layers.platforms : layers.points).getBounds();
      if (bounds.isValid()) api.map.fitBounds(bounds, { padding: [20, 20], maxZoom: 14, animate: false });
      fitNeeded = false;
    }
  }
  function graphics() {
    const scenario = current();
    const rows = Object.entries(scenario.groups).map(([key, m]) => `<tr><td>${esc(labels[key])}</td><td>${number(m.coveredPlatformAreaKm2, 2)}</td><td>${number(m.censusUrbanCoveredPopulation)}</td><td>${number(m.censusUrbanCoveredPct, 2)} %</td><td>${number(m.coveredPopulation)}</td></tr>`).join("");
    const gain = scenario.groups.combined.coveredPopulation - scenario.groups.current.coveredPopulation;
    const urbanGain = scenario.groups.combined.censusUrbanCoveredPopulation - scenario.groups.current.censusUrbanCoveredPopulation;
    el.graphicAnalysis.innerHTML = `<section class="proposal-report"><h3>Comparación · radio ${api.radius()} m</h3><div class="proposal-table-wrap"><table class="mini-table"><thead><tr><th>Grupo</th><th>Área en plataformas · km²</th><th>Población urbana cubierta</th><th>% de 177.213</th><th>Población cubierta total</th></tr></thead><tbody>${rows}</tbody></table></div><p>Aporte neto de las 110 intervenciones sobre las 73 actuales: ${number(gain)} personas en todas las manzanas disponibles; ${number(urbanGain)} en el ámbito urbano censal. No se suman las coberturas aisladas porque se solapan.</p><div class="current-coverage-bars">${Object.entries(scenario.groups).map(([key, m]) => `<label><span>${esc(labels[key])}</span><meter min="0" max="177213" value="${m.censusUrbanCoveredPopulation}" style="accent-color:${colors[key]}">${number(m.censusUrbanCoveredPopulation)}</meter><strong>${number(m.censusUrbanCoveredPct, 2)} %</strong></label>`).join("")}</div></section>`;
    el.graphicAnalysis.innerHTML += `<section class="proposal-report"><h3>Áreas y manzanas · radio ${api.radius()} m</h3><div class="proposal-table-wrap"><table class="mini-table"><thead><tr><th>Grupo</th><th>Dentro de Riobamba · km²</th><th>Fuera del cantón · km²</th><th>Radios sin recorte · km²</th><th>Manzanas cubiertas en Riobamba · km²</th><th>Completas</th><th>Parciales</th><th>Sin cobertura</th><th>Total</th></tr></thead><tbody>${Object.entries(scenario.groups).map(([key, m]) => `<tr><td>${esc(labels[key])}</td><td>${number(m.coveredCantonAreaKm2, 2)}</td><td>${number(m.outsideCantonAreaKm2, 2)}</td><td>${number(m.dissolvedAreaKm2, 2)}</td><td>${number(m.blockStats.coveredCantonAreaKm2, 2)}</td><td>${number(m.blockStats.full)}</td><td>${number(m.blockStats.partial)}</td><td>${number(m.blockStats.uncovered)}</td><td>${number(m.blockStats.total)}</td></tr>`).join("")}</tbody></table></div></section>`;
  }
  function renderMethodology() {
    document.getElementById("methodologyPanel").innerHTML = `<h3>Cobertura potencial · 73 / 110 / 183</h3>` + rowHtml([["Cálculo", "Unión de buffers EPSG:32717; 64 segmentos por cuadrante"], ["Radios", "100, 150 y 200 m"], ["Área", "Intersección con la unión de 18 plataformas, sin duplicar solapes"], ["Población urbana", "Manzanas 060150, zonas 001–899; base oficial 177.213"], ["Población total", "Todas las manzanas disponibles dentro y fuera de plataformas"], ["Población estimada", "Distribución uniforme por área de manzana; datos faltantes no imputados"], ["Geometrías", "Cámaras actuales y propuestas del paquete SIG activo, sin moverlas"]]);
    document.getElementById("methodologyPanel").innerHTML += rowHtml([
      ["Área total de radios", "Unión completa de los radios, incluidas las áreas exteriores a las plataformas"],
      ["Área cubierta en Riobamba", "Unión de radios recortada al límite cantonal original. Excluye la superficie exterior al cantón"],
      ["Área de manzanas de Riobamba", "Intersección de radios, unión de manzanas censales y límite cantonal. No equivale al área de radios ni al área en plataformas"],
      ["Área cubierta en manzanas", "Intersección de la unión de manzanas censales con los radios unidos, sin duplicar superficies"],
      ["Manzanas", "Completas, parciales y sin cobertura sobre todas las geometrías censales disponibles, tengan o no dato poblacional"],
      ["Dibujo de parciales", "Solo la porción alcanzada; no se pinta toda la manzana como cubierta"],
      ["Precisión", "Estadísticas con geometrías originales; cartografía derivada simplificada 0,5 m. Tolerancia superficial 0,01 m²; completa si falta como máximo 0,0001 % o 0,01 m²"]]);
  }
  async function render() {
    if (!api.active()) return;
    const token = ++version;
    active = true; el.workspace.classList.add("current-coverage-active");
    layerControls.hidden = false;
    el.overlayTitle.textContent = "Cobertura potencial de cámaras";
    el.status.textContent = "Cargando cobertura vigente de 73 / 110 / 183…";
    try { await load(); } catch (error) { if (api.active() && token === version) { el.status.textContent = error.message; el.summary.textContent = "Cobertura no disponible"; } return; }
    if (!api.active() || token !== version) return;
    const m = metrics();
    const clipKey = `${api.radius()}-${group}`;
    try {
      const clips = await loadClips(m.blockClipsFile);
      if (!api.active() || token !== version) return;
      data.activeClips = clips; activeClipKey = clipKey;
    } catch (error) { if (api.active() && token === version) el.status.textContent = `No se pudieron cargar las manzanas: ${error.message}`; return; }
    document.getElementById("currentCoverageExtent").value = extent;
    el.overlayText.textContent = `${labels[group]} · radio ${api.radius()} m · paquete SIG vigente`;
    el.summary.innerHTML = [["Actuales sin cambio", "73"], ["Intervenciones", "110"], ["Sistema completo", "183"], ["Área cubierta en plataformas", `${number(m.coveredPlatformAreaKm2, 2)} km²`], ["Población urbana cubierta", number(m.censusUrbanCoveredPopulation)], ["Cobertura urbana · base 177.213", `${number(m.censusUrbanCoveredPct, 2)} %`], ["Población cubierta total", number(m.coveredPopulation)], ["Fuera de plataformas", number(m.outsidePlatformPopulation)]].map(([title, value]) => `<div class="card"><span>${esc(title)}</span><strong>${esc(value)}</strong></div>`).join("");
    el.summary.innerHTML += [["Área cubierta en Riobamba", `${number(m.coveredCantonAreaKm2, 2)} km²`], ["Área cubierta en manzanas de Riobamba", `${number(m.blockStats.coveredCantonAreaKm2, 2)} km²`], ["Manzanas alcanzadas · completas + parciales", `${number(m.blockStats.covered)} / ${number(m.blockStats.total)}`]].map(([title, value]) => `<div class="card"><span>${esc(title)}</span><strong>${esc(value)}</strong></div>`).join("");
    controls.querySelectorAll("[data-current-group]").forEach(button => { button.classList.toggle("is-active", button.dataset.currentGroup === group); button.setAttribute("aria-pressed", String(button.dataset.currentGroup === group)); });
    draw(); detail(); graphics(); renderLegend();
    el.status.textContent = `${labels[group]} · ${api.radius()} m · cobertura métrica sin solapes duplicados · ${number(current().population.blocksWithoutPopulation)} manzanas sin población disponible; ${number(current().population.urbanPopulationPendingReconciliation)} habitantes urbanos por conciliar.`;
  }
  controls.querySelectorAll("[data-current-group]").forEach(button => button.addEventListener("click", () => { group = button.dataset.currentGroup; selected = null; render(); }));
  document.getElementById("currentCoverageExtent").addEventListener("change", event => { extent = event.target.value; fitNeeded = true; render(); });
  layerControls.querySelectorAll("[data-current-layer]").forEach(input => input.addEventListener("change", () => { toggles[input.dataset.currentLayer] = input.checked; if (active && data && activeClipKey === `${api.radius()}-${group}`) draw(); }));
  return { render, leave, reset, renderLegend, renderMethodology, clearLegacyLayers };
};
