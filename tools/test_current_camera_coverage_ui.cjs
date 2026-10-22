"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const release = JSON.parse(fs.readFileSync(path.join(root, "sig-bridge-active.json"))).root;
const script = fs.readFileSync(path.join(root, "riobamba-cobertura-actual.js"), "utf8");
const html = fs.readFileSync(path.join(root, "visor-seguridad-riobamba-v2.html"), "utf8");
for (const [, body] of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(body);
const node = dataset => ({ dataset, hidden: true, handlers: {}, innerHTML: "", textContent: "", value: "",
  classList: { add() {}, remove() {}, toggle() {} }, setAttribute() {},
  addEventListener(event, fn) { this.handlers[event] = fn; } });
const buttons = ["current", "interventions", "combined"].map(key => node({ currentGroup: key }));
const checks = ["points", "buffers", "platforms"].map(key => node({ currentLayer: key }));
const controls = { currentCoverageControls: { querySelectorAll: () => buttons },
  currentCoverageLayerControls: { querySelectorAll: () => checks }, currentCoverageExtent: node() };
const elements = Object.fromEntries(["workspace", "overlayTitle", "overlayText", "status", "summary", "detailTitle", "detail", "graphicAnalysis", "legend"].map(key => [key, node()]));
let active = true, radius = 200;
const visible = new Set();
const map = { removeLayer: layer => visible.delete(layer), invalidateSize() {}, fitBounds() {} };
const context = vm.createContext({ window: { RIOBAMBA_SIG_RELEASE_ROOT: "release/" },
  document: { getElementById: id => controls[id] || node() },
  fetch: async url => ({ ok: true, json: async () => JSON.parse(fs.readFileSync(path.join(root, release, url.replace("release/", "")), "utf8")) }),
  L: { divIcon: value => value, marker: (latlng, options) => ({ latlng, options }),
    geoJSON(data, options = {}) {
      const layer = { cameraCount: 0, addTo() { visible.add(this); }, getBounds: () => ({ isValid: () => true }) };
      if (options.pointToLayer) for (const feature of data.features) { options.pointToLayer(feature, feature.geometry.coordinates); layer.cameraCount++; }
      return layer;
    } }
});
vm.runInContext(script, context);
const controller = context.window.createRiobambaCurrentCoverage({ map, elements, active: () => active,
  radius: () => radius, esc: value => String(value ?? ""), layers: () => [] });
const cameras = () => [...visible].reduce((sum, layer) => sum + layer.cameraCount, 0);
(async () => {
  await controller.render();
  assert.equal(cameras(), 183);
  assert.ok(elements.summary.innerHTML.includes("93.645"));
  buttons[0].handlers.click(); await controller.render();
  assert.equal(cameras(), 73);
  assert.ok(elements.summary.innerHTML.includes("46.630"));
  buttons[1].handlers.click(); await controller.render();
  assert.equal(cameras(), 110);
  assert.ok(elements.summary.innerHTML.includes("63.137"));
  radius = 100; await controller.render();
  assert.ok(elements.summary.innerHTML.includes("16.159"));
  checks[0].checked = false; checks[0].handlers.change();
  assert.equal(cameras(), 0);
  active = false; controller.leave();
  assert.equal(visible.size, 0);
  console.log("PASS: HTML syntax, 73/110/183 switching, radius changes, layer toggles and lifecycle cleanup.");
})().catch(error => { console.error(error); process.exitCode = 1; });
