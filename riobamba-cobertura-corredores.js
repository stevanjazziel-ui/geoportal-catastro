/* Corridor coverage view backed by metric 200 m calculations. */
(function () {
  "use strict";

  window.createRiobambaCorridorCoverage = function createRiobambaCorridorCoverage(api) {
    const el = api.elements;
    const colors = { A: "#246db5", B: "#18815b", C: "#8b46b5" };
    const cameraColors = { existing: "#246db5", municipal: "#18815b", police: "#e8bd16" };
    const corridorLabels = {
      BOULEVARD_MACAJI_BELLAVISTA: "Macají–Bellavista",
      ANILLO_VIAL: "Anillo Vial",
      CICLOVIAS: "Ciclovías",
      QUEBRADA_LAS_ABRAS: "Quebrada Las Abras",
    };
    const scenarioLabels = {
      A: "Existentes · 103",
      B: "Existentes + municipales · 153",
      C: "Sistema completo · 183",
    };
    let data = null;
    let active = false;
    let renderVersion = 0;
    let selectedCorridor = "BOULEVARD_MACAJI_BELLAVISTA";
    let scenario = "B";
    let compare = false;
    let selected = null;
    let corridorLayer = null;
    let cameraLayer = null;
    let bufferLayer = null;
    let fitNeeded = true;
    let loadedPromise = null;

    const esc = api.esc || ((value) => String(value ?? ""));
    const fmt = api.fmt || ((value) => Number(value || 0).toLocaleString("es-EC"));
    const number = (value, decimals = 0) => Number(value || 0).toLocaleString("es-EC", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    const pct = (value) => `${number(value, 1)} %`;
    const km = (value) => `${number(Number(value || 0) / 1000, 2)} km`;
    const meters = (value) => `${number(value, 0)} m`;
    const rowHtml = (rows) => rows.map(([label, value]) => `<div class="mini-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    const selectedData = () => data?.scenarios?.[scenario];
    const corridorData = (key = selectedCorridor, code = scenario) => data?.scenarios?.[code]?.corridors?.[key];
    const cameraGroupVisible = (camera) => camera.group !== "police" || Boolean(el.toggleCorridorPolice?.checked);
    const visibleScenarioCameras = () => (selectedData()?.cameras || []).filter(cameraGroupVisible);
    const removeLayer = (layer) => { if (layer && api.map.hasLayer(layer)) api.map.removeLayer(layer); };
    const clearOwnLayer = (layer) => { removeLayer(layer); if (layer?.clearLayers) layer.clearLayers(); };

    function clearLegacyLayers() {
      (api.layers?.() || []).forEach((layer) => removeLayer(layer));
    }

    function clearOwnLayers() {
      clearOwnLayer(corridorLayer);
      clearOwnLayer(cameraLayer);
      clearOwnLayer(bufferLayer);
      corridorLayer = cameraLayer = bufferLayer = null;
    }

    function icon(camera) {
      const color = cameraColors[camera.group] || "#246db5";
      const shape = camera.group === "existing" && camera.requiresChange ? "square" : "circle";
      return L.divIcon({
        className: "corridor-camera-icon",
        html: `<span class="corridor-camera-dot ${shape}" style="--camera-color:${color}"></span>`,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      });
    }

    function featureStyle(kind, code = scenario) {
      if (compare && kind === "covered") return { color: colors[code], weight: 6, opacity: 0.82 };
      return kind === "covered"
        ? { color: "#18815b", weight: 7, opacity: 0.86 }
        : { color: "#d64545", weight: 6, opacity: 0.92, dashArray: "9 7" };
    }

    function segmentPopup(feature) {
      const p = feature.properties || {};
      return `<strong>${esc(p.TIPO === "SIN_COBERTURA" ? "Tramo sin cobertura" : "Tramo cubierto")}</strong><br>${esc(corridorLabels[p.CORREDOR] || p.CORREDOR)}<br>Longitud: ${meters(p.LONGITUD_M)}${p.TIPO === "SIN_COBERTURA" ? `<br>Cámara más cercana: ${esc(p.CAMARA_MAS_CERCANA || "No disponible")}<br>Distancia: ${meters(p.DISTANCIA_CAMARA_M)}` : ""}`;
    }

    function cameraPopup(camera, corridor) {
      const referenceOnly = corridor?.status === "REFERENCIA_SIN_INTERSECCION";
      return `<strong>${esc(camera.id)}</strong><br>Origen: ${esc(camera.origin)}<br>Tipo: ${esc(camera.type)}<br>Radio: 200 m<br>Corredor: ${esc(corridorLabels[selectedCorridor])}<br>Estado: ${referenceOnly ? "Referencia sin intersección con el tramo cantonal" : "Contribuye a la cobertura"}<br>Longitud cubierta por esta cámara: ${meters(corridor?.lengthM)}<br>Corredores atendidos: ${camera.corridors.map((item) => esc(item.name)).join(", ")}`;
    }

    function drawSegments() {
      corridorLayer = L.featureGroup().addTo(api.map);
      const add = (fc, kind, code = scenario) => L.geoJSON(fc, {
        style: () => featureStyle(kind, code),
        onEachFeature: (feature, layer) => layer.bindPopup(segmentPopup(feature)).on("click", () => { selected = { kind: "segment", feature }; renderDetail(); }),
      }).addTo(corridorLayer);
      if (compare) {
        ["A", "B", "C"].forEach((code) => add(corridorData(selectedCorridor, code).covered, "covered", code));
        add(corridorData(selectedCorridor, scenario).uncovered, "uncovered", scenario);
      } else {
        const current = corridorData();
        add(current.uncovered, "uncovered");
        add(current.covered, "covered");
      }
    }

    function drawCameras() {
      if (compare) return;
      const current = corridorData();
      bufferLayer = L.layerGroup();
      cameraLayer = L.layerGroup().addTo(api.map);
      const cameras = visibleScenarioCameras().filter((camera) => camera.corridors.some((corridor) => corridor.key === selectedCorridor));
      cameras.forEach((camera) => {
        const corridor = camera.corridors.find((item) => item.key === selectedCorridor);
        const color = cameraColors[camera.group] || "#246db5";
        if (el.toggleCorridorBuffers?.checked) L.circle([camera.lat, camera.lng], { radius: 200, color, weight: 1.5, opacity: 0.75, fillColor: color, fillOpacity: 0.13, interactive: false }).addTo(bufferLayer);
        L.marker([camera.lat, camera.lng], { icon: icon(camera), title: camera.id }).addTo(cameraLayer)
          .bindPopup(cameraPopup(camera, corridor))
          .bindTooltip(esc(camera.id), { direction: "top", opacity: 0.95 })
          .on("popupopen", () => { selected = { kind: "camera", camera, corridor }; renderDetail(); })
          .on("click", () => { selected = { kind: "camera", camera, corridor }; renderDetail(); });
      });
      if (el.toggleCorridorBuffers?.checked) bufferLayer.addTo(api.map);
      const currentCameraIds = new Set((current.cameras || []).map((camera) => camera.id));
      if (!cameras.length && currentCameraIds.size) el.status.textContent = "No hay cámaras que contribuyan individualmente a este corredor en el escenario seleccionado.";
    }

    function renderSummary() {
      const current = corridorData();
      if (!current) return;
      const meets = selectedCorridor === "BOULEVARD_MACAJI_BELLAVISTA" ? current.coveredPct >= 99.999 : null;
      el.summary.innerHTML = [
        ["Cobertura del corredor", pct(current.coveredPct)],
        ["Longitud total", km(current.totalM)],
        ["Longitud cubierta", km(current.coveredM)],
        ["Sin cobertura", meters(current.uncoveredM)],
        ["Cámaras contribuyentes", String((current.cameras || []).length)],
        [selectedCorridor === "BOULEVARD_MACAJI_BELLAVISTA" ? "Objetivo Macají" : "Estado del corredor", selectedCorridor === "BOULEVARD_MACAJI_BELLAVISTA" ? (meets ? "Cumple" : "No cumple") : "Referencia"],
      ].map(([label, value]) => `<div class="card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
    }

    function renderDetail() {
      if (selected?.kind === "camera") {
        const camera = selected.camera;
        const rows = [
          ["ID", camera.id], ["Origen", camera.origin], ["Tipo", camera.type], ["Radio", "200 m"],
          ["Corredor seleccionado", corridorLabels[selectedCorridor]], ["Longitud cubierta por esta cámara", meters(selected.corridor?.lengthM)],
          ["Estado", selected.corridor?.status === "REFERENCIA_SIN_INTERSECCION" ? "Referencia sin intersección con el tramo cantonal" : "Contribuye a la cobertura"],
          ["Corredores atendidos", camera.corridors.map((item) => item.name).join(", ")],
        ];
        el.detailTitle.textContent = "Detalle de cámara";
        el.detail.innerHTML = `<section class="corridor-detail"><h3>${esc(camera.id)}</h3>${rowHtml(rows)}<p>La longitud individual se informa por intersección del buffer métrico de 200 m con el eje; no se suma para obtener la cobertura total.</p></section>`;
        return;
      }
      if (selected?.kind === "segment") {
        const p = selected.feature.properties || {};
        el.detailTitle.textContent = p.TIPO === "SIN_COBERTURA" ? "Detalle de tramo sin cobertura" : "Detalle de tramo";
        el.detail.innerHTML = `<section class="corridor-detail"><h3>${esc(corridorLabels[p.CORREDOR] || p.CORREDOR)}</h3>${rowHtml([["Estado", p.TIPO === "SIN_COBERTURA" ? "Sin cobertura" : "Cubierto"], ["Longitud", meters(p.LONGITUD_M)], ["ID de tramo", p.ID], ["Cámara más cercana", p.CAMARA_MAS_CERCANA || "No disponible"], ["Distancia a cámara", meters(p.DISTANCIA_CAMARA_M)]])}<p>El segmento es resultado de la diferencia entre el eje del corredor y la unión disuelta de buffers de 200 m.</p></section>`;
        return;
      }
      const current = corridorData();
      el.detailTitle.textContent = "Detalle de corredor";
      el.detail.innerHTML = `<section class="corridor-detail"><h3>${esc(corridorLabels[selectedCorridor])}</h3>${rowHtml([["Escenario", scenarioLabels[scenario]], ["Radio", "200 m"], ["Longitud total", km(current.totalM)], ["Longitud cubierta", km(current.coveredM)], ["Longitud sin cobertura", meters(current.uncoveredM)], ["Cobertura", pct(current.coveredPct)], ["Cámaras que contribuyen", String((current.cameras || []).length)], ["Cámaras de referencia", String((current.referenceCameras || []).length)]])}<p>Las cámaras de referencia se muestran por su asociación operativa al corredor; solo cuentan como cobertura cuando su buffer intersecta el eje cantonal.</p></section>`;
    }

    function renderGraphics() {
      const rows = Object.keys(corridorLabels).map((key) => {
        const current = corridorData(key, scenario);
        return `<tr><td><button type="button" data-corridor-row="${key}">${esc(corridorLabels[key])}</button></td><td>${km(current.totalM)}</td><td>${km(current.coveredM)}</td><td>${meters(current.uncoveredM)}</td><td>${pct(current.coveredPct)}</td><td>${(current.cameras || []).length}</td></tr>`;
      }).join("");
      const bars = Object.keys(corridorLabels).map((key) => {
        const current = corridorData(key, scenario);
        return `<div class="corridor-bar-row"><span>${esc(corridorLabels[key])}</span><div><i style="width:${Math.max(0, Math.min(100, current.coveredPct))}%;background:#18815b"></i></div><strong>${pct(current.coveredPct)}</strong></div>`;
      }).join("");
      const comparison = Object.keys(corridorLabels).map((key) => `<tr><td>${esc(corridorLabels[key])}</td>${["A", "B", "C"].map((code) => `<td>${pct(corridorData(key, code).coveredPct)}</td>`).join("")}</tr>`).join("");
      el.graphicAnalysis.innerHTML = `<section class="graphic-card corridor-graphic-card"><h3>Cobertura de corredores · ${esc(scenarioLabels[scenario])}</h3>${bars}</section><section class="graphic-card corridor-graphic-card"><h3>Indicadores de corredores</h3><div class="table-scroll"><table class="mini-table"><thead><tr><th>Corredor</th><th>Total</th><th>Cubierto</th><th>Sin cobertura</th><th>% cubierto</th><th>Cámaras</th></tr></thead><tbody>${rows}</tbody></table></div></section><section class="graphic-card corridor-graphic-card"><h3>Comparación de escenarios · radio 200 m</h3><div class="table-scroll"><table class="mini-table"><thead><tr><th>Corredor</th><th>103</th><th>153</th><th>183</th></tr></thead><tbody>${comparison}</tbody></table></div></section>`;
      el.graphicAnalysis.querySelectorAll("[data-corridor-row]").forEach((node) => node.addEventListener("click", () => { selectedCorridor = node.dataset.corridorRow; selected = null; fitNeeded = true; syncControls(); render(); }));
    }

    function renderLegend() {
      el.legend.innerHTML = `<div><span class="corridor-key covered"></span>Tramo cubierto · buffer 200 m</div><div><span class="corridor-key uncovered"></span>Tramo sin cobertura</div><div><span class="corridor-key existing"></span>Cámara existente</div><div><span class="corridor-key change"></span>Existente para cambio</div><div><span class="corridor-key municipal"></span>Municipal propuesta</div><div><span class="corridor-key police"></span>Policía propuesta · oculta por defecto</div>${compare ? `<div><span class="corridor-key scenario-a"></span>103 existentes · comparación</div><div><span class="corridor-key scenario-b"></span>153 equipos · comparación</div><div><span class="corridor-key scenario-c"></span>183 equipos · comparación</div>` : ""}<div>Radio de influencia: 200 m (radio, no diámetro).</div>`;
    }

    function syncControls() {
      if (el.corridorSelect) el.corridorSelect.value = selectedCorridor;
      if (el.corridorScenario) el.corridorScenario.value = scenario;
      if (el.corridorCompareButton) { el.corridorCompareButton.classList.toggle("is-active", compare); el.corridorCompareButton.textContent = compare ? "Volver al escenario" : "Ver los 3"; }
      if (el.corridorLayerRow) el.corridorLayerRow.hidden = !active;
      if (el.corridorPoliceLayerRow) el.corridorPoliceLayerRow.hidden = !active;
      if (el.corridorBuffersLayerRow) el.corridorBuffersLayerRow.hidden = !active;
    }

    async function load() {
      if (loadedPromise) return loadedPromise;
      loadedPromise = fetch("./data/seguridad-riobamba/REUBICACION_POL24_20261007_B/CORRIDOR_COVERAGE_200M.json?v=lasabras-camaras-20261007")
        .then((response) => { if (!response.ok) throw new Error("No se pudo cargar la cobertura de corredores"); return response.json(); })
        .then((value) => { data = value; return value; });
      return loadedPromise;
    }

    function draw() {
      clearLegacyLayers();
      clearOwnLayers();
      drawSegments();
      drawCameras();
      api.map.invalidateSize({ pan: false });
      requestAnimationFrame(() => {
        const bounds = corridorLayer?.getBounds?.();
        if (active && fitNeeded && bounds?.isValid()) { api.map.fitBounds(bounds.pad(0.12), { maxZoom: 15, animate: false }); fitNeeded = false; }
      });
    }

    async function render() {
      if (!api.active()) return;
      const version = ++renderVersion;
      active = true;
      el.workspace.classList.add("corridor-active");
      el.overlayTitle.textContent = "Cobertura de corredores";
      el.overlayText.textContent = "Cobertura real de ejes estratégicos mediante unión de buffers métricos de 200 m.";
      el.status.textContent = "Cargando cobertura de corredores…";
      syncControls();
      try { await load(); } catch (error) { el.status.textContent = error.message; return; }
      if (!api.active() || version !== renderVersion) return;
      renderSummary();
      draw();
      renderDetail();
      renderGraphics();
      renderLegend();
      syncControls();
      el.status.textContent = `${scenarioLabels[scenario]} · ${corridorLabels[selectedCorridor]} · radio 200 m · cobertura calculada en ${data.metadata.metricCrs}.`;
      api.map.invalidateSize();
    }

    function leave() {
      active = false;
      renderVersion += 1;
      clearOwnLayers();
      el.workspace.classList.remove("corridor-active");
      syncControls();
    }

    function reset() { selected = null; fitNeeded = true; }

    [el.corridorSelect, el.corridorScenario].forEach((control) => control?.addEventListener("change", () => {
      if (control === el.corridorSelect) selectedCorridor = control.value;
      if (control === el.corridorScenario) scenario = control.value;
      selected = null; fitNeeded = true; render();
    }));
    el.corridorCompareButton?.addEventListener("click", () => { compare = !compare; selected = null; fitNeeded = true; render(); });
    el.toggleCorridorPolice?.addEventListener("change", () => { if (active) render(); });
    el.toggleCorridorBuffers?.addEventListener("change", () => { if (active) render(); });

    return { render, leave, reset, renderLegend, clearLegacyLayers };
  };
})();
