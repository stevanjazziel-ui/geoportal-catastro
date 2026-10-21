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
context.number = value => Number(value).toLocaleString("es-EC");
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
const percentageExpression = script.slice(script.indexOf("const coveredPopulationPct ="), script.indexOf("el.summary.innerHTML ="));
for (const population of results.population) {
  const calculated = vm.runInNewContext(percentageExpression + "; coveredPopulationPct;", { population });
  assert.ok(Math.abs(calculated - population.PCT_CUBIERTO) < 1e-9);
  assert.ok(population.POBLACION_CUBIERTA <= population.POBLACION_ANALIZADA);
}
for (const area of results.territorial) {
  assert.ok(Math.abs(100 * area.AREA_CUBIERTA_URBANA_KM2 / area.AREA_TOTAL_URBANA_KM2 - area.PCT_URBANO) < 1e-9);
}
console.log("PASS: platform label totals; population and area denominators; original layers, unique colors, no duplicates, and scenarios intact.");
