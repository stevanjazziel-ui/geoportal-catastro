"""Read-only production audit; writes only cantonal review artifacts."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/seguridad-riobamba/auditoria-cantonal-20261001"
DOWNLOADS = Path("C:/Users/PC/Downloads")
TERRITORY = DOWNLOADS / "barrios y plataformas/dar poder a la gente"
CENSUS_FILE = DOWNLOADS / "1.3 BDD_CPV_2022_MANLOC_CSV/CPV_2022_Poblacion_Manloc.csv"


def load(file):
    return json.loads(file.read_text(encoding="utf-8-sig"))


def read_js(name, variable):
    text = (ROOT / name).read_text(encoding="utf-8")
    return json.JSONDecoder().raw_decode(text.split(f"window.{variable} = ", 1)[1])[0]


def fingerprint(file):
    h = hashlib.sha256()
    with file.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def population_audit():
    counts, areas = Counter(), Counter()
    by_code = defaultdict(Counter)
    all_rows = 0
    with CENSUS_FILE.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        columns = next(reader)
        indexes = {name: columns.index(name) for name in ("I01", "I02", "PARROQ", "AUR", "CANTON")}
        for row in reader:
            all_rows += 1
            if len(row) != len(columns):
                raise ValueError(f"Unexpected census row length: {all_rows}")
            if row[indexes["I01"]] != "06" or row[indexes["I02"]] != "01":
                continue
            code, aur = row[indexes["PARROQ"]], row[indexes["AUR"]]
            assert row[indexes["CANTON"]] == "0601"
            counts[code] += 1
            areas[aur] += 1
            by_code[code][aur] += 1
    result = {"source": str(CENSUS_FILE), "method": "Conteo de personas (una fila por persona); filtro I01=06 e I02=01, verificado CANTON=0601. AUR conserva codigos originales, no se infiere significado sin diccionario.",
              "sourceSize": CENSUS_FILE.stat().st_size, "allRowsScanned": all_rows,
              "total": sum(counts.values()), "byParishCode": dict(counts), "byAUR": dict(areas),
              "byParishCodeAndAUR": {k: dict(v) for k, v in by_code.items()}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "POBLACION_CPV_AUDITADA.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


def main():
    import shapefile
    from pyproj import CRS, Transformer
    from shapely.geometry import Point, shape
    from shapely.ops import transform, unary_union
    from shapely.validation import explain_validity

    OUT.mkdir(parents=True, exist_ok=True)
    inputs = [ROOT / f for f in ("visor-seguridad-riobamba-v2.html", "visor-seguridad-riobamba-data.js", "riobamba-camaras-data.js", "policia-06d01-data.js", "riobamba-metodologia-data.js", "riobamba-incidentes-spatial-data.js", "riobamba-seguridad-diagnostico-data.js", "riobamba-accesibilidad-policial-data.js", "riobamba-seguridad-kde-validacion-data.js", "riobamba-censo-data/riobamba_plataformas.geojson", "riobamba-censo-data/riobamba_manzanas_stats.json", "data/premio-habitat/premio-habitat-boulevares.geojson", "data/premio-habitat/premio-habitat-conexiones.geojson")]
    before = {str(p.relative_to(ROOT)): fingerprint(p) for p in inputs}
    to_m = Transformer.from_crs(4326, 32717, always_xy=True).transform

    def read_shp(file):
        crs = CRS.from_wkt(file.with_suffix(".prj").read_text())
        project = Transformer.from_crs(crs, 32717, always_xy=True).transform
        reader = shapefile.Reader(str(file), encoding="utf-8")
        fields = [f[0] for f in reader.fields[1:]]
        features = [(dict(zip(fields, sr.record)), transform(project, shape(sr.shape.__geo_interface__))) for sr in reader.iterShapeRecords()]
        return features, {"file": str(file), "crs": crs.to_string(), "fields": fields, "records": len(features), "invalid": [{"row": i, "reason": explain_validity(g)} for i, (_, g) in enumerate(features) if not g.is_valid], "sha256": {suffix: fingerprint(file.with_suffix(suffix)) for suffix in (".shp", ".shx", ".dbf", ".prj")}}

    parish_features, parish_meta = read_shp(TERRITORY / "division_parroquial_riobamba_wgs84.shp")
    canton_features, canton_meta = read_shp(TERRITORY / "limite_canton_riobamba_wgs84.shp")
    if parish_meta["invalid"] or canton_meta["invalid"]:
        raise ValueError("Invalid territory geometry; no silent repair permitted")
    canton = unary_union([g for _, g in canton_features])
    administrative = unary_union([g for _, g in parish_features])
    rural = [(p, g) for p, g in parish_features if p["ESTADO"] == "RURAL"]
    administrative_urban = unary_union([g for p, g in parish_features if p["ESTADO"] == "URBANA"])
    platform_features = load(ROOT / "riobamba-censo-data/riobamba_plataformas.geojson")["features"]
    platforms = [(f["properties"]["platform_name"], transform(to_m, shape(f["geometry"]))) for f in platform_features]
    assert len(platforms) == 18 and all(g.is_valid for _, g in platforms)
    urban = unary_union([g for _, g in platforms])
    rural_union = unary_union([g for _, g in rural])

    def assign(point):
        if not canton.covers(point):
            return "SIN_ASIGNAR", "", "FUERA_DEL_CANTON", []
        hits = [name for name, geom in platforms if geom.covers(point)]
        if hits:
            return "URBANO", hits[0], "PLATAFORMA_INTERSECTADA", hits
        hits = [p["PARROQUIA"] for p, geom in rural if geom.covers(point)]
        if len(hits) == 1:
            return "RURAL", hits[0], "PARROQUIA_RURAL_INTERSECTADA", hits
        if len(hits) > 1:
            return "SIN_ASIGNAR", "", "MULTIPLES_PARROQUIAS_RURALES", hits
        return "SIN_ASIGNAR", "", "DENTRO_CANTON_FUERA_PLATAFORMAS_Y_PARROQUIAS_RURALES", []

    source = read_js("visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    events = source["events"]
    totals, analytic = Counter(), Counter()
    by_scope_class = defaultdict(Counter)
    by_rural = {p["PARROQUIA"]: Counter() for p, _ in rural}
    reasons, original_parish_mismatch = Counter(), Counter()
    urban_in_rural, multi_platform = Counter(), []
    rows = []
    for event in events:
        point = Point(to_m(event["lng"], event["lat"]))
        scope, unit, reason, hits = assign(point)
        totals[scope] += 1
        class_id = int(event["analyticalClassId"])
        by_scope_class[scope][str(class_id)] += 1
        if class_id in (1, 2, 3):
            analytic[scope] += 1
        if scope == "URBANO":
            for properties, geom in rural:
                if geom.covers(point):
                    urban_in_rural[properties["PARROQUIA"]] += 1
            if len(hits) > 1:
                multi_platform.append(event["id"])
        if scope == "RURAL":
            by_rural[unit][str(class_id)] += 1
            original = event.get("parish", "")
            if unit not in original.upper():
                original_parish_mismatch[f"{original} -> {unit}"] += 1
        if scope == "SIN_ASIGNAR":
            reasons[reason] += 1
        rows.append({"ID": event["id"], "LONGITUD": event["lng"], "LATITUD": event["lat"], "FECHA": event["date"], "CLASE": class_id, "SUBTIPO": event["subtype"], "PARROQUIA_ORIGINAL": event.get("parish", ""), "AMBITO_PROPUESTO": scope, "UNIDAD_ESPACIAL": unit, "MOTIVO": reason, "COINCIDENCIAS": " | ".join(hits)})
    assert sum(totals.values()) == len(events) and sum(analytic.values()) == 11042
    for file, selected in (("ASIGNACION_PRELIMINAR.csv", rows), ("SIN_ASIGNAR.csv", [r for r in rows if r["AMBITO_PROPUESTO"] == "SIN_ASIGNAR"])):
        with (OUT / file).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(selected)

    # Spatial crosswalk: census codes are never matched to the unrelated CODPAR field.
    votes = defaultdict(Counter)
    manzanas = load(ROOT / "riobamba-censo-data/riobamba_manzanas.geojson")["features"]
    for f in manzanas:
        geom = transform(to_m, shape(f["geometry"]))
        if not geom.is_valid:
            continue
        code = str(f["properties"]["man"])[:6]
        for p, parish in parish_features:
            area = geom.intersection(parish).area
            if area > .01:
                votes[code][p["PARROQUIA"]] += area
    census = load(OUT / "POBLACION_CPV_AUDITADA.json")
    crosswalk = {}
    for code, matches in votes.items():
        total = sum(matches.values())
        name, area = matches.most_common(1)[0]
        crosswalk[code] = {"dominantGeometry": name, "dominantAreaPct": area / total * 100, "intersectionAreaByNameM2": dict(matches), "censusPopulation": census["byParishCode"].get(code)}

    cameras = read_js("riobamba-camaras-data.js", "RIOBAMBA_CAMERAS_DATA")["cameras"]
    assert len(cameras) == len({c["id"] for c in cameras}) == 31
    camera_units = [{"id": c["id"], "scope": assign(Point(to_m(c["lng"], c["lat"])))[0], "unit": assign(Point(to_m(c["lng"], c["lat"])))[1]} for c in cameras]
    police = read_js("policia-06d01-data.js", "RIOBAMBA_POLICE_SIG_DATA")["infrastructure"]["features"]
    police_units = [{"properties": f["properties"], "scope": assign(transform(to_m, shape(f["geometry"])))[0], "unit": assign(transform(to_m, shape(f["geometry"])))[1]} for f in police]
    rural_rows = []
    for properties, _ in rural:
        name = properties["PARROQUIA"]
        matches = [(code, match) for code, match in crosswalk.items() if match["dominantGeometry"] == name and match["dominantAreaPct"] > 99]
        assert len(matches) == 1, f"Ambiguous census crosswalk: {name}"
        code, match = matches[0]
        counts = by_rural[name]
        rural_rows.append({"PARROQUIA": name, "CODIGO_CPV_PROPUESTO": code, "POBLACION_CPV": match["censusPopulation"], "CONCORDANCIA_GEOMETRICA_PCT": match["dominantAreaPct"], "INCIDENTES": sum(counts.values()), "DELINCUENCIA": counts["1"], "VIOLENCIA": counts["2"], "CONVIVENCIA": counts["3"], "INSTITUCIONAL": counts["4"], "OTROS_REVISION": counts["5"], "DEPENDENCIAS_INVENTARIADAS": sum(p["scope"] == "RURAL" and p["unit"] == name for p in police_units), "GI_RURAL": "NO CALCULADO", "TASAS_RURALES": "PENDIENTE CONCORDANCIA DE AMBITOS", "CAMARAS_RURALES": "INVENTARIO NO DISPONIBLE"})
    with (OUT / "PARROQUIAS_PRELIMINAR.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rural_rows[0]))
        writer.writeheader()
        writer.writerows(rural_rows)
    _, road_meta = read_shp(DOWNLOADS / "barrios y plataformas/vias/vias_canton_riobamba_wgs84.shp")
    proposal = load(ROOT / "data/seguridad-riobamba/revision-metodologica-20261001/AUDITORIA_Y_CLASIFICACION.json")["classification"]
    class_counts = Counter(e["analyticalClassId"] for e in events)
    with (OUT / "CLASIFICACION_SUBTIPOS.md").open("w", encoding="utf-8") as handle:
        handle.write("# Clasificacion cantonal propuesta para revision\n\nSe conserva la clasificacion analitica local auditada; no se resuelven arbitrariamente los 39 subtipos ambiguos. No aplicada a la interfaz cantonal.\n\n| Subtipo | Registros | Clasificacion actual | Propuesta cantonal | Estado |\n|---|---:|---|---|---|\n")
        for item in proposal:
            example = next(e for e in events if e["subtype"] == item["SUBTIPO"])
            current = example["category"]
            handle.write(f"| {item['SUBTIPO']} | {item['NUMERO_REGISTROS']} | {current} | {current} | {example.get('classificationStatus', 'Revision')} |\n")
    report = {"generatedAt": datetime.now().isoformat(timespec="seconds"), "stage": "AUDITORIA_PREVIA_SIN_CAMBIOS_EN_INTERFAZ", "referencePopulation": {"cantonal": 260882, "urban": 177213, "rural": 83669},
              "cantonSource": canton_meta, "parishSource": parish_meta, "roads": road_meta,
              "geometry": {"cantonAreaKm2": canton.area/1e6, "parishUnionDifferenceM2": canton.symmetric_difference(administrative).area, "parishOverlapM2": sum(g.area for _, g in parish_features) - administrative.area, "urbanPlatformAreaKm2": urban.area/1e6, "administrativeUrbanAreaKm2": administrative_urban.area/1e6, "urbanOutsideCantonM2": urban.difference(canton).area, "urbanRuralOverlapKm2": urban.intersection(rural_union).area/1e6, "withinCantonUnclassifiedAreaKm2": canton.difference(urban.union(rural_union)).area/1e6},
              "assignmentRule": "Interseccion espacial en EPSG:32717; primero verificar canton, luego Plataformas urbanas, luego parroquias RURAL. Los huecos de ambito no se asignan por texto; cruces multiples quedan reportados. Es una propuesta operativa para revision.",
              "urbanEventsAlsoInRuralParish": dict(urban_in_rural), "eventsInMultiplePlatforms": multi_platform,
              "totalRecords": len(events), "assigned": dict(totals), "analyticAssigned": dict(analytic), "classesByScope": {k: dict(v) for k, v in by_scope_class.items()}, "classesTotal": dict(class_counts), "unassignedReasons": dict(reasons), "byRuralParish": {k: dict(v) for k, v in by_rural.items()}, "originalParishMismatch": dict(original_parish_mismatch), "census": census, "censusSpatialCrosswalk": crosswalk,
              "cameraAssignments": camera_units, "policeAssignments": police_units,
              "ruralPopulationAndEventsPreliminary": rural_rows,
              "protectedProductionHashesBefore": before, "protectedProductionHashesAfter": {str(p.relative_to(ROOT)): fingerprint(p) for p in inputs}}
    assert report["protectedProductionHashesBefore"] == report["protectedProductionHashesAfter"]
    assert 177213 + 83669 == 260882
    (OUT / "AUDITORIA_CANTONAL.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("totalRecords", "assigned", "analyticAssigned", "unassignedReasons", "geometry", "classesTotal", "censusSpatialCrosswalk")}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--population-only", action="store_true")
    args = parser.parse_args()
    population_audit() if args.population_only else main()
