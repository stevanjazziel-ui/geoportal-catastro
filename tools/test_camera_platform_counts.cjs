"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const script = fs.readFileSync(path.join(root, "riobamba-camaras-propuesta.js"), "utf8");
const html = fs.readFileSync(path.join(root, "visor-seguridad-riobamba-v2.html"), "utf8");
const spatial = html.slice(html.indexOf("const pointInRing ="), html.indexOf("const platformMaskRings ="));
const counting = script.slice(script.indexOf("function countPlatformCameras("), script.indexOf("async function load("));
const context = vm.createContext({});
vm.runInContext(spatial + "; this.contains = pointInsideFeature;", context);
context.groups = { existing: "Existentes", municipal: "Municipio", police: "Policia" };
context.api = { pointInsideFeature: context.contains };
context.change = feature => feature.properties?.REQUIERE_CAMBIO === true;
context.displayGroup = (group, feature) => group === "existing" && !context.change(feature) ? "existing" : "interventions";
context.originSymbol = (group, feature) => group === "existing" ? (context.change(feature) ? "change" : "existing") : group;
context.fc = features => ({ type: "FeatureCollection", features });
vm.runInContext(script.slice(script.indexOf("const colors ="), script.indexOf("const groups =")), context);
vm.runInContext(script.slice(script.indexOf("const defaults ="), script.indexOf("const labels =")), context);
context.groupEnabled = () => true;
vm.runInContext(counting, context);
const release = JSON.parse(fs.readFileSync(path.join(root, "sig-bridge-active.json"), "utf8"));
const dataRoot = path.resolve(root, release.root);
const read = name => JSON.parse(fs.readFileSync(path.join(dataRoot, name + ".geojson"), "utf8"));
const source = {
  platforms: read("PLATAFORMAS_TERRITORIALES"),
  existing: read("CAMARAS_EXISTENTES_103_FINAL"),
  municipal: read("PROPUESTA_MUNICIPAL_50_FINAL"),
  police: read("PROPUESTA_POLICIA_30_FINAL")
};
context.data = source;
vm.runInContext(script.slice(script.indexOf("function displayFeatures("), script.indexOf("const rowHtml =")), context);
const result = context.countPlatformCameras(source);
source.platformCounts = result;
context.esc = value => String(value);
context.number = (value, digits = 0) => Number(value).toLocaleString("es-EC", { maximumFractionDigits: digits });
assert.equal(result.rows.length, 18);
for (const row of result.rows) {
  const total = Object.values(row.counts).reduce((sum, value) => sum + value, 0);
  assert.ok(context.platformLabel(row.feature).includes(`${total} ${total === 1 ? "cámara" : "cámaras"}`));
}
for (const [group, expected] of Object.entries({ existing: 103, municipal: 50, police: 30 })) {
  assert.equal(result.rows.reduce((sum, row) => sum + row.counts[group], result.outside[group]), expected);
}
// Independent Shapely covers() totals for the current published geometries.
if (release.releaseId === "MUN036_JACINTO_UNIDAD_NACIONAL_20261021") {
  const expected = { A: [0, 1, 0], B: [3, 3, 0], C: [2, 0, 1], D: [3, 1, 1],
    E: [1, 0, 1], F: [3, 1, 2], G: [2, 0, 1], H: [5, 1, 2], I: [6, 2, 1],
    J: [11, 7, 5], K: [20, 2, 0], L: [3, 0, 0], M: [6, 1, 2], N: [1, 0, 0],
    "\u00d1": [7, 4, 1], O: [7, 3, 0], P: [6, 1, 2], Q: [5, 2, 1] };
  for (const row of result.rows) {
    const letter = row.feature.properties.platform_name.replace("PLATAFORMA ", "");
    assert.deepEqual(Object.values(row.counts), expected[letter]);
  }
  assert.deepEqual(Object.values(result.outside), [12, 21, 10]);
}
const totals = { existing: 103, municipal: 50, police: 30 };
assert.equal(result.rows.reduce((sum, row) => sum + row.changeCount, result.outsideChanges), 30);
for (const [scenario, enabled, expected] of [
  ["A", ["existing"], [73, 30, 103]],
  ["B", ["existing", "municipal"], [73, 80, 153]],
  ["C", ["existing", "municipal", "police"], [73, 110, 183]]
]) {
  context.groupEnabled = group => group === "change" || enabled.includes(group);
  assert.deepEqual(Array.from(context.platformCountValues(totals, 30)), expected, scenario);
  const current = context.displayFeatures("existing").features;
  const interventions = context.displayFeatures("interventions").features;
  assert.equal(current.length, expected[0]);
  assert.equal(interventions.length, expected[1]);
  assert.equal(new Set([...current, ...interventions].map(f => f.properties.ID_CAMARA || f.properties.ID_PROPUESTA || f.properties.ID_POLICIA)).size, expected[2]);
  assert.ok(current.every(f => !context.change(f)));
  assert.equal(interventions.filter(f => f.properties.GRUPO_ORIGEN_VISOR === "existing").length, 30);
  assert.ok(source.existing.features.every(f => !("GRUPO_ORIGEN_VISOR" in f.properties)));
}
const polygon = coordinates => ({ properties: { platform_name: "PLATAFORMA TEST" }, geometry: { type: "Polygon", coordinates } });
const synthetic = { platforms: { features: [polygon([[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]])] },
  existing: { features: [{ geometry: { coordinates: [1, 1] } }, { geometry: { coordinates: [3, 3] } }] },
  municipal: { features: [] }, police: { features: [] } };
const sample = context.countPlatformCameras(synthetic);
assert.equal(sample.rows[0].counts.existing, 1);
assert.equal(sample.outside.existing, 1);
assert.equal(vm.runInContext("new Set(Object.values(colors)).size", context), 5);
const visible = () => Array.from(vm.runInContext("cameraKeys.filter(layerVisible).flatMap(key => displayFeatures(key).features)", context));
const uniqueCount = rows => new Set(rows.map(f => f.properties.ID_CAMARA || f.properties.ID_PROPUESTA || f.properties.ID_POLICIA)).size;
assert.equal(visible().length, 183);
assert.equal(uniqueCount(visible()), 183);
context.setLayerToggle("interventions", true);
assert.equal(vm.runInContext("individualKeys.some(key => toggles[key])", context), false);
assert.equal(visible().length, 183);
assert.equal(uniqueCount(visible()), 183);
context.setLayerToggle("police", true);
assert.equal(vm.runInContext("toggles.interventions", context), false);
assert.equal(visible().length, 103);
context.setLayerToggle("municipal", true);
context.setLayerToggle("change", true);
assert.equal(visible().length, 183);
context.setLayerToggle("interventionsRadius", true);
assert.equal(vm.runInContext("individualKeys.some(key => layerVisible(key + 'Radius'))", context), false);
context.setLayerToggle("municipalRadius", true);
assert.equal(vm.runInContext("layerVisible('interventionsRadius')", context), false);
const results = JSON.parse(fs.readFileSync(path.join(dataRoot, "RESULTADOS.json"), "utf8"));
source.results = results;
const comparison = results.populationComparison;
assert.deepEqual(comparison.scenarios.map(row => row.cameraCount), [73, 183]);
const fullPopulation = results.population.find(row => row.ESCENARIO === "C");
assert.ok(Math.abs(comparison.insidePlatformAnalyzedPopulation - fullPopulation.POBLACION_ANALIZADA) < .1);
assert.ok(Math.abs(comparison.scenarios[1].insidePlatformPopulation - fullPopulation.POBLACION_CUBIERTA) < .1);
assert.ok(comparison.analyzedPopulation > fullPopulation.POBLACION_ANALIZADA);
assert.ok(Math.abs(comparison.additionalPopulation - (comparison.scenarios[1].coveredPopulation - comparison.scenarios[0].coveredPopulation)) < 1e-9);
for (const row of comparison.scenarios) {
  assert.equal(comparison.officialUrbanReferencePopulation, 177213);
  assert.ok(row.censusUrbanCoveredPopulation <= row.coveredPopulation);
  assert.ok(Math.abs(row.censusUrbanCoveredPct - 100 * row.censusUrbanCoveredPopulation / 177213) < 1e-9);
  assert.ok(row.outsidePlatformPopulation > 0);
  assert.ok(Math.abs(row.coveredPopulation - row.insidePlatformPopulation - row.outsidePlatformPopulation) < 1e-9);
  assert.ok(Math.abs(row.coveredPct - 100 * row.coveredPopulation / comparison.analyzedPopulation) < 1e-9);
}
assert.equal(comparison.mappedCensusUrbanPopulation + comparison.urbanPopulationPendingReconciliation, 177213);
assert.ok(context.populationComparisonHtml().includes("73 cámaras"));
assert.ok(context.populationComparisonHtml().includes("183 cámaras"));
assert.ok(context.populationComparisonHtml().includes("Población adicional cubierta"));
assert.ok(context.populationComparisonHtml().includes("46.630 habitantes"));
assert.ok(context.populationComparisonHtml().includes("93.645 habitantes"));
assert.ok(context.populationComparisonHtml().includes("de 177.213 habitantes · 26,31 %"));
assert.ok(context.populationComparisonHtml().includes("de 177.213 habitantes · 52,84 %"));
assert.ok(context.populationComparisonHtml().includes("+26,53 puntos porcentuales"));
assert.ok(script.includes('document.getElementById("proposalPopulationContent").innerHTML = populationComparisonHtml()'));
const platformComparison = context.platformCameraComparison();
assert.deepEqual(Array.from(platformComparison.inside), [64, 140]);
assert.deepEqual(Array.from(platformComparison.outside), [9, 43]);
assert.deepEqual(Array.from(platformComparison.totals), [73, 183]);
assert.equal(platformComparison.rows.length, 18);
assert.ok(context.platformCameraComparisonHtml().includes("Fuera de plataformas"));
assert.ok(!context.populationComparisonHtml().includes("Porcentajes respecto a la referencia"));
assert.ok(!script.includes('["Población urbana oficial · INEC 2022", number(comparison.officialUrbanReferencePopulation)]'));
assert.ok(!context.populationComparisonHtml().includes("Total ampliado:"));
assert.ok(!script.includes("El porcentaje urbano usa el total oficial"));
assert.ok(!script.includes("El total ampliado incluye exteriores"));
assert.ok(!script.includes('["Población urbana cubierta · estimada", number(fullPopulation.censusUrbanCoveredPopulation)]'));
const percentageStart = script.indexOf("const coveredPopulationPct =");
const percentageExpression = script.slice(percentageStart, script.indexOf(";", percentageStart) + 1);
assert.ok(html.includes('id="populationButton"'));
assert.ok(html.includes('aria-controls="populationPopover"'));
assert.ok(html.includes('id="proposalPopulationContent"'));
assert.ok(!script.includes('<details id="proposalPopulationPanel"'));
assert.ok(!script.includes('<p class="proposal-inventory-note">Intervenciones:'));
const calculated = vm.runInNewContext(percentageExpression + "; coveredPopulationPct;", { comparison, fullPopulation: comparison.scenarios[1] });
assert.ok(Math.abs(calculated - comparison.scenarios[1].coveredPct) < 1e-9);
for (const area of results.territorial) {
  assert.ok(Math.abs(100 * area.AREA_CUBIERTA_URBANA_KM2 / area.AREA_TOTAL_URBANA_KM2 - area.PCT_URBANO) < 1e-9);
}
const classes = new Set();
const sidebar = { classList: { remove: key => classes.delete(key), toggle: (key, enabled) => enabled ? classes.add(key) : classes.delete(key) } };
const node = () => ({ hidden: true, attributes: {}, handlers: {},
  setAttribute(key, value) { this.attributes[key] = value; },
  addEventListener(key, handler) { this.handlers[key] = handler; },
  focus() {}, scrollIntoView() {}, closest() { return sidebar; } });
const nodes = Object.fromEntries(["layersButton", "layersPopover", "closeLayersButton", "populationButton", "populationPopover", "closePopulationButton"].map(key => [key, node()]));
const documentHandlers = {};
const panelContext = vm.createContext({ elements: nodes,
  document: { getElementById: id => nodes[id], addEventListener: (key, handler) => { documentHandlers[key] = handler; } },
  invalidateMapLayout() {}, requestAnimationFrame: callback => callback(),
  cameraProposal: { invalidateMiniMap() {}, renderLegend() {} },
  isCameraProposalMode: () => true,
  window: { matchMedia: () => ({ matches: true }) }
});
vm.runInContext(html.slice(html.indexOf("const layersSidebar ="), html.indexOf("[elements.baseCartographic, elements.baseSatellite].forEach")), panelContext);
const clickPanel = key => nodes[key].handlers.click({ stopPropagation() {} });
clickPanel("populationButton");
assert.equal(nodes.populationPopover.hidden, false);
assert.equal(nodes.layersPopover.hidden, true);
assert.ok(classes.has("population-open"));
clickPanel("layersButton");
assert.equal(nodes.populationPopover.hidden, true);
assert.equal(nodes.layersPopover.hidden, false);
assert.ok(!classes.has("population-open"));
clickPanel("populationButton");
assert.equal(nodes.layersPopover.hidden, true);
documentHandlers.keydown({ key: "Escape" });
assert.equal(nodes.populationPopover.hidden, true);
assert.equal(nodes.populationButton.attributes["aria-expanded"], "false");
clickPanel("populationButton");
clickPanel("closePopulationButton");
assert.equal(nodes.populationPopover.hidden, true);
console.log("PASS: population/layers panel switching, close and Escape; platform totals, denominators, original layers and scenarios intact.");
