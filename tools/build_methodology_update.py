"""Reproducible analytical classes, dissolved camera scenarios and validation tables."""
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, box, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/seguridad-riobamba/revision-metodologica-20261001"
TO_M = Transformer.from_crs(4326, 32717, always_xy=True).transform


def read_js(file, variable):
    return json.JSONDecoder().raw_decode((ROOT / file).read_text(encoding="utf-8").split(f"window.{variable} = ", 1)[1])[0]


def load(file):
    return json.loads((ROOT / file).read_text(encoding="utf-8-sig"))


def main():
    source = read_js("visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    diagnosis = read_js("riobamba-seguridad-diagnostico-data.js", "RIOBAMBA_SECURITY_DIAGNOSIS")
    spatial = read_js("riobamba-incidentes-spatial-data.js", "RIOBAMBA_INCIDENT_SPATIAL")
    cameras = read_js("riobamba-camaras-data.js", "RIOBAMBA_CAMERAS_DATA")["cameras"]
    assert len(cameras) == len({c["id"] for c in cameras}) == 31
    platforms = {f["properties"]["platform_name"]: transform(TO_M, shape(f["geometry"])) for f in load("riobamba-censo-data/riobamba_plataformas.geojson")["features"]}
    study = unary_union(list(platforms.values()))
    overlap_m2 = sum(g.area for g in platforms.values()) - study.area
    census = load("riobamba-censo-data/riobamba_manzanas_stats.json")["byMan"]
    manzanas = [(f["properties"]["man"], transform(TO_M, shape(f["geometry"]))) for f in load("riobamba-censo-data/riobamba_manzanas.geojson")["features"]]
    roads = unary_union([transform(TO_M, shape(f["geometry"])) for file in ("premio-habitat-boulevares.geojson", "premio-habitat-conexiones.geojson") for f in load("data/premio-habitat/" + file)["features"]])
    police = read_js("policia-06d01-data.js", "RIOBAMBA_POLICE_SIG_DATA")["infrastructure"]["features"]
    police_points = [(f, transform(TO_M, shape(f["geometry"]))) for f in police]
    upc_points = [point for feature, point in police_points if feature.get("properties", {}).get("type") == "UPC"]
    bands = ["POB_0_250", "POB_250_500", "POB_500_1000", "POB_1000_2000", "POB_MAS_2000"]
    proximity = {name: {"PLATFORM_NAME": name, "PLATAFORMA": name.replace("PLATAFORMA ", ""), "POBLACION": diagnosis["byPlatformName"][name]["population"], "AREA_KM2": geom.area/1e6, "NUM_INF_POL": sum(geom.covers(p) for _, p in police_points), "NUM_UPC": sum(geom.covers(p) for p in upc_points), "weightedDistance": 0., "allocatedPopulation": 0., "DIST_MAX": 0., **{band: 0. for band in bands}} for name, geom in platforms.items()}
    proximity_manzanas = {}
    for code, geom in manzanas:
        if geom.is_empty or geom.area <= 0:
            continue
        representative = geom.representative_point()
        distance = min(representative.distance(p) for _, p in police_points)
        band = bands[next((i for i, limit in enumerate((250, 500, 1000, 2000)) if distance <= limit), 4)]
        proximity_manzanas[code] = {"DIST_INF_POL": distance, "DIST_UPC": min(representative.distance(p) for p in upc_points) if upc_points else None, "class": band}
        population = float(census.get(code, {}).get("population_total") or 0)
        for name, platform in platforms.items():
            allocated = population * geom.intersection(platform).area / geom.area
            if allocated:
                row = proximity[name]
                row[band] += allocated
                row["allocatedPopulation"] += allocated
                row["weightedDistance"] += allocated * distance
                row["DIST_MAX"] = max(row["DIST_MAX"], distance)
    for name, row in proximity.items():
        population = row["POBLACION"]
        row["DIST_MEDIA"] = row.pop("weightedDistance") / row["allocatedPopulation"] if row["allocatedPopulation"] else None
        allocated = row.pop("allocatedPopulation")
        # Largest remainders reconcile rounded distance-band estimates with census totals.
        raw = [row[key] / allocated * population if allocated else 0 for key in bands]
        rounded = [math.floor(n) for n in raw]
        for index in sorted(range(5), key=lambda i: raw[i] - rounded[i], reverse=True)[:population - sum(rounded)]:
            rounded[index] += 1
        for index, band in enumerate(bands):
            row[band] = rounded[index]
            row[band.replace("POB_", "PCT_")] = rounded[index] / population * 100 if population else None
        row["INF_10K"] = row["NUM_INF_POL"] / population * 10000 if population else None
        row["UPC_10K"] = row["NUM_UPC"] / population * 10000 if population else None
        row["POB_POR_UPC"] = population / row["NUM_UPC"] if row["NUM_UPC"] else None
    points = {e["id"]: Point(TO_M(e["lng"], e["lat"])) for e in source["events"] if e["mappable"]}
    events = [e for e in source["events"] if e.get("platform")]
    analytic = [e for e in events if e["analyticalClassId"] in (1, 2, 3)]
    class_names = source["analyticalClasses"]
    by_platform = {}
    for name, geom in platforms.items():
        rows = [e for e in events if "PLATAFORMA " + e["platform"] == name]
        population = diagnosis["byPlatformName"][name]["population"]
        counts = {str(i): sum(e["analyticalClassId"] == i for e in rows) for i in range(1, 6)}
        by_platform[name] = {
            "population": population, "counts": counts,
            "rates1000": {str(i): counts[str(i)] / population * 1000 if population else None for i in (1, 2, 3)},
            "predominantClass": max((1, 2, 3), key=lambda i: counts[str(i)]) if sum(counts[str(i)] for i in (1, 2, 3)) else None,
            "predominantSubtype": Counter(e["subtype"] for e in rows if e["hotspotEligible"]).most_common(1),
            "months": dict(sorted(Counter(e["date"][:7] for e in rows if e["hotspotEligible"]).items())),
            "boulevardNearbyByClass": {str(i): sum(e["analyticalClassId"] == i and points[e["id"]].distance(roads) <= 100 for e in rows) for i in (1, 2, 3)},
        }
    cells = spatial["giGrid"]["cells"]
    grid = spatial["giGrid"]
    size = grid["cellSize"]
    geometries = {cell["cellId"]: box(cell["x"] - size/2, cell["y"] - size/2, cell["x"] + size/2, cell["y"] + size/2).intersection(study) for cell in cells}
    cell_tree = STRtree(list(geometries.values()))
    exposure = unary_union([points[e["id"]].buffer(250) for e in analytic])
    scenarios = {}
    camera_points = [Point(TO_M(c["lng"], c["lat"])) for c in cameras]
    for radius in (100, 150, 200):
        coverage = unary_union([point.buffer(radius, quad_segs=64) for point in camera_points])
        by_name = {name: {"platformName": name, "platform": name.replace("PLATAFORMA ", ""), "population": by_platform[name]["population"], "coveredPopulation": 0., "partialPopulation": 0., "areaKm2": geom.area / 1e6, "coveredAreaKm2": geom.intersection(coverage).area / 1e6, "coveredManzanas": 0, "partialManzanas": 0, "uncoveredManzanas": 0} for name, geom in platforms.items()}
        fractions = {}
        cell_population = {cell["cellId"]: 0. for cell in cells}
        cell_uncovered_population = {cell["cellId"]: 0. for cell in cells}
        for row in by_name.values():
            row["exposedUncoveredPopulation250"] = 0.
        for code, geom in manzanas:
            if geom.is_empty or geom.area <= 0:
                continue
            population = float(census.get(code, {}).get("population_total") or 0)
            intersection = geom.intersection(coverage)
            fraction = intersection.area / geom.area
            fractions[code] = min(1, max(0, fraction))
            for name, platform in platforms.items():
                part = geom.intersection(platform)
                if part.area <= .01:
                    continue
                covered = part.intersection(coverage).area
                row = by_name[name]
                row["coveredPopulation"] += population * covered / geom.area
                row["exposedUncoveredPopulation250"] += population * part.intersection(exposure).difference(coverage).area / geom.area
                if covered >= part.area * .999999:
                    row["coveredManzanas"] += 1
                elif covered > .01:
                    row["partialManzanas"] += 1
                    row["partialPopulation"] += population * part.area / geom.area
                else:
                    row["uncoveredManzanas"] += 1
            if population:
                for index in cell_tree.query(geom, predicate="intersects"):
                    cell = cells[int(index)]
                    intersection = geometries[cell["cellId"]].intersection(geom)
                    area = intersection.area
                    if area:
                        cell_population[cell["cellId"]] += population * area / geom.area
                        cell_uncovered_population[cell["cellId"]] += population * intersection.difference(coverage).area / geom.area
        for row in by_name.values():
            row["coveredPopulation"] = min(row["population"], round(row["coveredPopulation"]))
            row["uncoveredPopulation"] = row["population"] - row["coveredPopulation"]
            row["coveredPct"] = row["coveredPopulation"] / row["population"] * 100 if row["population"] else None
            row["uncoveredPct"] = 100 - row["coveredPct"] if row["coveredPct"] is not None else None
            row["coveredAreaPct"] = row["coveredAreaKm2"] / row["areaKm2"] * 100
            row["incidentsByClass"] = {str(i): {"total": by_platform[row["platformName"]]["counts"][str(i)], "covered": sum(e["analyticalClassId"] == i and "PLATAFORMA " + e["platform"] == row["platformName"] and coverage.covers(points[e["id"]]) for e in analytic)} for i in (1, 2, 3)}
        scenarios[str(radius)] = {"byPlatformName": by_name, "byMan": fractions,
            "totalAreaKm2": study.area / 1e6, "totalCoveredAreaKm2": study.intersection(coverage).area / 1e6,
            "totalManzanas": sum(g.intersection(study).area > .01 for _, g in manzanas),
            "coveredManzanas": sum(g.intersection(study).intersection(coverage).area > .01 for _, g in manzanas),
            "incidentIdsCovered": [e["id"] for e in analytic if coverage.covers(points[e["id"]])],
            "byCell": {cell["cellId"]: {"coveredPct": geometries[cell["cellId"]].intersection(coverage).area / geometries[cell["cellId"]].area * 100, "population": cell_population[cell["cellId"]], "uncoveredPopulation": cell_uncovered_population[cell["cellId"]]} for cell in cells}}
        print(f"Scenario {radius} m: area={sum(r['coveredAreaKm2'] for r in by_name.values()):.6f} km2, population={sum(r['coveredPopulation'] for r in by_name.values())}", flush=True)
    urban_counts = {str(i): sum(e["analyticalClassId"] == i for e in analytic) for i in (1, 2, 3)}
    result = {"generatedAt": datetime.now().isoformat(timespec="seconds"), "crs": "EPSG:32717", "classNames": class_names,
        "urbanReferencePopulation": 177213, "urbanScope": "Union de las 18 Plataformas; ambito operativo autorizado, no limite urbano legal",
        "urbanCounts": urban_counts, "urbanRates100000": {key: value / 177213 * 100000 for key, value in urban_counts.items()},
        "byPlatformName": by_platform, "cameraScenarios": scenarios,
        "platformOverlapM2": overlap_m2,
        "limitations": ["Clases analiticas no equivalen a delitos judicialmente confirmados; clase 5 pendiente de revision.", "Poblacion cubierta estimada por distribucion uniforme dentro de manzanas CPV 2022; no personas observadas.", "Gi*: inferencia normal nominal sin correccion de pruebas multiples.", "KDE: intensidad relativa, no peligrosidad ni significancia.", "No se calculan pesos, indice ni ranking final de brechas.", f"Solape original de plataformas: {overlap_m2:.3f} m2; area global de union evita doble conteo; poblacion mantiene estimador censal existente."]}
    (ROOT / "riobamba-metodologia-data.js").write_text("window.RIOBAMBA_METHODOLOGY = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    total_population = sum(row["POBLACION"] for row in proximity.values())
    proximity_summary = {"population": total_population, "infrastructure": sum(row["NUM_INF_POL"] for row in proximity.values()), "upc": sum(row["NUM_UPC"] for row in proximity.values()), **{band: sum(row[band] for row in proximity.values()) for band in bands}}
    proximity_summary.update({"INF_10K": proximity_summary["infrastructure"] / total_population * 10000, "UPC_10K": proximity_summary["upc"] / total_population * 10000, "POB_POR_UPC": total_population / proximity_summary["upc"] if proximity_summary["upc"] else None})
    proximity_data = {"generatedAt": result["generatedAt"], "name": "Proximidad a infraestructura policial", "crs": "EPSG:32717 calculo metrico / EPSG:4326 visualizacion", "method": "Distancia euclidiana desde punto representativo de manzana a la mas cercana de las 26 dependencias originales; poblacion distribuida por fraccion de interseccion areal CPV 2022, misma fuente censal. No tiempo de respuesta ni distancia de red.", "validations": {"infrastructureTotal": len(police), "upcTotal": len(upc_points)}, "summary": proximity_summary, "table": list(proximity.values()), "byPlatformName": proximity, "byMan": proximity_manzanas}
    (ROOT / "riobamba-accesibilidad-policial-data.js").write_text("window.RIOBAMBA_POLICE_ACCESSIBILITY = " + json.dumps(proximity_data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    headers = ["PLATAFORMA", "POBLACION", "DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA", "ACTIVIDAD_INSTITUCIONAL", "OTROS_REVISION", "TASA_DELINCUENCIA_1000", "TASA_VIOLENCIA_1000", "TASA_CONVIVENCIA_1000", "GI_HOTSPOTS", "AREA_TOTAL_KM2", "AREA_CUBIERTA_KM2_150", "PCT_TERRITORIO_CUBIERTO_150", "POB_CUBIERTA_150", "PCT_POB_CUBIERTA_150", "PCT_DELINCUENCIA_CUBIERTA_150"]
    with (OUT / "VALIDACION_PLATAFORMAS.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for name, row in by_platform.items():
            coverage = scenarios["150"]["byPlatformName"][name]
            count = row["counts"]["1"]
            writer.writerow([name, row["population"], *row["counts"].values(), *row["rates1000"].values(), spatial["giSummaryByPlatform"][name]["hotspots"], coverage["areaKm2"], coverage["coveredAreaKm2"], coverage["coveredAreaPct"], coverage["coveredPopulation"], coverage["coveredPct"], coverage["incidentsByClass"]["1"]["covered"] / count * 100 if count else "No disponible"])
    print(json.dumps({"urbanCounts": urban_counts, "urbanRates100000": result["urbanRates100000"], "cameras": len(cameras), "platformPopulation": sum(r["population"] for r in by_platform.values())}))


if __name__ == "__main__":
    main()
