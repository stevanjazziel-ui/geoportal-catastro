/* Final GIS results in UTM 17S; Leaflet renders their WGS84 derivatives. */
window.createRiobambaCameraProposal = function (api) {
  "use strict";
  const { map, elements: el, esc } = api;
  const root = "./data/seguridad-riobamba/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA/";
  const controls = document.getElementById("proposalLayerControls");
  const scenarioControl = document.getElementById("proposalScenario");
  const radiusControl = document.getElementById("proposalRadius");
  const extentControl = document.getElementById("proposalExtent");
  const colors = { existing: "#246db5", change: "#8b46b5", municipal: "#18815b", police: "#e8bd16" };
  const groups = { existing: "Existentes", municipal: "Municipio · propuesta", police: "Policía · propuesta" };
  const names = { BOULEVARD_MACAJI_BELLAVISTA: "Macají–Bellavista", CICLOVIAS: "Ciclovías", ANILLO_VIAL: "Anillo vial", QUEBRADA_LAS_ABRAS: "Las Abras" };
  const corridorColors = { BOULEVARD_MACAJI_BELLAVISTA: "#297d55", CICLOVIAS: "#246db5", ANILLO_VIAL: "#a564ad", QUEBRADA_LAS_ABRAS: "#16a1b2" };
  const defaults = { existing: true, municipal: true, police: true, existingRadius: true, municipalRadius: true, policeRadius: true, platforms: true, hotspots: false, corridors: true, voids: false };
  const toggles = { ...defaults };
  const labels = { existing: "Existentes · 103 (31 para cambio)", municipal: "Municipio · 50 propuestas", police: "Policía · 30 propuestas", existingRadius: "Radio existentes · 200 m", municipalRadius: "Radio Municipio · 200 m", policeRadius: "Radio Policía · 200 m", platforms: "18 Plataformas", hotspots: "Hot Spots · Gi*", corridors: "Corredores", voids: "Tramos sin cobertura · escenario 183" };
  const layers = {};
  let data, loading, active = false, fitNeeded = true, drawKey = "", selected = null, miniMap = null;
  let hotspotScope = "URBANO", hotspotCategory = "DELINCUENCIA";
  const number = (v, digits = 0) => v == null || !Number.isFinite(Number(v)) ? "No disponible" : Number(v).toLocaleString("es-EC", { maximumFractionDigits: digits });
  const pct = v => v == null ? "No disponible" : `${number(v, 1)} %`;
  const scenario = () => ({ actual: "A", municipal: "B", future: "C" })[scenarioControl.value] || "C";
  const groupEnabled = key => key === "existing" || (key === "municipal" && scenario() !== "A") || (key === "police" && scenario() === "C");
  const cameraId = f => f.properties.ID_CAMARA || f.properties.ID_PROPUESTA || f.properties.ID_POLICIA;
  const change = f => f.properties.REQUIERE_CAMBIO === true;
  const point = f => [f.geometry.coordinates[1], f.geometry.coordinates[0]];
  const fc = features => ({ type: "FeatureCollection", features });
  const rowHtml = rows => rows.map(([label, value]) => `<div class="mini-row"><span>${esc(label)}</span><strong>${esc(value ?? "No disponible")}</strong></div>`).join("");
  const table = (title, headings, rows, note = "") => `<section class="proposal-report"><h3>${esc(title)}</h3><div class="proposal-table-wrap"><table class="mini-table"><thead><tr>${headings.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(v => `<td>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${note ? `<p>${esc(note)}</p>` : ""}</section>`;
  const links = () => `<div class="proposal-links"><a href="${root}../CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.zip" download>Paquete GIS ZIP</a><a href="${root}../BRECHAS_ACTUALIZADAS_20261004.zip" download>Brechas recalculadas ZIP</a><a href="${root}CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.gpkg" download>GeoPackage</a><a href="${root}CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.qgz" download>QGIS</a><a href="${root}index.html" target="_blank" rel="noopener">Mapas finales</a><a href="${root}INFORME_FINAL.md" target="_blank" rel="noopener">Informe y metodología</a><a href="${root}RESULTADOS.json" download>Resultados</a><a href="${root}VALIDACION.json" download>Validación GIS</a></div>`;
  const metric = (kind, code = scenario()) => data.results[kind].find(r => r.ESCENARIO === code);

  controls.innerHTML = Object.entries(labels).map(([key, label]) => `<label>${esc(label)}<input type="checkbox" data-proposal-layer="${key}" ${toggles[key] ? "checked" : ""}></label>`).join("") +
    `<label for="proposalHotspotScope">Ámbito Gi*</label><select id="proposalHotspotScope" aria-label="Ámbito de Hot Spots"><option value="URBANO">Urbano</option><option value="RURAL">Rural · exploratorio</option></select>` +
    `<label for="proposalHotspotCategory">Categoría Gi*</label><select id="proposalHotspotCategory" aria-label="Categoría de Hot Spots"><option>DELINCUENCIA</option><option>VIOLENCIA</option><option>CONVIVENCIA</option></select>`;
  function syncToggles() {
    controls.querySelectorAll("[data-proposal-layer]").forEach(n => {
      n.checked = toggles[n.dataset.proposalLayer];
      n.disabled = !groupEnabled(n.dataset.proposalLayer.replace("Radius", "")) && /^(municipal|police)/.test(n.dataset.proposalLayer);
    });
  }
  function clearLegacyLayers() { api.layers().forEach(layer => { if (map.hasLayer(layer)) map.removeLayer(layer); }); }
  function removeMini() { miniMap?.remove(); miniMap = null; }
  function leave() {
    if (!active) return;
    active = false; el.workspace.classList.remove("proposal-active");
    Object.values(layers).forEach(layer => map.removeLayer(layer));
    removeMini(); drawKey = "";
  }
  function reset() {
    scenarioControl.value = "future"; radiusControl.value = "200"; extentControl.value = "urban";
    Object.assign(toggles, defaults); selected = null; fitNeeded = true; syncToggles();
  }
  async function load() {
    if (data) return;
    if (!loading) loading = (async () => {
      const files = { results: "RESULTADOS.json", existing: "CAMARAS_EXISTENTES_103_FINAL.geojson", municipal: "PROPUESTA_MUNICIPAL_50_FINAL.geojson", police: "PROPUESTA_POLICIA_30_FINAL.geojson",
        existingRadius: "RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson", municipalRadius: "COBERTURA_MUNICIPAL_200M.geojson", policeRadius: "COBERTURA_POLICIA_200M.geojson", platforms: "PLATAFORMAS_TERRITORIALES.geojson", corridors: "CORREDORES.geojson",
        DELINCUENCIA: "HOTSPOT_DELINCUENCIA.geojson", VIOLENCIA: "HOTSPOT_VIOLENCIA.geojson", CONVIVENCIA: "HOTSPOT_CONVIVENCIA.geojson" };
      const entries = await Promise.all(Object.entries(files).map(async ([key, name]) => {
        const response = await fetch(root + name + "?v=cierre-183-20261004");
        if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
        return [key, await response.json()];
      }));
      const next = Object.fromEntries(entries);
      for (const [key, expected] of [["existing", 103], ["municipal", 50], ["police", 30]]) {
        if (next[key].features.length !== expected || next[key].features.some(f => !f.geometry || f.geometry.type !== "Point" || !f.geometry.coordinates.every(Number.isFinite))) throw new Error(`Inventario ${key} inconsistente`);
      }
      if (next.existing.features.filter(change).length !== 31) throw new Error("Conteo de cámaras para cambio inconsistente");
      const voids = await Promise.all(["MACAJI", "ANILLO", "CICLOVIAS", "LAS_ABRAS"].map(async name => {
        const response = await fetch(root + `BRECHA_${name}_FINAL.geojson`);
        if (!response.ok) throw new Error(`Brecha ${name}: HTTP ${response.status}`);
        return response.json();
      }));
      next.voids = fc(voids.flatMap(r => r.features)); data = next;
      console.info("[Cierre videovigilancia]", { existentes: 103, paraCambio: 31, municipales: 50, policia: 30, radioM: 200, crs: "EPSG:32717", fuente: root });
    })().catch(error => { loading = null; throw error; });
    return loading;
  }
  function pane(name, z) {
    const id = `proposal-${name}`;
    if (!map.getPane(id)) map.createPane(id).style.zIndex = z;
    return id;
  }
  function icon(key, f) {
    const symbol = key === "existing" && change(f) ? "change" : key;
    return L.divIcon({ className: `proposal-camera-icon proposal-camera-${symbol}`, html: "<span></span>", iconSize: [20, 20], iconAnchor: [10, 10] });
  }
  const coverageStyle = key => ({ color: colors[key], weight: 1, opacity: .65, fillColor: colors[key], fillOpacity: .18 });
  const radiusStyle = key => feature => coverageStyle(key === "existing" && change(feature) ? "change" : key);
  function selectEntity(value, bounds) {
    selected = value; detail();
    if (bounds?.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 17, animate: false });
  }
  function replaceLayer(key, layer) { if (layers[key]) map.removeLayer(layers[key]); layers[key] = layer; }
  function draw() {
    const key = `${hotspotScope}-${hotspotCategory}`;
    if (drawKey === key) { syncLayers(); return; }
    drawKey = key;
    for (const group of Object.keys(groups)) {
      replaceLayer(group, L.geoJSON(data[group], { pane: pane("points", 460), pointToLayer: (f, pos) => L.marker(pos, { icon: icon(group, f), keyboard: true, title: cameraId(f) }),
        onEachFeature: (f, layer) => {
          const select = () => selectEntity({ kind: "camera", group, feature: f });
          const keyboard = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); select(); } };
          layer.bindTooltip(`${esc(cameraId(f))} · ${esc(groups[group])}${change(f) ? " · Requiere cambio" : ""}`).on("click", select);
          layer.on("add", () => { const node = layer.getElement(); L.DomEvent.off(node, "keydown", keyboard); L.DomEvent.on(node, "keydown", keyboard); });
        } }));
      replaceLayer(group + "Radius", L.geoJSON(data[group + "Radius"], { pane: pane("coverage", 410), interactive: false, style: radiusStyle(group) }));
    }
    replaceLayer("platforms", L.geoJSON(data.platforms, { pane: pane("platforms", 440), style: { color: "#385a52", weight: 1.6, fill: false },
      onEachFeature: (f, layer) => layer.bindTooltip(esc(f.properties.platform_name)).on("click", () => selectEntity({ kind: "platform", feature: f })) }));
    replaceLayer("corridors", L.geoJSON(data.corridors, { pane: pane("lines", 430), style: f => ({ color: corridorColors[f.properties.CORREDOR], weight: 2.5, opacity: .85 }),
      onEachFeature: (f, layer) => layer.bindTooltip(esc(names[f.properties.CORREDOR])).on("click", () => selectEntity({ kind: "corridor", feature: f })) }));
    replaceLayer("hotspots", L.geoJSON(fc(data[hotspotCategory].features.filter(f => f.properties.AMBITO === hotspotScope)), { pane: pane("hotspots", 420),
      style: f => ({ color: "#b14242", weight: .6, fillColor: f.properties.NIVEL === 99 ? "#c74f5b" : f.properties.NIVEL === 95 ? "#e69383" : "#f1c5a0", fillOpacity: .25 }),
      onEachFeature: (f, layer) => layer.bindTooltip(`${esc(f.properties.AMBITO)} · ${esc(f.properties.CATEGORIA)} · ${esc(f.properties.GI_CLASS)}`).on("click", () => selectEntity({ kind: "hotspot", feature: f })) }));
    replaceLayer("voids", L.geoJSON(data.voids, { pane: pane("voids", 435), style: { color: "#c24c58", weight: 4, dashArray: "6 5", opacity: .9 },
      onEachFeature: (f, layer) => layer.bindTooltip(`${esc(f.properties.ID)} · ${number(f.properties.LONGITUD_M, 1)} m`).on("click", () => selectEntity({ kind: "void", feature: f })) }));
    syncLayers();
  }
  function syncLayers() {
    clearLegacyLayers(); if (!active) return;
    Object.entries(layers).forEach(([key, layer]) => {
      const enabled = toggles[key] && (!/^(existing|municipal|police)/.test(key) || groupEnabled(key.replace("Radius", ""))) && (key !== "voids" || scenario() === "C");
      enabled ? layer.addTo(map) : map.removeLayer(layer);
    });
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
    el.legend.innerHTML = `<div><span class="proposal-key existing"></span>Existentes · 103</div><div><span class="proposal-key change"></span>Requieren cambio · 31 de las 103</div><div><span class="proposal-key municipal"></span>Municipio · 50 propuestas</div><div><span class="proposal-key police"></span>Policía · 30 propuestas</div>` +
      Object.keys(groups).filter(groupEnabled).map(k => `<div><span class="proposal-key" style="background:${colors[k]};opacity:.5"></span>Radio ${esc(groups[k])} · 200 m</div>`).join("") +
      `<div><span class="proposal-key" style="background:${colors.change};opacity:.5"></span>Radio para cambio · 200 m</div>` +
      (toggles.hotspots ? `<div>Gi*: ${esc(hotspotScope)} / ${esc(hotspotCategory)} · 90/95/99 %</div>` : "") +
      Object.entries(corridorColors).map(([k, color]) => `<div><span class="proposal-key" style="background:${color}"></span>${esc(names[k])}</div>`).join("") + `<div>Radios geométricos potenciales, no campo visual efectivo.</div>`;
  }
  function mini(feature) {
    const node = document.getElementById("proposalDetailMap"); if (!node) return;
    miniMap = L.map(node, { zoomControl: false, scrollWheelZoom: false, preferCanvas: true, zoomAnimation: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap", className: "osm-gray-tile", maxZoom: 20 }).addTo(miniMap);
    for (const key of Object.keys(groups).filter(groupEnabled)) {
      L.geoJSON(data[key + "Radius"], { interactive: false, style: radiusStyle(key) }).addTo(miniMap);
      L.geoJSON(data[key], { pointToLayer: (f, pos) => L.marker(pos, { icon: icon(key, f), title: cameraId(f) }) }).addTo(miniMap);
    }
    L.geoJSON(data.platforms, { interactive: false, style: { color: "#385a52", weight: 1, fill: false } }).addTo(miniMap);
    if (feature?.geometry.type === "Point") miniMap.setView(point(feature), 16);
    else {
      const focus = L.geoJSON(feature || data.platforms, { style: { color: "#385a52", weight: 2, fillOpacity: .08 } }).addTo(miniMap);
      miniMap.fitBounds(focus.getBounds(), { padding: [12, 12], maxZoom: 16, animate: false });
    }
    requestAnimationFrame(() => miniMap?.invalidateSize());
  }
  function detail() {
    removeMini();
    const a = metric("territorial"), p = metric("population"), f = selected?.feature, v = f?.properties;
    let title = "Escenario " + ({ A: "103 existentes", B: "153 equipos", C: "183 equipos" })[scenario()];
    let rows = [["Radio", "200 m"], ["Área urbana cubierta", `${number(a.AREA_CUBIERTA_URBANA_KM2, 2)} km²`], ["Territorio urbano cubierto", pct(a.PCT_URBANO)], ["Población urbana cubierta estimada", number(p.POBLACION_CUBIERTA)], ["% población urbana cubierta", pct(p.PCT_CUBIERTO)], ["Población rural cubierta", "No disponible"]];
    if (selected?.kind === "camera") {
      title = cameraId(f);
      rows = [["Grupo", groups[selected.group]], ["Estado", v.ESTADO || v.ESTADO_VALIDACION], ["Dirección / nodo", v.DIRECCION || v.INTERSECCION_O_NODO], ["Radio potencial", "200 m"], ["X / Y · EPSG:32717", `${number(v.X, 2)} / ${number(v.Y, 2)}`]];
      if (selected.group === "existing") rows.push(["Requiere cambio", change(f) ? "Sí" : "No"], ["Método geográfico", v.METODO_GEO], ["Confianza", v.CONFIANZA_GEO], ["Observación", v.OBSERVACION_GEO]);
      else rows.push(["Parroquia", v.PARROQUIA], ["Grupo territorial", v.GRUPO || v.AMBITO_HOTSPOT], ["Gi* Delincuencia / Violencia", `${number(v.NIVEL_DEL)} % / ${number(v.NIVEL_VIOL)} %`], ["D / V / C a 200 m", `${number(v.DELINCUENCIA_200M)} / ${number(v.VIOLENCIA_200M)} / ${number(v.CONVIVENCIA_200M)}`], ["Población asociada estimada", number(v.POBLACION_ASOCIADA)], ["UPC cercana", v.NOMBRE_UPC], ["Distancia a UPC", `${number(v.DIST_UPC_M)} m`], ["Justificación", v.JUSTIFICACION]);
      if (selected.group === "police") rows.push(["Eventos D+V exclusivos", number(v.EVENTOS_DV_NUEVOS)], ["Solape con cobertura previa", pct(v.SOLAPE_PREVIO_PCT)], ["Decisión final", v.DECISION_FINAL]);
    } else if (selected?.kind === "hotspot") {
      title = v.CELL_ID; rows = [["Ámbito / categoría", `${v.AMBITO} / ${v.CATEGORIA}`], ["Clase", v.GI_CLASS], ["Registros", number(v.COUNT)], ["Gi* / z-score", number(v.GI_ZSCORE, 4)], ["p-value", number(v.GI_PVALUE, 6)], ["Distancia estadística", `${number(v.DISTANCE_M)} m`], ["Cobertura del escenario", pct(v[`COB_${scenario()}_PCT`])], ["Atención geométrica", v[`ESTADO_${scenario()}`]]];
    } else if (selected?.kind === "corridor") {
      title = names[v.CORREDOR]; const r = data.results.corridors.find(r => r.ESCENARIO === scenario() && r.CORREDOR === v.CORREDOR);
      rows = [["Longitud total", `${number(r.TOTAL_M / 1000, 2)} km`], ["Cubierta", `${number(r.CUBIERTO_M / 1000, 2)} km`], ["Sin cobertura", `${number(r.NO_CUBIERTO_M)} m`], ["% cubierto", pct(r.PCT_CUBIERTO)]];
    } else if (selected?.kind === "void") {
      title = v.ID; rows = [["Longitud sin cobertura · 183", `${number(v.LONGITUD_M, 1)} m`], ["Cámara más próxima", v.CAMARA_MAS_CERCANA], ["Distancia al segmento", `${number(v.DIST_CAMARA_M, 1)} m`]];
    } else if (selected?.kind === "platform") {
      title = v.platform_name; rows = [["Fuente", "Plataformas Territoriales reales"], ["Escenario", scenarioControl.selectedOptions[0].text], ["Radio potencial", "200 m"]];
    }
    el.detailTitle.textContent = selected ? "Detalle de evaluación" : "Impacto de la propuesta";
    el.detail.innerHTML = `<section class="proposal-detail"><h3>${esc(title)}</h3>${rowHtml(rows)}<div id="proposalDetailMap" class="proposal-detail-map"></div><p>La cobertura representa proximidad geométrica, no visibilidad ni tiempo de respuesta.</p>${links()}</section>`;
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
      ["ALTA", "MEDIA", "BAJA", "SIN EVIDENCIA"].map(level => [esc(level), ...codes.map(k => number(gaps.scenarios["200"][k].gapCounts[level]))]),
      `${gaps.metadata.eventAssignment} Reglas operativas sin ponderaciones; población y problemática constantes entre escenarios. No representa peligrosidad. Descarga GIS disponible en Brechas recalculadas ZIP.`);
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
      toggles[group] = true; syncToggles(); syncLayers(); selectEntity({ kind: "camera", group, feature: f }); map.setView(point(f), 16, { animate: false });
    }));
    el.graphicAnalysis.querySelectorAll("[data-proposal-corridor]").forEach(n => n.addEventListener("click", () => {
      const f = data.corridors.features.find(f => f.properties.CORREDOR === n.dataset.proposalCorridor);
      selectEntity({ kind: "corridor", feature: f }, L.geoJSON(f).getBounds());
    }));
  }
  function renderMethodology() {
    const panel = document.getElementById("methodologyPanel"); if (!panel) return;
    panel.innerHTML = `<h3>Cierre final de videovigilancia</h3>${rowHtml([["Inventario existente", "103 equipos / 103 geometrías"], ["Requieren cambio", "31 del inventario existente"], ["Municipio / Policía", "50 / 30 propuestas, no instaladas"], ["CRS métrico / visual", "EPSG:32717 / EPSG:4326"], ["Radio potencial", "200 m (no diámetro)"], ["Cobertura", "Buffers métricos; unión disuelta; intersección con puntos, líneas y polígonos"], ["Población", "Estimación areal CPV2022 dentro de 18 Plataformas; rural completa no disponible"], ["Hot Spots", "Gi* congelado por ámbito y categoría; no se recalculó para cobertura"], ["Cámaras coincidentes", "Equipos conservados; cobertura disuelta sin doble conteo"]])}<p>Las propuestas municipales atienden cabeceras, Las Abras y red estructural. Policía se selecciona por Hot Spots de Delincuencia y Violencia; los corredores son beneficios secundarios. Las posiciones requieren validación operativa de campo.</p><p>La nueva priorización del Anillo reduce Ciclovías. Las discrepancias de georreferenciación de las cámaras recuperadas permanecen documentadas; no se certifica un levantamiento de campo.</p>${links()}`;
  }
  async function render() {
    active = true; el.workspace.classList.add("proposal-active"); clearLegacyLayers();
    el.overlayTitle.textContent = "Sistema de videovigilancia · propuestas finales";
    if (!data) {
      el.summary.textContent = "Cargando resultados finales…"; el.detail.textContent = "Cargando evaluación.";
      try { await load(); } catch (error) { if (api.active()) { el.detail.textContent = `No se pudo cargar: ${error.message}`; el.summary.textContent = "Evaluación no disponible"; } return; }
    }
    if (!api.active()) return;
    const area = metric("territorial"), population = metric("population");
    const total = Object.keys(groups).filter(groupEnabled).reduce((n, k) => n + data[k].features.length, 0);
    el.overlayText.textContent = `${total} equipos en el escenario · radio 200 m · cobertura potencial · originales conservados`;
    el.summary.innerHTML = [["Existentes", 103, "existing"], ["Para cambio · incluidas", 31, "change"], ["Municipales propuestas", scenario() === "A" ? 0 : 50, "municipal"], ["Policía propuesta", scenario() === "C" ? 30 : 0, "police"], ["Área urbana cubierta", `${number(area.AREA_CUBIERTA_URBANA_KM2, 2)} km²`], ["Población urbana cubierta", `${number(population.POBLACION_CUBIERTA)} · ${pct(population.PCT_CUBIERTO)}`]].map(([label, value, symbol]) => `<div class="card"><span>${symbol ? `<i class="proposal-key ${symbol}" aria-hidden="true"></i>` : ""}${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    syncToggles(); draw(); detail(); graphics(); renderLegend();
    map.invalidateSize(); if (fitNeeded) fit();
    el.status.textContent = "103 existentes (31 para cambio) + 50 Municipio + 30 Policía. Radio potencial 200 m. Gi* y geometrías originales conservados.";
  }
  scenarioControl.addEventListener("change", () => { selected = null; render(); });
  extentControl.addEventListener("change", () => { fitNeeded = true; render(); });
  controls.querySelectorAll("[data-proposal-layer]").forEach(n => n.addEventListener("change", () => { toggles[n.dataset.proposalLayer] = n.checked; syncLayers(); renderLegend(); }));
  document.getElementById("proposalHotspotScope").addEventListener("change", e => { hotspotScope = e.target.value; render(); });
  document.getElementById("proposalHotspotCategory").addEventListener("change", e => { hotspotCategory = e.target.value; render(); });
  window.addEventListener("resize", () => { if (api.active()) requestAnimationFrame(() => miniMap?.invalidateSize()); });
  return { render, leave, reset, clearLegacyLayers, renderLegend, renderMethodology };
};
