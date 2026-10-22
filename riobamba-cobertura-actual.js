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
  const layers = {};
  const toggles = { points: true, buffers: true, platforms: true };
  const current = () => data.coverage.scenarios[String(api.radius())];
  const metrics = () => current().groups[group];
  function clear() { Object.values(layers).forEach(layer => api.map.removeLayer(layer)); }
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
        municipal: "PROPUESTA_MUNICIPAL_50_FINAL.geojson", police: "PROPUESTA_POLICIA_30_FINAL.geojson", platforms: "PLATAFORMAS_TERRITORIALES.geojson" };
      const entries = await Promise.all(Object.entries(names).map(async ([key, file]) => {
        const response = await fetch(root + file, { cache: "no-store" });
        if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
        return [key, await response.json()];
      }));
      const next = Object.fromEntries(entries);
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
  function renderLegend() {
    el.legend.innerHTML = `<span><i class="proposal-key existing"></i>73 actuales</span><span><i class="proposal-key interventions"></i>110 intervenciones</span><span>Unión disuelta · ${api.radius()} m</span>`;
  }
  function detail() {
    el.detailTitle.textContent = selected ? selected.title : "Cobertura del escenario";
    const m = metrics();
    const rows = selected?.rows || [["Grupo", labels[group]], ["Radio", `${api.radius()} m`],
      ["Área cubierta en plataformas", `${number(m.coveredPlatformAreaKm2, 2)} km² (${number(m.coveredPlatformAreaPct, 2)} %)`],
      ["Población urbana cubierta", `${number(m.censusUrbanCoveredPopulation)} (${number(m.censusUrbanCoveredPct, 2)} % de 177.213)`],
      ["Población cubierta total", number(m.coveredPopulation)], ["Dentro de plataformas", number(m.insidePlatformPopulation)],
      ["Fuera de plataformas", number(m.outsidePlatformPopulation)]];
    el.detail.innerHTML = rowHtml(rows) + `<p class="current-coverage-note">110 intervenciones: 30 para cambio + 50 municipales + 30 policiales. Las 30 para cambio están incluidas en el inventario original, no son equipos adicionales. Cobertura potencial por proximidad, no visibilidad comprobada.</p>`;
  }
  function draw() {
    (api.layers() || []).forEach(layer => api.map.removeLayer(layer)); clear();
    const m = metrics();
    layers.buffers = L.geoJSON(m.coverage, { interactive: false, style: { color: colors[group], weight: 1.3, fillColor: colors[group], fillOpacity: .22 } });
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
    for (const [key, layer] of Object.entries(layers)) if (toggles[key]) layer.addTo(api.map);
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
  }
  function renderMethodology() {
    document.getElementById("methodologyPanel").innerHTML = `<h3>Cobertura potencial · 73 / 110 / 183</h3>` + rowHtml([["Cálculo", "Unión de buffers EPSG:32717; 64 segmentos por cuadrante"], ["Radios", "100, 150 y 200 m"], ["Área", "Intersección con la unión de 18 plataformas, sin duplicar solapes"], ["Población urbana", "Manzanas 060150, zonas 001–899; base oficial 177.213"], ["Población total", "Todas las manzanas disponibles dentro y fuera de plataformas"], ["Población estimada", "Distribución uniforme por área de manzana; datos faltantes no imputados"], ["Geometrías", "Cámaras actuales y propuestas del paquete SIG activo, sin moverlas"]]);
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
    document.getElementById("currentCoverageExtent").value = extent;
    el.overlayText.textContent = `${labels[group]} · radio ${api.radius()} m · paquete SIG vigente`;
    el.summary.innerHTML = [["Actuales sin cambio", "73"], ["Intervenciones", "110"], ["Sistema completo", "183"], ["Área cubierta en plataformas", `${number(m.coveredPlatformAreaKm2, 2)} km²`], ["Población urbana cubierta", number(m.censusUrbanCoveredPopulation)], ["Cobertura urbana · base 177.213", `${number(m.censusUrbanCoveredPct, 2)} %`], ["Población cubierta total", number(m.coveredPopulation)], ["Fuera de plataformas", number(m.outsidePlatformPopulation)]].map(([title, value]) => `<div class="card"><span>${esc(title)}</span><strong>${esc(value)}</strong></div>`).join("");
    controls.querySelectorAll("[data-current-group]").forEach(button => { button.classList.toggle("is-active", button.dataset.currentGroup === group); button.setAttribute("aria-pressed", String(button.dataset.currentGroup === group)); });
    draw(); detail(); graphics(); renderLegend();
    el.status.textContent = `${labels[group]} · ${api.radius()} m · cobertura métrica sin solapes duplicados · ${number(current().population.blocksWithoutPopulation)} manzanas sin población disponible; ${number(current().population.urbanPopulationPendingReconciliation)} habitantes urbanos por conciliar.`;
  }
  controls.querySelectorAll("[data-current-group]").forEach(button => button.addEventListener("click", () => { group = button.dataset.currentGroup; selected = null; render(); }));
  document.getElementById("currentCoverageExtent").addEventListener("change", event => { extent = event.target.value; fitNeeded = true; render(); });
  layerControls.querySelectorAll("[data-current-layer]").forEach(input => input.addEventListener("change", () => { toggles[input.dataset.currentLayer] = input.checked; if (active && data) draw(); }));
  return { render, leave, reset, renderLegend, renderMethodology };
};
