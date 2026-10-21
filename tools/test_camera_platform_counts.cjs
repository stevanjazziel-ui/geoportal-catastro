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
const result = context.countPlatformCameras(source);
assert.equal(result.rows.length, 18);
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
for (const [scenario, enabled, expected] of [
  ["A", ["existing"], [103, 0, 0, 103]],
  ["B", ["existing", "municipal"], [103, 50, 0, 153]],
  ["C", ["existing", "municipal", "police"], [103, 50, 30, 183]]
]) {
  context.groupEnabled = group => enabled.includes(group);
  assert.deepEqual(Array.from(context.platformCountValues(totals)), expected, scenario);
}
const polygon = coordinates => ({ properties: { platform_name: "PLATAFORMA TEST" }, geometry: { type: "Polygon", coordinates } });
const synthetic = { platforms: { features: [polygon([[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]])] },
  existing: { features: [{ geometry: { coordinates: [1, 1] } }, { geometry: { coordinates: [3, 3] } }] },
  municipal: { features: [] }, police: { features: [] } };
const sample = context.countPlatformCameras(synthetic);
assert.equal(sample.rows[0].counts.existing, 1);
assert.equal(sample.outside.existing, 1);
console.log("PASS: 18 platforms, independent spatial counts, outside cameras, scenarios 103/153/183.");
