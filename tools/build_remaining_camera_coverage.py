"""Separate metric coverage of inventory cameras outside the agreed replacement set."""
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/seguridad-riobamba/cobertura-camaras-restantes-20261002"
PROJECT = Transformer.from_crs(4326, 32717, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32717, 4326, always_xy=True).transform
PROTECTED = ["riobamba-camaras-data.js", "riobamba-camaras-inventario-data.js",
             "riobamba-metodologia-data.js", "riobamba-conflictividad-data.js",
             "riobamba-cantonal-data.js", "visor-seguridad-riobamba-data.js",
             "riobamba-seguridad-diagnostico-data.js", "riobamba-accesibilidad-policial-data.js"]


def digest(file):
    return hashlib.sha256((ROOT / file).read_bytes()).hexdigest()


def read_js(file):
    text = (ROOT / file).read_text(encoding="utf-8")
    return json.JSONDecoder().raw_decode(text.split(" = ", 1)[1])[0]


def load(file):
    return json.loads((ROOT / file).read_text(encoding="utf-8-sig"))


def main(full_inventory=False):
    out = ROOT / "data/seguridad-riobamba/deficit-inventario-20261002" if full_inventory else OUT
    prefix = "INVENTARIO" if full_inventory else "RESTANTES"
    universe = "CAMARAS_INVENTARIO_COMPLETO" if full_inventory else "CAMARAS_RESTANTES"
    before = {file: digest(file) for file in PROTECTED}
    inventory = read_js("riobamba-camaras-inventario-data.js")["cameras"]
    study = read_js("riobamba-camaras-data.js")["cameras"]
    study_ids = {camera["id"] for camera in study}
    remaining = [camera for camera in inventory if camera["id"] not in study_ids]
    universe_cameras = inventory if full_inventory else remaining
    located = [camera for camera in universe_cameras if camera["mappable"]]
    pending = [camera for camera in universe_cameras if not camera["mappable"]]
    assert len(inventory) == 103 and len(study_ids) == 31 and len(remaining) == 72
    assert len(located) == (99 if full_inventory else 68) and len(pending) == 4
    assert all(not camera["requiresChange"] for camera in remaining)
    assert all(camera["lat"] is None and camera["lng"] is None for camera in pending)
    points = {camera["id"]: Point(PROJECT(camera["lng"], camera["lat"])) for camera in located}
    territory = read_js("riobamba-cantonal-data.js")
    correction = read_js("riobamba-conflictividad-data.js")
    population_rows = correction["derivedMethodology"]["cameraScenarios"]["150"]["byPlatformName"]
    platforms = {feature["properties"]["platform_name"]: transform(PROJECT, shape(feature["geometry"]))
                 for feature in load("riobamba-censo-data/riobamba_plataformas.geojson")["features"]}
    urban = unary_union(list(platforms.values()))
    canton = transform(PROJECT, shape(territory["canton"]["geometry"]))
    rural = canton.difference(urban)
    parishes = {feature["properties"]["name"]: transform(PROJECT, shape(feature["geometry"])).difference(urban)
                for feature in territory["parishes"]["features"]}
    census = load("riobamba-censo-data/riobamba_manzanas_stats.json")["byMan"]
    blocks = [(feature["properties"]["man"], transform(PROJECT, shape(feature["geometry"])))
              for feature in load("riobamba-censo-data/riobamba_manzanas.geojson")["features"]]
    parts = {code: {name: geometry.intersection(platform) for name, platform in platforms.items()
                    if geometry.intersects(platform)} for code, geometry in blocks}
    events = read_js("visor-seguridad-riobamba-data.js")["events"]
    event_points = {event["id"]: Point(PROJECT(event["lng"], event["lat"])) for event in events
                    if event.get("mappable") and correction["dictionary"][event["subtype"]] in ("DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA")
                    and territory["assignments"][event["id"]]["scope"] == "URBANO"}
    out.mkdir(parents=True, exist_ok=True)
    scenarios, report = {}, []
    previous_area = previous_population = -1
    for radius in (100, 150, 200):
        buffers = [point.buffer(radius, quad_segs=64) for point in points.values()]
        coverage = unary_union(buffers)
        assert coverage.is_valid and coverage.area <= sum(buffer.area for buffer in buffers) + .01
        rows = {name: {"platformName": name, "platform": name.replace("PLATAFORMA ", ""),
                       "population": population_rows[name]["population"], "coveredPopulation": 0., "partialPopulation": 0.,
                       "areaKm2": geometry.area / 1e6, "coveredAreaKm2": geometry.intersection(coverage).area / 1e6,
                       "cameras": sum(geometry.covers(point) for point in points.values()),
                       "coveredManzanas": 0, "partialManzanas": 0, "uncoveredManzanas": 0}
                for name, geometry in platforms.items()}
        fractions, total_blocks, covered_blocks = {}, 0, 0
        for code, geometry in blocks:
            if geometry.is_empty or geometry.area <= 0:
                continue
            population = float(census.get(code, {}).get("population_total") or 0)
            covered = geometry.intersection(coverage)
            fractions[code] = min(1, max(0, covered.area / geometry.area))
            urban_part = geometry.intersection(urban)
            total_blocks += urban_part.area > .01
            covered_blocks += urban_part.intersection(coverage).area > .01
            for name, part in parts[code].items():
                if part.area <= .01:
                    continue
                local_area = part.intersection(coverage).area
                row = rows[name]
                row["coveredPopulation"] += population * local_area / geometry.area
                if local_area >= part.area * .999999:
                    row["coveredManzanas"] += 1
                elif local_area > .01:
                    row["partialManzanas"] += 1
                    row["partialPopulation"] += population * part.area / geometry.area
                else:
                    row["uncoveredManzanas"] += 1
        for row in rows.values():
            row["coveredPopulation"] = min(row["population"], round(row["coveredPopulation"]))
            row["uncoveredPopulation"] = row["population"] - row["coveredPopulation"]
            row["coveredPct"] = row["coveredPopulation"] / row["population"] * 100 if row["population"] else None
            row["coveredAreaPct"] = row["coveredAreaKm2"] / row["areaKm2"] * 100
        def area_result(geometry):
            return {"areaKm2": geometry.area / 1e6, "coveredAreaKm2": geometry.intersection(coverage).area / 1e6,
                    "cameras": sum(geometry.covers(point) for point in points.values()),
                    "coveredPopulation": None, "population": None}
        feature = {"type": "Feature", "properties": {"universe": universe, "radius_m": radius,
                   "cameras_total": len(universe_cameras), "cameras_located": len(located), "crs_calculation": "EPSG:32717"},
                   "geometry": mapping(transform(UNPROJECT, coverage))}
        scenarios[str(radius)] = {"byPlatformName": rows, "byMan": fractions,
                                 "totalAreaKm2": urban.area / 1e6, "totalCoveredAreaKm2": urban.intersection(coverage).area / 1e6,
                                 "totalManzanas": total_blocks, "coveredManzanas": covered_blocks,
                                 "incidentIdsCovered": [code for code, point in event_points.items() if coverage.covers(point)],
                                 "coverage": feature, "fullDissolvedAreaKm2": coverage.area / 1e6,
                                 "cantonal": area_result(canton), "rural": area_result(rural),
                                 "byParish": {name: area_result(geometry) for name, geometry in parishes.items()}}
        if full_inventory:
            scenarios[str(radius)]["uncovered"] = {"type": "Feature", "properties": {"universe": universe,
                "radius_m": radius, "meaning": "Territorio urbano fuera de cobertura potencial"},
                "geometry": mapping(transform(UNPROJECT, urban.difference(coverage)))}
        area, covered_population = scenarios[str(radius)]["totalCoveredAreaKm2"], sum(row["coveredPopulation"] for row in rows.values())
        assert area >= previous_area and covered_population >= previous_population
        previous_area, previous_population = area, covered_population
        report.append({"radius": radius, "cameras": len(located), "dissolvedAreaKm2": coverage.area / 1e6,
                       "urbanCoveredAreaKm2": area, "urbanCoveredPopulation": covered_population,
                       "ruralCoveredAreaKm2": scenarios[str(radius)]["rural"]["coveredAreaKm2"],
                       "populationScope": "Union de las 18 Plataformas; no poblacion cantonal/rural completa"})
        (out / f"COBERTURA_{prefix}_{radius}M.geojson").write_text(json.dumps(feature, separators=(",", ":")), encoding="utf-8")
        with (out / f"INDICADORES_{prefix}_{radius}M.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(next(iter(rows.values()))))
            writer.writeheader()
            writer.writerows(rows.values())
        print(json.dumps(report[-1]), flush=True)
    result = {"metadata": {"generatedAt": datetime.now(ZoneInfo("America/Guayaquil")).isoformat(timespec="seconds"),
              "universe": universe, "totalRecords": len(universe_cameras), "locatedRecords": len(located),
              "pendingRecords": [{"id": camera["id"], "address": camera["address"], "reason": camera["method"]} for camera in pending],
              "cameraIds": [camera["id"] for camera in universe_cameras], "locatedIds": list(points), "crs": "EPSG:32717",
              "radiiMeters": [100, 150, 200], "bufferQuadSegments": 64, "sourceHashes": before,
              "populationScope": "Union de las 18 Plataformas; estimacion areal CPV 2022, misma metodologia existente",
              "limitations": "Posiciones aproximadas; cobertura potencial, no alcance visual ni operatividad verificada. Cuatro registros sin coordenadas quedan excluidos. No se estima poblacion rural completa. Las 31 para cambio y sus derivados no se modifican."},
              "scenarios": scenarios}
    output_js = "riobamba-camaras-inventario-cobertura-data.js" if full_inventory else "riobamba-camaras-restantes-cobertura-data.js"
    output_variable = "RIOBAMBA_INVENTORY_CAMERA_COVERAGE" if full_inventory else "RIOBAMBA_REMAINING_CAMERA_COVERAGE"
    (ROOT / output_js).write_text(
        "window." + output_variable + " = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    assert all(digest(file) == value for file, value in before.items()), "Protected analytical inputs changed"
    (out / f"VALIDACION_COBERTURA_{prefix}.json").write_text(json.dumps({"sourceHashes": before, "protectedUnchanged": True,
        "records": len(universe_cameras), "located": len(located), "pending": result["metadata"]["pendingRecords"], "scenarios": report}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", action="store_true", help="Recalculate the union of all located inventory cameras, leaving the 31-camera baseline unchanged")
    main(parser.parse_args().inventory)
