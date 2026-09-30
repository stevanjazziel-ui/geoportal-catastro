"""Build the fixed Gi* grid and metric coordinates from the real incident source."""
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]


def read_js(filename, variable):
    text = (ROOT / filename).read_text(encoding="utf-8")
    return json.JSONDecoder().raw_decode(text.split(f"window.{variable} = ", 1)[1])[0]


def main():
    security = read_js("visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    kde = read_js("riobamba-seguridad-kde-validacion-data.js", "RIOBAMBA_KDE_VALIDATION")
    features = json.loads((ROOT / "riobamba-censo-data/riobamba_plataformas.geojson").read_text(encoding="utf-8"))["features"]
    to_metric = Transformer.from_crs(4326, 32717, always_xy=True).transform
    to_geo = Transformer.from_crs(32717, 4326, always_xy=True).transform
    platforms = [(f["properties"]["platform_name"], transform(to_metric, shape(f["geometry"]))) for f in features]
    study = unary_union([geom for _, geom in platforms])
    size = 250
    west, south, east, north = study.bounds
    minx, miny = math.floor(west / size) * size, math.floor(south / size) * size
    cols, rows = math.ceil((east - minx) / size), math.ceil((north - miny) / size)
    cells = []
    for row in range(rows):
        for col in range(cols):
            x, y = minx + (col + 0.5) * size, miny + (row + 0.5) * size
            geom = box(minx + col * size, miny + row * size, minx + (col + 1) * size, miny + (row + 1) * size)
            if not study.intersects(geom) or study.intersection(geom).area < 0.01:
                continue
            center = Point(x, y)
            platform = next((name for name, area in platforms if area.covers(center)), None)
            if platform is None:
                platform = max(platforms, key=lambda item: item[1].intersection(geom).area)[0]
            lng, lat = to_geo(x, y)
            cells.append({"cellId": f"GI-{row}-{col}", "row": row, "col": col, "x": x, "y": y,
                          "lng": lng, "lat": lat, "platform": platform, "geometry": mapping(transform(to_geo, geom))})
    eligible = [event for event in security["events"] if event.get("hotspotEligible") is True]
    ids = {point["id"] for point in kde["kdeInputPoints"]}
    assert ids == {event["id"] for event in eligible}, "KDE and real incident source differ"
    cell_index = {(cell["row"], cell["col"]): index for index, cell in enumerate(cells)}
    counts = [0] * len(cells)
    for point in kde["kdeInputPoints"]:
        if not point.get("platform"):
            continue
        key = (math.floor((point["y"] - miny) / size), math.floor((point["x"] - minx) / size))
        counts[cell_index[key]] += 1
    n = len(cells)
    mean = sum(counts) / n
    std = math.sqrt(max(0, sum(value * value for value in counts) / n - mean * mean))
    by_platform = {name: {"hotspots": 0, "coldspots": 0, "hotspotIncidents": 0, "hotspotsNearBoulevard": 0} for name, _ in platforms}
    roads = []
    for filename in ("premio-habitat-boulevares.geojson", "premio-habitat-conexiones.geojson"):
        road_data = json.loads((ROOT / "data/premio-habitat" / filename).read_text(encoding="utf-8"))
        roads.extend(transform(to_metric, shape(feature["geometry"])) for feature in road_data["features"])
    road_union = unary_union(roads)
    radius = 2
    for index, cell in enumerate(cells):
        neighbors = []
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                other = cell_index.get((cell["row"] + dr, cell["col"] + dc))
                if other is not None and math.hypot(dr * size, dc * size) <= 500:
                    neighbors.append(other)
        num_neighbors = len(neighbors)
        denominator = std * math.sqrt(max(0, (n * num_neighbors - num_neighbors**2) / (n - 1)))
        z = (sum(counts[other] for other in neighbors) - mean * num_neighbors) / denominator if denominator else 0
        bucket = by_platform[cell["platform"]]
        if z >= 1.65:
            bucket["hotspots"] += 1
            bucket["hotspotIncidents"] += counts[index]
            if Point(cell["x"], cell["y"]).distance(road_union) <= 100:
                bucket["hotspotsNearBoulevard"] += 1
        elif z <= -1.65:
            bucket["coldspots"] += 1
    result = {"crs": "EPSG:32717", "weight": 1, "sourceRows": len(security["events"]),
              "eligibleRows": len(eligible), "byId": {point["id"]: [point["x"], point["y"]] for point in kde["kdeInputPoints"]},
              "giSummaryByPlatform": by_platform,
              "giGrid": {"cellSize": size, "neighborDistance": 500, "minX": minx, "minY": miny,
                         "cols": cols, "rows": rows, "cells": cells}}
    (ROOT / "riobamba-incidentes-spatial-data.js").write_text("window.RIOBAMBA_INCIDENT_SPATIAL = " + json.dumps(result, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(json.dumps({"sourceRows": result["sourceRows"], "eligibleRows": len(eligible), "giCells": len(cells), "crs": result["crs"], "weight": 1}))


if __name__ == "__main__":
    main()
