/* Scope adapter for the existing Leaflet workspace and its shared chart primitives. */
window.createRiobambaCantonalView = function (api) {
  "use strict";
  const data = window.RIOBAMBA_CANTONAL_DATA;
  const { map, elements: el, events, esc, fmt } = api;
  let scope = "URBANO", parish = "__ALL__", lastFit = "", miniMap = null, surfaceCache = null;
  const boundaries = L.layerGroup().addTo(map);
  const analysis = L.layerGroup().addTo(map);
  const pointRenderer = L.canvas({padding: .5});
  const units = data.parishes.features;
  const unitControl = document.getElementById("ruralUnitSelect");
  const scopeButtons = [...document.querySelectorAll("[data-territorial-scope]")];
  const palette = ["#F1F8E9", "#C5E1A5", "#80CBC4", "#26A69A", "#00695C"];
  const classNames = ["Delincuencia", "Violencia", "Convivencia"];
  const assignment = (id) => data.assignments[id];
  const featureName = (f) => f.properties.name;
  const selectedUnit = () => units.find((f) => featureName(f) === parish);
  const setScope = (next) => {
    scope = next;
    parish = "__ALL__";
    unitControl.value = parish;
    lastFit = "";
  };
  const cameraMatchesScope = (camera) => {
    if (scope === "CANTONAL") return true;
    if (!camera.mappable || !Number.isFinite(camera.lng) || !Number.isFinite(camera.lat)) return false;
    const urban = api.pointInsideFeature(data.urban, camera.lng, camera.lat);
    return scope === "URBANO" ? urban : !urban && api.pointInsideFeature(selectedUnit() || data.canton, camera.lng, camera.lat);
  };
  const matchesScope = (event, checkUnit = true) => {
    const a = assignment(event.id);
    return Boolean(a && (scope === "CANTONAL" ? a.insideCanton : a.scope === scope)
      && (!checkUnit || scope !== "RURAL" || parish === "__ALL__" || a.unit === parish));
  };
  const analyticModule = () => ["kde", "giHotspots", "incidence", "videoDeficitGap", "lowCoverageConcentrations", "exposureLowCoverage", "territorialGaps", "candidateZones"].includes(api.current().key);
  const records = (checkUnit = true, forceAnalytic = false, ignoreScope = false) => {
    const searchEnabled = ["incidents", "incidentQuery"].includes(api.current().key);
    const query = searchEnabled ? el.search.value.trim().toLocaleLowerCase() : "";
    return events.filter((e) => (ignoreScope || matchesScope(e, checkUnit))
      && (!(analyticModule() || forceAnalytic) || [1, 2, 3].includes(e.analyticalClassId))
      && (el.category.value === "__ALL__" || e.category === el.category.value)
      && (el.subtype.value === "__ALL__" || e.subtype === el.subtype.value)
      && (el.kdePeriod.value === "__ALL__" || e.date.startsWith(el.kdePeriod.value))
      && (!el.incidentDate.value || e.date === el.incidentDate.value)
      && (api.current().key !== "incidentQuery" || el.precision.value === "__ALL__" || e.precision === el.precision.value)
      && (api.current().key !== "incidentQuery" || el.source.value === "__ALL__" || e.source === el.source.value)
      && (!query || `${e.subtype} ${e.location} ${e.source}`.toLocaleLowerCase().includes(query)));
  };
  const population = () => selectedUnit()?.properties.population ?? data.population[scope];
  const counts = (items) => [1, 2, 3].map((id) => items.filter((e) => e.analyticalClassId === id).length);
  const cardHtml = (cards) => cards.map(([label, value]) => `<div class="card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  const table = (title, headers, rows) => `<div class="graphic-card"><h3>${esc(title)}</h3><div style="overflow-x:auto"><table class="mini-table"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  const bars = (title, entries, color = "#26A69A") => api.metricBars(title, entries.map(([label, value]) => ({label, value, color})), Math.max(1, ...entries.map((e) => e[1])), color);
  const note = () => `<p class="cantonal-note">${esc(data.metadata.limitations[0])} ${esc(data.metadata.limitations[1])}</p>`;
  unitControl.innerHTML = `<option value="__ALL__">Todas las Parroquias</option>${units.map((f) => `<option value="${esc(featureName(f))}">${esc(featureName(f))}</option>`).join("")}`;
  unitControl.addEventListener("change", () => { parish = unitControl.value; api.update(); });
  scopeButtons.forEach((button) => button.addEventListener("click", () => {
    scope = button.dataset.territorialScope;
    parish = "__ALL__";
    unitControl.value = parish;
    el.parish.value = el.kdePlatform.value = "__ALL__";
    api.clearSelection();
    lastFit = "";
    api.update();
  }));
  const territoryControls = {};
  const layerHost = document.getElementById("layersPopover");
  ["canton", "urban", "rural", "hot", "cold"].forEach((key, index) => {
    const label = document.createElement("label");
    label.className = "layer-toggle";
    label.innerHTML = `<span>${["Límite cantonal", "Límite urbano operativo", "Parroquias rurales", "Hotspots", "Coldspots"][index]}</span><input type="checkbox" checked>`;
    (layerHost || el.mapLayerControl).appendChild(label);
    territoryControls[key] = { label, input: label.querySelector("input") };
    territoryControls[key].input.addEventListener("change", api.update);
  });

  function syncControls() {
    const inventory = api.current().key === "cameras";
    const independent = ["kde", "giHotspots"].includes(api.current().key);
    if (independent && scope === "CANTONAL") { scope = "URBANO"; parish = "__ALL__"; lastFit = ""; }
    scopeButtons.forEach((b) => {
      b.hidden = independent && b.dataset.territorialScope === "CANTONAL";
      const active = b.dataset.territorialScope === scope;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    unitControl.hidden = scope !== "RURAL";
    // The legacy parish control filters original text, not the verified geometry.
    el.parish.hidden = true;
    el.parish.value = "__ALL__";
    if (scope !== "URBANO") el.kdePlatform.hidden = true;
    document.querySelector('[data-layer-row="platforms"]').hidden = scope !== "URBANO";
    territoryControls.rural.label.hidden = scope === "URBANO";
    territoryControls.canton.label.hidden = scope === "URBANO";
    const gi = api.current().key === "giHotspots";
    territoryControls.hot.label.hidden = territoryControls.cold.label.hidden = !gi;
    el.toggleAnalysisResult.disabled = false;
    el.toggleCameras.disabled = scope === "RURAL" && !inventory;
    el.toggleBoulevards.disabled = scope === "RURAL";
    el.toggleCameraCoverage.disabled = scope === "RURAL";
    if (el.cameraLayerLabel && scope === "RURAL" && !inventory) el.cameraLayerLabel.textContent = "Cámaras rurales · No disponible";
    if (scope === "RURAL" && el.cameraCoverageControls) el.cameraCoverageControls.hidden = true;
    if (scope !== "URBANO") {
      document.querySelector('[data-layer-row="manzanas"]').hidden = true;
      document.querySelector('[data-layer-row="externalCameras"]').hidden = true;
      const incidentModules=["kde","giHotspots","incidence","incidents","incidentQuery","typologies","temporal"];
      if(!inventory && !incidentModules.includes(api.current().key)) {
        [el.search,el.category,el.subtype,el.precision,el.source,el.kdePeriod,el.incidentDate].forEach((control)=>control.hidden=true);
        el.category.value=el.subtype.value=el.kdePeriod.value="__ALL__";
        el.incidentDate.value="";
      }
      if(scope==="RURAL" && ["cameraCoverage","populationCoverage","boulevards","institutionalCoverage","videoDeficitGap","lowCoverageConcentrations","exposureLowCoverage","territorialGaps","candidateZones"].includes(api.current().key)) {
        el.toggleAnalysisResult.disabled=true;
        el.analysisResultLayerLabel.textContent+=" · datos rurales no disponibles";
      }
    }
  }

  function renderBoundaries() {
    boundaries.clearLayers();
    const layers = [];
    const add = (feature, style) => {
      const layer = L.geoJSON(feature, {style, interactive: false}).addTo(boundaries);
      layers.push(layer);
      return layer;
    };
    if (scope !== "URBANO" && territoryControls.canton.input.checked) add(data.canton, {color: "#1f2937", weight: 1.5, fillOpacity: 0});
    if (territoryControls.urban.input.checked) add(data.urban, {color: "#0f766e", weight: 1.6, dashArray: "5 4", fillOpacity: 0});
    if (scope !== "URBANO" && territoryControls.rural.input.checked) {
      const rural = L.geoJSON(data.parishes, {
        style: (f) => ({color: featureName(f) === parish ? "#075985" : "#596c78", weight: featureName(f) === parish ? 2.5 : 1, fillColor: "#80CBC4", fillOpacity: featureName(f) === parish ? .12 : .015}),
        onEachFeature: (f, layer) => {
          const select = () => {
            if (scope !== "RURAL") return;
            parish = featureName(f);
            unitControl.value = parish;
            api.clearSelection();
            api.update();
          };
          layer.bindTooltip(esc(featureName(f)), {permanent: true, interactive: true, direction: "center", className: "rural-name"});
          layer.on("click", select);
          layer.getTooltip().on("click", (event) => {
            if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);
            select();
          });
        },
      }).addTo(boundaries);
      rural.bringToBack();
      layers.push(rural);
    }
    const key = `${scope}:${parish}`;
    if (lastFit !== key) {
      const target = selectedUnit() || (scope === "URBANO" ? data.urban : data.canton);
      const bounds = L.geoJSON(target).getBounds();
      map.invalidateSize();
      map.fitBounds(bounds, {padding: [18, 18], maxZoom: scope === "URBANO" ? 14 : 13, animate: false});
      lastFit = key;
    }
    if (scope === "URBANO" && ["kde", "giHotspots"].includes(api.current().key) && !el.toggleAnalysisResult.checked) map.removeLayer(api.analysisLayer());
  }

  function giResult(grid, items) {
    const cells = grid.cells.map((c) => ({...c, incCount: 0, incidents: []}));
    const index = new Map(cells.map((c, i) => [`${c.row}:${c.col}`, i]));
    items.forEach((e) => {
      const a = assignment(e.id);
      const i = index.get(`${Math.floor((a.y-grid.minY)/grid.cellSize)}:${Math.floor((a.x-grid.minX)/grid.cellSize)}`);
      if (i !== undefined) { cells[i].incCount++; cells[i].incidents.push(e); }
    });
    const n = cells.length, mean = items.length/n;
    const sd = Math.sqrt(Math.max(0, cells.reduce((s,c) => s+c.incCount*c.incCount,0)/n-mean*mean));
    cells.forEach((c,i) => {
      const neighbors = grid.neighbors[i], k = neighbors.length;
      const den = sd*Math.sqrt(Math.max(0,(n*k-k*k)/(n-1)));
      c.zScore = den ? (neighbors.reduce((s,j) => s+cells[j].incCount,0)-mean*k)/den : 0;
      c.pValue = Math.max(0,2*(1-api.giNormalCdf(Math.abs(c.zScore))));
      const level = c.pValue <= .01 ? 99 : c.pValue <= .05 ? 95 : c.pValue <= .1 ? 90 : 0;
      c.giClass = level ? `${c.zScore > 0 ? "HOTSPOT" : "COLDSPOT"} ${level} %` : "NO SIGNIFICATIVO";
      c.giStar = c.zScore;
    });
    return cells;
  }
  function ruralGi() {
    // Parish selection is a display/summary filter: it never changes the Gi* reference universe.
    const items = records(false, true, true).filter((e) => assignment(e.id)?.scope === "RURAL");
    return giResult(data.ruralGrid, items);
  }
  function visibleGi(c) {
    return api.giCellPassesFilter(c)
      && (parish === "__ALL__" || c.parishAreas?.[parish] > 0)
      && allowsGi(c);
  }
  function drawGi(cells, label) {
    if (!el.toggleAnalysisResult.checked) return;
    cells.filter(visibleGi).forEach((c) => L.geoJSON(c.geometry, {style: {
      color: "#ffffff", weight: .4, fillColor: api.giClassColor(c.giClass), fillOpacity: c.giClass === "NO SIGNIFICATIVO" ? .035 : .7,
    }}).bindTooltip(`${esc(c.giClass)} · ${fmt(c.incCount)} eventos`, {sticky:true})
      .bindPopup(`${esc(label)} · ${esc(c.cellId)}<br>${esc(c.PARROQUIA || c.platform)}<br>COUNT: ${c.incCount}<br>GI_ZSCORE: ${c.zScore.toFixed(3)}<br>GI_PVALUE: ${c.pValue.toFixed(6)}<br>${esc(c.giClass)}<br>Significancia nominal exploratoria; sin FDR.`)
      .on("click", () => {
        api.clearSelection();
        clearDetailMiniMap();
        el.detailTitle.textContent = "Detalle de hotspot";
        el.detail.innerHTML = [["Celda", c.cellId], ["Incidentes", c.incCount], ["Unidad territorial", c.PARROQUIA || c.platform || "No disponible"], ["Z-score", c.zScore.toFixed(3)], ["p-value", c.pValue.toFixed(6)], ["Clasificación", c.giClass]].map(([name, value]) => `<div class="mini-row"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join("") + "<p>Significancia nominal exploratoria; sin FDR.</p>";
      }).addTo(analysis));
  }
  function giSummary(cells) {
    const items = records(false, true, true).filter((e) => assignment(e.id)?.scope === "RURAL");
    const labels = ["HOTSPOT 99 %", "HOTSPOT 95 %", "HOTSPOT 90 %", "NO SIGNIFICATIVO", "COLDSPOT 90 %", "COLDSPOT 95 %", "COLDSPOT 99 %"];
    const rows = units.filter((u) => parish === "__ALL__" || featureName(u) === parish).map((u) => {
      const name = featureName(u), local = cells.filter((c) => c.parishAreas[name] > 0);
      const area = local.filter((c) => c.giClass.startsWith("HOT")).reduce((s,c) => s+c.parishAreas[name],0);
      return [name, items.filter((e) => assignment(e.id).unit === name).length, local.length,
        ...labels.map((label) => local.filter((c) => c.giClass === label).length), area.toFixed(2), (area/u.properties.areaKm2*100).toFixed(2)+"%"];
    });
    return table("Gi* por parroquia · resumen, no clasificación de toda la parroquia", ["Parroquia", "Eventos", "Celdas", "H99", "H95", "H90", "NS", "C90", "C95", "C99", "Área hotspot km²", "% territorio"], rows)
      + `<p class="cantonal-note">Las celdas limítrofes pueden intersectar varias parroquias: sus áreas se reparten geométricamente; sus conteos de celdas no deben sumarse como unidades únicas. ${esc(data.metadata.ruralGridSelection)}</p>`;
  }

  function kdeSurface(items) {
    const grid = data.kdeGrids[scope], h = window.RiobambaConflictivity.parameters(scope, el.category.value).bandwidth;
    const key = `${scope}:${h}:${items.map((e) => e.id).join(",")}`;
    if (surfaceCache?.key === key) return surfaceCache;
    const points = items.map((event) => ({id:event.id, x:assignment(event.id).x, y:assignment(event.id).y}));
    const surface = window.RiobambaConflictivity.calculate(points, grid, h);
    surfaceCache={key,...surface,grid:{...grid,bandwidth:h},url:window.RiobambaConflictivity.renderRaster(surface),
      concentrations:api.countKdeConcentrations(surface.density,grid.width,grid.height,surface.maxDensity)};
    return surfaceCache;
  }
  function renderLegend() {
    const key = api.current().key;
    let html = `<strong>${key === "kde" ? "CONCENTRACIÓN ESPACIAL" : scope}</strong>`;
    if (key === "kde") html = "<strong>CONCENTRACIÓN ESPACIAL DE EVENTOS</strong>" + window.RiobambaConflictivity.legend();
    if (key === "giHotspots") html += ["HOTSPOT 99 %","HOTSPOT 95 %","HOTSPOT 90 %","NO SIGNIFICATIVO","COLDSPOT 90 %","COLDSPOT 95 %","COLDSPOT 99 %"].map((label)=>`<div class="legend-row"><span class="legend-swatch" style="background:${api.giClassColor(label)}"></span>${label}</div>`).join("") + "<p class='cantonal-note'>Gi* nominal, sin FDR. Urbano: 250/500 m. Rural: 1000/2000 m. No son un único análisis.</p>";
    html += "<div class='legend-row'>Límite cantonal · gris</div><div class='legend-row'>Ámbito urbano operativo · verde discontinuo</div><div class='legend-row'>Parroquias rurales · gris fino</div>";
    el.legend.innerHTML=html;
  }
  function renderMethodology() {
    document.getElementById("methodologyPanel").innerHTML = `<h3>${esc(scope)} · ${esc(api.current().key)}</h3>`
      + data.metadata.limitations.map((text)=>`<p>${esc(text)}</p>`).join("")
      + (["kde", "giHotspots"].includes(api.current().key) ? window.RiobambaConflictivity.methodologyHtml(scope, el.category.value) : "")
      + `<h3>Gi* rural</h3><p>${esc(data.metadata.ruralGridSelection)} Significancia nominal exploratoria, sin corrección FDR.</p>`
      + table("Evaluación de malla y vecindad", ["Celda m","Vecindad m","Celdas","Ocupadas","Vacías","Media","Máximo","Vecinos medios","Mínimo","Máximo","Aisladas"], data.gridAssessment.map((r)=>[r.cellSize,r.distance,r.cells,r.occupied,r.empty,r.meanIncidents.toFixed(3),r.maximum,r.meanNeighbors.toFixed(2),r.minNeighbors,r.maxNeighbors,r.isolated]));
  }
  function unitRows(items) {
    const totalRural=items.filter((e)=>assignment(e.id).scope==="RURAL").length;
    const giCells=ruralGi();
    return units.filter((u)=>parish === "__ALL__" || featureName(u)===parish).map((u)=> {
      const local=items.filter((e)=>assignment(e.id).unit===featureName(u)), c=counts(local);
      const subtype=Object.entries(local.reduce((a,e)=>(a[e.subtype]=(a[e.subtype]||0)+1,a),{})).sort((a,b)=>b[1]-a[1])[0];
      const months=Object.entries(local.reduce((a,e)=>(a[e.date.slice(0,7)]=(a[e.date.slice(0,7)]||0)+1,a),{})).sort().map(([month,n])=>`${month}: ${n}`).join(" · ");
      const analytic=el.category.value==="__ALL__" || events.some((e)=>e.category===el.category.value && [1,2,3].includes(e.analyticalClassId));
      const hot=analytic ? giCells.filter((c)=>c.parishAreas[featureName(u)]>0 && c.giClass.startsWith("HOT")).length : "No aplica";
      return [featureName(u),fmt(u.properties.population),local.length,...c,...c.map((n)=>(n/u.properties.population*1000).toFixed(2)),subtype?.[0]||"No disponible",totalRural?(local.length/totalRural*100).toFixed(2)+"%":"No disponible",months||"Sin registros en el periodo",hot];
    });
  }
  function comparison() {
    const all=records(false,true,true);
    return table("Comparación urbano / rural · tasas de referencia, no peligrosidad", ["Ámbito","Población","Eventos analíticos","% analítico cantonal","Delincuencia","Violencia","Convivencia","Del. /100.000","Viol. /100.000","Conv. /100.000"], ["URBANO","RURAL"].map((s)=>{
      const local=all.filter((e)=>assignment(e.id).scope===s), c=counts(local), pop=data.population[s];
      const total=all.filter((e)=>assignment(e.id).insideCanton).length;
      return [s,fmt(pop),local.length,total ? (local.length/total*100).toFixed(2)+"%":"No disponible",...c,...c.map((n)=>(n/pop*100000).toFixed(2))];
    })) + note();
  }
  function clearDetailMiniMap() {
    if (miniMap) { miniMap.remove(); miniMap = null; }
  }
  function renderDetail(items) {
    clearDetailMiniMap();
    if (api.renderSelectedEntityDetail(items)) return;
    const unit=selectedUnit(), c=counts(items), pop=population(), scale=unit ? 1000 : 100000;
    el.detailTitle.textContent=unit ? featureName(unit) : `${scope} · detalle territorial`;
    el.detail.innerHTML=`<div id="cantonalDetailMap" class="cantonal-mini-map"></div>`
      + [["Población de referencia",fmt(pop)],["Eventos filtrados",items.length],...classNames.map((label,i)=>[`${label} / ${fmt(scale)} hab.`,(c[i]/pop*scale).toFixed(2)]),["Videovigilancia rural","No disponible"],["Cobertura poblacional rural","No disponible"]].map(([label,value])=>`<div class="mini-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("")
      + note();
    miniMap=L.map("cantonalDetailMap",{zoomControl:false,attributionControl:false,preferCanvas:true});
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{className:"osm-gray-tile"}).addTo(miniMap);
    const target=L.geoJSON(unit||data.canton,{style:{color:"#075985",weight:1.5,fillColor:"#80CBC4",fillOpacity:.2}}).addTo(miniMap);
    miniMap.fitBounds(target.getBounds(),{padding:[10,10]});
  }
  function clearAnalysis() {
    analysis.clearLayers();
    clearDetailMiniMap();
  }
  function allowsGi(c) {
    return (!c.giClass.startsWith("HOT") || territoryControls.hot.input.checked)
      && (!c.giClass.startsWith("COLD") || territoryControls.cold.input.checked);
  }
  function drawPoints(items) {
    const key=api.current().key;
    if(["incidents","incidentQuery"].includes(key) && !el.toggleAnalysisResult.checked) return;
    if (!["incidents","incidentQuery","kde","typologies","temporal","giHotspots"].includes(key) || !el.toggleEvents.checked) return;
    items.forEach((e)=>L.circleMarker([e.lat,e.lng],{renderer:pointRenderer,radius:key==="kde"?2:3,color:"#ffffff",weight:.5,fillColor:key==="kde"?"#263238":["#2876aa","#a84d65","#38977e","#808994","#b7a24c"][e.analyticalClassId-1],fillOpacity:.8})
      .bindPopup(`${esc(e.subtype)}<br>${esc(e.category)}<br>${esc(e.date)}<br>${esc(assignment(e.id).unit||"Sin asignar ámbito")}`)
      .on("click", () => { clearDetailMiniMap(); api.selectEvent(e.id, false); }).addTo(analysis));
  }
  function drawPolice() {
    if((api.current().mode==="police" || api.current().metric==="policeAccessibility") && !el.toggleAnalysisResult.checked) return;
    if (!el.togglePoliceInfrastructure.checked && api.current().mode!=="police" && api.current().metric!=="policeAccessibility") return;
    const entries=api.policeInfrastructure.filter((f)=> {
      const name=f.properties?.code;
      const a=data.policeAssignments.find((a)=>a.properties.code===name);
      return scope==="CANTONAL" ? a?.scope!=="SIN_ASIGNAR" : a?.scope==="RURAL" && (parish==="__ALL__" || a.unit===parish);
    });
    L.geoJSON({type:"FeatureCollection",features:entries},{pointToLayer:(_,p)=>L.circleMarker(p,{radius:6,color:"#fff",fillColor:"#075985",fillOpacity:1,weight:1.5}),onEachFeature:(f,l)=>l.bindPopup(`${esc(f.properties.name||f.properties.code)}<br>${esc(f.properties.type)}<br>Inventario disponible, no exhaustivo.`).on("click", () => { clearDetailMiniMap(); api.selectPolice(f.properties.code, false); })}).addTo(analysis);
  }
  function render() {
    clearAnalysis();
    api.layers().forEach((layer)=>map.removeLayer(layer));
    analysis.addTo(map);
    boundaries.addTo(map);
    const state=api.current(), key=state.key, items=records(), pop=population();
    const c=counts(items), total=c.reduce((a,b)=>a+b,0), scale=selectedUnit()?1000:100000;
    el.overlayTitle.textContent = ({kde:"Concentración de incidentes",giHotspots:"Zonas críticas",incidence:"Incidencia poblacional",typologies:"Tipos de incidentes",temporal:"Evolución temporal"})[key] || (el.analysisResultLayerLabel?.textContent || "Diagnóstico territorial");
    el.overlayText.textContent=`${scope} · ${parish==="__ALL__"?"Todo el ámbito":parish} · ${el.category.value==="__ALL__"?"Todas las clases admitidas":el.category.value} · ${fmt(items.length)} registros · ${el.kdePeriod.value==="__ALL__"?"enero – agosto 2026":el.kdePeriod.value}.`;
    const cards=[["Población de referencia",fmt(pop)],["Eventos filtrados",fmt(items.length)],["Delincuencia",fmt(c[0])],["Violencia",fmt(c[1])],["Convivencia",fmt(c[2])]];
    let graphic="";
    if(key==="kde") {
      const surface=kdeSurface(items);
      if(el.toggleAnalysisResult.checked) L.imageOverlay(surface.url,surface.grid.bounds,{opacity:.45,interactive:false}).addTo(analysis);
      cards.splice(2,3,["Categoría",el.category.value === "__ALL__" ? "General analítico" : classNames[(events.find((e)=>e.category===el.category.value)?.analyticalClassId||1)-1]],["Bandwidth / celda",`${surface.grid.bandwidth} / ${surface.grid.cellSize} m`],["Concentraciones relativas",surface.concentrations]);
      graphic=bars("Eventos por unidad territorial",unitRows(items).map((r)=>[r[0],r[2]]));
      graphic+=`<p class="cantonal-note">KDE_${el.category.value==="__ALL__"?"GENERAL_ANALITICO":classNames[(events.find((e)=>e.category===el.category.value)?.analyticalClassId||1)-1]?.toUpperCase()||"ANALITICO"}. Peso 1; una cuadrícula continua en EPSG:32717. Concentraciones: componentes conectados ≥35% del máximo, descriptivos y no significativos estadísticamente.</p>`;
    } else if(key==="giHotspots") {
      const cells=ruralGi(), local=cells.filter((c)=>parish==="__ALL__" || c.parishAreas[parish]>0);
      const hot=local.filter((c)=>c.giClass.startsWith("HOT") && api.giCellPassesFilter(c));
      const cold=local.filter((c)=>c.giClass.startsWith("COLD") && api.giCellPassesFilter(c));
      drawGi(cells,"Gi* rural · celda 1000 m / vecindad 2000 m");
      let urbanGi = null;
      if(scope==="CANTONAL") {
        urbanGi=api.getUrbanGi();
        drawGi(urbanGi.cells,"Gi* urbano · celda 250 m / vecindad 500 m");
      }
      cards.splice(2,3,["Celdas rurales analizadas",local.length],["Hotspots · filtro activo",hot.length],["Coldspots · filtro activo",cold.length]);
      graphic=giSummary(cells);
      graphic+="<p class='cantonal-note'>La tabla conserva los siete niveles del cálculo de referencia. Las tarjetas de hotspots/coldspots y el mapa responden al filtro de significancia y tipo; los controles de capas sólo cambian visibilidad.</p>";
      if(urbanGi) {
        const analyzed=cells.reduce((s,c)=>s+c.incCount,0)+urbanGi.points.length;
        graphic+=`<p class="cantonal-note">En la vista cantonal, ${fmt(analyzed)} eventos tienen malla Gi* urbana o rural asignada. ${fmt(items.length-analyzed)} eventos internos sin ámbito asignado no participan en ninguna de esas dos mallas. No se afirma que el resultado cubra estadísticamente todo el cantón.</p>`;
      }
      el.overlayText.textContent+=" Gi* urbano y rural conservan metodologías distintas. Nominal exploratorio, sin FDR.";
    } else if(key==="incidence") {
      cards.splice(2,3,...classNames.map((label,i)=>[`${label} / ${fmt(scale)} hab.`,(c[i]/pop*scale).toFixed(2)]));
      graphic=comparison();
    } else if(key==="temporal") {
      const months={}, days=Array(7).fill(0);
      items.forEach((e)=>{const month=e.date.slice(0,7);months[month]=(months[month]||0)+1;days[new Date(`${e.date}T12:00:00Z`).getUTCDay()]++;});
      graphic=bars("Eventos por mes",Object.entries(months).sort())+bars("Eventos por día de semana",["Dom","Lun","Mar","Mié","Jue","Vie","Sáb"].map((label,i)=>[label,days[i]]))+"<p class='cantonal-note'>Hora no disponible en la fuente; no se genera distribución horaria.</p>";
    } else if(key==="typologies") {
      const types=items.reduce((a,e)=>(a[e.subtype]=(a[e.subtype]||0)+1,a),{});
      graphic=bars("Distribución por subtipo",Object.entries(types).sort((a,b)=>b[1]-a[1]));
    } else if(["cameraCoverage","populationCoverage","cameras","institutionalCoverage","videoDeficitGap","lowCoverageConcentrations","exposureLowCoverage","territorialGaps","candidateZones"].includes(key)) {
      cards.splice(2,3,["Cámaras rurales","No disponible"],["Cobertura rural","No disponible"],["Escenario urbano",`${api.cameras.length} cámaras`]);
      graphic=`<div class="graphic-card"><h3>Disponibilidad de recursos y brechas</h3><p>Información de videovigilancia rural no disponible. No significa ausencia de cámaras. Las 31 cámaras del escenario urbano se conservan; no se extrapolan al cantón.</p><p>Sin inventario rural ni población georreferenciada completa no se calculan déficit, cobertura o zonas candidatas rurales. Se muestran problemática, población de referencia y dependencias inventariadas sin pesos ni ranking.</p></div>`;
      if(scope==="CANTONAL") {
        const urban=api.cameraCoverage(), rows=Object.values(urban?.byPlatformName || {});
        const covered=rows.reduce((s,r)=>s+r.coveredPopulation,0), population=rows.reduce((s,r)=>s+r.population,0);
        graphic+=table(`Escenario urbano disponible · radio ${state.scenario} m`,["Variable","Total urbano analizado","Cubierto","Fuera del escenario","%"],[
          ["Superficie (km²)",urban.totalAreaKm2.toFixed(3),urban.totalCoveredAreaKm2.toFixed(3),(urban.totalAreaKm2-urban.totalCoveredAreaKm2).toFixed(3),(urban.totalCoveredAreaKm2/urban.totalAreaKm2*100).toFixed(2)+"%"],
          ["Población (habitantes)",fmt(population),fmt(covered),fmt(population-covered),(covered/population*100).toFixed(2)+"%"],
        ])+"<p class='cantonal-note'>Sólo el escenario urbano disponible, no cobertura total del cantón. Las unidades y denominadores son independientes.</p>";
      }
      graphic+=table("Recursos rurales inventariados",["Parroquia","Población CPV","Dependencias inventariadas","Cámaras","Exposición georreferenciada"],units.filter((f)=>parish==="__ALL__"||featureName(f)===parish).map((f)=>[featureName(f),fmt(f.properties.population),f.properties.police,"No disponible","No disponible"]));
    } else if(key==="police" || state.metric==="policeAccessibility") {
      const policePoints=data.policeMetric || [];
      const distances=items.map((e)=> {
        const a=assignment(e.id);
        return Math.min(...policePoints.map((p)=>Math.hypot(a.x-p.x,a.y-p.y)));
      }).filter(Number.isFinite);
      cards.push(["Proximidad media de eventos",distances.length?`${Math.round(distances.reduce((a,b)=>a+b,0)/distances.length)} m`:"No disponible"]);
      graphic=table("Dependencias policiales inventariadas por parroquia",["Parroquia","Dependencias"],units.map((f)=>[featureName(f),f.properties.police]))+"<p class='cantonal-note'>Distancia euclidiana de puntos de eventos a dependencias georreferenciadas; no distancia de toda la población ni tiempo de respuesta. La red vial no dispone de velocidades validadas.</p>";
    } else if(key==="demography") {
      graphic=bars("Población censal de parroquias rurales",units.map((f)=>[featureName(f),f.properties.population]))+"<p class='cantonal-note'>La suma de estas once parroquias es 71.991. La referencia rural cantonal de 83.669 incluye también población rural de PARROQ 060150. Densidad/exposición rural completa no disponible sin delimitación censal y georreferenciación completas.</p>";
    } else if(key==="boulevards") {
      graphic="<div class='graphic-card'><h3>Bulevares y conexiones</h3><p>Se conserva la red urbana original. No hay inventario rural validado de Bulevares Seguros ni cobertura poblacional rural completa. Selecciona Urbano para sus indicadores calculados.</p></div>";
    } else {
      graphic=comparison();
    }
    if(["incidents","incidentQuery"].includes(key)) graphic+=table("Consulta de incidentes · primeros 200 registros filtrados",["ID","Fecha","Clase","Subtipo","Unidad espacial"],items.slice(0,200).map((e)=>[e.id,e.date,e.category,e.subtype,assignment(e.id).unit||"Sin asignar"]));
    const parishRows=unitRows(items);
    graphic+=table("Validación y tasas por parroquia · sin ranking",["Parroquia","Población","Eventos filtrados","Del.","Viol.","Conv.","Del./1000","Viol./1000","Conv./1000","Subtipo predominante","% selección rural","Evolución mensual","Celdas hotspot nominal"],parishRows);
    graphic+=`<div class="graphic-card"><button type="button" id="exportCantonalResults" class="header-action">Descargar resultados CSV</button></div>`;
    el.summary.innerHTML=cardHtml(cards);
    el.graphicAnalysis.innerHTML=graphic;
    document.getElementById("exportCantonalResults").addEventListener("click",()=>{
      const rows=[["AMBITO",scope],["UNIDAD",parish],["CATEGORIA",el.category.value],["SUBTIPO",el.subtype.value],["PERIODO",el.kdePeriod.value],["CRS","EPSG:32717"],["POBLACION_REFERENCIA",pop],["REGISTROS_FILTRADOS",items.length],[],["PARROQUIA","POBLACION","EVENTOS_FILTRADOS","DELINCUENCIA","VIOLENCIA","CONVIVENCIA","TASA_DEL_1000","TASA_VIOL_1000","TASA_CONV_1000","SUBTIPO_PREDOMINANTE","PORCENTAJE_SELECCION_RURAL","EVOLUCION_MENSUAL","CELDAS_HOTSPOT_NOMINAL"],...parishRows,[],["LIMITACIONES",data.metadata.limitations.join(" | ")]];
      const text=rows.map((row)=>row.map((v)=>`"${String(v).replaceAll('"','""')}"`).join(";")).join("\r\n");
      const url=URL.createObjectURL(new Blob(["\uFEFF",text],{type:"text/csv;charset=utf-8"}));
      const anchor=document.createElement("a");anchor.href=url;anchor.download=`riobamba-${scope.toLowerCase()}-${key}.csv`;anchor.click();URL.revokeObjectURL(url);
    });
    el.list.innerHTML="";
    el.status.textContent=`${scope}: ${fmt(items.length)} registros filtrados. Base: 23.732 urbanos + 2.134 rurales + 850 sin asignar = 26.716. Cantonal incluye 820 sin asignar internos; excluye 30 externos.`;
    renderDetail(items);
    drawPoints(items); drawPolice();
    if(scope==="CANTONAL") {
      if(el.toggleCameraCoverage.checked || (["cameraCoverage","populationCoverage"].includes(key) && el.toggleAnalysisResult.checked)) {
        api.renderCoverageLayer();
        api.coverageLayer().addTo(map);
      }
      if(el.toggleBoulevards.checked || key==="boulevards") api.boulevardLayer().addTo(map);
      if(el.toggleCameras.checked || (key==="cameras" && el.toggleAnalysisResult.checked)) api.cameras.forEach((c)=>L.circleMarker([c.lat,c.lng],{radius:4,color:"white",fillColor:"#2563eb",weight:1,fillOpacity:1}).bindPopup(`${esc(c.id)}<br>${esc(c.address)}<br>Escenario urbano, requiere cambio.`).on("click", () => { clearDetailMiniMap(); api.selectCamera(c.id, false); }).addTo(analysis));
    }
    renderBoundaries(); renderLegend(); renderMethodology();
    console.info("Validación territorial",{scope,parish,records:items.length,analytic:total,weight:1,crs:"EPSG:32717"});
  }
  el.toggleAnalysisResult.addEventListener("change", api.update);
  return {scope:()=>scope,setScope,cameraMatchesScope,assignment,matchesScope,syncControls,render,renderBoundaries,clearAnalysis,renderLegend,renderMethodology,allowsGi};
};
