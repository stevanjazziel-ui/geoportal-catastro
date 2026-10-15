"""Versioned, auditable coverage refresh for the user-confirmed 103/30 inventory."""
import json
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely import covers
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sig-bridge"))
from bridge.store import Store, read_json, write_json, digest, clean, now, require
from bridge.engine import calculate, verify_derived
import recalculate_current_gaps as legacy

INVENTORY = ROOT / "data/seguridad-riobamba/INVENTARIO_103_FINAL_20261015"
DESTINATION = ROOT / "data/seguridad-riobamba/SIG_BRIDGE_RELEASES/INVENTARIO_103_30_20261015"


def finalize_release(accept_ring_exception=False):
    results = read_json(DESTINATION / "RESULTADOS.json")
    validation = read_json(DESTINATION / "VALIDACION.json")
    results["counts"] = {"existing": 103, "changeIncluded": 30, "municipal": 50, "police": 30}
    if "kdeComparison" in results:
        results["historicalKdeOptimization"] = {"sourcePackage": "POLICIA_KDE_INTERSECCIONES_20261015",
            "notCurrentInventoryEvaluation": True, "comparison": results.pop("kdeComparison")}
    if accept_ring_exception:
        warnings = [message for message in validation["publishBlocks"] if message.startswith("Restriccion municipal ANILLO_VIAL:")]
        warnings = warnings or validation.get("approvedException", {}).get("warnings", [])
        validation["publishBlocks"] = [message for message in validation["publishBlocks"] if message not in warnings]
        validation["approvedException"] = {
            "constraint": "ANILLO_VIAL escenario B >= 80%", "observedPct": next(
                r["PCT_CUBIERTO"] for r in results["corridors"] if r["ESCENARIO"] == "B" and r["CORREDOR"] == "ANILLO_VIAL"),
            "reason": "Nuevo inventario final; usuario autoriza publicar resultados reales sin mover camaras",
            "authorization": "Publicar los resultados reales, sin mover camaras", "warnings": warnings,
        }
    require(not validation["publishBlocks"], "Hay bloqueos no autorizados: " + str(validation["publishBlocks"]))
    validation["status"] = "PASS_WITH_APPROVED_EXCEPTION" if validation.get("approvedException") else "PASS"
    results["bridge"] = validation
    results["sourcePackage"] = DESTINATION.name
    results["warnings"] = [
        "11 esquinas estimadas no verificadas; no se certifican postes reales ni visibilidad efectiva.",
        "Anillo escenario municipal B: 78.29%; sistema completo C: 80.92%. Excepcion municipal autorizada por el usuario.",
        "Municipales y Policia permanecen fijas; estadisticos Gi* y KDE no recalculados.",
    ]
    write_json(DESTINATION / "VALIDACION.json", validation)
    write_json(DESTINATION / "RESULTADOS.json", results)
    dependencies = DESTINATION / "coverage-inputs"
    gaps = read_json(dependencies / "RESULTADOS.json")
    gaps["metadata"]["sourceInventory"] = {"package": "CAMARAS_103_ESQUINAS_PROPUESTAS.zip",
        "member": "CAMARAS_103_ESQUINAS.shp", "replacementField": "ACTUALIZ",
        "confirmedReplacement": 30, "estimatedCorners": 11,
        "sha256": read_json(INVENTORY / "IMPORTACION.json")["sourceSha256"]}
    for camera in gaps["inventoryCameraOverlay"]:
        camera.setdefault("originalSourcePackage", camera.get("sourcePackage"))
        camera.update({"sourcePackage": "CAMARAS_103_ESQUINAS_PROPUESTAS.zip",
            "sourceMember": "CAMARAS_103_ESQUINAS.shp", "source": "Inventario final recibido; clasificacion para cambio confirmada por el usuario",
            "studyCamera": camera["requiresChange"], "ambitoEstudio": "MUNICIPAL",
            "coordinateSource": "INVENTARIO_103_FINAL_20261015; geometria recibida sin modificaciones"})
    encoded_gaps = json.dumps(gaps, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    (dependencies / "RESULTADOS.json").write_text(encoded_gaps, encoding="utf-8")
    (DESTINATION / "riobamba-brechas-actualizadas-data.js").write_text("window.RIOBAMBA_UPDATED_GAPS = " + encoded_gaps + ";\n", encoding="utf-8")
    with zipfile.ZipFile(dependencies / "BRECHAS_ACTUALIZADAS.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dependencies.iterdir()):
            if path.is_file() and path.suffix != ".zip":
                archive.write(path, path.name)
    corridor_data = read_json(DESTINATION / "CORRIDOR_COVERAGE_200M.json")
    corridor_data["metadata"]["sourcePackage"] = DESTINATION.name
    write_json(DESTINATION / "CORRIDOR_COVERAGE_200M.json", corridor_data)
    (DESTINATION / "INFORME_FINAL.md").write_text(
        "# Coberturas con inventario final 103/30\n\n"
        "103 existentes: 30 para cambio (ACTUALIZ=SI, confirmado por el usuario), 73 sin cambio. "
        "Las 30 estan incluidas en las 103. Fuente y geometrias recibidas conservadas.\n\n"
        "Union de buffers metricos, EPSG:32717, radio 200 m y quad_segs=64. "
        "Escenarios A=103, B=153 y C=183. Las dependencias censales se actualizan tambien a 100 y 150 m. "
        "No se modifica la asignacion estricta de incidentes a manzanas ni los percentiles.\n\n"
        "Las 50 municipales y las 30 policiales permanecen en sus ubicaciones. No se optimizan. "
        "KDE, geometrias Gi*, estadisticos, parametros y significancias permanecen sin cambios. "
        "Solo cambia su estado de cobertura.\n\n"
        "Macaji-Bellavista: B/C 100%, longitud sin cobertura 0 m. "
        "Anillo Vial: B 78.288525%, C 80.924451%. "
        "El usuario autoriza publicar el resultado real del nuevo inventario sin mover propuestas, "
        "aceptando la excepcion al minimo municipal anterior de 80%.\n\n"
        "El archivo recibido documenta 11 esquinas estimadas no verificadas. "
        "Estas coberturas son potenciales, no prueban instalacion, operatividad, campo visual ni postes reales.\n\n"
        "VERIFICACION_INDEPENDIENTE.json documenta controles de escenarios, fuentes, inventarios y radios. "
        "COMPARACION_COBERTURAS.json conserva resultados anteriores y nuevos.\n",
        encoding="ascii",
    )
    with zipfile.ZipFile(DESTINATION / "ENTREGA_POLICIA_KDE.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DESTINATION.iterdir()):
            if path.is_file() and path.suffix != ".zip":
                archive.write(path, path.name)
    return validation


def main():
    store = Store()
    store.base = ROOT / "data/seguridad-riobamba/POLICIA_KDE_INTERSECCIONES_20261015/ESCENARIO_FINAL_183.gpkg"
    store.web = store.base.parent
    imported = read_json(INVENTORY / "IMPORTACION.json")
    source = INVENTORY / "INVENTARIO_FINAL_103.gpkg"
    require(digest(source) == imported["files"][source.name], "Inventario recibido modificado")
    require(digest(store.base) == imported["previousSha256"], "La base ya no coincide con la comparada")
    inventory = gpd.read_file(source, layer="CAMARAS_EXISTENTES_103_FINAL")
    require(len(inventory) == 103 and int(inventory.REQUIERE_CAMBIO.sum()) == 30, "Inventario confirmado inconsistente")
    protected = {str(store.base): digest(store.base), str(source): digest(source)}
    protected.update({str(ROOT / n): digest(ROOT / n) for n in (
        "riobamba-hotspot-urbano-200m-data.js", "riobamba-conflictividad-data.js",
        "riobamba-seguridad-kde-validacion-data.js", "riobamba-incidentes-spatial-data.js",
        "riobamba-cantonal-data.js", "visor-seguridad-riobamba-data.js")})
    DESTINATION.mkdir(parents=True, exist_ok=False)
    manual = {}
    for key, spec in store.config["layers"].items():
        frame = gpd.read_file(store.base, layer=spec["source"])
        frame["OBSERVACION_MANUAL"] = ""
        manual[key] = frame
    receipt = {"revision": DESTINATION.name, "changes": [], "baseHashes": protected,
               "inventorySourceSha256": digest(source), "createdAt": now()}
    print("Recalculando A/B/C a radio 200 m; propuestas y estadisticos fijos", flush=True)
    validation = calculate(store, DESTINATION, DESTINATION, manual, receipt, inventory)
    package = DESTINATION / "ESCENARIO_FINAL_183.gpkg"
    results = read_json(DESTINATION / "RESULTADOS.json")
    print("Recalculando dependencias censales y radios 100/150/200 m", flush=True)
    dependencies = DESTINATION / "coverage-inputs"
    dependencies.mkdir()
    legacy.main(final=package, out=dependencies,
                js_output=DESTINATION / "riobamba-brechas-actualizadas-data.js", expected_replacements=30)
    gaps = read_json(dependencies / "RESULTADOS.json")
    require(sum(c["requiresChange"] for c in gaps["inventoryCameraOverlay"]) == 30, "Overlay desincronizado")
    for radius in (100, 150, 200):
        scenarios = gaps["scenarios"][str(radius)]
        require([scenarios[k]["cameraRecords"] for k in ("A", "B", "C", "REEMPLAZO_30")] == [103,153,183,30], "Universos inconsistentes")
        for key, id_field in (("PROPUESTA_MUNICIPAL_50_FINAL", "ID_PROPUESTA"), ("PROPUESTA_POLICIA_30_FINAL", "ID_POLICIA")):
            before = gpd.read_file(store.base, layer=key).set_index(id_field)
            after = gpd.read_file(package, layer=key).set_index(id_field).loc[before.index]
            require(before.geometry.to_wkb().tolist() == after.geometry.to_wkb().tolist(), "Una propuesta se movio")
        for data in (gaps["inventoryCoverage"]["scenarios"][str(radius)], gaps["replacementScenarios"][str(radius)]):
            require(0 <= data["totalCoveredAreaKm2"] <= data["totalAreaKm2"], "Superficie inconsistente")
            for row in data["byPlatformName"].values():
                require(row["coveredPopulation"] + row["uncoveredPopulation"] == row["population"], "Poblacion inconsistente")
    verify_derived(store, package, results, inventory)
    # Independently recompute event coverage; statistical attributes are checked by verify_derived.
    events = gpd.read_file(package, layer="INCIDENTES_CLASIFICADOS")
    for code in ("A", "B", "C"):
        mask = gpd.read_file(package, layer="COBERTURA_"+code).geometry.iloc[0]
        require(np.array_equal(covers(mask, events.geometry.values), events["CUB_"+code].astype(bool).values), "Cobertura puntual incorrecta")
    require(all(digest(Path(p)) == h for p, h in protected.items()), "Se modifico una fuente protegida")
    results.update({"status": "INVENTARIO_FINAL_103_30", "generatedAt": now(),
        "counts": {"existing": 103, "changeIncluded": 30, "municipal": 50, "police": 30},
        "inventory": {"total": 103, "replacement": 30, "withoutReplacement": 73,
            "uniqueSites": 103, "source": "INVENTARIO_103_FINAL_20261015",
            "sourceSha256": digest(source), "estimatedCorners": imported["estimatedCornerIds"],
            "notice": "11 esquinas estimadas no verificadas; cobertura potencial, no visibilidad real certificada"}})
    write_json(DESTINATION / "RESULTADOS.json", results)
    validation.update({"confirmedReplacement": 30, "withoutReplacement": 73,
        "proposalsUnmoved": True, "originalsUnmodified": True, "exactReceivedGeometry": True,
        "radiiM": [100,150,200], "coverageDependenciesUpdated": True,
        "sourceHashes": protected, "inventory": results["inventory"]})
    write_json(DESTINATION / "VALIDACION.json", validation)
    before_results = read_json(store.web / "RESULTADOS.json")
    comparison = {key: {"before": before_results[key], "after": results[key]}
                  for key in ("territorial", "population", "incidents", "hotspots", "corridors")}
    write_json(DESTINATION / "COMPARACION_COBERTURAS.json", comparison)
    with zipfile.ZipFile(DESTINATION / "ENTREGA_POLICIA_KDE.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DESTINATION.iterdir()):
            if path.is_file() and path.suffix != ".zip":
                archive.write(path, path.name)
    print(json.dumps(clean({"validation": validation, "corridors": results["corridors"], "population": results["population"]}), ensure_ascii=True), flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--accept-approved-ring-exception", action="store_true")
    args = parser.parse_args()
    if not args.finalize_only:
        main()
    print(json.dumps(finalize_release(args.accept_approved_ring_exception), ensure_ascii=True), flush=True)
