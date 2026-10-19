/* Final GIS results in UTM 17S; Leaflet renders their WGS84 derivatives. */
window.createRiobambaCameraProposal = function (api) {
  "use strict";
  const { map, elements: el, esc } = api;
  const root = window.RIOBAMBA_SIG_RELEASE_ROOT || "./data/seguridad-riobamba/POLICIA_KDE_INTERSECCIONES_20261015/";
  const controls = document.getElementById("proposalLayerControls");
  const scenarioControl = document.getElementById("proposalScenario");
  const radiusControl = document.getElementById("proposalRadius");
  const extentControl = document.getElementById("proposalExtent");
  const colors = { existing: "#246db5", change: "#8b46b5", municipal: "#18815b", police: "#e8bd16" };
  const groups = { existing: "Existentes", municipal: "Municipio · propuesta", police: "Policía · propuesta" };
  const names = { BOULEVARD_MACAJI_BELLAVISTA: "Macají–Bellavista", CICLOVIAS: "Ciclovías", ANILLO_VIAL: "Anillo vial", QUEBRADA_LAS_ABRAS: "Las Abras" };
  const corridorToggles = { corridorRing: "ANILLO_VIAL", corridorMacaji: "BOULEVARD_MACAJI_BELLAVISTA", corridorAbras: "QUEBRADA_LAS_ABRAS", corridorCiclovias: "CICLOVIAS" };
  const corridorFeatures = corridor => data.corridors.features.filter(f => f.properties.CORREDOR === corridor);
  const corridorColors = { ANILLO_VIAL: "#a564ad", BOULEVARD_MACAJI_BELLAVISTA: "#297d55", QUEBRADA_LAS_ABRAS: "#16a1b2", CICLOVIAS: "#246db5" };
  const urbanAxesStyle = { color: "#d62828", weight: 3, opacity: 1 };
  const platformStyle = { color: "#385a52", weight: 1.6, opacity: .6, fill: false };
  const defaults = { existing: true, change: true, municipal: true, police: true, existingRadius: true, changeRadius: true, municipalRadius: true, policeRadius: true, platforms: true, kde: true, corridorRing: false, corridorMacaji: false, corridorAbras: false, corridorCiclovias: false, macajiSegment: true, urbanAxes: true, voids: false };
  const toggles = { ...defaults };
  const labels = { existing: "Sin cambio requerido", change: "Requieren cambio", municipal: "Municipio · 50 propuestas", police: "Policía · 30 propuestas", existingRadius: "Radio sin cambio · 200 m", changeRadius: "Radio para cambio · 200 m", municipalRadius: "Radio Municipio · 200 m", policeRadius: "Radio Policía · 200 m", platforms: "18 Plataformas", kde: "Concentración de incidentes · KDE", corridorRing: "Anillo Vial", corridorMacaji: "Bulevares · Macají–Bellavista", corridorAbras: "Quebrada Las Abras", corridorCiclovias: "Ciclovías", macajiSegment: "Tramo Bulevar Macají–Bellavista", urbanAxes: "Ejes Urbanos prioritarios", voids: "Tramos sin cobertura · escenario 183" };
  const macajiSegmentStyle = { color: "#d62828", weight: 5, opacity: 1 };
  const layers = {};
  const renderers = new Map();
  const panes = new Set();
  let renderVersion = 0;
  let data, loading, active = false, fitNeeded = true, drawKey = "", selected = null, miniMap = null;
  let kdeMetadata = null;
  let platformLabelFrame = null;
  const number = (v, digits = 0) => v == null || !Number.isFinite(Number(v)) ? "No disponible" : Number(v).toLocaleString("es-EC", { maximumFractionDigits: digits });
  const pct = v => v == null ? "No disponible" : `${number(v, 1)} %`;
  const scenario = () => ({ actual: "A", municipal: "B", future: "C" })[scenarioControl.value] || "C";
  const groupEnabled = key => key === "existing" || key === "change" || (key === "municipal" && scenario() !== "A") || (key === "police" && scenario() === "C");
  const cameraId = f => f.properties.ID_CAMARA || f.properties.ID_PROPUESTA || f.properties.ID_POLICIA;
  const change = f => f.properties.REQUIERE_CAMBIO === true;
  const point = f => [f.geometry.coordinates[1], f.geometry.coordinates[0]];
  const fc = features => ({ type: "FeatureCollection", features });
  const cameraSymbols = group => group === "existing" ? ["existing", "change"] : [group];
  const symbolFeatures = (group, symbol, suffix = "") => fc(data[group + suffix].features.filter(feature => group !== "existing" || change(feature) === (symbol === "change")));
  const rowHtml = rows => rows.map(([label, value]) => `<div class="mini-row"><span>${esc(label)}</span><strong>${esc(value ?? "No disponible")}</strong></div>`).join("");
  const table = (title, headings, rows, note = "") => `<section class="proposal-report"><h3>${esc(title)}</h3><div class="proposal-table-wrap"><table class="mini-table"><thead><tr>${headings.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(v => `<td>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${note ? `<p>${esc(note)}</p>` : ""}</section>`;
  const links = () => `<div class="proposal-links"><a href="${root}ENTREGA_POLICIA_KDE.zip" download>Paquete GIS final ZIP</a><a href="${root}ESCENARIO_FINAL_183.gpkg" download>GeoPackage final</a><a href="${root}MOVIMIENTOS_POLICIA_30.csv" download>Movimientos de Policía</a><a href="${root}POLICIA_BENEFICIO_FINAL.csv" download>Beneficio y solapes finales</a><a href="${root}INFORME_FINAL.md" target="_blank" rel="noopener">Informe y metodología</a><a href="${root}RESULTADOS.json" download>Resultados</a><a href="${root}VALIDACION.json" download>Validación GIS</a></div>`;
  const metric = (kind, code = scenario()) => data.results[kind].find(r => r.ESCENARIO === code);

  const cameraLayerKeys = ["existing", "change", "municipal", "police", "existingRadius", "changeRadius", "municipalRadius", "policeRadius", "platforms"];
  const analysisLayerKeys = ["kde", ...Object.keys(corridorToggles), "macajiSegment", "urbanAxes", "voids"];
  const layerRow = key => {
    const symbol = key.replace("Radius", "");
    return `<label class="proposal-layer-row"><span>${key === "urbanAxes" ? '<i class="proposal-key urban-axes" aria-hidden="true"></i>' : key === "macajiSegment" ? `<i class="proposal-key corridor-line" style="background:${macajiSegmentStyle.color}" aria-hidden="true"></i>` : corridorToggles[key] ? `<i class="proposal-key corridor-line" style="background:${corridorColors[corridorToggles[key]]}" aria-hidden="true"></i>` : colors[symbol] ? `<i class="proposal-key ${symbol}" aria-hidden="true"></i>` : ""}${esc(labels[key])}</span><input type="checkbox" data-proposal-layer="${key}" ${toggles[key] ? "checked" : ""}></label>`;
  };
  controls.innerHTML = `<section class="proposal-layer-group"><h4>Cámaras y radios</h4>${cameraLayerKeys.map(layerRow).join("")}</section>` +
    `<section class="proposal-layer-group"><h4>Análisis territorial</h4>${analysisLayerKeys.map(layerRow).join("")}</section>`;
  function syncToggles() {
    controls.querySelectorAll("[data-proposal-layer]").forEach(n => {
      n.checked = toggles[n.dataset.proposalLayer];
      if (data && ["existing", "change"].includes(n.dataset.proposalLayer)) {
        const key = n.dataset.proposalLayer;
        n.previousElementSibling.innerHTML = `<i class="proposal-key ${key}" aria-hidden="true"></i>${esc(labels[key])} · ${symbolFeatures("existing", key).features.length}`;
      }
      n.disabled = !groupEnabled(n.dataset.proposalLayer.replace("Radius", "")) && /^(municipal|police)/.test(n.dataset.proposalLayer);
    });
  }
  function clearLegacyLayers() { api.layers().forEach(layer => { if (map.hasLayer(layer)) map.removeLayer(layer); }); }
  function removeMini() { miniMap?.remove(); miniMap = null; }
  function leave() {
    renderVersion++;
    if (!active) return;
    active = false; el.workspace.classList.remove("proposal-active");
    Object.values(layers).forEach(layer => map.removeLayer(layer));
    panes.forEach(id => { map.getPane(id).style.display = "none"; });
    selected = null; removeMini(); drawKey = "";
  }
  function reset() {
    scenarioControl.value = "future"; radiusControl.value = "200"; extentControl.value = "urban";
    Object.assign(toggles, defaults); selected = null; fitNeeded = true; syncToggles();
  }
  async function load() {
    if (data) return;
    if (!loading) loading = (async () => {
      const files = { results: "RESULTADOS.json", existing: "CAMARAS_EXISTENTES_103_FINAL.geojson", municipal: "PROPUESTA_MUNICIPAL_50_FINAL.geojson", police: "PROPUESTA_POLICIA_30_FINAL.geojson",
        existingRadius: "RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson", municipalRadius: "COBERTURA_MUNICIPAL_200M.geojson", policeRadius: "COBERTURA_POLICIA_200M.geojson", platforms: "PLATAFORMAS_TERRITORIALES.geojson", corridors: "CORREDORES.geojson", macajiCorridor: "CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson" };
      const entries = await Promise.all(Object.entries(files).map(async ([key, name]) => {
        const response = await fetch(root + name + "?v=tramo-macaji-independiente-20261018", { cache: "no-store" });
        if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
        return [key, await response.json()];
      }));
      const next = Object.fromEntries(entries);
      for (const [key, expected] of [["existing", 103], ["municipal", 50], ["police", 30]]) {
        if (next[key].features.length !== expected || next[key].features.some(f => !f.geometry || f.geometry.type !== "Point" || !f.geometry.coordinates.every(Number.isFinite))) throw new Error(`Inventario ${key} inconsistente`);
      }
      if (next.existing.features.filter(change).length !== next.results.counts.changeIncluded) throw new Error("Conteo de cámaras para cambio inconsistente");
      const changeIds = new Set(next.existing.features.filter(change).map(cameraId));
      next.existingRadius.features.forEach(feature => {
        feature.properties.REQUIERE_CAMBIO = changeIds.has(feature.properties.ID_CAMARA || feature.properties.ID);
      });
      const voids = await Promise.all(["MACAJI", "ANILLO", "CICLOVIAS", "LAS_ABRAS"].map(async name => {
        const response = await fetch(root + `BRECHA_${name}_FINAL.geojson`);
        if (!response.ok) throw new Error(`Brecha ${name}: HTTP ${response.status}`);
        return response.json();
      }));
      next.voids = fc(voids.flatMap(r => r.features)); data = next;
      console.info("[Cierre videovigilancia]", { existentes: 103, paraCambio: changeIds.size, municipales: 50, policia: 30, radioM: 200, crs: "EPSG:32717", fuente: root });
    })().catch(error => { loading = null; throw error; });
    return loading;
  }
  function pane(name, z) {
    const id = `proposal-${name}`;
    if (!map.getPane(id)) map.createPane(id).style.zIndex = z;
    panes.add(id);
    map.getPane(id).style.display = active ? "" : "none";
    return id;
  }
  function renderer(name, z) {
    const id = pane(name, z);
    // SVG paths receive clicks individually; separate canvas panes block each other.
    if (!renderers.has(id)) renderers.set(id, L.svg({ pane: id }));
    return renderers.get(id);
  }
  function icon(key, f) {
    const symbol = key === "existing" && change(f) ? "change" : key;
    return L.divIcon({ className: `proposal-camera-icon proposal-camera-${symbol}`, html: "<span></span>", iconSize: [20, 20], iconAnchor: [10, 10] });
  }
  const coverageStyle = key => ({ color: colors[key], weight: 1, opacity: .65, fillColor: colors[key], fillOpacity: .18 });
  const radiusStyle = key => feature => coverageStyle(key === "existing" && change(feature) ? "change" : key);
  function selectEntity(value, bounds) {
    if (!active || !api.active()) return;
    selected = value; detail();
    if (bounds?.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 17, animate: false });
  }
  function replaceLayer(key, layer) { if (layers[key]) map.removeLayer(layers[key]); layers[key] = layer; }
  function layoutPlatformLabels() {
    if (!active || !toggles.platforms || !layers.platforms) return;
    const placed = [], bounds = map.getContainer().getBoundingClientRect();
    layers.platforms.eachLayer(layer => {
      const tooltip = layer.getTooltip();
      if (!tooltip?.getElement() || !map.getBounds().contains(layer.getCenter())) return;
      let bestDirection = "center", bestScore = Infinity;
      // Keep every name visible; try nearby label positions without moving its polygon.
      for (const direction of ["center", "left", "right", "top", "bottom"]) {
        L.setOptions(tooltip, { direction }); tooltip.update();
        const rect = tooltip.getElement().getBoundingClientRect();
        const overflow = Math.max(0, bounds.left - rect.left) + Math.max(0, rect.right - bounds.right) + Math.max(0, bounds.top - rect.top) + Math.max(0, rect.bottom - bounds.bottom);
        const overlap = placed.reduce((sum, other) => sum + Math.max(0, Math.min(rect.right, other.right + 2) - Math.max(rect.left, other.left - 2)) * Math.max(0, Math.min(rect.bottom, other.bottom + 2) - Math.max(rect.top, other.top - 2)), 0);
        const score = overflow * 1000 + overlap;
        if (score < bestScore) { bestScore = score; bestDirection = direction; }
        if (score === 0) break;
      }
      L.setOptions(tooltip, { direction: bestDirection }); tooltip.update();
      placed.push(tooltip.getElement().getBoundingClientRect());
    });
  }
  function schedulePlatformLabels() {
    if (platformLabelFrame !== null) return;
    platformLabelFrame = requestAnimationFrame(() => { platformLabelFrame = null; layoutPlatformLabels(); });
  }
  function draw() {
    const key = "camera-proposal";
    if (drawKey === key) { syncLayers(); return; }
    drawKey = key;
    for (const group of Object.keys(groups)) {
      for (const symbol of cameraSymbols(group)) {
        replaceLayer(symbol, L.geoJSON(symbolFeatures(group, symbol), { pane: pane("points", 460), pointToLayer: (f, pos) => L.marker(pos, { icon: icon(group, f), keyboard: true, title: cameraId(f) }),
          onEachFeature: (f, layer) => {
            const select = () => selectEntity({ kind: "camera", group, feature: f });
            const keyboard = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); select(); } };
            layer.bindTooltip(`${esc(cameraId(f))} · ${esc(groups[group])}${change(f) ? " · Requiere cambio" : ""}`).on("click", select);
            layer.on("add", () => { const node = layer.getElement(); L.DomEvent.off(node, "keydown", keyboard); L.DomEvent.on(node, "keydown", keyboard); });
          } }));
        replaceLayer(symbol + "Radius", L.geoJSON(symbolFeatures(group, symbol, "Radius"), { pane: pane("coverage", 410), renderer: renderer("coverage", 410), interactive: false, style: radiusStyle(group) }));
      }
    }
    replaceLayer("platforms", L.geoJSON(data.platforms, { pane: pane("platforms", 440), renderer: renderer("platforms", 440), style: platformStyle,
      onEachFeature: (f, layer) => layer.bindTooltip(esc(f.properties.platform_name.replace("PLATAFORMA ", "Plataforma ")), { permanent: true, direction: "center", className: "proposal-platform-label", opacity: 1, interactive: false }).on("click", () => selectEntity({ kind: "platform", feature: f })) }));
    replaceLayer("urbanAxes", L.geoJSON(data.corridors, { pane: pane("urban-axes", 430), renderer: renderer("urban-axes", 430), style: urbanAxesStyle,
      onEachFeature: (f, layer) => layer.bindTooltip(esc(names[f.properties.CORREDOR] || labels.urbanAxes)).on("click", () => selectEntity({ kind: "corridor", feature: f })) }));
    for (const [toggle, corridor] of Object.entries(corridorToggles)) {
      replaceLayer(toggle, L.geoJSON(fc(corridorFeatures(corridor)), {
        pane: pane("individual-corridors", 431), renderer: renderer("individual-corridors", 431), style: { color: corridorColors[corridor], weight: 2.5, opacity: .85 },
        onEachFeature: (f, layer) => layer.bindTooltip(esc(names[corridor])).on("click", () => selectEntity({ kind: "corridor", feature: f })) }));
    }
    replaceLayer("macajiSegment", L.geoJSON(data.macajiCorridor, { pane: pane("individual-corridors", 432), renderer: renderer("individual-corridors", 432), style: macajiSegmentStyle,
      onEachFeature: (f, layer) => layer.bindTooltip(esc(labels.macajiSegment)).on("click", () => selectEntity({ kind: "macajiSegment", feature: f })) }));
    replaceLayer("voids", L.geoJSON(data.voids, { pane: pane("voids", 435), renderer: renderer("voids", 435), style: { color: "#c24c58", weight: 4, dashArray: "6 5", opacity: .9 },
      onEachFeature: (f, layer) => layer.bindTooltip(`${esc(f.properties.ID)} · ${number(f.properties.LONGITUD_M, 1)} m`).on("click", () => selectEntity({ kind: "void", feature: f })) }));
    syncLayers();
  }
  function syncLayers() {
    clearLegacyLayers(); if (!active) return;
    panes.forEach(id => { const layerPane = map.getPane(id); if (layerPane) layerPane.style.display = ""; });
    if (toggles.kde && !layers.kde) {
      kdeMetadata = api.kdeOverlay();
      layers.kde = L.imageOverlay(kdeMetadata.url, kdeMetadata.bounds, { pane: pane("kde", 405), opacity: 1, interactive: false });
    }
    Object.entries(layers).forEach(([key, layer]) => {
      const enabled = toggles[key] && (!/^(existing|change|municipal|police)/.test(key) || groupEnabled(key.replace("Radius", ""))) && (key !== "voids" || scenario() === "C");
      enabled ? layer.addTo(map) : map.removeLayer(layer);
    });
    schedulePlatformLabels();
  }
  function fit() {
    const view = extentControl.value;
    let bounds;
    if (view === "urban") bounds = layers.platforms.getBounds();
    else if (["ring", "abras"].includes(view)) bounds = L.geoJSON(fc(data.corridors.features.filter(f => f.properties.CORREDOR === (view === "ring" ? "ANILLO_VIAL" : "QUEBRADA_LAS_ABRAS")))).getBounds();
    else bounds = L.geoJSON(fc(view === "rural" ? data.municipal.features.filter(f => f.properties.GRUPO === "CABECERA_RURAL") : Object.keys(groups).filter(groupEnabled).flatMap(k => data[k].features))).getBounds();
    if (bounds?.isValid()) map.fitBounds(bounds, { padding: [20, 20], maxZoom: 14, animate: false });
    fitNeeded = false;
  }
  function renderLegend() {
    if (!data) return;
    const existingCount = data.existing.features.length;
    const changeCount = data.existing.features.filter(change).length;
    el.legend.innerHTML = `<div>Cámaras existentes · ${existingCount} en total</div><div><span class="proposal-key existing"></span>Sin cambio requerido · ${existingCount - changeCount}</div><div><span class="proposal-key change"></span>Requieren cambio · ${changeCount} de las ${existingCount}</div><div><span class="proposal-key municipal"></span>Municipio · 50 propuestas</div><div><span class="proposal-key police"></span>Policía · 30 propuestas</div>` +
      Object.keys(groups).filter(groupEnabled).map(k => `<div><span class="proposal-key" style="background:${colors[k]};opacity:.5"></span>Radio ${k === "existing" ? "sin cambio requerido" : esc(groups[k])} · 200 m</div>`).join("") +
      `<div><span class="proposal-key" style="background:${colors.change};opacity:.5"></span>Radio para cambio · 200 m</div>` +
      (toggles.kde ? `<div class="proposal-kde-legend"><span aria-hidden="true" style="background:linear-gradient(90deg,#ffffb2,#fed976,#feb24c,#f03b20,#bd0026)"></span>Concentración de incidentes · KDE combinado provisional · ${number(kdeMetadata?.records)} registros · radio ${number(kdeMetadata?.bandwidth)} m</div><div>${esc(kdeMetadata?.period || "")}</div><div>${esc(kdeMetadata?.warning || "")}</div><div>La capa KDE no recalcula los indicadores de cobertura de incidentes.</div>` : "") +
      (toggles.urbanAxes ? `<div><span class="proposal-key urban-axes"></span>${esc(labels.urbanAxes)}</div>` : "") +
      Object.entries(corridorToggles).filter(([toggle]) => toggles[toggle]).map(([toggle, corridor]) => `<div><span class="proposal-key corridor-line" style="background:${corridorColors[corridor]}"></span>${esc(labels[toggle])}</div>`).join("") +
      (toggles.macajiSegment ? `<div><span class="proposal-key corridor-line" style="background:${macajiSegmentStyle.color}"></span>${esc(labels.macajiSegment)}</div>` : "") + `<div>Radios geométricos potenciales, no campo visual efectivo.</div>`;
  }
  function selectedCorridorStyle(corridor) {
    const toggle = Object.keys(corridorToggles).find(key => corridorToggles[key] === corridor);
    return toggles[toggle] ? { color: corridorColors[corridor], weight: 2.5, opacity: .85 } : { ...urbanAxesStyle, opacity: toggles.urbanAxes ? 1 : 0 };
  }
  function mini(feature) {
    const node = document.getElementById("proposalDetailMap"); if (!node) return;
    miniMap = L.map(node, { zoomControl: false, scrollWheelZoom: false, preferCanvas: true, zoomAnimation: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap", className: "osm-gray-tile", maxZoom: 20 }).addTo(miniMap);
    for (const key of Object.keys(groups).filter(groupEnabled)) {
      for (const symbol of cameraSymbols(key)) {
        if (toggles[symbol + "Radius"]) L.geoJSON(symbolFeatures(key, symbol, "Radius"), { interactive: false, style: radiusStyle(key) }).addTo(miniMap);
        if (toggles[symbol]) L.geoJSON(symbolFeatures(key, symbol), { pointToLayer: (f, pos) => L.marker(pos, { icon: icon(key, f), title: cameraId(f) }) }).addTo(miniMap);
      }
    }
    if (toggles.platforms) L.geoJSON(data.platforms, { interactive: false, style: { ...platformStyle, weight: 1 } }).addTo(miniMap);
    if (toggles.urbanAxes) L.geoJSON(data.corridors, { interactive: false, style: urbanAxesStyle }).addTo(miniMap);
    for (const [toggle, corridor] of Object.entries(corridorToggles)) {
      if (toggles[toggle]) L.geoJSON(fc(corridorFeatures(corridor)), { interactive: false, style: { color: corridorColors[corridor], weight: 2.5, opacity: .85 } }).addTo(miniMap);
    }
    if (toggles.macajiSegment) L.geoJSON(data.macajiCorridor, { interactive: false, style: macajiSegmentStyle }).addTo(miniMap);
    if (feature?.geometry.type === "Point") miniMap.setView(point(feature), 16);
    else {
      const focus = L.geoJSON(feature || data.platforms, { style: selected?.kind === "macajiSegment" ? macajiSegmentStyle : selected?.kind === "corridor" ? selectedCorridorStyle(feature.properties.CORREDOR) : selected?.kind === "platform" || !feature ? { ...platformStyle, weight: 2, opacity: toggles.platforms ? platformStyle.opacity : 0 } : { color: "#385a52", weight: 2, fillOpacity: .08 } }).addTo(miniMap);
      miniMap.fitBounds(focus.getBounds(), { padding: [12, 12], maxZoom: 16, animate: false });
    }
    requestAnimationFrame(() => miniMap?.invalidateSize());
  }
  function detail() {
    removeMini();
    const a = metric("territorial"), p = metric("population"), f = selected?.feature, v = f?.properties;
    let title = "Escenario " + ({ A: "103 existentes", B: "153 equipos", C: "183 equipos" })[scenario()];
    let rows = [["Radio", "200 m"], ["Área urbana cubierta", `${number(a.AREA_CUBIERTA_URBANA_KM2, 2)} km²`], ["Territorio urbano cubierto", pct(a.PCT_URBANO)], ["Población urbana cubierta estimada", number(p.POBLACION_CUBIERTA)], ["% población urbana cubierta", pct(p.PCT_CUBIERTO)], ["Población rural cubierta", "No disponible"]];
    const quality = data.results.inventoryGeolocation;
    if (quality) rows.push(["Coordenadas documentadas intactas", quality.documentedUnchanged], ["Cruces revisados / aprobados", quality.reviewedApprovedIntersections], ["Ubicaciones provisionales pendientes", quality.pendingValidation]);
    if (selected?.kind === "camera") {
      title = cameraId(f);
      rows = [["Grupo", groups[selected.group]], ["Estado", v.ESTADO || v.ESTADO_VALIDACION], ["Dirección / nodo", v.DIRECCION || v.INTERSECCION_O_NODO], ["Radio potencial", "200 m"], ["X / Y · EPSG:32717", `${number(v.X, 2)} / ${number(v.Y, 2)}`]];
      if (selected.group === "existing") rows.push(["Requiere cambio", change(f) ? "Sí" : "No"], ["Estado geográfico", v.ESTADO_GEO], ["Método geográfico", v.METODO_GEO], ["Confianza", v.CONFIANZA_GEO], ["Observación", v.OBSERVACION_GEO]);
      else rows.push(["Parroquia", v.PARROQUIA], ["Grupo territorial", v.GRUPO || v.AMBITO_HOTSPOT], ["Gi* Delincuencia / Violencia", `${number(v.NIVEL_DEL)} % / ${number(v.NIVEL_VIOL)} %`], ["D / V / C a 200 m", `${number(v.DELINCUENCIA_200M)} / ${number(v.VIOLENCIA_200M)} / ${number(v.CONVIVENCIA_200M)}`], ["Población asociada estimada", number(v.POBLACION_ASOCIADA)], ["UPC cercana", v.NOMBRE_UPC], ["Distancia a UPC", `${number(v.DIST_UPC_M)} m`], ["Justificación", v.JUSTIFICACION]);
      if (selected.group === "police") rows.push(["Eventos D+V exclusivos", number(v.EVENTOS_DV_NUEVOS)], ["Solape con cobertura previa", pct(v.SOLAPE_PREVIO_PCT)], ["Fuente del cruce", v.FUENTE_CRUCE], ["Alcance visual", v.ALCANCE_VISUAL], ["Decisión final", v.DECISION_FINAL]);
    } else if (selected?.kind === "macajiSegment") {
      title = labels.macajiSegment;
      rows = [["Longitud del tramo", `${number(v.LONGITUD_M / 1000, 2)} km`], ["Fuente", v.FUENTE]];
    } else if (selected?.kind === "corridor") {
      title = names[v.CORREDOR]; const r = data.results.corridors.find(r => r.ESCENARIO === scenario() && r.CORREDOR === v.CORREDOR);
      rows = [["Longitud total", `${number(r.TOTAL_M / 1000, 2)} km`], ["Cubierta", `${number(r.CUBIERTO_M / 1000, 2)} km`], ["Sin cobertura", `${number(r.NO_CUBIERTO_M)} m`], ["% cubierto", pct(r.PCT_CUBIERTO)]];
    } else if (selected?.kind === "void") {
      title = v.ID; rows = [["Longitud sin cobertura · 183", `${number(v.LONGITUD_M, 1)} m`], ["Cámara más próxima", v.CAMARA_MAS_CERCANA], ["Distancia al segmento", `${number(v.DIST_CAMARA_M, 1)} m`]];
    } else if (selected?.kind === "platform") {
      title = v.platform_name; rows = [["Fuente", "Plataformas Territoriales reales"], ["Escenario", scenarioControl.selectedOptions[0].text], ["Radio potencial", "200 m"]];
    }
    el.detailTitle.textContent = selected ? "Detalle de evaluación" : "Impacto de la propuesta";
    el.detail.innerHTML = `<section class="proposal-detail"><h3>${esc(title)}</h3>${rowHtml(rows)}<div id="proposalDetailMap" class="proposal-detail-map"></div><p>La cobertura representa proximidad geométrica, no visibilidad ni tiempo de respuesta. La visión se orienta por las vías; no se presupone alcance a través de manzanas o detrás de esquinas.</p>${links()}</section>`;
    mini(f);
  }
  function graphics() {
    const codes = ["A", "B", "C"], r = data.results;
    let html = api.metricBars("Incidentes potencialmente cubiertos · escenario seleccionado", ["DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA"].map(category => {
      const v = r.incidents.find(x => x.ESCENARIO === scenario() && x.AMBITO === "CANTONAL" && x.CATEGORIA === category);
      return { label: category, value: Number(v.PCT_CUBIERTO.toFixed(1)), color: "#246db5" };
    }), 100, "#246db5");
    html += table("Comparación de escenarios · radio 200 m", ["Indicador", "103 existentes", "103 + 50", "103 + 50 + 30"], [
      ["Área urbana cubierta · km²", ...codes.map(k => number(metric("territorial", k).AREA_CUBIERTA_URBANA_KM2, 2))],
      ["Territorio urbano cubierto", ...codes.map(k => pct(metric("territorial", k).PCT_URBANO))],
      ["Población urbana cubierta estimada", ...codes.map(k => number(metric("population", k).POBLACION_CUBIERTA))],
      ["Población urbana cubierta · %", ...codes.map(k => pct(metric("population", k).PCT_CUBIERTO))],
      ...["DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA"].map(category => [esc(category) + " · cubierto cantonal", ...codes.map(k => pct(r.incidents.find(x => x.ESCENARIO === k && x.AMBITO === "CANTONAL" && x.CATEGORIA === category).PCT_CUBIERTO))])
    ], "Las coberturas se calculan sobre la unión disuelta: no se suman áreas superpuestas. Población: estimación areal CPV2022 en las 18 Plataformas; no población rural completa.");
    const gaps = window.RIOBAMBA_UPDATED_GAPS;
    if (gaps) html += table("Brechas por manzana · clasificación provisional · 200 m", ["Nivel", "103 existentes", "103 + 50", "103 + 50 + 30"],
      ["ALTA", "MEDIA", "BAJA", "SIN EVIDENCIA"].map(level => [esc(level), ...codes.map(k => k === "C" && r.gapScenarioCValidated === false ? "No disponible" : number(gaps.scenarios["200"][k].gapCounts[level]))]),
      `${gaps.metadata.eventAssignment} Reglas operativas sin ponderaciones; no representa peligrosidad. Las brechas por manzana del escenario 183 anterior no se reutilizan tras las ocho reubicaciones policiales. Los escenarios 103 y 153 se conservan.`);
    html += table("Cobertura de corredores", ["Corredor", "Longitud km", "103 · %", "153 · %", "183 · %", "Sin cobertura 183 · m"], Object.entries(names).map(([key, label]) => {
      const values = codes.map(k => r.corridors.find(x => x.ESCENARIO === k && x.CORREDOR === key));
      return [`<button type="button" data-proposal-corridor="${key}">${esc(label)}</button>`, number(values[0].TOTAL_M / 1000, 2), ...values.map(v => pct(v.PCT_CUBIERTO)), number(values[2].NO_CUBIERTO_M)];
    }));
    html += `<section class="proposal-report"><p class="proposal-warning">La prioridad de maximizar el Anillo, después de Macají ≥98 %, reduce la cobertura de Ciclovías respecto a la propuesta anterior. El informe conserva la comparación y las alternativas; no se presenta como mejora de todos los corredores.</p></section>`;
    html += table("Hot Spots · atención por escenario seleccionado", ["Ámbito", "Categoría", "Nivel", "Celdas", "Completas", "Parciales", "Sin cobertura", "% área cubierta"], r.hotspots.filter(v => v.ESCENARIO === scenario()).map(v => [esc(v.AMBITO), esc(v.CATEGORIA), `${v.NIVEL} %`, number(v.TOTAL), number(v.CUBIERTO), number(v.PARCIAL), number(v.SIN_COBERTURA), pct(v.PCT_AREA_CUBIERTA)]), "Son celdas estadísticas, no número de concentraciones. Gi* original conservado, urbano 100/200 m y rural sin cambios.");
    html += `<section class="proposal-report"><details><summary>Inventario y propuestas · 183 equipos</summary>` + table("Cámaras", ["ID", "Grupo", "Estado", "Para cambio", "X", "Y"], Object.keys(groups).flatMap(key => data[key].features.map(f => {
      const p = f.properties; return [`<button type="button" data-proposal-camera="${esc(cameraId(f))}" data-group="${key}">${esc(cameraId(f))}</button>`, esc(groups[key]), esc(p.ESTADO || p.ESTADO_VALIDACION || "No disponible"), key === "existing" ? (change(f) ? "Sí" : "No") : "No aplica", number(p.X, 2), number(p.Y, 2)];
    }))) + `</details>${links()}</section>`;
    el.graphicAnalysis.innerHTML = html;
    el.graphicAnalysis.querySelectorAll("[data-proposal-camera]").forEach(n => n.addEventListener("click", () => {
      const group = n.dataset.group, f = data[group].features.find(f => cameraId(f) === n.dataset.proposalCamera);
      if (!groupEnabled(group)) { scenarioControl.value = group === "police" ? "future" : "municipal"; render(); }
      toggles[group === "existing" && change(f) ? "change" : group] = true; syncToggles(); syncLayers(); selectEntity({ kind: "camera", group, feature: f }); map.setView(point(f), 16, { animate: false });
    }));
    el.graphicAnalysis.querySelectorAll("[data-proposal-corridor]").forEach(n => n.addEventListener("click", () => {
      const toggle = Object.keys(corridorToggles).find(key => corridorToggles[key] === n.dataset.proposalCorridor);
      if (toggle) { toggles[toggle] = true; syncToggles(); syncLayers(); renderLegend(); }
      const f = data.corridors.features.find(f => f.properties.CORREDOR === n.dataset.proposalCorridor);
      selectEntity({ kind: "corridor", feature: f }, L.geoJSON(f).getBounds());
    }));
  }
  function renderMethodology() {
    const panel = document.getElementById("methodologyPanel"); if (!panel) return;
    const replacementCount = data?.results.counts.changeIncluded ?? api.inventory.filter(c => c.requiresChange).length;
    const quality = data?.results.inventoryGeolocation;
    const geolocation = quality ? `${quality.documentedUnchanged} documentadas intactas; ${quality.reviewedApprovedIntersections} cruces revisados/aprobados; ${quality.pendingValidation} pendientes` : "103 equipos / procedencia conservada";
    panel.innerHTML = `<h3>Evaluación de videovigilancia</h3>${rowHtml([["Inventario existente", geolocation], ["Requieren cambio", `${replacementCount} incluidas en las 103 existentes`], ["Municipio / Policía", "50 / 30 propuestas, no instaladas"], ["CRS métrico / visual", "EPSG:32717 / EPSG:4326"], ["Radio potencial", "200 m (no diámetro)"], ["Cobertura", "Buffers métricos; unión disuelta; intersección con puntos, líneas y polígonos"], ["Población", "Estimación areal CPV2022 dentro de 18 Plataformas; rural completa no disponible"], ["Policía · criterio principal", "KDE urbano de Delincuencia + Violencia; aporte marginal"], ["Policía · emplazamiento", "30 nodos reales de grado ≥3 en vías Expresa, Arterial o Colectora"], ["Hot Spots", "Gi* de referencia, conservado por ámbito y categoría; sin recálculo"], ["Cámaras coincidentes", "Equipos conservados; cobertura disuelta sin doble conteo"]])}<p>Las 50 propuestas municipales y las 30 policiales permanecen fijas en este recálculo. KDE y Gi* no se recalculan.</p><p>La continuidad de observación por ejes es un objetivo parcial por la cantidad limitada de cámaras. Los radios no certifican visibilidad: se requiere validar poste, altura, orientación y obstáculos en campo. ${quality ? esc(quality.warning) : "Las ubicaciones estimadas conservan sus limitaciones documentadas."}</p>${links()}`;
  }
  async function render() {
    if (!api.active()) return;
    const version = ++renderVersion;
    active = true; el.workspace.classList.add("proposal-active"); clearLegacyLayers();
    el.overlayTitle.textContent = "Sistema de videovigilancia · propuestas finales";
    if (!data) {
      el.summary.textContent = "Cargando resultados finales…"; el.detail.textContent = "Cargando evaluación.";
      el.detailTitle.textContent = "Evaluación de cámaras";
      el.overlayText.textContent = "Cargando resultados finales…";
      el.graphicAnalysis.textContent = "Cargando evaluación.";
      el.legend.textContent = "Cargando capas.";
      try { await load(); } catch (error) { if (api.active() && version === renderVersion) { el.detail.textContent = `No se pudo cargar: ${error.message}`; el.summary.textContent = "Evaluación no disponible"; } return; }
    }
    if (!api.active() || version !== renderVersion) return;
    const area = metric("territorial"), population = metric("population");
    const total = Object.keys(groups).filter(groupEnabled).reduce((n, k) => n + data[k].features.length, 0);
    const quality = data.results.inventoryGeolocation;
    el.overlayText.textContent = `${total} equipos en el escenario · radio 200 m · cobertura potencial${quality ? ` · ${quality.documentedUnchanged} documentadas intactas · ${quality.pendingValidation} provisionales pendientes` : " · originales conservados"}`;
    const existingCount = data.existing.features.length;
    const changeCount = data.existing.features.filter(change).length;
    el.summary.innerHTML = [["Cámaras existentes", existingCount, "existing change"], ["Requieren cambio", `${changeCount} de las ${existingCount}`, "change"], ["Sin cambio requerido", existingCount - changeCount, "existing"], ["Municipales propuestas", scenario() === "A" ? 0 : 50, "municipal"], ["Policía propuesta", scenario() === "C" ? 30 : 0, "police"], ["Área urbana cubierta", `${number(area.AREA_CUBIERTA_URBANA_KM2, 2)} km²`], ["Población urbana cubierta", `${number(population.POBLACION_CUBIERTA)} · ${pct(population.PCT_CUBIERTO)}`]].map(([label, value, symbols]) => `<div class="card"><span>${symbols ? symbols.split(" ").map(symbol => `<i class="proposal-key ${symbol}" aria-hidden="true"></i>`).join("") : ""}${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("")
      + `<p class="proposal-inventory-note">Las ${changeCount} cámaras para cambio están incluidas en las ${existingCount} existentes; no son cámaras adicionales. ${existingCount - changeCount} + ${changeCount} = ${existingCount}.${quality ? ` ${esc(quality.warning)}` : ""}</p>`;
    syncToggles(); draw(); detail(); graphics(); renderLegend();
    map.invalidateSize(); if (fitNeeded) fit();
    el.status.textContent = `103 existentes (${changeCount} para cambio) + 50 Municipio + 30 Policía. Radio potencial 200 m; ${quality ? `${quality.pendingValidation} posiciones provisionales pendientes incluidas` : "ubicaciones estimadas documentadas"}. Propuestas, KDE y Gi* sin cambios.`;
  }
  scenarioControl.addEventListener("change", () => { selected = null; render(); });
  extentControl.addEventListener("change", () => { fitNeeded = true; render(); });
  controls.querySelectorAll("[data-proposal-layer]").forEach(n => n.addEventListener("change", () => {
    toggles[n.dataset.proposalLayer] = n.checked; syncToggles(); syncLayers(); renderLegend();
    if (cameraLayerKeys.includes(n.dataset.proposalLayer) || n.dataset.proposalLayer === "urbanAxes" || n.dataset.proposalLayer === "macajiSegment" || corridorToggles[n.dataset.proposalLayer]) { removeMini(); mini(selected?.feature); }
  }));
  window.addEventListener("resize", () => { if (api.active()) requestAnimationFrame(() => miniMap?.invalidateSize()); });
  map.on("zoomend moveend resize", schedulePlatformLabels);
  return { render, leave, reset, clearLegacyLayers, renderLegend, renderMethodology, invalidateMiniMap: () => miniMap?.invalidateSize() };
};
