"""Reproducible cantonal inputs; original incidents and urban results stay immutable."""
import csv
import json
import math
from collections import Counter
from datetime import datetime

import shapefile
from pyproj import Transformer
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import transform, unary_union
from shapely.prepared import prep

from audit_cantonal_expansion import ROOT, OUT, TERRITORY, load, read_js


def gi(counts, neighbors):
    n = len(counts)
    mean = sum(counts) / n
    sd = math.sqrt(max(0, sum(v*v for v in counts)/n - mean*mean))
    result = []
    for ids in neighbors:
        k = len(ids)
        den = sd * math.sqrt(max(0, (n*k-k*k)/(n-1)))
        z = (sum(counts[i] for i in ids)-mean*k)/den if den else 0
        p = math.erfc(abs(z)/math.sqrt(2))
        level = 99 if p <= .01 else 95 if p <= .05 else 90 if p <= .1 else 0
        cls = f"{'HOTSPOT' if z > 0 else 'COLDSPOT'} {level}%" if level else "NO SIGNIFICATIVO"
        result.append({"COUNT": counts[len(result)], "GI_ZSCORE": z, "GI_PVALUE": p, "GI_CLASS": cls})
    return result


def main():
    audit = load(OUT / "AUDITORIA_CANTONAL.json")
    project = Transformer.from_crs(4326, 32717, always_xy=True).transform
    unproject = Transformer.from_crs(32717, 4326, always_xy=True).transform

    def shp(name):
        reader = shapefile.Reader(str(TERRITORY / name), encoding="utf-8")
        fields = [f[0] for f in reader.fields[1:]]
        return [(dict(zip(fields, item.record)), transform(project, shape(item.shape.__geo_interface__))) for item in reader.iterShapeRecords()]

    canton = unary_union([g for _, g in shp("limite_canton_riobamba_wgs84.shp")])
    platforms = load(ROOT / "riobamba-censo-data/riobamba_plataformas.geojson")
    urban = unary_union([transform(project, shape(f["geometry"])) for f in platforms["features"]])
    parishes = [(p, g) for p, g in shp("division_parroquial_riobamba_wgs84.shp") if p["ESTADO"] == "RURAL"]
    rural = unary_union([g for _, g in parishes]).difference(urban).intersection(canton)
    source = read_js("visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    events = {e["id"]: e for e in source["events"]}
    assignments = {}
    with (OUT / "ASIGNACION_PRELIMINAR.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            x, y = project(float(row["LONGITUD"]), float(row["LATITUD"]))
            assignments[row["ID"]] = {"scope": row["AMBITO_PROPUESTO"], "unit": row["UNIDAD_ESPACIAL"], "insideCanton": row["MOTIVO"] != "FUERA_DEL_CANTON", "reason": row["MOTIVO"], "x": x, "y": y}
    points = [(a["x"], a["y"], int(events[id]["analyticalClassId"]), id) for id, a in assignments.items() if a["scope"] == "RURAL" and events[id]["hotspotEligible"]]
    parish_rows = {r["PARROQUIA"]: r for r in audit["ruralPopulationAndEventsPreliminary"]}
    parish_features = []
    for props, geom in parishes:
        operative = geom.difference(urban).intersection(canton)
        row = parish_rows[props["PARROQUIA"]]
        parish_features.append({"type": "Feature", "properties": {"name": props["PARROQUIA"], "population": row["POBLACION_CPV"], "censusCode": row["CODIGO_CPV_PROPUESTO"], "areaKm2": operative.area/1e6, "police": row["DEPENDENCIAS_INVENTARIADAS"]}, "geometry": mapping(transform(unproject, operative))})
    grids = []
    assessments = []
    for size in (500, 750, 1000):
        west, south, east, north = rural.bounds
        minx, miny = math.floor(west/size)*size, math.floor(south/size)*size
        cells = []
        for row in range(math.ceil((north-miny)/size)):
            for col in range(math.ceil((east-minx)/size)):
                square = box(minx+col*size, miny+row*size, minx+(col+1)*size, miny+(row+1)*size)
                clipped = square.intersection(rural)
                if clipped.area < 1:
                    continue
                parish_areas = {p["PARROQUIA"]: clipped.intersection(g).area/1e6 for p, g in parishes if g.intersects(clipped)}
                name = max(parish_areas, key=parish_areas.get)
                cells.append({"cellId": f"R-{size}-{row}-{col}", "row": row, "col": col, "x": minx+(col+.5)*size, "y": miny+(row+.5)*size, "PARROQUIA": name, "parishAreas": parish_areas, "areaKm2": clipped.area/1e6, "geometry": mapping(transform(unproject, clipped))})
        index = {(c["row"], c["col"]): i for i, c in enumerate(cells)}
        counts = [0]*len(cells)
        for x, y, _, _ in points:
            counts[index[(math.floor((y-miny)/size), math.floor((x-minx)/size))]] += 1
        distribution = dict(Counter(counts))
        occupied = sum(v > 0 for v in counts)
        grid = {"cellSize": size, "minX": minx, "minY": miny, "cells": cells}
        for distance in (size*1.5, size*2, size*3):
            neighbors = []
            radius = math.ceil(distance/size)
            for c in cells:
                neighbors.append([index[(c["row"]+dr, c["col"]+dc)] for dr in range(-radius, radius+1) for dc in range(-radius, radius+1) if math.hypot(dr*size, dc*size) <= distance and (c["row"]+dr, c["col"]+dc) in index])
            neighbor_counts = [len(ids)-1 for ids in neighbors]
            results = gi(counts, neighbors)
            classes = Counter(r["GI_CLASS"] for r in results)
            assessments.append({"cellSize": size, "distance": distance, "cells": len(cells), "occupied": occupied, "empty": len(cells)-occupied, "meanIncidents": sum(counts)/len(cells), "maximum": max(counts), "distribution": distribution, "meanNeighbors": sum(neighbor_counts)/len(cells), "minNeighbors": min(neighbor_counts), "maxNeighbors": max(neighbor_counts), "isolated": neighbor_counts.count(0), "classes": dict(classes)})
            if distance == size*2:
                grid.update(neighborDistance=distance, neighbors=neighbors, generalResults=results)
        grids.append(grid)
    # Select coarsest evaluated support to reduce sparsity, then minimum tested
    # distance giving no isolated units and >=8 neighbors on average. No Gi classes enter selection.
    selected = max(grids, key=lambda g: g["cellSize"])
    candidates = [r for r in assessments if r["cellSize"] == selected["cellSize"] and r["isolated"] == 0 and r["meanNeighbors"] >= 8]
    chosen = min(candidates, key=lambda r: r["distance"]) if candidates else None
    assert chosen and chosen["distance"] == selected["neighborDistance"], "Review rural neighborhood selection"
    selected["byClass"] = {}
    for class_id in (1, 2, 3):
        counts = [0]*len(selected["cells"])
        index = {(c["row"], c["col"]): i for i, c in enumerate(selected["cells"])}
        for x, y, cls, _ in points:
            if cls == class_id:
                counts[index[(math.floor((y-selected["minY"])/1000), math.floor((x-selected["minX"])/1000))]] += 1
        selected["byClass"][str(class_id)] = gi(counts, selected["neighbors"])
    distances = sorted(min(math.hypot(x-xx, y-yy) for xx, yy, _, other in points if other != id) for x, y, _, id in points)
    kde_grids = {}
    for key, geometry in (("RURAL", rural), ("CANTONAL", canton)):
        cell = 100
        west, south, east, north = geometry.bounds
        west, south = math.floor(west/cell)*cell, math.floor(south/cell)*cell
        width, height = math.ceil((east-west)/cell), math.ceil((north-south)/cell)
        east, north = west+width*cell, south+height*cell
        prepared = prep(geometry)
        mask = [row*width+col for row in range(height) for col in range(width) if prepared.covers(Point(west+(col+.5)*cell, north-(row+.5)*cell))]
        gw, gs, ge, gn = transform(unproject, geometry).bounds
        warp = []
        for row in range(height):
            for col in range(width):
                x, y = project(gw+(col+.5)*(ge-gw)/width, gn-(row+.5)*(gn-gs)/height)
                mx, my = math.floor((x-west)/cell), math.floor((north-y)/cell)
                warp.append(my*width+mx if 0 <= mx < width and 0 <= my < height else -1)
        bounds = [[gs, gw], [gn, ge]]
        kde_grids[key] = {"cellSize": cell, "bandwidth": 1500, "width": width, "height": height, "metricBounds": [[west, south], [east, north]], "bounds": bounds, "mask": mask, "warpIndex": warp}
    out = ROOT / "data/seguridad-riobamba/expansion-cantonal-20261001"
    out.mkdir(parents=True, exist_ok=True)
    metadata = {"generatedAt": datetime.now().isoformat(timespec="seconds"), "crs": "EPSG:32717", "weight": 1, "period": "2026-01-01 / 2026-08-31", "source": "Base de Datos Emergencias_SC_Riobamba (2).xlsx; CPV 2022; shapefiles cantonales disponibles", "geometryAudit": audit["geometry"], "assignment": audit["assignmentRule"], "ruralGridSelection": "Mayor soporte evaluado (1000 m) para reducir celdas vacias; menor vecindad evaluada sin aislados y con media >=8 vecinos. Seleccion independiente de hotspots. Resultados nominales exploratorios sin FDR; distribucion escasa limita aproximacion normal.", "kdeParameters": {"urban": {"cell": 20, "bandwidth": 700}, "rural": {"cell": 100, "bandwidth": 1500}, "cantonal": {"cell": 100, "bandwidth": 1500}, "kernel": "Gaussiano truncado a bandwidth; peso 1; suma continua antes de mascara", "ruralAssessment": {"nearestNeighborMedian": distances[len(distances)//2], "nearestNeighborP90": distances[int(len(distances)*.9)], "candidates": [1000, 1500, 2000], "selection": "1500 m como escenario exploratorio fijo de escala rural, no optimizado para significancia; requiere validacion y sensibilidad antes de decisiones"}}, "limitations": ["Limite urbano operativo: union de 18 Plataformas; no equivale al limite urbano legal/censal oficial no disponible.", "83.669 habitantes rurales incluyen 11.678 de PARROQ 060150 fuera de las once parroquias rurales. Sus poblaciones suman 71.991. Tasas de referencia operativa, no denominadores espacialmente concordantes certificados.", "850 registros SIN_ASIGNAR: 820 dentro del canton incluidos en analisis cantonal y 30 fuera excluidos.", "Inventario rural de camaras no disponible; no se interpreta como cero.", "Poblacion georreferenciada rural incompleta; cobertura y exposicion poblacional rural no disponibles.", "Gi* rural nominal, sin correccion multiple; escasez y exceso de ceros requieren cautela. No implica peligrosidad."]}
    result = {"metadata": metadata, "population": {"CANTONAL": 260882, "URBANO": 177213, "RURAL": 83669}, "assignments": assignments, "canton": {"type": "Feature", "properties": {"name": "Riobamba"}, "geometry": mapping(transform(unproject, canton))}, "urban": {"type": "Feature", "properties": {"name": "Ambito urbano operativo (18 Plataformas)"}, "geometry": mapping(transform(unproject, urban))}, "parishes": {"type": "FeatureCollection", "features": parish_features}, "ruralGrid": selected, "gridAssessment": assessments, "kdeGrids": kde_grids, "policeAssignments": audit["policeAssignments"], "validation": {"total": len(events), "scopes": audit["assigned"], "classes": audit["classesByScope"]}}
    police_source = read_js("policia-06d01-data.js", "RIOBAMBA_POLICE_SIG_DATA")["infrastructure"]["features"]
    metadata["limitations"].append("Coordenadas de origen conservadas; clase A no equivale a certificacion independiente de exactitud. Las coincidencias entre observaciones distintas se mantienen.")
    metadata["methodReferences"] = ["https://pro.arcgis.com/en/pro-app/3.4/tool-reference/spatial-statistics/h-how-hot-spot-analysis-getis-ord-gi-spatial-stati.htm"]
    result["policeMetric"] = [{"x": project(*f["geometry"]["coordinates"])[0], "y": project(*f["geometry"]["coordinates"])[1], "properties": f["properties"]} for f in police_source]
    (ROOT / "riobamba-cantonal-data.js").write_text("window.RIOBAMBA_CANTONAL_DATA = "+json.dumps(result, ensure_ascii=False, separators=(",", ":"))+";\n", encoding="utf-8")
    (out / "METODOLOGIA.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "EVALUACION_GI_RURAL.json").write_text(json.dumps(assessments, indent=2), encoding="utf-8")
    with (out / "GI_RURAL_GENERAL.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["CELL_ID", "PARROQUIA", "COUNT", "GI_ZSCORE", "GI_PVALUE", "GI_CLASS"])
        writer.writeheader()
        writer.writerows({"CELL_ID": c["cellId"], "PARROQUIA": c["PARROQUIA"], **r} for c, r in zip(selected["cells"], selected["generalResults"]))
    for class_id, name in ((1, "DELINCUENCIA"), (2, "VIOLENCIA"), (3, "CONVIVENCIA")):
        with (out / f"GI_RURAL_{name}.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["CELL_ID", "PARROQUIA", "COUNT", "GI_ZSCORE", "GI_PVALUE", "GI_CLASS"])
            writer.writeheader()
            writer.writerows({"CELL_ID": c["cellId"], "PARROQUIA": c["PARROQUIA"], **r} for c, r in zip(selected["cells"], selected["byClass"][str(class_id)]))
    with (out / "ASIGNACION_ESPACIAL.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ID", "AMBITO", "UNIDAD", "DENTRO_CANTON", "MOTIVO", "X_UTM17S", "Y_UTM17S"])
        writer.writeheader()
        writer.writerows({"ID": id, "AMBITO": a["scope"], "UNIDAD": a["unit"], "DENTRO_CANTON": a["insideCanton"], "MOTIVO": a["reason"], "X_UTM17S": a["x"], "Y_UTM17S": a["y"]} for id, a in assignments.items())
    validation_rows = []
    for feature in parish_features:
        props = feature["properties"]
        name = props["name"]
        local = [e for id, e in events.items() if assignments[id]["scope"] == "RURAL" and assignments[id]["unit"] == name]
        classes = Counter(e["analyticalClassId"] for e in local)
        cells = [(cell, res) for cell, res in zip(selected["cells"], selected["generalResults"]) if cell["parishAreas"].get(name, 0) > 0]
        levels = Counter(res["GI_CLASS"] for _, res in cells)
        hotspot_area = sum(cell["parishAreas"][name] for cell, res in cells if res["GI_CLASS"].startswith("HOT"))
        validation_rows.append({"PARROQUIA": name, "POBLACION_CPV": props["population"], "EVENTOS_TOTALES": len(local), "DELINCUENCIA": classes[1], "VIOLENCIA": classes[2], "CONVIVENCIA": classes[3], "INSTITUCIONAL": classes[4], "OTROS_REVISION": classes[5], "TASA_DEL_1000_REFERENCIA": classes[1]/props["population"]*1000, "TASA_VIOL_1000_REFERENCIA": classes[2]/props["population"]*1000, "TASA_CONV_1000_REFERENCIA": classes[3]/props["population"]*1000, "DEPENDENCIAS_INVENTARIADAS": props["police"], "CAMARAS_RURALES": "NO DISPONIBLE", "CELDAS_INTERSECTADAS": len(cells), "H99": levels["HOTSPOT 99%"], "H95": levels["HOTSPOT 95%"], "H90": levels["HOTSPOT 90%"], "NS": levels["NO SIGNIFICATIVO"], "C90": levels["COLDSPOT 90%"], "C95": levels["COLDSPOT 95%"], "C99": levels["COLDSPOT 99%"], "AREA_HOTSPOT_KM2": hotspot_area, "PCT_TERRITORIO_HOTSPOT": hotspot_area/props["areaKm2"]*100, "ADVERTENCIA": "Tasas de referencia operativa; denominadores censales no ajustados por fraccion urbana. Gi* nominal exploratorio sin FDR."})
    with (out / "TABLA_VALIDACION_PARROQUIAS.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(validation_rows[0]))
        writer.writeheader()
        writer.writerows(validation_rows)
    print(json.dumps({"validation": result["validation"], "ruralGi": chosen, "kde": metadata["kdeParameters"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
